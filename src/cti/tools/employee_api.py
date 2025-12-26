"""
Employee API Tools
Tools for interacting with the Employee API
"""

from typing import Any, Dict, Optional

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

# Language-specific employee API messages
EMPLOYEE_MESSAGES = {
    Language.VI: {
        "get_list_success": "Lấy danh sách employees thành công",
        "get_list_error": "Lỗi khi lấy danh sách employees: {error}",
        "get_available_success": "Lấy danh sách nhân viên rảnh thành công",
        "get_available_error": "Lỗi khi lấy danh sách nhân viên rảnh: {error}",
    },
    Language.EN: {
        "get_list_success": "Successfully retrieved employee list",
        "get_list_error": "Error retrieving employee list: {error}",
        "get_available_success": "Successfully retrieved available employees",
        "get_available_error": "Error retrieving available employees: {error}",
    },
    Language.JP: {
        "get_list_success": "従業員一覧の取得に成功しました",
        "get_list_error": "従業員一覧の取得中にエラーが発生しました: {error}",
        "get_available_success": "空きのある従業員一覧の取得に成功しました",
        "get_available_error": "空きのある従業員一覧の取得中にエラーが発生しました: {error}",
    },
}


def _get_employee_message(key: str, **kwargs) -> str:
    """Get employee message based on current language setting."""
    messages = EMPLOYEE_MESSAGES.get(settings.LANGUAGE, EMPLOYEE_MESSAGES[Language.EN])
    message = messages.get(key, "")
    if not message:
        # Fallback to English if key not found
        message = EMPLOYEE_MESSAGES[Language.EN].get(key, "")
    return message.format(**kwargs) if kwargs else message


class GetEmployeeListTool(BaseTool):
    """Tool để lấy danh sách employees"""

    @property
    def name(self) -> str:
        return "get_employee_list"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách employees với phân trang",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "description": "Số trang (mặc định: 1)",
                    },
                    "size": {
                        "type": "integer",
                        "description": "Số lượng items mỗi trang (mặc định: 5)",
                    },
                },
                "required": [],
            },
        }

    async def execute(
        self,
        session_manager: SessionManager,
        page: Optional[int] = None,
        size: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute get employee list"""
        try:
            params = {}
            if page is not None:
                params["page"] = page
            if size is not None:
                params["size"] = size

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}employees",
                    client=client,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_employee_message("get_list_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_employee_message(
                    "get_list_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_employee_message("get_list_error", error=str(e)),
            }


class GetAvailableEmployeesTool(BaseTool):
    """Tool để lấy danh sách nhân viên đang rảnh trong khoảng thời gian"""

    @property
    def name(self) -> str:
        return "get_available_employees"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách nhân viên đang rảnh trong khoảng thời gian mong muốn",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "integer",
                        "description": "Số trang (mặc định: 1)",
                    },
                    "size": {
                        "type": "integer",
                        "description": "Số lượng items mỗi trang (mặc định: 5)",
                    },
                    # "employeeName": {
                    #     "type": "string",
                    #     "description": "Lọc theo tên nhân viên (tùy chọn)",
                    # },
                    "employeeId": {
                        "type": "string",
                        "description": "Lọc theo ID nhân viên, lấy `employeeId` từ `get_employee_list()`",
                    },
                    "startTime": {
                        "type": "string",
                        "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm)",
                    },
                    "endTime": {
                        "type": "string",
                        "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm)",
                    },
                },
                "required": ["startTime", "endTime", "employeeId"],
            },
        }

    async def execute(
        self,
        session_manager: SessionManager,
        page: Optional[int] = None,
        size: Optional[int] = None,
        employeeName: Optional[str] = None,
        employeeId: Optional[str] = None,
        startTime: Optional[str] = None,
        endTime: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute get available employees"""
        try:
            params: Dict[str, Any] = {}
            if page is not None:
                params["page"] = page
            if size is not None:
                params["size"] = size
            if employeeName:
                params["employeeName"] = employeeName
            if employeeId:
                params["employeeId"] = employeeId
            if startTime:
                params["startTime"] = startTime
            if endTime:
                params["endTime"] = endTime

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}employees/availables",
                    client=client,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_employee_message("get_available_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_employee_message(
                    "get_available_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_employee_message("get_available_error", error=str(e)),
            }
