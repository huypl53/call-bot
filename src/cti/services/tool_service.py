"""
Tool Service - Registry và execution cho tools
"""

from typing import Any, Dict, List

from cti.tools.base import BaseTool
from cti.tools.booking_api import (
    CheckBookingAvailabilityTool,
    CreateBookingTool,
    GetBookingDetailTool,
    GetBookingListTool,
    UpdateBookingStatusTool,
)
from cti.tools.booking_saver import BookingSaverTool
from cti.tools.employee_api import GetEmployeeListTool
from cti.tools.room_checker import RoomCheckerTool
from cti.tools.service_api import GetServiceListTool
from cti.tools.summary_getter import SummaryGetterTool


class ToolService:
    """
    Service quản lý và execute tools.
    Sử dụng Registry pattern để dễ dàng thêm tools mới.
    """

    def __init__(self):
        # Registry of available tools
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register các tools mặc định"""
        tools = [
            # RoomCheckerTool(),
            # BookingSaverTool(),
            SummaryGetterTool(),
            GetBookingListTool(),
            GetBookingDetailTool(),
            CheckBookingAvailabilityTool(),
            CreateBookingTool(),
            UpdateBookingStatusTool(),
            GetEmployeeListTool(),
            GetServiceListTool(),
        ]
        for tool in tools:
            self.register_tool(tool)

    def register_tool(self, tool: BaseTool):
        """
        Đăng ký một tool mới.

        Args:
            tool: Instance của BaseTool
        """
        self._tools[tool.name] = tool
        print(f"✓ Registered tool: {tool.name}")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Lấy definitions của tất cả tools cho OpenAI.

        Returns:
            List of tool definitions
        """
        return [tool.get_definition() for tool in self._tools.values()]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_manager: Any
    ) -> Dict[str, Any]:
        """
        Execute một tool với arguments.

        Args:
            tool_name: Tên tool cần execute
            arguments: Arguments từ OpenAI
            session_manager: Session manager instance

        Returns:
            Result từ tool execution

        Raises:
            ValueError: Nếu tool không tồn tại
        """
        if tool_name not in self._tools:
            return {
                "error": f"Unknown tool: {tool_name}",
                "success": False
            }

        try:
            tool = self._tools[tool_name]
            # Pass session_manager to tool
            result = await tool.execute(session_manager=session_manager, **arguments)
            return result
        except Exception as e:
            return {
                "error": f"Error executing tool {tool_name}: {str(e)}",
                "success": False
            }

    def get_tool(self, tool_name: str) -> BaseTool:
        """Get tool instance by name"""
        return self._tools.get(tool_name)

    @property
    def available_tools(self) -> List[str]:
        """List of available tool names"""
        return list(self._tools.keys())
