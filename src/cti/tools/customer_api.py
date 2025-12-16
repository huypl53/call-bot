"""
Customer API Tools
Tools for interacting with the Customer API
"""

from typing import Any, Dict, Optional

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

CUSTOMER_MESSAGES = {
    Language.VI: {
        "get_list_success": "Lấy danh sách khách hàng thành công",
        "get_list_error": "Lỗi khi lấy danh sách khách hàng: {error}",
        "create_success": "Tạo khách hàng mới thành công",
        "create_error": "Lỗi khi tạo khách hàng: {error}",
        "update_success": "Cập nhật khách hàng thành công",
        "update_error": "Lỗi khi cập nhật khách hàng: {error}",
        "delete_success": "Xóa khách hàng thành công",
        "delete_error": "Lỗi khi xóa khách hàng: {error}",
    },
    Language.EN: {
        "get_list_success": "Successfully retrieved customer list",
        "get_list_error": "Error retrieving customer list: {error}",
        "create_success": "Successfully created customer",
        "create_error": "Error creating customer: {error}",
        "update_success": "Successfully updated customer",
        "update_error": "Error updating customer: {error}",
        "delete_success": "Successfully deleted customer",
        "delete_error": "Error deleting customer: {error}",
    },
    Language.JP: {
        "get_list_success": "顧客一覧の取得に成功しました",
        "get_list_error": "顧客一覧の取得中にエラーが発生しました: {error}",
        "create_success": "顧客の作成に成功しました",
        "create_error": "顧客の作成中にエラーが発生しました: {error}",
        "update_success": "顧客の更新に成功しました",
        "update_error": "顧客の更新中にエラーが発生しました: {error}",
        "delete_success": "顧客の削除に成功しました",
        "delete_error": "顧客の削除中にエラーが発生しました: {error}",
    },
}


def _get_customer_message(key: str, **kwargs) -> str:
    messages = CUSTOMER_MESSAGES.get(settings.LANGUAGE, CUSTOMER_MESSAGES[Language.EN])
    message = messages.get(key, "")
    if not message:
        message = CUSTOMER_MESSAGES[Language.EN].get(key, "")
    return message.format(**kwargs) if kwargs else message


class GetCustomerListTool(BaseTool):
    """Tool để lấy danh sách khách hàng"""

    @property
    def name(self) -> str:
        return "get_customer_list"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách khách hàng với bộ lọc tùy chọn",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Số trang (mặc định: 1)"},
                    "size": {"type": "integer", "description": "Số lượng items mỗi trang (mặc định: 10)"},
                    "name": {"type": "string", "description": "Lọc theo tên khách hàng (tùy chọn)"},
                    "phoneNumber": {"type": "string", "description": "Lọc theo số điện thoại (tùy chọn)"},
                    "category": {"type": "string", "description": "Lọc theo nhóm khách hàng (tùy chọn)"},
                    "code": {"type": "string", "description": "Lọc theo mã khách hàng (tùy chọn)"},
                    "gender": {"type": "string", "description": "Lọc theo giới tính (tùy chọn)"},
                    "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên (tùy chọn)"},
                    "ageFrom": {"type": "integer", "description": "Độ tuổi từ"},
                    "ageTo": {"type": "integer", "description": "Độ tuổi đến"},
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
        phoneNumber: Optional[str] = None,
        category: Optional[str] = None,
        code: Optional[str] = None,
        gender: Optional[str] = None,
        firstContactSource: Optional[str] = None,
        ageFrom: Optional[int] = None,
        ageTo: Optional[int] = None,
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
            if phoneNumber:
                params["phoneNumber"] = phoneNumber
            if category:
                params["category"] = category
            if code:
                params["code"] = code
            if gender:
                params["gender"] = gender
            if firstContactSource:
                params["firstContactSource"] = firstContactSource
            if ageFrom is not None:
                params["ageFrom"] = ageFrom
            if ageTo is not None:
                params["ageTo"] = ageTo

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}customers",
                    client=client,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_customer_message("get_list_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_customer_message("get_list_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_customer_message("get_list_error", error=str(e))
            }


