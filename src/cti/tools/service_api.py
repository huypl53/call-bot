"""
Service API Tools
Tools for interacting with the Service API
"""

from typing import Any, Dict, Optional

import httpx

from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


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
                response = await client.get(
                    f"{settings.API_HOST}services",
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": "Lấy danh sách services thành công"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi lấy danh sách services: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi lấy danh sách services: {str(e)}"
            }

