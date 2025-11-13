"""
Service API Tools
Tools for interacting with the Service API
"""

from typing import Annotated, Any, Dict, Optional

import httpx

from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class GetServiceListTool(BaseTool):
    """Tool để lấy danh sách services với phân trang"""

    @property
    def name(self) -> str:
        return "get_service_list"

    async def execute(
        self,
        session_manager: SessionManager,
        page: Annotated[Optional[int], "Số trang (mặc định: 1)"] = None,
        size: Annotated[Optional[int], "Số lượng items mỗi trang (mặc định: 5)"] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Lấy danh sách services với phân trang"""
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

