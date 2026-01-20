"""
Tests for BookingService.

This module tests the booking service including:
- Customer creation and retrieval
- Appointment booking with conflict detection
- Appointment cancellation
- Appointment rescheduling
- Daily schedule retrieval
"""

from datetime import datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
import pytz
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, Customer, SyncStatus
from app.services.booking import BookingService
from tests.conftest import get_next_weekday

# Use a fixed timezone offset for test consistency (Eastern Time, -5 hours)
EST = timezone(timedelta(hours=-5))


class TestGetOrCreateCustomer:
    """Tests for BookingService.get_or_create_customer method."""

    @pytest.mark.asyncio
    async def test_create_new_customer(self, test_db: AsyncSession):
        """
        Verify that a new customer is created when email doesn't exist.
        
        Expected behavior:
        - Customer is created with provided email, name, and phone
        - Customer ID is assigned
        """
        service = BookingService(test_db)
        
        customer = await service.get_or_create_customer(
            email="new@example.com",
            name="New Customer",
            phone="555-1234",
        )
        
        assert customer.id is not None
        assert customer.email == "new@example.com"
        assert customer.name == "New Customer"
        assert customer.phone == "555-1234"

    @pytest.mark.asyncio
    async def test_retrieve_existing_customer(
        self, test_db: AsyncSession, sample_customer: Customer
    ):
        """
        Verify that existing customer is retrieved by email.
        
        Expected behavior:
        - Same customer is returned when email matches
        - No duplicate is created
        """
        service = BookingService(test_db)
        
        customer = await service.get_or_create_customer(
            email=sample_customer.email,
        )
        
        assert customer.id == sample_customer.id
        assert customer.email == sample_customer.email

    @pytest.mark.asyncio
    async def test_update_customer_partial_info(
        self, test_db: AsyncSession
    ):
        """
        Verify that customer info is updated when missing fields are provided.
        
        Expected behavior:
        - Name is updated if previously empty
        - Phone is updated if previously empty
        - Existing values are not overwritten
        """
        service = BookingService(test_db)
        
        # Create customer with only email
        customer1 = await service.get_or_create_customer(email="partial@example.com")
        assert customer1.name is None
        assert customer1.phone is None
        
        # Update with name and phone
        customer2 = await service.get_or_create_customer(
            email="partial@example.com",
            name="Updated Name",
            phone="555-9999",
        )
        
        assert customer2.id == customer1.id
        assert customer2.name == "Updated Name"
        assert customer2.phone == "555-9999"


class TestBookAppointment:
    """Tests for BookingService.book_appointment method."""

    @pytest.mark.asyncio
    async def test_book_appointment_success(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that an appointment can be booked successfully.
        
        Expected behavior:
        - Returns success=True
        - Appointment is created with correct details
        - Customer is created or retrieved
        """
        service = BookingService(test_db)
        next_monday = get_next_weekday(0)
        # Use timezone-aware datetime (10 AM Eastern)
        start_time = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        
        result = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="booker@example.com",
            start_time=start_time,
            service_type="test_service",
            duration_minutes=60,
            title="Test Booking",
            notes="Test notes",
            customer_name="Test Booker",
        )
        
        assert result["success"] is True
        assert result["appointment"] is not None
        assert result["appointment"]["service_type"] == "test_service"
        assert result["appointment"]["customer"]["email"] == "booker@example.com"

    @pytest.mark.asyncio
    async def test_book_appointment_nonexistent_business(self, test_db: AsyncSession):
        """
        Verify that booking with non-existent business fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates business not found
        """
        service = BookingService(test_db)
        
        result = await service.book_appointment(
            business_id=99999,
            customer_email="test@example.com",
            start_time=datetime.now(),
            service_type="test",
        )
        
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_book_appointment_conflict_detection(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that conflicting appointments are detected.
        
        Expected behavior:
        - First booking succeeds
        - Second booking at same time fails with conflict message
        """
        service = BookingService(test_db)
        next_monday = get_next_weekday(0)
        # Use timezone-aware datetime (10 AM Eastern)
        start_time = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        
        # First booking
        result1 = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="first@example.com",
            start_time=start_time,
            service_type="test",
        )
        assert result1["success"] is True
        
        # Second booking at same time
        result2 = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="second@example.com",
            start_time=start_time,
            service_type="test",
        )
        assert result2["success"] is False
        assert "conflict" in result2["message"].lower() or "not available" in result2["message"].lower()

    @pytest.mark.asyncio
    async def test_book_appointment_outside_business_hours(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that booking outside business hours fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates time is outside business hours
        """
        service = BookingService(test_db)
        next_monday = get_next_weekday(0)
        # 7 AM is before 9 AM opening
        early_time = datetime.combine(next_monday, time(7, 0))
        
        result = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="early@example.com",
            start_time=early_time,
            service_type="test",
        )
        
        assert result["success"] is False
        assert "outside" in result["message"].lower() or "blocked" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_book_appointment_timezone_handling(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that timezone-aware datetimes are handled correctly.
        
        Expected behavior:
        - Timezone-aware datetime is converted to UTC for storage
        - Appointment is created successfully
        """
        service = BookingService(test_db)
        next_monday = get_next_weekday(0)
        
        # Create timezone-aware datetime (10 AM Eastern)
        eastern = pytz.timezone("America/New_York")
        start_time = eastern.localize(datetime.combine(next_monday, time(10, 0)))
        
        result = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="tz@example.com",
            start_time=start_time,
            service_type="test",
        )
        
        assert result["success"] is True


