"""Booking service with conflict detection."""

from datetime import datetime, timedelta
import uuid

import pytz
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, Business, Customer, SyncStatus
from app.services.availability import AvailabilityService


class BookingService:
    """Service for booking appointments with conflict detection."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.availability_service = AvailabilityService(db)

    async def get_or_create_customer(
        self,
        email: str,
        name: str | None = None,
        phone: str | None = None,
    ) -> Customer:
        """Get existing customer by email or create a new one."""
        result = await self.db.execute(
            select(Customer).where(Customer.email == email)
        )
        customer = result.scalar_one_or_none()
        
        if customer:
            # Update name/phone if provided
            if name and not customer.name:
                customer.name = name
            if phone and not customer.phone:
                customer.phone = phone
            return customer
        
        # Create new customer
        customer = Customer(email=email, name=name, phone=phone)
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def book_appointment(
        self,
        business_id: int,
        customer_email: str,
        start_time: datetime,
        service_type: str,
        duration_minutes: int = 60,
        title: str = "Appointment",
        notes: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
    ) -> dict:
        """
        Book an appointment with conflict detection.
        
        Uses SELECT FOR UPDATE to prevent race conditions.
        
        Returns:
            dict with success, message, and optionally appointment data
        """
        # Get business
        result = await self.db.execute(
            select(Business).where(Business.id == business_id)
        )
        business = result.scalar_one_or_none()
        
        if not business:
            return {
                "success": False,
                "message": f"Business with ID {business_id} not found",
                "appointment": None,
            }

        # Ensure start_time is timezone-aware
        if start_time.tzinfo is None:
            start_time = pytz.UTC.localize(start_time)
        
        # Calculate end time
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        # Convert to UTC for storage
        start_time_utc = start_time.astimezone(pytz.UTC)
        end_time_utc = end_time.astimezone(pytz.UTC)

        # Check for conflicts with row locking
        # Lock all overlapping appointments to prevent race conditions
        conflict_query = (
            select(Appointment)
            .where(
                and_(
                    Appointment.business_id == business_id,
                    Appointment.status == AppointmentStatus.CONFIRMED,
                    Appointment.start_time < end_time_utc,
                    Appointment.end_time > start_time_utc,
                )
            )
            .with_for_update()
        )
        
        result = await self.db.execute(conflict_query)
        conflicts = result.scalars().all()
        
        if conflicts:
            return {
                "success": False,
                "message": "Time slot is not available. There is a conflicting appointment.",
                "appointment": None,
            }

        # Check if slot is within business hours
        is_available = await self.availability_service.is_slot_available(
            business_id, start_time_utc, end_time_utc
        )
        
        if not is_available:
            return {
                "success": False,
                "message": "Time slot is outside business hours or blocked.",
                "appointment": None,
            }

        # Get or create customer
        customer = await self.get_or_create_customer(
            email=customer_email,
            name=customer_name,
            phone=customer_phone,
        )

        # Create appointment
        appointment = Appointment(
            business_id=business_id,
            customer_id=customer.id,
            title=title,
            service_type=service_type,
            start_time=start_time_utc,
            end_time=end_time_utc,
            status=AppointmentStatus.CONFIRMED,
            notes=notes,
            external_uid=str(uuid.uuid4()),
            sync_status=SyncStatus.PENDING,
        )
        
        self.db.add(appointment)
        await self.db.flush()
        await self.db.refresh(appointment)
        
        # Load customer relationship
        await self.db.refresh(appointment, ["customer"])

        return {
            "success": True,
            "message": "Appointment booked successfully",
            "appointment": self._appointment_to_dict(appointment),
        }

    async def cancel_appointment(
        self,
        appointment_id: int,
        reason: str = "",
    ) -> dict:
        """Cancel an existing appointment."""
        result = await self.db.execute(
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .with_for_update()
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            return {
                "success": False,
                "message": f"Appointment with ID {appointment_id} not found",
                "appointment": None,
            }
        
        if appointment.status == AppointmentStatus.CANCELLED:
            return {
                "success": False,
                "message": "Appointment is already cancelled",
                "appointment": None,
            }

        appointment.status = AppointmentStatus.CANCELLED
        if reason:
            appointment.notes = f"{appointment.notes or ''}\nCancellation reason: {reason}".strip()
        appointment.sync_status = SyncStatus.PENDING
        
        await self.db.flush()
        await self.db.refresh(appointment, ["customer"])

        return {
            "success": True,
            "message": "Appointment cancelled successfully",
            "appointment": self._appointment_to_dict(appointment),
        }

    async def reschedule_appointment(
        self,
        appointment_id: int,
        new_start_time: datetime,
    ) -> dict:
        """Reschedule an appointment to a new time."""
        result = await self.db.execute(
            select(Appointment)
            .where(Appointment.id == appointment_id)
            .with_for_update()
        )
        appointment = result.scalar_one_or_none()
        
        if not appointment:
            return {
                "success": False,
                "message": f"Appointment with ID {appointment_id} not found",
                "appointment": None,
            }
        
        if appointment.status != AppointmentStatus.CONFIRMED:
            return {
                "success": False,
                "message": f"Cannot reschedule appointment with status {appointment.status.value}",
                "appointment": None,
            }

        # Calculate duration from original appointment
        original_duration = appointment.end_time - appointment.start_time
        
        # Ensure new_start_time is timezone-aware
        if new_start_time.tzinfo is None:
            new_start_time = pytz.UTC.localize(new_start_time)
        
        new_start_time_utc = new_start_time.astimezone(pytz.UTC)
        new_end_time_utc = new_start_time_utc + original_duration

        # Check for conflicts (excluding current appointment)
        conflict_query = (
            select(Appointment)
            .where(
                and_(
                    Appointment.business_id == appointment.business_id,
                    Appointment.id != appointment_id,
                    Appointment.status == AppointmentStatus.CONFIRMED,
                    Appointment.start_time < new_end_time_utc,
                    Appointment.end_time > new_start_time_utc,
                )
            )
            .with_for_update()
        )
        
        result = await self.db.execute(conflict_query)
        conflicts = result.scalars().all()
        
        if conflicts:
            return {
                "success": False,
                "message": "New time slot is not available. There is a conflicting appointment.",
                "appointment": None,
            }

        # Check if new slot is within business hours
        is_available = await self.availability_service.is_slot_available(
            appointment.business_id, new_start_time_utc, new_end_time_utc
        )
        
        if not is_available:
            return {
                "success": False,
                "message": "New time slot is outside business hours or blocked.",
                "appointment": None,
            }

        # Update appointment
        appointment.start_time = new_start_time_utc
        appointment.end_time = new_end_time_utc
        appointment.sync_status = SyncStatus.PENDING
        
        await self.db.flush()
        await self.db.refresh(appointment, ["customer"])

        return {
            "success": True,
            "message": "Appointment rescheduled successfully",
            "appointment": self._appointment_to_dict(appointment),
        }

    async def get_appointment(self, appointment_id: int) -> Appointment | None:
        """Get an appointment by ID."""
        result = await self.db.execute(
            select(Appointment)
            .where(Appointment.id == appointment_id)
        )
        return result.scalar_one_or_none()

    async def get_daily_schedule(
        self,
        business_id: int,
        target_date: str,  # YYYY-MM-DD
    ) -> dict:
        """Get all appointments for a business on a specific date."""
        from datetime import date as date_type
        
        # Get business
        result = await self.db.execute(
            select(Business).where(Business.id == business_id)
        )
        business = result.scalar_one_or_none()
        
        if not business:
            return {
                "business_id": business_id,
                "date": target_date,
                "appointments": [],
                "error": "Business not found",
            }

        # Parse date
        try:
            parsed_date = date_type.fromisoformat(target_date)
        except ValueError:
            return {
                "business_id": business_id,
                "date": target_date,
                "appointments": [],
                "error": "Invalid date format. Use YYYY-MM-DD",
            }

        # Get appointments
        appointments = await self.availability_service.get_appointments_for_date(
            business_id, parsed_date, business.timezone
        )

        # Sort by start time
        appointments.sort(key=lambda a: a.start_time)

        # Load customer relationships
        for appt in appointments:
            await self.db.refresh(appt, ["customer"])

        return {
            "business_id": business_id,
            "date": target_date,
            "timezone": business.timezone,
            "appointments": [self._appointment_to_dict(a) for a in appointments],
        }

    def _appointment_to_dict(self, appointment: Appointment) -> dict:
        """Convert appointment to dictionary."""
        return {
            "id": appointment.id,
            "business_id": appointment.business_id,
            "customer": {
                "id": appointment.customer.id,
                "email": appointment.customer.email,
                "phone": appointment.customer.phone,
                "name": appointment.customer.name,
            } if appointment.customer else None,
            "title": appointment.title,
            "service_type": appointment.service_type,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "status": appointment.status.value,
            "notes": appointment.notes,
            "external_uid": appointment.external_uid,
            "sync_status": appointment.sync_status.value,
            "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
            "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None,
        }

