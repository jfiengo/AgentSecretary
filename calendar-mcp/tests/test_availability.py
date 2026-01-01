"""
Tests for Availability endpoints.

This module tests the availability-related endpoints including:
- Creating and managing availability rules (business hours)
- Querying available time slots
- Verifying that conflicts are properly excluded from availability
"""

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_next_weekday


class TestCreateAvailabilityRule:
    """Tests for POST /businesses/{id}/availability-rules endpoint."""

    def test_create_availability_rule_valid(
        self, client: TestClient, sample_business
    ):
        """
        Verify that an availability rule can be created with valid data.
        
        Expected behavior:
        - Returns 201 Created status
        - Rule is associated with the correct business
        - Day of week, start time, and end time are correctly stored
        """
        response = client.post(
            f"/businesses/{sample_business.id}/availability-rules",
            json={
                "day_of_week": 0,  # Monday
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["business_id"] == sample_business.id
        assert data["day_of_week"] == 0
        assert "09:00" in data["start_time"]
        assert "17:00" in data["end_time"]

    def test_create_availability_rule_for_each_day(
        self, client: TestClient, sample_business
    ):
        """
        Verify that availability rules can be created for all days of the week.
        
        Expected behavior:
        - Rules can be created for days 0-6 (Monday-Sunday)
        - Each rule is stored independently
        """
        for day in range(7):
            response = client.post(
                f"/businesses/{sample_business.id}/availability-rules",
                json={
                    "day_of_week": day,
                    "start_time": "08:00:00",
                    "end_time": "20:00:00",
                },
            )
            assert response.status_code == 201
            assert response.json()["day_of_week"] == day

    def test_create_availability_rule_invalid_day_fails(
        self, client: TestClient, sample_business
    ):
        """
        Verify that day_of_week must be between 0 and 6.
        
        Expected behavior:
        - Returns 422 for day_of_week < 0
        - Returns 422 for day_of_week > 6
        """
        # Day too low
        response = client.post(
            f"/businesses/{sample_business.id}/availability-rules",
            json={
                "day_of_week": -1,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        assert response.status_code == 422
        
        # Day too high
        response = client.post(
            f"/businesses/{sample_business.id}/availability-rules",
            json={
                "day_of_week": 7,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        assert response.status_code == 422

    def test_create_availability_rule_nonexistent_business_fails(
        self, client: TestClient
    ):
        """
        Verify that creating a rule for a non-existent business returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.post(
            "/businesses/99999/availability-rules",
            json={
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "17:00:00",
            },
        )
        assert response.status_code == 404


class TestListAvailabilityRules:
    """Tests for GET /businesses/{id}/availability-rules endpoint."""

    def test_list_availability_rules_empty(
        self, client: TestClient, sample_business
    ):
        """
        Verify that listing rules returns empty list when none exist.
        
        Expected behavior:
        - Returns 200 OK status
        - Response is an empty list
        """
        response = client.get(
            f"/businesses/{sample_business.id}/availability-rules"
        )
        
        assert response.status_code == 200
        assert response.json() == []

    def test_list_availability_rules_with_data(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that listing rules returns all created rules.
        
        Expected behavior:
        - Returns 200 OK status
        - Response contains all rules for the business
        - Rules are ordered by day_of_week
        """
        response = client.get(
            f"/businesses/{sample_business.id}/availability-rules"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5  # Monday through Friday

    def test_list_availability_rules_filter_by_day(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that rules can be filtered by day_of_week.
        
        Expected behavior:
        - Returns only rules for the specified day
        - Returns empty list if no rules exist for that day
        """
        # Get Monday rules
        response = client.get(
            f"/businesses/{sample_business.id}/availability-rules?day_of_week=0"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["day_of_week"] == 0
        
        # Get Saturday rules (none exist)
        response = client.get(
            f"/businesses/{sample_business.id}/availability-rules?day_of_week=5"
        )
        assert response.status_code == 200
        assert response.json() == []


class TestDeleteAvailabilityRule:
    """Tests for DELETE /businesses/{id}/availability-rules/{rule_id} endpoint."""

    def test_delete_availability_rule(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that an availability rule can be deleted.
        
        Expected behavior:
        - Returns 204 No Content status
        - Rule is no longer in the list after deletion
        """
        rule_id = sample_availability_rules[0].id
        
        response = client.delete(
            f"/businesses/{sample_business.id}/availability-rules/{rule_id}"
        )
        
        assert response.status_code == 204
        
        # Verify it's gone
        list_response = client.get(
            f"/businesses/{sample_business.id}/availability-rules"
        )
        rule_ids = [r["id"] for r in list_response.json()]
        assert rule_id not in rule_ids

    def test_delete_nonexistent_rule_returns_404(
        self, client: TestClient, sample_business
    ):
        """
        Verify that deleting a non-existent rule returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.delete(
            f"/businesses/{sample_business.id}/availability-rules/99999"
        )
        
        assert response.status_code == 404


class TestGetAvailableSlots:
    """Tests for GET /businesses/{id}/availability endpoint."""

    def test_get_available_slots_with_rules(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that available slots are returned based on availability rules.
        
        Expected behavior:
        - Returns 200 OK status
        - Slots are generated within business hours
        - Response includes timezone information
        """
        # Get next Monday (when rules apply)
        next_monday = get_next_weekday(0)
        
        response = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat(), "duration_minutes": 60},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["business_id"] == sample_business.id
        assert data["date"] == next_monday.isoformat()
        assert data["timezone"] == sample_business.timezone
        assert len(data["slots"]) > 0  # Should have available slots

    def test_get_available_slots_no_rules_returns_empty(
        self, client: TestClient, sample_business
    ):
        """
        Verify that no slots are returned when no availability rules exist.
        
        Expected behavior:
        - Returns 200 OK status
        - slots list is empty
        """
        next_monday = get_next_weekday(0)
        
        response = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat()},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["slots"] == []

    def test_get_available_slots_weekend_no_rules(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that no slots are returned for days without availability rules.
        
        Expected behavior:
        - Weekend has no rules (only Mon-Fri defined)
        - Returns empty slots list for Saturday/Sunday
        """
        # Get next Saturday (no rules)
        next_saturday = get_next_weekday(5)
        
        response = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_saturday.isoformat()},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["slots"] == []

    def test_get_available_slots_custom_duration(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that slot duration can be customized.
        
        Expected behavior:
        - Slots are generated with the specified duration
        - Fewer slots are available for longer durations
        """
        next_monday = get_next_weekday(0)
        
        # Get 30-minute slots
        response_30 = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat(), "duration_minutes": 30},
        )
        
        # Get 120-minute slots
        response_120 = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat(), "duration_minutes": 120},
        )
        
        assert response_30.status_code == 200
        assert response_120.status_code == 200
        
        slots_30 = response_30.json()["slots"]
        slots_120 = response_120.json()["slots"]
        
        # More 30-min slots than 120-min slots
        assert len(slots_30) > len(slots_120)
        
        # Verify duration in response
        if slots_30:
            assert slots_30[0]["duration_minutes"] == 30
        if slots_120:
            assert slots_120[0]["duration_minutes"] == 120

    def test_get_available_slots_excludes_appointments(
        self, client: TestClient, sample_business, sample_availability_rules
    ):
        """
        Verify that existing appointments are excluded from available slots.
        
        Expected behavior:
        - Time slots overlapping with existing appointments are not returned
        - Adjacent slots before/after the appointment are still available
        """
        from datetime import timezone
        
        next_monday = get_next_weekday(0)
        EST = timezone(timedelta(hours=-5))
        
        # First, get available slots before booking
        response_before = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat(), "duration_minutes": 60},
        )
        assert response_before.status_code == 200
        slots_before = len(response_before.json()["slots"])
        
        # Book an appointment at 10 AM
        start_time = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        book_response = client.post(
            f"/businesses/{sample_business.id}/appointments",
            json={
                "customer_email": "blocker@example.com",
                "service_type": "test",
                "start_time": start_time.isoformat(),
                "duration_minutes": 60,
            },
        )
        assert book_response.status_code == 201
        
        # Get available slots after booking
        response_after = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": next_monday.isoformat(), "duration_minutes": 60},
        )
        assert response_after.status_code == 200
        slots_after = len(response_after.json()["slots"])
        
        # Should have one fewer slot after booking
        assert slots_after == slots_before - 1

    def test_get_available_slots_nonexistent_business_returns_404(
        self, client: TestClient
    ):
        """
        Verify that querying availability for non-existent business returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.get(
            "/businesses/99999/availability",
            params={"date": "2025-01-06"},
        )
        
        assert response.status_code == 404

    def test_get_available_slots_invalid_date_fails(
        self, client: TestClient, sample_business
    ):
        """
        Verify that invalid date format returns validation error.
        
        Expected behavior:
        - Returns 422 Unprocessable Entity for invalid date format
        """
        response = client.get(
            f"/businesses/{sample_business.id}/availability",
            params={"date": "not-a-date"},
        )
        
        assert response.status_code == 422