class TestCancelAppointment:
    """Tests for BookingService.cancel_appointment method."""

    @pytest.mark.asyncio
    async def test_cancel_appointment_success(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that an appointment can be cancelled.
        
        Expected behavior:
        - Returns success=True
        - Appointment status is changed to cancelled
        """
        service = BookingService(test_db)
        
        result = await service.cancel_appointment(sample_appointment.id)
        
        assert result["success"] is True
        assert result["appointment"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_appointment_with_reason(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that cancellation reason is recorded.
        
        Expected behavior:
        - Reason is appended to appointment notes
        """
        service = BookingService(test_db)
        
        result = await service.cancel_appointment(
            sample_appointment.id,
            reason="Customer requested cancellation",
        )
        
        assert result["success"] is True
        assert "Customer requested cancellation" in result["appointment"]["notes"]

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_appointment(self, test_db: AsyncSession):
        """
        Verify that cancelling non-existent appointment fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates appointment not found
        """
        service = BookingService(test_db)
        
        result = await service.cancel_appointment(99999)
        
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_appointment(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that cancelling an already cancelled appointment fails.
        
        Expected behavior:
        - First cancellation succeeds
        - Second cancellation fails with appropriate message
        """
        service = BookingService(test_db)
        
        # First cancellation
        result1 = await service.cancel_appointment(sample_appointment.id)
        assert result1["success"] is True
        
        # Second cancellation
        result2 = await service.cancel_appointment(sample_appointment.id)
        assert result2["success"] is False
        assert "already cancelled" in result2["message"].lower()


class TestRescheduleAppointment:
    """Tests for BookingService.reschedule_appointment method."""

    @pytest.mark.asyncio
    async def test_reschedule_appointment_success(
        self, test_db: AsyncSession, sample_business, sample_availability_rules, sample_appointment: Appointment
    ):
        """
        Verify that an appointment can be rescheduled.
        
        Expected behavior:
        - Returns success=True
        - Appointment times are updated
        - Duration is preserved
        """
        service = BookingService(test_db)
        original_date = sample_appointment.start_time.date()
        new_time = datetime.combine(original_date, time(14, 0))
        
        result = await service.reschedule_appointment(
            sample_appointment.id,
            new_time,
        )
        
        assert result["success"] is True
        assert "14:00" in result["appointment"]["start_time"]

    @pytest.mark.asyncio
    async def test_reschedule_nonexistent_appointment(self, test_db: AsyncSession):
        """
        Verify that rescheduling non-existent appointment fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates appointment not found
        """
        service = BookingService(test_db)
        
        result = await service.reschedule_appointment(99999, datetime.now())
        
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_reschedule_cancelled_appointment_fails(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that rescheduling a cancelled appointment fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates status issue
        """
        service = BookingService(test_db)
        
        # Cancel first
        await service.cancel_appointment(sample_appointment.id)
        
        # Try to reschedule
        new_time = sample_appointment.start_time + timedelta(hours=2)
        result = await service.reschedule_appointment(sample_appointment.id, new_time)
        
        assert result["success"] is False
        assert "status" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_reschedule_to_conflicting_time_fails(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that rescheduling to a conflicting time fails.
        
        Expected behavior:
        - Returns success=False
        - Error message indicates conflict
        """
        service = BookingService(test_db)
        next_monday = get_next_weekday(0)
        
        # Create first appointment at 10 AM Eastern
        start_time_1 = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        result1 = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="first@example.com",
            start_time=start_time_1,
            service_type="test",
        )
        assert result1["success"] is True
        
        # Create second appointment at 11 AM Eastern
        start_time_2 = datetime.combine(next_monday, time(11, 0), tzinfo=EST)
        result2 = await service.book_appointment(
            business_id=sample_business.id,
            customer_email="second@example.com",
            start_time=start_time_2,
            service_type="test",
        )
        assert result2["success"] is True
        appointment_2_id = result2["appointment"]["id"]
        
        # Try to reschedule second to 10 AM (conflicts with first)
        result = await service.reschedule_appointment(appointment_2_id, start_time_1)
        
        assert result["success"] is False
        assert "conflict" in result["message"].lower() or "not available" in result["message"].lower()


class TestGetDailySchedule:
    """Tests for BookingService.get_daily_schedule method."""

    @pytest.mark.asyncio
    async def test_get_daily_schedule_success(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment
    ):
        """
        Verify that daily schedule returns appointments for the date.
        
        Expected behavior:
        - Returns appointments for the specified date
        - Includes timezone information
        """
        service = BookingService(test_db)
        target_date = sample_appointment.start_time.date().isoformat()
        
        result = await service.get_daily_schedule(sample_business.id, target_date)
        
        assert result["business_id"] == sample_business.id
        assert result["date"] == target_date
        assert "timezone" in result
        assert len(result["appointments"]) >= 1

    @pytest.mark.asyncio
    async def test_get_daily_schedule_nonexistent_business(self, test_db: AsyncSession):
        """
        Verify that schedule for non-existent business returns error.
        
        Expected behavior:
        - Returns error in result
        """
        service = BookingService(test_db)
        
        result = await service.get_daily_schedule(99999, "2025-01-06")
        
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_daily_schedule_invalid_date(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that invalid date format returns error.
        
        Expected behavior:
        - Returns error in result
        """
        service = BookingService(test_db)
        
        result = await service.get_daily_schedule(sample_business.id, "invalid-date")
        
        assert "error" in result
        assert "Invalid date" in result["error"]

    @pytest.mark.asyncio
    async def test_get_daily_schedule_empty_day(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that schedule for day with no appointments returns empty list.
        
        Expected behavior:
        - Returns empty appointments list
        """
        service = BookingService(test_db)
        
        result = await service.get_daily_schedule(sample_business.id, "2099-01-01")
        
        assert result["appointments"] == []


class TestGetAppointment:
    """Tests for BookingService.get_appointment method."""

    @pytest.mark.asyncio
    async def test_get_existing_appointment(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that an existing appointment can be retrieved.
        
        Expected behavior:
        - Returns the appointment object
        """
        service = BookingService(test_db)
        
        appointment = await service.get_appointment(sample_appointment.id)
        
        assert appointment is not None
        assert appointment.id == sample_appointment.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_appointment(self, test_db: AsyncSession):
        """
        Verify that non-existent appointment returns None.
        
        Expected behavior:
        - Returns None
        """
        service = BookingService(test_db)
        
        appointment = await service.get_appointment(99999)
        
        assert appointment is None
