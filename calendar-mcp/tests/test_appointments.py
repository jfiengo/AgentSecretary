"""
Tests for Appointment endpoints.

This module tests the appointment-related endpoints including:
- Booking new appointments with conflict detection
- Listing appointments by date
- Getting individual appointment details
- Updating appointment fields
- Cancelling appointments
- Rescheduling appointments to new times
"""

from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_next_weekday

# Use a fixed timezone offset for test consistency (Eastern Time, -5 hours)
EST = timezone(timedelta(hours=-5))


class TestBookAppointment:
    """Tests for POST /businesses/{id}/appointments endpoint."""

    def test_book_appointment_success(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that an appointment can be booked during business hours.
        
        Expected behavior:
        - Returns 201 Created status
        - Response includes success=True and appointment details
        - Customer is created or retrieved by email
        """
        next_monday = get_next_weekday(0)
        # Create timezone-aware datetime (10 AM Eastern)
        start_time = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        
        response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "newcustomer@example.com",
                "customer_name": "New Customer",
                "service_type": "junk_removal",
                "start_time": start_time.isoformat(),
                "duration_minutes": 60,
                "notes": "Large items pickup",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["appointment"] is not None
        assert data["appointment"]["service_type"] == "junk_removal"
        assert data["appointment"]["customer"]["email"] == "newcustomer@example.com"

    def test_book_appointment_creates_customer(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that a new customer is created when booking with new email.
        
        Expected behavior:
        - Customer is created with provided email, name, and phone
        - Customer info is included in appointment response
        """
        next_monday = get_next_weekday(0)
        # Create timezone-aware datetime (11 AM Eastern)
        start_time = datetime.combine(next_monday, time(11, 0), tzinfo=EST)
        
        response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "brand.new@example.com",
                "customer_name": "Brand New",
                "customer_phone": "555-9999",
                "service_type": "pool_cleaning",
                "start_time": start_time.isoformat(),
            },
        )
        
        assert response.status_code == 201
        customer = response.json()["appointment"]["customer"]
        assert customer["email"] == "brand.new@example.com"
        assert customer["name"] == "Brand New"
        assert customer["phone"] == "555-9999"

    def test_book_appointment_conflict_detection(
        self, client: TestClient, sample_business, sample_availability_rules, sample_appointment
    ):
        """
        Verify that booking at an already-booked time returns conflict error.
        
        Expected behavior:
        - Returns 409 Conflict status
        - Error message indicates time slot is not available
        """
        # Try to book at the same time as the existing appointment
        response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "another@example.com",
                "service_type": "test_service",
                "start_time": sample_appointment.start_time.isoformat(),
                "duration_minutes": 60,
            },
        )
        
        assert response.status_code == 409
        assert "conflict" in response.json()["detail"].lower() or "not available" in response.json()["detail"].lower()

    def test_book_appointment_outside_business_hours_fails(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that booking outside business hours returns error.
        
        Expected behavior:
        - Returns 409 Conflict status
        - Error indicates time is outside business hours
        """
        next_monday = get_next_weekday(0)
        # Try to book at 7 AM (before 9 AM opening)
        early_time = datetime.combine(next_monday, time(7, 0))
        
        response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "early@example.com",
                "service_type": "test_service",
                "start_time": early_time.isoformat(),
            },
        )
        
        assert response.status_code == 409

    def test_book_appointment_on_closed_day_fails(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that booking on a day without availability rules fails.
        
        Expected behavior:
        - Returns 409 Conflict status
        - Weekend (Sat/Sun) has no rules in sample_availability_rules
        """
        next_saturday = get_next_weekday(5)
        saturday_time = datetime.combine(next_saturday, time(10, 0))
        
        response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "weekend@example.com",
                "service_type": "test_service",
                "start_time": saturday_time.isoformat(),
            },
        )
        
        assert response.status_code == 409

    def test_book_appointment_nonexistent_business_fails(self, client: TestClient):
        """
        Verify that booking with non-existent business returns 409.
        
        Expected behavior:
        - Returns 409 Conflict (business not found in booking logic)
        """
        response = client.post(
            "/businesses/99999/appointments",
            json={
                "customer_email": "test@example.com",
                "service_type": "test",
                "start_time": "2025-01-06T10:00:00",
            },
        )
        
        assert response.status_code == 409


