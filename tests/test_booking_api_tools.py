import pytest

from cti.core.session_manager import SessionManager
from cti.tools.booking_api import CreateBookingTool


@pytest.mark.asyncio
async def test_create_booking_definition_includes_required_fields():
    tool = CreateBookingTool()
    definition = tool.get_definition()

    assert definition["name"] == "create_booking"
    required_fields = definition["parameters"]["required"]
    for field in ["source", "startTime", "endTime", "serviceId", "employeeId", "customerName"]:
        assert field in required_fields


@pytest.mark.asyncio
async def test_create_booking_execute_returns_success(monkeypatch):
    tool = CreateBookingTool()
    session_manager = SessionManager("test_stream_123")

    class FakeResponse:
        def __init__(self):
            self.content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "booking-123"}

    async def fake_logged_request(method, url, client, json, timeout):
        return FakeResponse()

    monkeypatch.setattr("cti.tools.booking_api.logged_request", fake_logged_request)

    result = await tool.execute(
        session_manager,
        startTime="2025-11-20 10:00:00",
        endTime="2025-11-20 11:00:00",
        serviceId="service-1",
        employeeId="employee-1",
        customerName="Test User",
    )

    assert result["success"] is True
    assert result["data"] == {"id": "booking-123"}
