"""
Service API Tools
Tools for interacting with the Service API
"""

from typing import Any, Dict, Optional

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

# Language-specific service API messages
SERVICE_MESSAGES = {
    Language.VI: {
        "get_list_success": "Lấy danh sách services thành công",
        "get_list_error": "Lỗi khi lấy danh sách services: {error}",
    },
    Language.EN: {
        "get_list_success": "Successfully retrieved service list",
        "get_list_error": "Error retrieving service list: {error}",
    },
    Language.JP: {
        "get_list_success": "サービス一覧の取得に成功しました",
        "get_list_error": "サービス一覧の取得中にエラーが発生しました: {error}",
    },
}


def _get_service_message(key: str, **kwargs) -> str:
    """Get service message based on current language setting."""
    messages = SERVICE_MESSAGES.get(settings.LANGUAGE, SERVICE_MESSAGES[Language.EN])
    message = messages.get(key, "")
    if not message:
        # Fallback to English if key not found
        message = SERVICE_MESSAGES[Language.EN].get(key, "")
    return message.format(**kwargs) if kwargs else message


class GetServiceListTool(BaseTool):
    """Tool để lấy danh sách services"""

    @property
    def name(self) -> str:
        return "get_service_list"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách services với phân trang",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Số trang (mặc định: 1)"},
                    "size": {"type": "integer", "description": "Số lượng items mỗi trang (mặc định: 5)"}
                },
                "required": []
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        page: Optional[int] = None,
        size: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute get service list"""
        try:
            params = {}
            if page is not None:
                params["page"] = page
            if size is not None:
                params["size"] = size

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}services",
                    client=client,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_service_message("get_list_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_service_message("get_list_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_service_message("get_list_error", error=str(e))
            }

