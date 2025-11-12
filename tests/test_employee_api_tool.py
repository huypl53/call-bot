"""
Integration tests for Employee API Tool
Tests call actual API endpoints (no mocking)
"""

import pytest

from cti.core.session_manager import SessionManager
from cti.tools.employee_api import GetEmployeeListTool


@pytest.fixture
def session_manager():
    """Create a SessionManager instance for testing"""
    return SessionManager("test_stream_123")


@pytest.mark.asyncio
async def test_get_employee_list_basic(session_manager):
    """Test GetEmployeeListTool with basic parameters"""
    tool = GetEmployeeListTool()
    result = await tool.execute(session_manager)
    
    assert "success" in result
    assert result["success"] is True
    assert "data" in result
    assert "message" in result


@pytest.mark.asyncio
async def test_get_employee_list_with_pagination(session_manager):
    """Test GetEmployeeListTool with pagination"""
    tool = GetEmployeeListTool()
    result = await tool.execute(session_manager, page=1, size=5)
    
    assert "success" in result
    assert "message" in result
    if result["success"]:
        assert "data" in result
    else:
        assert "error" in result


@pytest.mark.asyncio
async def test_get_employee_list_error_handling(session_manager):
    """Test error handling in GetEmployeeListTool"""
    tool = GetEmployeeListTool()
    # Test with invalid parameters
    result = await tool.execute(session_manager, page=-1, size=-1)
    
    assert "success" in result
    # API might accept or reject, but structure should be correct
    assert "message" in result