class TestListAppointments:
    """Tests for GET /businesses/{id}/appointments endpoint."""

    def test_list_appointments_empty(
        self, client: TestClient, sample_business
    ):
        """
        Verify that listing appointments returns empty when none exist.
        
        Expected behavior:
        - Returns 200 OK status
        - Response is an empty list
        """
        response = client.get(f"/businesses/{sample_business.id}/appointments")
        
        assert response.status_code == 200
        assert response.json() == []

    def test_list_appointments_with_data(
        self, client: TestClient, sample_business, sample_appointment
    ):
        """
        Verify that listing appointments returns existing appointments.
        
        Expected behavior:
        - Returns 200 OK status
        - Response includes the sample appointment
        """
        response = client.get(f"/businesses/{sample_business.id}/appointments")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        
        # Find our appointment
        appointment_ids = [a["id"] for a in data]
        assert sample_appointment.id in appointment_ids

    def test_list_appointments_by_date(
        self, client: TestClient, sample_business, sample_appointment
    ):
        """
        Verify that appointments can be filtered by date.
        
        Expected behavior:
        - Only appointments on the specified date are returned
        """
        appointment_date = sample_appointment.start_time.date()
        
        response = client.get(
            f"/businesses/{sample_business.id}/appointments",
            params={"date": appointment_date.isoformat()},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned appointments should be on that date
        for appt in data:
            appt_date = appt["start_time"][:10]  # Extract YYYY-MM-DD
            assert appt_date == appointment_date.isoformat()

    def test_list_appointments_exclude_cancelled(
        self, client: TestClient, sample_business, sample_appointment
    ):
        """
        Verify that cancelled appointments are excluded by default.
        
        Expected behavior:
        - Cancelled appointments are not returned unless include_cancelled=True
        """
        # Cancel the appointment first
        client.post(f"/appointments/{sample_appointment.id}/cancel")
        
        # List without include_cancelled
        response = client.get(f"/businesses/{sample_business.id}/appointments")
        assert response.status_code == 200
        appointment_ids = [a["id"] for a in response.json()]
        assert sample_appointment.id not in appointment_ids
        
        # List with include_cancelled=True
        response = client.get(
            f"/businesses/{sample_business.id}/appointments",
            params={"include_cancelled": True},
        )
        assert response.status_code == 200
        appointment_ids = [a["id"] for a in response.json()]
        assert sample_appointment.id in appointment_ids


class TestGetAppointment:
    """Tests for GET /appointments/{id} endpoint."""

    def test_get_existing_appointment(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that an existing appointment can be retrieved by ID.
        
        Expected behavior:
        - Returns 200 OK status
        - Response includes all appointment fields
        - Customer information is included
        """
        response = client.get(f"/appointments/{sample_appointment.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_appointment.id
        assert data["title"] == sample_appointment.title
        assert data["service_type"] == sample_appointment.service_type
        assert data["customer"] is not None

    def test_get_nonexistent_appointment_returns_404(self, client: TestClient):
        """
        Verify that requesting a non-existent appointment returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.get("/appointments/99999")
        
        assert response.status_code == 404


class TestUpdateAppointment:
    """Tests for PATCH /appointments/{id} endpoint."""

    def test_update_appointment_title(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that appointment title can be updated.
        
        Expected behavior:
        - Returns 200 OK status
        - Title is updated in the response
        """
        response = client.patch(
            f"/appointments/{sample_appointment.id}",
            json={"title": "Updated Title"},
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_update_appointment_notes(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that appointment notes can be updated.
        
        Expected behavior:
        - Returns 200 OK status
        - Notes are updated in the response
        """
        response = client.patch(
            f"/appointments/{sample_appointment.id}",
            json={"notes": "Updated notes with more details"},
        )
        
        assert response.status_code == 200
        assert response.json()["notes"] == "Updated notes with more details"

    def test_update_nonexistent_appointment_returns_404(self, client: TestClient):
        """
        Verify that updating a non-existent appointment returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.patch(
            "/appointments/99999",
            json={"title": "New Title"},
        )
        
        assert response.status_code == 404


class TestCancelAppointment:
    """Tests for POST /appointments/{id}/cancel endpoint."""

    def test_cancel_appointment_success(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that an appointment can be cancelled.
        
        Expected behavior:
        - Returns 200 OK status
        - Response includes success=True
        - Appointment status is changed to "cancelled"
        """
        response = client.post(f"/appointments/{sample_appointment.id}/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["appointment"]["status"] == "cancelled"

    def test_cancel_appointment_with_reason(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that cancellation reason is recorded.
        
        Expected behavior:
        - Reason is appended to appointment notes
        """
        response = client.post(
            f"/appointments/{sample_appointment.id}/cancel",
            params={"reason": "Customer requested cancellation"},
        )
        
        assert response.status_code == 200
        notes = response.json()["appointment"]["notes"]
        assert "Customer requested cancellation" in notes

    def test_cancel_already_cancelled_fails(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that cancelling an already-cancelled appointment fails.
        
        Expected behavior:
        - First cancellation succeeds
        - Second cancellation returns 404 (already cancelled)
        """
        # First cancellation
        response1 = client.post(f"/appointments/{sample_appointment.id}/cancel")
        assert response1.status_code == 200
        
        # Second cancellation attempt
        response2 = client.post(f"/appointments/{sample_appointment.id}/cancel")
        assert response2.status_code == 404

    def test_cancel_nonexistent_appointment_returns_404(self, client: TestClient):
        """
        Verify that cancelling a non-existent appointment returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.post("/appointments/99999/cancel")
        
        assert response.status_code == 404


class TestRescheduleAppointment:
    """Tests for POST /appointments/{id}/reschedule endpoint."""

    def test_reschedule_appointment_success(
        self, client: TestClient, sample_business, sample_availability_rules, sample_appointment
    ):
        """
        Verify that an appointment can be rescheduled to a new valid time.
        
        Expected behavior:
        - Returns 200 OK status
        - Response includes success=True
        - Appointment times are updated
        """
        # Reschedule to 2 PM on the same day
        original_date = sample_appointment.start_time.date()
        new_time = datetime.combine(original_date, time(14, 0))
        
        response = client.post(
            f"/appointments/{sample_appointment.id}/reschedule",
            params={"new_start_time": new_time.isoformat()},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "14:00" in data["appointment"]["start_time"]

    def test_reschedule_to_conflicting_time_fails(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that rescheduling to a time with existing appointment fails.
        
        Expected behavior:
        - Returns 409 Conflict status
        - Error indicates time slot is not available
        """
        next_monday = get_next_weekday(0)
        
        # Create first appointment at 10 AM Eastern
        start_time_1 = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        response1 = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "first@example.com",
                "service_type": "test",
                "start_time": start_time_1.isoformat(),
            },
        )
        assert response1.status_code == 201
        
        # Create second appointment at 11 AM Eastern
        start_time_2 = datetime.combine(next_monday, time(11, 0), tzinfo=EST)
        response2 = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "second@example.com",
                "service_type": "test",
                "start_time": start_time_2.isoformat(),
            },
        )
        assert response2.status_code == 201
        appointment_2_id = response2.json()["appointment"]["id"]
        
        # Try to reschedule second appointment to 10 AM (conflicts with first)
        response = client.post(
            f"/appointments/{appointment_2_id}/reschedule",
            params={"new_start_time": start_time_1.isoformat()},
        )
        
        assert response.status_code == 409

    def test_reschedule_outside_business_hours_fails(
        self, client: TestClient, sample_business, sample_availability_rules, sample_appointment
    ):
        """
        Verify that rescheduling to outside business hours fails.
        
        Expected behavior:
        - Returns 404 Not Found status (API returns 404 for "outside hours" errors)
        - Error indicates time is outside business hours
        """
        original_date = sample_appointment.start_time.date()
        # Try to reschedule to 7 AM Eastern (before 9 AM opening)
        early_time = datetime.combine(original_date, time(7, 0), tzinfo=EST)
        
        response = client.post(
            f"/appointments/{sample_appointment.id}/reschedule",
            params={"new_start_time": early_time.isoformat()},
        )
        
        # API returns 404 for "outside business hours" (not 409 which is for conflicts)
        assert response.status_code == 404
        assert "outside" in response.json()["detail"].lower() or "business hours" in response.json()["detail"].lower()

    def test_reschedule_cancelled_appointment_fails(
        self, client: TestClient, sample_appointment
    ):
        """
        Verify that a cancelled appointment cannot be rescheduled.
        
        Expected behavior:
        - Returns 404 Not Found (or similar error)
        - Error indicates appointment cannot be rescheduled
        """
        # Cancel first
        client.post(f"/appointments/{sample_appointment.id}/cancel")
        
        # Try to reschedule
        new_time = sample_appointment.start_time + timedelta(hours=2)
        response = client.post(
            f"/appointments/{sample_appointment.id}/reschedule",
            params={"new_start_time": new_time.isoformat()},
        )
        
        assert response.status_code in [404, 409]

    def test_reschedule_nonexistent_appointment_returns_404(self, client: TestClient):
        """
        Verify that rescheduling a non-existent appointment returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.post(
            "/appointments/99999/reschedule",
            params={"new_start_time": "2025-01-06T10:00:00"},
        )
        
        assert response.status_code == 404

    def test_reschedule_preserves_duration(
        self, client: TestClient, sample_business, sample_availability_rules, sample_appointment
    ):
        """
        Verify that rescheduling preserves the original appointment duration.
        
        Expected behavior:
        - End time is calculated based on original duration
        - Duration is not changed during reschedule
        """
        original_duration = sample_appointment.end_time - sample_appointment.start_time
        
        # Reschedule to 3 PM
        original_date = sample_appointment.start_time.date()
        new_time = datetime.combine(original_date, time(15, 0))
        
        response = client.post(
            f"/appointments/{sample_appointment.id}/reschedule",
            params={"new_start_time": new_time.isoformat()},
        )
        
        assert response.status_code == 200
        appointment = response.json()["appointment"]
        
        # Parse times and verify duration
        new_start = datetime.fromisoformat(appointment["start_time"].replace("Z", "+00:00").replace("+00:00", ""))
        new_end = datetime.fromisoformat(appointment["end_time"].replace("Z", "+00:00").replace("+00:00", ""))
        new_duration = new_end - new_start
        
        assert new_duration == original_duration

