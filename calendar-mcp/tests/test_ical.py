"""
Tests for iCalendar utilities.

This module tests the iCal export/import functions including:
- Creating iCal events from appointments
- Creating calendars with multiple appointments
- Exporting to ICS format
- Parsing ICS content
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from icalendar import Calendar

from app.models import AppointmentStatus
from app.utils.ical import (
    create_calendar,
    create_ical_event,
    export_to_ics,
    parse_ics,
)


def create_mock_appointment(
    id: int = 1,
    title: str = "Test Appointment",
    service_type: str = "test_service",
    start_time: datetime = None,
    end_time: datetime = None,
    status: AppointmentStatus = AppointmentStatus.CONFIRMED,
    notes: str = None,
    external_uid: str = None,
    customer_email: str = None,
    customer_name: str = None,
    created_at: datetime = None,
    updated_at: datetime = None,
) -> MagicMock:
    """Create a mock appointment for testing."""
    if start_time is None:
        start_time = datetime(2025, 1, 20, 10, 0)
    if end_time is None:
        end_time = start_time + timedelta(hours=1)
    
    appointment = MagicMock()
    appointment.id = id
    appointment.title = title
    appointment.service_type = service_type
    appointment.start_time = start_time
    appointment.end_time = end_time
    appointment.status = status
    appointment.notes = notes
    appointment.external_uid = external_uid
    appointment.created_at = created_at
    appointment.updated_at = updated_at
    
    if customer_email or customer_name:
        customer = MagicMock()
        customer.email = customer_email
        customer.name = customer_name
        appointment.customer = customer
    else:
        appointment.customer = None
    
    return appointment


class TestCreateIcalEvent:
    """Tests for create_ical_event function."""

    def test_create_event_basic(self):
        """
        Verify that a basic iCal event is created from an appointment.
        
        Expected behavior:
        - Event has required properties (uid, dtstart, dtend, summary)
        """
        appointment = create_mock_appointment()
        
        event = create_ical_event(appointment)
        
        assert event.get("uid") is not None
        assert event.get("dtstart") is not None
        assert event.get("dtend") is not None
        assert event.get("summary") == "Test Appointment"

    def test_create_event_with_external_uid(self):
        """
        Verify that external_uid is used as event UID.
        
        Expected behavior:
        - Event UID matches the external_uid
        """
        appointment = create_mock_appointment(external_uid="custom-uid-123")
        
        event = create_ical_event(appointment)
        
        assert str(event.get("uid")) == "custom-uid-123"

    def test_create_event_without_external_uid(self):
        """
        Verify that a default UID is generated when external_uid is None.
        
        Expected behavior:
        - Event UID is generated from appointment ID
        """
        appointment = create_mock_appointment(id=42, external_uid=None)
        
        event = create_ical_event(appointment)
        
        assert "appointment-42" in str(event.get("uid"))

    def test_create_event_with_notes(self):
        """
        Verify that notes are included as description.
        
        Expected behavior:
        - Event description contains the notes
        """
        appointment = create_mock_appointment(notes="Important notes here")
        
        event = create_ical_event(appointment)
        
        assert "Important notes here" in str(event.get("description"))

    def test_create_event_without_notes(self):
        """
        Verify that event is created without description when notes are None.
        
        Expected behavior:
        - Event is created successfully
        """
        appointment = create_mock_appointment(notes=None)
        
        event = create_ical_event(appointment)
        
        # Should not raise an error
        assert event.get("summary") is not None

    def test_create_event_status(self):
        """
        Verify that appointment status is included.
        
        Expected behavior:
        - Event status matches appointment status (uppercase)
        """
        appointment = create_mock_appointment(status=AppointmentStatus.CONFIRMED)
        
        event = create_ical_event(appointment)
        
        assert str(event.get("status")).upper() == "CONFIRMED"

    def test_create_event_with_service_type_category(self):
        """
        Verify that service_type is added as a category.
        
        Expected behavior:
        - Event categories include the service type
        """
        appointment = create_mock_appointment(service_type="pool_cleaning")
        
        event = create_ical_event(appointment)
        
        categories = event.get("categories")
        assert categories is not None
        assert "pool_cleaning" in str(categories.to_ical())

    def test_create_event_with_customer_email(self):
        """
        Verify that customer email is added as attendee.
        
        Expected behavior:
        - Event has attendee with customer email
        """
        appointment = create_mock_appointment(customer_email="customer@example.com")
        
        event = create_ical_event(appointment)
        
        attendee = event.get("attendee")
        assert attendee is not None
        assert "customer@example.com" in str(attendee)

    def test_create_event_with_customer_name(self):
        """
        Verify that customer name is added as organizer.
        
        Expected behavior:
        - Event has organizer with customer name
        """
        appointment = create_mock_appointment(
            customer_email="customer@example.com",
            customer_name="John Doe",
        )
        
        event = create_ical_event(appointment)
        
        organizer = event.get("organizer")
        assert organizer is not None
        assert "John Doe" in str(organizer)

    def test_create_event_with_timestamps(self):
        """
        Verify that created_at and updated_at are included.
        
        Expected behavior:
        - Event has created and last-modified properties
        """
        created = datetime(2025, 1, 15, 10, 0)
        updated = datetime(2025, 1, 18, 14, 30)
        appointment = create_mock_appointment(created_at=created, updated_at=updated)
        
        event = create_ical_event(appointment)
        
        assert event.get("created") is not None
        assert event.get("last-modified") is not None


class TestCreateCalendar:
    """Tests for create_calendar function."""

    def test_create_calendar_empty(self):
        """
        Verify that an empty calendar can be created.
        
        Expected behavior:
        - Calendar has required properties
        - No events are included
        """
        cal = create_calendar([])
        
        assert cal.get("prodid") is not None
        assert cal.get("version") == "2.0"
        
        # Count VEVENT components
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 0

    def test_create_calendar_with_appointments(self):
        """
        Verify that appointments are added as events.
        
        Expected behavior:
        - Each appointment becomes a VEVENT
        """
        appointments = [
            create_mock_appointment(id=1, title="Appointment 1"),
            create_mock_appointment(id=2, title="Appointment 2"),
            create_mock_appointment(id=3, title="Appointment 3"),
        ]
        
        cal = create_calendar(appointments)
        
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 3

    def test_create_calendar_custom_name(self):
        """
        Verify that calendar name can be customized.
        
        Expected behavior:
        - Calendar has custom x-wr-calname property
        """
        cal = create_calendar([], calendar_name="My Custom Calendar")
        
        assert str(cal.get("x-wr-calname")) == "My Custom Calendar"

    def test_create_calendar_properties(self):
        """
        Verify that calendar has standard properties.
        
        Expected behavior:
        - Calendar has prodid, version, calscale, method
        """
        cal = create_calendar([])
        
        assert "calendar-mcp" in str(cal.get("prodid"))
        assert cal.get("version") == "2.0"
        assert str(cal.get("calscale")) == "GREGORIAN"
        assert str(cal.get("method")) == "PUBLISH"


class TestExportToIcs:
    """Tests for export_to_ics function."""

    def test_export_to_ics_returns_bytes(self):
        """
        Verify that export returns bytes.
        
        Expected behavior:
        - Returns bytes object
        - Content is valid ICS format
        """
        appointments = [create_mock_appointment()]
        
        result = export_to_ics(appointments)
        
        assert isinstance(result, bytes)
        assert b"BEGIN:VCALENDAR" in result
        assert b"END:VCALENDAR" in result

    def test_export_to_ics_contains_events(self):
        """
        Verify that exported ICS contains events.
        
        Expected behavior:
        - ICS content includes VEVENT components
        """
        appointments = [
            create_mock_appointment(id=1, title="Event 1"),
            create_mock_appointment(id=2, title="Event 2"),
        ]
        
        result = export_to_ics(appointments)
        
        assert b"BEGIN:VEVENT" in result
        assert b"END:VEVENT" in result

    def test_export_to_ics_custom_calendar_name(self):
        """
        Verify that custom calendar name is included.
        
        Expected behavior:
        - ICS content includes X-WR-CALNAME property
        """
        result = export_to_ics([], calendar_name="Test Calendar")
        
        assert b"X-WR-CALNAME:Test Calendar" in result

    def test_export_to_ics_parseable(self):
        """
        Verify that exported ICS can be parsed back.
        
        Expected behavior:
        - Exported bytes can be parsed by icalendar library
        """
        appointments = [create_mock_appointment()]
        
        result = export_to_ics(appointments)
        
        # Should not raise an error
        cal = Calendar.from_ical(result)
        assert cal is not None


class TestParseIcs:
    """Tests for parse_ics function."""

    def test_parse_ics_basic(self):
        """
        Verify that ICS content can be parsed.
        
        Expected behavior:
        - Returns list of event dictionaries
        """
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid-123
DTSTART:20250120T100000Z
DTEND:20250120T110000Z
SUMMARY:Test Event
END:VEVENT
END:VCALENDAR"""
        
        events = parse_ics(ics_content)
        
        assert len(events) == 1
        assert events[0]["uid"] == "test-uid-123"
        assert events[0]["summary"] == "Test Event"

    def test_parse_ics_multiple_events(self):
        """
        Verify that multiple events are parsed.
        
        Expected behavior:
        - All events are returned
        """
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-1
DTSTART:20250120T100000Z
DTEND:20250120T110000Z
SUMMARY:Event 1
END:VEVENT
BEGIN:VEVENT
UID:event-2
DTSTART:20250121T100000Z
DTEND:20250121T110000Z
SUMMARY:Event 2
END:VEVENT
END:VCALENDAR"""
        
        events = parse_ics(ics_content)
        
        assert len(events) == 2

    def test_parse_ics_with_description(self):
        """
        Verify that description is parsed.
        
        Expected behavior:
        - Event description is included
        """
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid
DTSTART:20250120T100000Z
DTEND:20250120T110000Z
SUMMARY:Test Event
DESCRIPTION:This is the event description
END:VEVENT
END:VCALENDAR"""
        
        events = parse_ics(ics_content)
        
        assert events[0]["description"] == "This is the event description"

    def test_parse_ics_with_status(self):
        """
        Verify that status is parsed.
        
        Expected behavior:
        - Event status is included (lowercase)
        """
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid
DTSTART:20250120T100000Z
DTEND:20250120T110000Z
SUMMARY:Test Event
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""
        
        events = parse_ics(ics_content)
        
        assert events[0]["status"] == "confirmed"

    def test_parse_ics_empty_calendar(self):
        """
        Verify that empty calendar returns empty list.
        
        Expected behavior:
        - Returns empty list when no events
        """
        ics_content = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
END:VCALENDAR"""
        
        events = parse_ics(ics_content)
        
        assert events == []

    def test_parse_ics_roundtrip(self):
        """
        Verify that export and parse roundtrip works.
        
        Expected behavior:
        - Exported appointments can be parsed back
        - Key fields are preserved
        """
        original_appointments = [
            create_mock_appointment(
                id=1,
                title="Roundtrip Test",
                service_type="test",
                external_uid="roundtrip-uid-123",
                start_time=datetime(2025, 1, 20, 10, 0),
                end_time=datetime(2025, 1, 20, 11, 0),
            ),
        ]
        
        # Export
        ics_bytes = export_to_ics(original_appointments)
        
        # Parse
        parsed_events = parse_ics(ics_bytes)
        
        assert len(parsed_events) == 1
        assert parsed_events[0]["uid"] == "roundtrip-uid-123"
        assert parsed_events[0]["summary"] == "Roundtrip Test"
