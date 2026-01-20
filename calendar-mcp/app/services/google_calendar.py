"""Google Calendar sync service."""

from datetime import datetime, timedelta

import pytz
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.routes.oauth import get_google_credentials
from app.models import Appointment, AppointmentStatus, BlockedTime, Business, CalendarConnection, Customer, SyncStatus


class GoogleCalendarService:
    """Service for syncing with Google Calendar."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_calendar_service(self, business_id: int):
        """Get Google Calendar API service for a business."""
        credentials = await get_google_credentials(business_id, self.db)
        
        if not credentials:
            return None
        
        return build("calendar", "v3", credentials=credentials)

    async def push_appointment(self, appointment: Appointment) -> dict:
        """
        Push an appointment to Google Calendar.
        
        Creates or updates the event on Google Calendar.
        """
        service = await self.get_calendar_service(appointment.business_id)
        
        if not service:
            return {
                "success": False,
                "message": "Google Calendar not connected for this business",
            }

        # Get calendar ID
        result = await self.db.execute(
            select(CalendarConnection).where(
                and_(
                    CalendarConnection.business_id == appointment.business_id,
                    CalendarConnection.provider == "google",
                )
            )
        )
        connection = result.scalar_one_or_none()
        calendar_id = connection.calendar_id if connection else "primary"

        # Get business for timezone
        result = await self.db.execute(
            select(Business).where(Business.id == appointment.business_id)
        )
        business = result.scalar_one_or_none()
        timezone = business.timezone if business else "UTC"

        # Build event body
        event = {
            "summary": appointment.title,
            "description": f"Service: {appointment.service_type}\n{appointment.notes or ''}",
            "start": {
                "dateTime": appointment.start_time.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": appointment.end_time.isoformat(),
                "timeZone": timezone,
            },
        }

        # Add customer info if available
        if appointment.customer:
            attendees = []
            if appointment.customer.email:
                attendees.append({"email": appointment.customer.email})
            if attendees:
                event["attendees"] = attendees

        try:
            if appointment.external_uid:
                # Update existing event (or create if it doesn't exist)
                try:
                    existing = service.events().get(
                        calendarId=calendar_id,
                        eventId=appointment.external_uid,
                    ).execute()
                    
                    if existing:
                        result = service.events().update(
                            calendarId=calendar_id,
                            eventId=appointment.external_uid,
                            body=event,
                        ).execute()
                except HttpError:
                    # Event doesn't exist, create new
                    result = service.events().insert(
                        calendarId=calendar_id,
                        body=event,
                    ).execute()
            else:
                # Create new event
                result = service.events().insert(
                    calendarId=calendar_id,
                    body=event,
                ).execute()

            # Update appointment with Google Calendar event ID
            appointment.external_uid = result.get("id")
            appointment.sync_status = SyncStatus.SYNCED
            await self.db.flush()

            return {
                "success": True,
                "message": "Appointment synced to Google Calendar",
                "event_id": result.get("id"),
            }

        except HttpError as e:
            appointment.sync_status = SyncStatus.FAILED
            await self.db.flush()
            
            return {
                "success": False,
                "message": f"Failed to sync to Google Calendar: {str(e)}",
            }

    async def delete_appointment_event(self, appointment: Appointment) -> dict:
        """Delete an appointment event from Google Calendar."""
        if not appointment.external_uid:
            return {
                "success": True,
                "message": "No external event to delete",
            }

        service = await self.get_calendar_service(appointment.business_id)
        
        if not service:
            return {
                "success": False,
                "message": "Google Calendar not connected for this business",
            }

        # Get calendar ID
        result = await self.db.execute(
            select(CalendarConnection).where(
                and_(
                    CalendarConnection.business_id == appointment.business_id,
                    CalendarConnection.provider == "google",
                )
            )
        )
        connection = result.scalar_one_or_none()
        calendar_id = connection.calendar_id if connection else "primary"

        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=appointment.external_uid,
            ).execute()

            # Mark as synced (deletion complete)
            appointment.sync_status = SyncStatus.SYNCED
            await self.db.flush()

            return {
                "success": True,
                "message": "Event deleted from Google Calendar",
            }

        except HttpError as e:
            if e.resp.status == 404:
                # Event already deleted, still mark as synced
                appointment.sync_status = SyncStatus.SYNCED
                await self.db.flush()
                
                return {
                    "success": True,
                    "message": "Event not found (already deleted)",
                }
            
            appointment.sync_status = SyncStatus.FAILED
            await self.db.flush()
            
            return {
                "success": False,
                "message": f"Failed to delete event: {str(e)}",
            }

    async def pull_blocked_times(
        self,
        business_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """
        Pull events from Google Calendar and create blocked times.
        
        This syncs the business owner's calendar events as blocked times
        so that appointments cannot be scheduled during those periods.
        """
        service = await self.get_calendar_service(business_id)
        
        if not service:
            return {
                "success": False,
                "message": "Google Calendar not connected for this business",
                "blocked_times_created": 0,
            }

        # Get calendar ID and sync token
        result = await self.db.execute(
            select(CalendarConnection).where(
                and_(
                    CalendarConnection.business_id == business_id,
                    CalendarConnection.provider == "google",
                )
            )
        )
        connection = result.scalar_one_or_none()
        calendar_id = connection.calendar_id if connection else "primary"

        try:
            # Fetch events
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=start_date.isoformat() + "Z",
                timeMax=end_date.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])
            blocked_times_created = 0

            for event in events:
                # Skip all-day events
                if "dateTime" not in event.get("start", {}):
                    continue

                event_start = datetime.fromisoformat(
                    event["start"]["dateTime"].replace("Z", "+00:00")
                )
                event_end = datetime.fromisoformat(
                    event["end"]["dateTime"].replace("Z", "+00:00")
                )
                event_id = event.get("id")

                # Check if this blocked time already exists
                result = await self.db.execute(
                    select(BlockedTime).where(
                        and_(
                            BlockedTime.business_id == business_id,
                            BlockedTime.external_uid == event_id,
                        )
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing blocked time
                    existing.start_time = event_start
                    existing.end_time = event_end
                    existing.reason = event.get("summary", "Busy")
                else:
                    # Create new blocked time
                    blocked_time = BlockedTime(
                        business_id=business_id,
                        start_time=event_start,
                        end_time=event_end,
                        reason=event.get("summary", "Busy (from Google Calendar)"),
                        external_uid=event_id,
                    )
                    self.db.add(blocked_time)
                    blocked_times_created += 1

            # Update sync token for incremental sync
            if "nextSyncToken" in events_result:
                connection.sync_token = events_result["nextSyncToken"]

            await self.db.flush()

            return {
                "success": True,
                "message": f"Synced {len(events)} events from Google Calendar",
                "blocked_times_created": blocked_times_created,
                "total_events": len(events),
            }

        except HttpError as e:
            return {
                "success": False,
                "message": f"Failed to sync from Google Calendar: {str(e)}",
                "blocked_times_created": 0,
            }

    async def sync_pending_appointments(self, business_id: int) -> dict:
        """Sync all pending appointments for a business to Google Calendar."""
        result = await self.db.execute(
            select(Appointment)
            .options(selectinload(Appointment.customer))  # Eagerly load customer
            .where(
                and_(
                    Appointment.business_id == business_id,
                    Appointment.sync_status == SyncStatus.PENDING,
                    Appointment.status == AppointmentStatus.CONFIRMED,
                )
            )
        )
        appointments = result.scalars().all()

        synced = 0
        failed = 0

        for appointment in appointments:
            result = await self.push_appointment(appointment)
            if result["success"]:
                synced += 1
            else:
                failed += 1

        return {
            "success": True,
            "message": f"Synced {synced} appointments, {failed} failed",
            "synced": synced,
            "failed": failed,
        }

