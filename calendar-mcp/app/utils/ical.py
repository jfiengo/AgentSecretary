"""iCalendar export utilities."""

from datetime import datetime

from icalendar import Calendar, Event, vText

from app.models import Appointment


def create_ical_event(appointment: Appointment) -> Event:
    """Create an iCalendar event from an appointment."""
    event = Event()
    
    # Required properties
    event.add("uid", appointment.external_uid or f"appointment-{appointment.id}@calendar-mcp")
    event.add("dtstart", appointment.start_time)
    event.add("dtend", appointment.end_time)
    event.add("summary", appointment.title)
    
    # Optional properties
    if appointment.notes:
        event.add("description", appointment.notes)
    
    event.add("status", appointment.status.value.upper())
    
    # Add service type as a category
    event.add("categories", [appointment.service_type])
    
    # Add customer info if available
    if appointment.customer:
        if appointment.customer.email:
            event.add("attendee", f"mailto:{appointment.customer.email}")
        if appointment.customer.name:
            event["organizer"] = vText(appointment.customer.name)
    
    # Timestamps
    if appointment.created_at:
        event.add("created", appointment.created_at)
    if appointment.updated_at:
        event.add("last-modified", appointment.updated_at)
    
    return event


def create_calendar(
    appointments: list[Appointment],
    calendar_name: str = "Appointments",
) -> Calendar:
    """Create an iCalendar calendar with multiple appointments."""
    cal = Calendar()
    
    # Calendar properties
    cal.add("prodid", "-//Calendar MCP Server//calendar-mcp//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calendar_name)
    
    # Add events
    for appointment in appointments:
        event = create_ical_event(appointment)
        cal.add_component(event)
    
    return cal


def export_to_ics(
    appointments: list[Appointment],
    calendar_name: str = "Appointments",
) -> bytes:
    """Export appointments to iCalendar format (ICS file content)."""
    cal = create_calendar(appointments, calendar_name)
    return cal.to_ical()


def parse_ics(ics_content: bytes) -> list[dict]:
    """
    Parse an ICS file and extract event data.
    
    Returns a list of dicts with event information.
    """
    cal = Calendar.from_ical(ics_content)
    events = []
    
    for component in cal.walk():
        if component.name == "VEVENT":
            event_data = {
                "uid": str(component.get("uid", "")),
                "summary": str(component.get("summary", "")),
                "description": str(component.get("description", "")),
                "start_time": component.get("dtstart").dt if component.get("dtstart") else None,
                "end_time": component.get("dtend").dt if component.get("dtend") else None,
                "status": str(component.get("status", "")).lower(),
            }
            events.append(event_data)
    
    return events