class CreateCustomerTool(BaseTool):
    """Tool để tạo khách hàng mới"""

    @property
    def name(self) -> str:
        return "create_customer"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Tạo khách hàng mới",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên khách hàng"},
                    "furiganaName": {"type": "string", "description": "Tên furigana"},
                    "phoneNumber": {"type": "string", "description": "Số điện thoại"},
                    "age": {"type": "integer", "description": "Tuổi khách hàng"},
                    "gender": {"type": "string", "description": "Giới tính khách hàng"},
                    "category": {"type": "string", "description": "Nhóm khách hàng (ví dụ: 'new', 'VIP')"},
                    "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên (tùy chọn)"},
                    "note": {"type": "string", "description": "Ghi chú thêm (tùy chọn)"},
                },
                "required": ["name", "furiganaName", "phoneNumber", "age", "gender", "category"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        name: str,
        furiganaName: str,
        phoneNumber: str,
        age: int,
        gender: str,
        category: str,
        firstContactSource: Optional[str] = None,
        note: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            payload = {
                "name": name,
                "furiganaName": furiganaName,
                "phoneNumber": phoneNumber,
                "age": age,
                "gender": gender,
                "category": category
            }
            if firstContactSource:
                payload["firstContactSource"] = firstContactSource
            if note:
                payload["note"] = note

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "POST",
                    f"{settings.API_HOST}customers",
                    client=client,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_customer_message("create_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_customer_message("create_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_customer_message("create_error", error=str(e))
            }


class UpdateCustomerTool(BaseTool):
    """Tool để cập nhật khách hàng"""

    @property
    def name(self) -> str:
        return "update_customer"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Cập nhật thông tin khách hàng hiện có",
            "parameters": {
                "type": "object",
                "properties": {
                    "customerId": {"type": "string", "description": "ID khách hàng cần cập nhật"},
                    "name": {"type": "string", "description": "Tên khách hàng"},
                    "furiganaName": {"type": "string", "description": "Tên furigana"},
                    "phoneNumber": {"type": "string", "description": "Số điện thoại"},
                    "age": {"type": "integer", "description": "Tuổi khách hàng"},
                    "gender": {"type": "string", "description": "Giới tính khách hàng"},
                    "category": {"type": "string", "description": "Nhóm khách hàng"},
                    "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên"},
                    "note": {"type": "string", "description": "Ghi chú thêm"},
                },
                "required": ["customerId"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        customerId: str,
        name: Optional[str] = None,
        furiganaName: Optional[str] = None,
        phoneNumber: Optional[str] = None,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        category: Optional[str] = None,
        firstContactSource: Optional[str] = None,
        note: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            payload: Dict[str, Any] = {}
            if name:
                payload["name"] = name
            if furiganaName:
                payload["furiganaName"] = furiganaName
            if phoneNumber:
                payload["phoneNumber"] = phoneNumber
            if age is not None:
                payload["age"] = age
            if gender:
                payload["gender"] = gender
            if category:
                payload["category"] = category
            if firstContactSource:
                payload["firstContactSource"] = firstContactSource
            if note:
                payload["note"] = note

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "PATCH",
                    f"{settings.API_HOST}customers/{customerId}",
                    client=client,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_customer_message("update_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_customer_message("update_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_customer_message("update_error", error=str(e))
            }


class DeleteCustomerTool(BaseTool):
    """Tool để xóa khách hàng"""

    @property
    def name(self) -> str:
        return "delete_customer"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Xóa một khách hàng theo ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "customerId": {"type": "string", "description": "ID khách hàng cần xóa"}
                },
                "required": ["customerId"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        customerId: str,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "DELETE",
                    f"{settings.API_HOST}customers/{customerId}",
                    client=client,
                    timeout=30.0
                )
                response.raise_for_status()

            return {
                "success": True,
                "data": None,
                "message": _get_customer_message("delete_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_customer_message("delete_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_customer_message("delete_error", error=str(e))
            }
