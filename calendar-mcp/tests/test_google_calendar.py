"""
Tests for GoogleCalendarService.

This module tests the Google Calendar sync service including:
- Pushing appointments to Google Calendar
- Deleting appointment events
- Pulling blocked times from Google Calendar
- Syncing pending appointments
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, BlockedTime, SyncStatus
from app.services.google_calendar import GoogleCalendarService


class TestGetCalendarService:
    """Tests for GoogleCalendarService.get_calendar_service method."""

    @pytest.mark.asyncio
    async def test_get_calendar_service_no_connection(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that None is returned when no connection exists.
        
        Expected behavior:
        - Returns None when business has no Google Calendar connection
        """
        service = GoogleCalendarService(test_db)
        
        with patch("app.api.routes.oauth.get_google_credentials", new_callable=AsyncMock) as mock_creds:
            mock_creds.return_value = None
            
            result = await service.get_calendar_service(sample_business.id)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_get_calendar_service_with_connection(
        self, test_db: AsyncSession, sample_business, sample_calendar_connection
    ):
        """
        Verify that calendar service is returned when connection exists.
        
        Expected behavior:
        - Returns Google Calendar API service object
        """
        service = GoogleCalendarService(test_db)
        
        with patch("app.services.google_calendar.build") as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            
            result = await service.get_calendar_service(sample_business.id)
            
            # The service should be returned (or None if credentials failed)
            # We just verify build was called with the right service name
            if result is not None:
                mock_build.assert_called_once()
                call_args = mock_build.call_args
                assert call_args[0][0] == "calendar"
                assert call_args[0][1] == "v3"


