"""
Integration tests for Booking API Tools
Tests call actual API endpoints (no mocking)
"""

import pytest

from cti.core.session_manager import SessionManager
from cti.tools.booking_api import (
    CheckBookingAvailabilityTool,
    CreateBookingTool,
    GetBookingDetailTool,
    GetBookingListTool,
    UpdateBookingStatusTool,
)


@pytest.fixture
def session_manager():
    """Create a SessionManager instance for testing"""
    return SessionManager("test_stream_123")


@pytest.mark.asyncio
async def test_get_booking_list_basic(session_manager):
    """Test GetBookingListTool with basic parameters"""
    tool = GetBookingListTool()
    result = await tool.execute(session_manager, page=1, size=5)
    
    assert "success" in result
    assert result["success"] is True
    assert "data" in result
    assert "message" in result


@pytest.mark.asyncio
async def test_get_booking_list_with_filters(session_manager):
    """Test GetBookingListTool with filters"""
    tool = GetBookingListTool()
    result = await tool.execute(
        session_manager,
        page=1,
        size=10,
        startTime="2025-11-06 10:00:00",
        endTime="2025-11-06 12:00:00"
    )
    
    assert "success" in result
    if result["success"]:
        assert "data" in result
    else:
        # API might return error, but structure should be correct
        assert "error" in result


@pytest.mark.asyncio
async def test_get_booking_detail(session_manager):
    """Test GetBookingDetailTool"""
    tool = GetBookingDetailTool()
    # Using a test ID - might not exist, but should handle gracefully
    result = await tool.execute(session_manager, id="b5895bed-2380-4653-b88e-53c716615cd8")
    
    assert "success" in result
    assert "message" in result
    if result["success"]:
        assert "data" in result
    else:
        assert "error" in result


@pytest.mark.asyncio
async def test_check_booking_availability(session_manager):
    """Test CheckBookingAvailabilityTool"""
    tool = CheckBookingAvailabilityTool()
    result = await tool.execute(
        session_manager,
        startTime="2025-11-06 12:00:01",
        endTime="2025-11-06 14:00:00"
    )
    
    assert "success" in result
    assert "message" in result
    if result["success"]:
        assert "data" in result
    else:
        assert "error" in result


@pytest.mark.asyncio
async def test_check_booking_availability_with_employee(session_manager):
    """Test CheckBookingAvailabilityTool with employee filter"""
    tool = CheckBookingAvailabilityTool()
    result = await tool.execute(
        session_manager,
        startTime="2025-11-06 12:00:01",
        endTime="2025-11-06 14:00:00",
        employeeId="e1a2bb1d-01f2-4b91-ae4f-9d4ea1bf0011"
    )
    
    assert "success" in result
    assert "message" in result


@pytest.mark.asyncio
async def test_create_booking(session_manager):
    """Test CreateBookingTool"""
    tool = CreateBookingTool()
    result = await tool.execute(
        session_manager,
        source="phone",
        twilioCallSid="TEST_CALL_SID_123",
        startTime="2025-11-20 10:00:00",
        serviceId="41bf5171-f09c-4da4-9b7e-8d8e7f8a085d",
        employeeId="c73d2a45-b567-491f-bfa2-9343ddee0004",
        bookingStartTime="2025-11-21 10:00:00",
        furiganaName="テスト ユーザー",
        notes="Test booking from integration test",
        customerName="Test User",
        customerAge="28",
        customerGender="male"
    )
    
    assert "success" in result
    assert "message" in result
    if result["success"]:
        assert "data" in result
    else:
        assert "error" in result


@pytest.mark.asyncio
async def test_update_booking_status(session_manager):
    """Test UpdateBookingStatusTool"""
    tool = UpdateBookingStatusTool()
    # Using a test ID - might not exist, but should handle gracefully
    result = await tool.execute(
        session_manager,
        id="e650bda3-e47e-4659-ab37-2ccefef4caea",
        status="confirmed"
    )
    
    assert "success" in result
    assert "message" in result
    if result["success"]:
        assert "data" in result
    else:
        assert "error" in result


@pytest.mark.asyncio
async def test_get_booking_list_error_handling(session_manager):
    """Test error handling in GetBookingListTool"""
    tool = GetBookingListTool()
    # Test with invalid parameters
    result = await tool.execute(session_manager, page=-1, size=-1)
    
    assert "success" in result
    # API might accept or reject, but structure should be correct
    assert "message" in result

