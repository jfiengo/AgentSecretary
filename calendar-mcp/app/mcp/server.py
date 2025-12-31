"""MCP server with calendar scheduling tools."""

from datetime import date, datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.database import async_session_maker
from app.services.availability import AvailabilityService
from app.services.booking import BookingService

# Create MCP server instance
server = Server("calendar-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="check_availability",
            description="Returns available time slots for a given date. Use this to find when appointments can be scheduled.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {
                        "type": "integer",
                        "description": "The ID of the business to check availability for",
                    },
                    "date": {
                        "type": "string",
                        "description": "The date to check availability for (YYYY-MM-DD format)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration of the appointment in minutes (default: 60)",
                        "default": 60,
                    },
                },
                "required": ["business_id", "date"],
            },
        ),
        Tool(
            name="book_appointment",
            description="Books an appointment for a customer. Returns confirmation or conflict error.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {
                        "type": "integer",
                        "description": "The ID of the business to book with",
                    },
                    "customer_email": {
                        "type": "string",
                        "description": "Customer's email address",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Appointment start time in ISO format (e.g., 2024-01-15T09:00:00-05:00)",
                    },
                    "service_type": {
                        "type": "string",
                        "description": "Type of service being booked (e.g., 'junk removal', 'pool cleaning')",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration of the appointment in minutes (default: 60)",
                        "default": 60,
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes for the appointment",
                        "default": "",
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's name (optional)",
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number (optional)",
                    },
                },
                "required": ["business_id", "customer_email", "start_time", "service_type"],
            },
        ),
        Tool(
            name="cancel_appointment",
            description="Cancels an existing appointment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "integer",
                        "description": "The ID of the appointment to cancel",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for cancellation (optional)",
                        "default": "",
                    },
                },
                "required": ["appointment_id"],
            },
        ),
        Tool(
            name="reschedule_appointment",
            description="Reschedules an existing appointment to a new time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "integer",
                        "description": "The ID of the appointment to reschedule",
                    },
                    "new_start_time": {
                        "type": "string",
                        "description": "New appointment start time in ISO format",
                    },
                },
                "required": ["appointment_id", "new_start_time"],
            },
        ),
        Tool(
            name="get_daily_schedule",
            description="Returns all appointments for a business on a given date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {
                        "type": "integer",
                        "description": "The ID of the business",
                    },
                    "date": {
                        "type": "string",
                        "description": "The date to get schedule for (YYYY-MM-DD format)",
                    },
                },
                "required": ["business_id", "date"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    import json

    async with async_session_maker() as db:
        try:
            if name == "check_availability":
                result = await handle_check_availability(db, arguments)
            elif name == "book_appointment":
                result = await handle_book_appointment(db, arguments)
            elif name == "cancel_appointment":
                result = await handle_cancel_appointment(db, arguments)
            elif name == "reschedule_appointment":
                result = await handle_reschedule_appointment(db, arguments)
            elif name == "get_daily_schedule":
                result = await handle_get_daily_schedule(db, arguments)
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            result = {"error": str(e)}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_check_availability(db, arguments: dict) -> dict:
    """Handle check_availability tool call."""
    business_id = arguments["business_id"]
    date_str = arguments["date"]
    duration_minutes = arguments.get("duration_minutes", 60)

    # Parse date
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    service = AvailabilityService(db)
    return await service.get_available_slots(business_id, target_date, duration_minutes)


async def handle_book_appointment(db, arguments: dict) -> dict:
    """Handle book_appointment tool call."""
    business_id = arguments["business_id"]
    customer_email = arguments["customer_email"]
    start_time_str = arguments["start_time"]
    service_type = arguments["service_type"]
    duration_minutes = arguments.get("duration_minutes", 60)
    notes = arguments.get("notes", "")
    customer_name = arguments.get("customer_name")
    customer_phone = arguments.get("customer_phone")

    # Parse start time
    try:
        start_time = datetime.fromisoformat(start_time_str)
    except ValueError:
        return {"error": "Invalid start_time format. Use ISO format (e.g., 2024-01-15T09:00:00-05:00)"}

    service = BookingService(db)
    return await service.book_appointment(
        business_id=business_id,
        customer_email=customer_email,
        start_time=start_time,
        service_type=service_type,
        duration_minutes=duration_minutes,
        notes=notes,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )


async def handle_cancel_appointment(db, arguments: dict) -> dict:
    """Handle cancel_appointment tool call."""
    appointment_id = arguments["appointment_id"]
    reason = arguments.get("reason", "")

    service = BookingService(db)
    return await service.cancel_appointment(appointment_id, reason)


async def handle_reschedule_appointment(db, arguments: dict) -> dict:
    """Handle reschedule_appointment tool call."""
    appointment_id = arguments["appointment_id"]
    new_start_time_str = arguments["new_start_time"]

    # Parse new start time
    try:
        new_start_time = datetime.fromisoformat(new_start_time_str)
    except ValueError:
        return {"error": "Invalid new_start_time format. Use ISO format"}

    service = BookingService(db)
    return await service.reschedule_appointment(appointment_id, new_start_time)


async def handle_get_daily_schedule(db, arguments: dict) -> dict:
    """Handle get_daily_schedule tool call."""
    business_id = arguments["business_id"]
    date_str = arguments["date"]

    service = BookingService(db)
    return await service.get_daily_schedule(business_id, date_str)


async def run_server():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for the MCP server."""
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()