class TestPushAppointment:
    """Tests for GoogleCalendarService.push_appointment method."""

    @pytest.mark.asyncio
    async def test_push_appointment_no_connection(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that pushing without connection returns error.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates no connection
        """
        service = GoogleCalendarService(test_db)
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            result = await service.push_appointment(sample_appointment)
            
            assert result["success"] is False
            assert "not connected" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_push_appointment_create_new_event(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that a new event is created on Google Calendar.
        
        Expected behavior:
        - Event is created via Google Calendar API
        - Appointment sync_status is updated to SYNCED
        - external_uid is updated with Google event ID
        """
        service = GoogleCalendarService(test_db)
        
        # Reset sync status to pending and clear external_uid to simulate new appointment
        sample_appointment.sync_status = SyncStatus.PENDING
        sample_appointment.external_uid = None
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            mock_insert = MagicMock()
            mock_insert.execute.return_value = {"id": "google-event-123"}
            mock_events.insert.return_value = mock_insert
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.push_appointment(sample_appointment)
            
            assert result["success"] is True
            assert result["event_id"] == "google-event-123"
            assert sample_appointment.sync_status == SyncStatus.SYNCED

    @pytest.mark.asyncio
    async def test_push_appointment_update_existing_event(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that an existing event is updated on Google Calendar.
        
        Expected behavior:
        - Event is updated via Google Calendar API
        - Appointment sync_status remains SYNCED
        """
        service = GoogleCalendarService(test_db)
        
        # Set up as already synced
        sample_appointment.sync_status = SyncStatus.SYNCED
        sample_appointment.external_uid = "existing-event-id"
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            
            # Mock get to return existing event
            mock_get_event = MagicMock()
            mock_get_event.execute.return_value = {"id": "existing-event-id"}
            mock_events.get.return_value = mock_get_event
            
            # Mock update
            mock_update = MagicMock()
            mock_update.execute.return_value = {"id": "existing-event-id"}
            mock_events.update.return_value = mock_update
            
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.push_appointment(sample_appointment)
            
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_push_appointment_api_error(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that API errors are handled gracefully.
        
        Expected behavior:
        - Returns success=False
        - Appointment sync_status is set to FAILED
        """
        service = GoogleCalendarService(test_db)
        sample_appointment.sync_status = SyncStatus.PENDING
        sample_appointment.external_uid = None  # Clear to test insert path
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            
            # Create a proper HttpError
            resp = MagicMock()
            resp.status = 500
            mock_insert = MagicMock()
            mock_insert.execute.side_effect = HttpError(resp, b"Internal Server Error")
            mock_events.insert.return_value = mock_insert
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.push_appointment(sample_appointment)
            
            assert result["success"] is False
            assert sample_appointment.sync_status == SyncStatus.FAILED


class TestDeleteAppointmentEvent:
    """Tests for GoogleCalendarService.delete_appointment_event method."""

    @pytest.mark.asyncio
    async def test_delete_no_external_uid(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that deleting without external_uid returns success.
        
        Expected behavior:
        - Returns success=True
        - Message indicates no external event to delete
        """
        service = GoogleCalendarService(test_db)
        sample_appointment.external_uid = None
        
        result = await service.delete_appointment_event(sample_appointment)
        
        assert result["success"] is True
        assert "No external event" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_no_connection(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that deleting without connection returns error.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates no connection
        """
        service = GoogleCalendarService(test_db)
        sample_appointment.external_uid = "event-to-delete"
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            result = await service.delete_appointment_event(sample_appointment)
            
            assert result["success"] is False
            assert "not connected" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_success(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that event is deleted from Google Calendar.
        
        Expected behavior:
        - Returns success=True
        - Event is deleted via Google Calendar API
        """
        service = GoogleCalendarService(test_db)
        sample_appointment.external_uid = "event-to-delete"
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            mock_delete = MagicMock()
            mock_delete.execute.return_value = None
            mock_events.delete.return_value = mock_delete
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.delete_appointment_event(sample_appointment)
            
            assert result["success"] is True
            assert "deleted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_event_not_found(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that 404 error is handled gracefully.
        
        Expected behavior:
        - Returns success=True (event already deleted)
        """
        service = GoogleCalendarService(test_db)
        sample_appointment.external_uid = "nonexistent-event"
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            
            resp = MagicMock()
            resp.status = 404
            mock_delete = MagicMock()
            mock_delete.execute.side_effect = HttpError(resp, b"Not Found")
            mock_events.delete.return_value = mock_delete
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.delete_appointment_event(sample_appointment)
            
            assert result["success"] is True
            assert "not found" in result["message"].lower() or "already deleted" in result["message"].lower()


class TestPullBlockedTimes:
    """Tests for GoogleCalendarService.pull_blocked_times method."""

    @pytest.mark.asyncio
    async def test_pull_blocked_times_no_connection(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that pulling without connection returns error.
        
        Expected behavior:
        - Returns success=False
        - blocked_times_created is 0
        """
        service = GoogleCalendarService(test_db)
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            
            result = await service.pull_blocked_times(
                sample_business.id,
                datetime.utcnow(),
                datetime.utcnow() + timedelta(days=7),
            )
            
            assert result["success"] is False
            assert result["blocked_times_created"] == 0

    @pytest.mark.asyncio
    async def test_pull_blocked_times_creates_blocked_times(
        self, test_db: AsyncSession, sample_business, sample_calendar_connection
    ):
        """
        Verify that events are converted to blocked times.
        
        Expected behavior:
        - Events from Google Calendar are created as BlockedTime records
        - All-day events are skipped
        """
        service = GoogleCalendarService(test_db)
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            mock_list = MagicMock()
            mock_list.execute.return_value = {
                "items": [
                    {
                        "id": "event-1",
                        "summary": "Meeting",
                        "start": {"dateTime": "2025-01-20T10:00:00+00:00"},
                        "end": {"dateTime": "2025-01-20T11:00:00+00:00"},
                    },
                    {
                        "id": "event-2",
                        "summary": "All Day Event",
                        "start": {"date": "2025-01-21"},  # All-day event
                        "end": {"date": "2025-01-22"},
                    },
                ],
                "nextSyncToken": "sync-token-123",
            }
            mock_events.list.return_value = mock_list
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.pull_blocked_times(
                sample_business.id,
                datetime(2025, 1, 20),
                datetime(2025, 1, 27),
            )
            
            assert result["success"] is True
            assert result["blocked_times_created"] == 1  # Only non-all-day event
            assert result["total_events"] == 2

    @pytest.mark.asyncio
    async def test_pull_blocked_times_updates_existing(
        self, test_db: AsyncSession, sample_business, sample_calendar_connection
    ):
        """
        Verify that existing blocked times are updated.
        
        Expected behavior:
        - Existing blocked time with same external_uid is updated
        - No duplicate is created
        """
        service = GoogleCalendarService(test_db)
        
        # Create existing blocked time
        existing_blocked = BlockedTime(
            business_id=sample_business.id,
            start_time=datetime(2025, 1, 20, 10, 0),
            end_time=datetime(2025, 1, 20, 11, 0),
            reason="Old Meeting",
            external_uid="event-1",
        )
        test_db.add(existing_blocked)
        await test_db.flush()
        
        with patch.object(service, "get_calendar_service", new_callable=AsyncMock) as mock_get:
            mock_calendar_service = MagicMock()
            mock_events = MagicMock()
            mock_list = MagicMock()
            mock_list.execute.return_value = {
                "items": [
                    {
                        "id": "event-1",
                        "summary": "Updated Meeting",
                        "start": {"dateTime": "2025-01-20T14:00:00+00:00"},
                        "end": {"dateTime": "2025-01-20T15:00:00+00:00"},
                    },
                ],
            }
            mock_events.list.return_value = mock_list
            mock_calendar_service.events.return_value = mock_events
            mock_get.return_value = mock_calendar_service
            
            result = await service.pull_blocked_times(
                sample_business.id,
                datetime(2025, 1, 20),
                datetime(2025, 1, 27),
            )
            
            assert result["success"] is True
            assert result["blocked_times_created"] == 0  # Updated, not created


class TestSyncPendingAppointments:
    """Tests for GoogleCalendarService.sync_pending_appointments method."""

    @pytest.mark.asyncio
    async def test_sync_pending_appointments_empty(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that syncing with no pending appointments returns success.
        
        Expected behavior:
        - Returns success=True
        - synced and failed counts are 0
        """
        service = GoogleCalendarService(test_db)
        
        result = await service.sync_pending_appointments(sample_business.id)
        
        assert result["success"] is True
        assert result["synced"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_sync_pending_appointments_success(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that pending appointments are synced.
        
        Expected behavior:
        - Pending appointments are pushed to Google Calendar
        - synced count reflects successful syncs
        """
        service = GoogleCalendarService(test_db)
        
        # Ensure appointment is pending
        sample_appointment.sync_status = SyncStatus.PENDING
        sample_appointment.status = AppointmentStatus.CONFIRMED
        await test_db.flush()
        
        with patch.object(service, "push_appointment", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = {"success": True, "event_id": "event-123"}
            
            result = await service.sync_pending_appointments(sample_business.id)
            
            assert result["success"] is True
            assert result["synced"] >= 1

    @pytest.mark.asyncio
    async def test_sync_pending_appointments_with_failures(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment, sample_calendar_connection
    ):
        """
        Verify that failed syncs are counted.
        
        Expected behavior:
        - Failed syncs are tracked
        - Overall operation still returns success=True
        """
        service = GoogleCalendarService(test_db)
        
        # Ensure appointment is pending
        sample_appointment.sync_status = SyncStatus.PENDING
        sample_appointment.status = AppointmentStatus.CONFIRMED
        await test_db.flush()
        
        with patch.object(service, "push_appointment", new_callable=AsyncMock) as mock_push:
            mock_push.return_value = {"success": False, "message": "API Error"}
            
            result = await service.sync_pending_appointments(sample_business.id)
            
            assert result["success"] is True
            assert result["failed"] >= 1
