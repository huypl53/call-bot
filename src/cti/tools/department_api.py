"""
Department API Tools
"""

from typing import Any, Dict, Optional

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

DEPARTMENT_MESSAGES = {
    Language.VI: {
        "get_list_success": "Lấy danh sách chi nhánh/phòng ban thành công",
        "get_list_error": "Lỗi khi lấy danh sách chi nhánh/phòng ban: {error}",
    },
    Language.EN: {
        "get_list_success": "Successfully retrieved department list",
        "get_list_error": "Error retrieving department list: {error}",
    },
    Language.JP: {
        "get_list_success": "部署一覧の取得に成功しました",
        "get_list_error": "部署一覧の取得中にエラーが発生しました: {error}",
    },
}


def _get_department_message(key: str, **kwargs) -> str:
    messages = DEPARTMENT_MESSAGES.get(settings.LANGUAGE, DEPARTMENT_MESSAGES[Language.EN])
    message = messages.get(key, "")
    if not message:
        message = DEPARTMENT_MESSAGES[Language.EN].get(key, "")
    return message.format(**kwargs) if kwargs else message


class GetDepartmentListTool(BaseTool):
    """Tool để lấy danh sách departments"""

    @property
    def name(self) -> str:
        return "get_department_list"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách chi nhánh/phòng ban với phân trang",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Số trang (mặc định: 1)"},
                    "size": {"type": "integer", "description": "Số lượng items mỗi trang (mặc định: 0 nghĩa là tất cả)"},
                    "name": {"type": "string", "description": "Tên phòng ban (tùy chọn)"},
                    "address": {"type": "string", "description": "Địa chỉ (tùy chọn)"}
                },
                "required": []
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        page: Optional[int] = None,
        size: Optional[int] = None,
        name: Optional[str] = None,
        address: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            params: Dict[str, Any] = {}
            if page is not None:
                params["page"] = page
            if size is not None:
                params["size"] = size
            if name:
                params["name"] = name
            if address is not None:
                params["address"] = address

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}departments",
                    client=client,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_department_message("get_list_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_department_message("get_list_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_department_message("get_list_error", error=str(e))
            }
