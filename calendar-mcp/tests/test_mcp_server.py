"""
Tests for MCP Server.

This module tests the MCP server tool handlers including:
- list_tools returns all available tools
- check_availability tool handler
- book_appointment tool handler
- cancel_appointment tool handler
- reschedule_appointment tool handler
- get_daily_schedule tool handler
- Error handling for unknown tools
"""

import json
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.server import (
    call_tool,
    handle_book_appointment,
    handle_cancel_appointment,
    handle_check_availability,
    handle_get_daily_schedule,
    handle_reschedule_appointment,
    list_tools,
)
from app.models import Appointment, AppointmentStatus
from tests.conftest import get_next_weekday

# Use a fixed timezone offset for test consistency (Eastern Time, -5 hours)
EST = timezone(timedelta(hours=-5))


class TestListTools:
    """Tests for list_tools function."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """
        Verify that list_tools returns all available tools.
        
        Expected behavior:
        - Returns 5 tools
        - Each tool has name, description, and inputSchema
        """
        tools = await list_tools()
        
        assert len(tools) == 5
        
        tool_names = [t.name for t in tools]
        assert "check_availability" in tool_names
        assert "book_appointment" in tool_names
        assert "cancel_appointment" in tool_names
        assert "reschedule_appointment" in tool_names
        assert "get_daily_schedule" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_has_descriptions(self):
        """
        Verify that all tools have descriptions.
        
        Expected behavior:
        - Each tool has a non-empty description
        """
        tools = await list_tools()
        
        for tool in tools:
            assert tool.description is not None
            assert len(tool.description) > 0

    @pytest.mark.asyncio
    async def test_list_tools_has_input_schemas(self):
        """
        Verify that all tools have input schemas.
        
        Expected behavior:
        - Each tool has an inputSchema with type and properties
        """
        tools = await list_tools()
        
        for tool in tools:
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"
            assert "properties" in tool.inputSchema

    @pytest.mark.asyncio
    async def test_check_availability_tool_schema(self):
        """
        Verify check_availability tool has correct schema.
        
        Expected behavior:
        - Required: business_id, date
        - Optional: duration_minutes
        """
        tools = await list_tools()
        tool = next(t for t in tools if t.name == "check_availability")
        
        assert "business_id" in tool.inputSchema["properties"]
        assert "date" in tool.inputSchema["properties"]
        assert "duration_minutes" in tool.inputSchema["properties"]
        assert tool.inputSchema["required"] == ["business_id", "date"]

    @pytest.mark.asyncio
    async def test_book_appointment_tool_schema(self):
        """
        Verify book_appointment tool has correct schema.
        
        Expected behavior:
        - Required: business_id, customer_email, start_time, service_type
        """
        tools = await list_tools()
        tool = next(t for t in tools if t.name == "book_appointment")
        
        required = tool.inputSchema["required"]
        assert "business_id" in required
        assert "customer_email" in required
        assert "start_time" in required
        assert "service_type" in required


class TestHandleCheckAvailability:
    """Tests for handle_check_availability function."""

    @pytest.mark.asyncio
    async def test_check_availability_success(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that check_availability returns available slots.
        
        Expected behavior:
        - Returns slots for the specified date
        """
        next_monday = get_next_weekday(0)
        
        result = await handle_check_availability(test_db, {
            "business_id": sample_business.id,
            "date": next_monday.isoformat(),
            "duration_minutes": 60,
        })
        
        assert "slots" in result
        assert result["business_id"] == sample_business.id

    @pytest.mark.asyncio
    async def test_check_availability_invalid_date(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that invalid date format returns error.
        
        Expected behavior:
        - Returns error message for invalid date
        """
        result = await handle_check_availability(test_db, {
            "business_id": sample_business.id,
            "date": "invalid-date",
        })
        
        assert "error" in result
        assert "Invalid date" in result["error"]

    @pytest.mark.asyncio
    async def test_check_availability_default_duration(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that default duration is used when not specified.
        
        Expected behavior:
        - Uses 60 minutes as default duration
        """
        next_monday = get_next_weekday(0)
        
        result = await handle_check_availability(test_db, {
            "business_id": sample_business.id,
            "date": next_monday.isoformat(),
        })
        
        assert "slots" in result


class TestHandleBookAppointment:
    """Tests for handle_book_appointment function."""

    @pytest.mark.asyncio
    async def test_book_appointment_success(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that book_appointment creates an appointment.
        
        Expected behavior:
        - Returns success=True
        - Appointment is created
        """
        next_monday = get_next_weekday(0)
        # Use timezone-aware datetime (10 AM Eastern)
        start_time = datetime.combine(next_monday, time(10, 0), tzinfo=EST)
        
        result = await handle_book_appointment(test_db, {
            "business_id": sample_business.id,
            "customer_email": "mcp@example.com",
            "start_time": start_time.isoformat(),
            "service_type": "mcp_test",
        })
        
        assert result["success"] is True
        assert result["appointment"] is not None

    @pytest.mark.asyncio
    async def test_book_appointment_invalid_time_format(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that invalid time format returns error.
        
        Expected behavior:
        - Returns error message for invalid time
        """
        result = await handle_book_appointment(test_db, {
            "business_id": sample_business.id,
            "customer_email": "test@example.com",
            "start_time": "not-a-valid-time",
            "service_type": "test",
        })
        
        assert "error" in result
        assert "Invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_book_appointment_with_optional_fields(
        self, test_db: AsyncSession, sample_business, sample_availability_rules
    ):
        """
        Verify that optional fields are handled.
        
        Expected behavior:
        - Notes, customer_name, customer_phone are included
        """
        next_monday = get_next_weekday(0)
        # Use timezone-aware datetime (11 AM Eastern)
        start_time = datetime.combine(next_monday, time(11, 0), tzinfo=EST)
        
        result = await handle_book_appointment(test_db, {
            "business_id": sample_business.id,
            "customer_email": "optional@example.com",
            "start_time": start_time.isoformat(),
            "service_type": "test",
            "notes": "Test notes",
            "customer_name": "Test Name",
            "customer_phone": "555-1234",
        })
        
        assert result["success"] is True


class TestHandleCancelAppointment:
    """Tests for handle_cancel_appointment function."""

    @pytest.mark.asyncio
    async def test_cancel_appointment_success(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that cancel_appointment cancels an appointment.
        
        Expected behavior:
        - Returns success=True
        - Appointment status is cancelled
        """
        result = await handle_cancel_appointment(test_db, {
            "appointment_id": sample_appointment.id,
        })
        
        assert result["success"] is True
        assert result["appointment"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_appointment_with_reason(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that cancellation reason is recorded.
        
        Expected behavior:
        - Reason is included in notes
        """
        result = await handle_cancel_appointment(test_db, {
            "appointment_id": sample_appointment.id,
            "reason": "Customer requested",
        })
        
        assert result["success"] is True
        assert "Customer requested" in result["appointment"]["notes"]

    @pytest.mark.asyncio
    async def test_cancel_appointment_not_found(self, test_db: AsyncSession):
        """
        Verify that cancelling non-existent appointment returns error.
        
        Expected behavior:
        - Returns success=False
        """
        result = await handle_cancel_appointment(test_db, {
            "appointment_id": 99999,
        })
        
        assert result["success"] is False


class TestHandleRescheduleAppointment:
    """Tests for handle_reschedule_appointment function."""

    @pytest.mark.asyncio
    async def test_reschedule_appointment_success(
        self, test_db: AsyncSession, sample_business, sample_availability_rules, sample_appointment: Appointment
    ):
        """
        Verify that reschedule_appointment updates appointment time.
        
        Expected behavior:
        - Returns success=True
        - Appointment time is updated
        """
        original_date = sample_appointment.start_time.date()
        new_time = datetime.combine(original_date, time(14, 0))
        
        result = await handle_reschedule_appointment(test_db, {
            "appointment_id": sample_appointment.id,
            "new_start_time": new_time.isoformat(),
        })
        
        assert result["success"] is True
        assert "14:00" in result["appointment"]["start_time"]

    @pytest.mark.asyncio
    async def test_reschedule_appointment_invalid_time(
        self, test_db: AsyncSession, sample_appointment: Appointment
    ):
        """
        Verify that invalid time format returns error.
        
        Expected behavior:
        - Returns error message
        """
        result = await handle_reschedule_appointment(test_db, {
            "appointment_id": sample_appointment.id,
            "new_start_time": "invalid-time",
        })
        
        assert "error" in result

    @pytest.mark.asyncio
    async def test_reschedule_appointment_not_found(self, test_db: AsyncSession):
        """
        Verify that rescheduling non-existent appointment returns error.
        
        Expected behavior:
        - Returns success=False
        """
        result = await handle_reschedule_appointment(test_db, {
            "appointment_id": 99999,
            "new_start_time": "2025-01-20T10:00:00",
        })
        
        assert result["success"] is False


class TestHandleGetDailySchedule:
    """Tests for handle_get_daily_schedule function."""

    @pytest.mark.asyncio
    async def test_get_daily_schedule_success(
        self, test_db: AsyncSession, sample_business, sample_appointment: Appointment
    ):
        """
        Verify that get_daily_schedule returns appointments.
        
        Expected behavior:
        - Returns appointments for the date
        """
        target_date = sample_appointment.start_time.date().isoformat()
        
        result = await handle_get_daily_schedule(test_db, {
            "business_id": sample_business.id,
            "date": target_date,
        })
        
        assert result["business_id"] == sample_business.id
        assert "appointments" in result

    @pytest.mark.asyncio
    async def test_get_daily_schedule_empty(
        self, test_db: AsyncSession, sample_business
    ):
        """
        Verify that empty schedule is returned for day with no appointments.
        
        Expected behavior:
        - Returns empty appointments list
        """
        result = await handle_get_daily_schedule(test_db, {
            "business_id": sample_business.id,
            "date": "2099-01-01",
        })
        
        assert result["appointments"] == []


class TestCallTool:
    """Tests for call_tool function."""

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self):
        """
        Verify that unknown tool returns error.
        
        Expected behavior:
        - Returns error message for unknown tool
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            result = await call_tool("unknown_tool", {})
            
            assert len(result) == 1
            content = json.loads(result[0].text)
            assert "error" in content
            assert "Unknown tool" in content["error"]

    @pytest.mark.asyncio
    async def test_call_tool_check_availability(self):
        """
        Verify that call_tool routes to check_availability handler.
        
        Expected behavior:
        - Returns result from check_availability handler
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_check_availability", new_callable=AsyncMock) as mock_handler:
                mock_handler.return_value = {"slots": [], "business_id": 1}
                
                result = await call_tool("check_availability", {
                    "business_id": 1,
                    "date": "2025-01-20",
                })
                
                mock_handler.assert_called_once()
                assert len(result) == 1

    @pytest.mark.asyncio
    async def test_call_tool_handles_exception(self):
        """
        Verify that exceptions are caught and returned as errors.
        
        Expected behavior:
        - Exception is caught
        - Error message is returned
        - Transaction is rolled back
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_check_availability", new_callable=AsyncMock) as mock_handler:
                mock_handler.side_effect = Exception("Test error")
                
                result = await call_tool("check_availability", {
                    "business_id": 1,
                    "date": "2025-01-20",
                })
                
                content = json.loads(result[0].text)
                assert "error" in content
                assert "Test error" in content["error"]
                mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_book_appointment(self):
        """
        Verify that call_tool routes to book_appointment handler.
        
        Expected behavior:
        - Returns result from book_appointment handler
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_book_appointment", new_callable=AsyncMock) as mock_handler:
                mock_handler.return_value = {"success": True, "appointment": {}}
                
                result = await call_tool("book_appointment", {
                    "business_id": 1,
                    "customer_email": "test@example.com",
                    "start_time": "2025-01-20T10:00:00",
                    "service_type": "test",
                })
                
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_cancel_appointment(self):
        """
        Verify that call_tool routes to cancel_appointment handler.
        
        Expected behavior:
        - Returns result from cancel_appointment handler
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_cancel_appointment", new_callable=AsyncMock) as mock_handler:
                mock_handler.return_value = {"success": True}
                
                result = await call_tool("cancel_appointment", {
                    "appointment_id": 1,
                })
                
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_reschedule_appointment(self):
        """
        Verify that call_tool routes to reschedule_appointment handler.
        
        Expected behavior:
        - Returns result from reschedule_appointment handler
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_reschedule_appointment", new_callable=AsyncMock) as mock_handler:
                mock_handler.return_value = {"success": True}
                
                result = await call_tool("reschedule_appointment", {
                    "appointment_id": 1,
                    "new_start_time": "2025-01-20T14:00:00",
                })
                
                mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_get_daily_schedule(self):
        """
        Verify that call_tool routes to get_daily_schedule handler.
        
        Expected behavior:
        - Returns result from get_daily_schedule handler
        """
        with patch("app.mcp.server.async_session_maker") as mock_session_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session_maker.return_value = mock_session
            
            with patch("app.mcp.server.handle_get_daily_schedule", new_callable=AsyncMock) as mock_handler:
                mock_handler.return_value = {"appointments": []}
                
                result = await call_tool("get_daily_schedule", {
                    "business_id": 1,
                    "date": "2025-01-20",
                })
                
                mock_handler.assert_called_once()
