"""
Booking API Tools
Tools for interacting with the Booking API
"""

import logging
from typing import Any, Dict, Optional, TypedDict

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Language-specific booking API messages
BOOKING_MESSAGES = {
    Language.VI: {
        "get_list_success": "Lấy danh sách bookings thành công",
        "get_list_error": "Lỗi khi lấy danh sách bookings: {error}",
        "get_detail_success": "Lấy chi tiết booking thành công",
        "get_detail_error": "Lỗi khi lấy chi tiết booking: {error}",
        "check_availability_success": "Kiểm tra booking availability thành công",
        "check_availability_error": "Lỗi khi kiểm tra booking availability: {error}",
        "create_success": "Tạo booking thành công",
        "create_error": "Lỗi khi tạo booking: {error}",
        "update_status_success": "Cập nhật trạng thái booking thành công: {status}",
        "update_status_error": "Lỗi khi cập nhật trạng thái booking: {error}",
        "get_calendar_success": "Lấy lịch đặt phòng theo ngày thành công",
        "get_calendar_error": "Lỗi khi lấy lịch đặt phòng: {error}",
    },
    Language.EN: {
        "get_list_success": "Successfully retrieved booking list",
        "get_list_error": "Error retrieving booking list: {error}",
        "get_detail_success": "Successfully retrieved booking details",
        "get_detail_error": "Error retrieving booking details: {error}",
        "check_availability_success": "Successfully checked booking availability",
        "check_availability_error": "Error checking booking availability: {error}",
        "create_success": "Successfully created booking",
        "create_error": "Error creating booking: {error}",
        "update_status_success": "Successfully updated booking status: {status}",
        "update_status_error": "Error updating booking status: {error}",
        "get_calendar_success": "Successfully retrieved booking calendar",
        "get_calendar_error": "Error retrieving booking calendar: {error}",
    },
    Language.JP: {
        "get_list_success": "予約一覧の取得に成功しました",
        "get_list_error": "予約一覧の取得中にエラーが発生しました: {error}",
        "get_detail_success": "予約詳細の取得に成功しました",
        "get_detail_error": "予約詳細の取得中にエラーが発生しました: {error}",
        "check_availability_success": "予約の空き状況確認に成功しました",
        "check_availability_error": "予約の空き状況確認中にエラーが発生しました: {error}",
        "create_success": "予約の作成に成功しました",
        "create_error": "予約の作成中にエラーが発生しました: {error}",
        "update_status_success": "予約ステータスの更新に成功しました: {status}",
        "update_status_error": "予約ステータスの更新中にエラーが発生しました: {error}",
        "get_calendar_success": "予約カレンダーの取得に成功しました",
        "get_calendar_error": "予約カレンダーの取得中にエラーが発生しました: {error}",
    },
}


def _get_booking_message(key: str, **kwargs) -> str:
    """Get booking message based on current language setting."""
    messages = BOOKING_MESSAGES.get(settings.LANGUAGE, BOOKING_MESSAGES[Language.EN])
    message = messages.get(key, "")
    if not message:
        # Fallback to English if key not found
        message = BOOKING_MESSAGES[Language.EN].get(key, "")
    return message.format(**kwargs) if kwargs else message


class BookingInfoDict(TypedDict, total=False):
    """TypedDict for bookingInfo in CreateBookingTool"""
    serviceId: str
    employeeId: str
    startTime: str
    endTime: str
    notes: Optional[str]


class CustomerInfoDict(TypedDict, total=False):
    """TypedDict for customerInfo in CreateBookingTool"""
    id: Optional[str]
    name: Optional[str]
    furiganaName: str
    age: Optional[str]
    gender: Optional[str]
    phoneNumber: Optional[str]
    firstContactSource: Optional[str]
    category: Optional[str]
    note: Optional[str]


class GetBookingListTool(BaseTool):
    """Tool để lấy danh sách bookings"""

    @property
    def name(self) -> str:
        return "get_booking_list"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy danh sách bookings với phân trang và các bộ lọc tùy chọn",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "description": "Số trang (mặc định: 1)"},
                    "size": {"type": "integer", "description": "Số lượng items mỗi trang (mặc định: 5)"},
                    "startTime": {"type": "string", "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"},
                    "endTime": {"type": "string", "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)"},
                    "employeeId": {"type": "string", "description": "ID của nhân viên"},
                    "employeeName": {"type": "string", "description": "Tên nhân viên"}
                },
                "required": []
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        page: Optional[int] = None,
        size: Optional[int] = None,
        startTime: Optional[str] = None,
        endTime: Optional[str] = None,
        employeeId: Optional[str] = None,
        employeeName: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute get booking list"""
        try:
            params = {}
            if page is not None:
                params["page"] = page
            if size is not None:
                params["size"] = size
            if startTime:
                params["startTime"] = startTime
            if endTime:
                params["endTime"] = endTime
            if employeeId:
                params["employeeId"] = employeeId
            if employeeName:
                params["employeeName"] = employeeName

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}bookings",
                    client=client,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_list_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("get_list_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_list_error", error=str(e))
            }


class GetBookingDetailTool(BaseTool):
    """Tool để lấy chi tiết booking"""

    @property
    def name(self) -> str:
        return "get_booking_detail"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy chi tiết booking theo ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID của booking"}
                },
                "required": ["id"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute get booking detail"""
        try:
            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}bookings/{id}",
                    client=client,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_detail_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("get_detail_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_detail_error", error=str(e))
            }


class CheckBookingAvailabilityTool(BaseTool):
    """Tool để kiểm tra booking có sẵn không"""

    @property
    def name(self) -> str:
        return "check_booking_availability"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Kiểm tra booking có sẵn trong khoảng thời gian",
            "parameters": {
                "type": "object",
                "properties": {
                    "startTime": {
                        "type": "string",
                        "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm hoặc YYYY-MM-DD HH:mm:ss)"
                    },
                    "endTime": {
                        "type": "string",
                        "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm hoặc YYYY-MM-DD HH:mm:ss)"
                    },
                    "employeeId": {"type": "string", "description": "ID của nhân viên (tùy chọn)"},
                    "employeeName": {"type": "string", "description": "Tên nhân viên (tùy chọn)"}
                },
                "required": ["startTime", "endTime"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        startTime: str,
        endTime: str,
        employeeId: Optional[str] = None,
        employeeName: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute check booking availability"""
        try:
            params = {
                "startTime": startTime,
                "endTime": endTime
            }
            if employeeId:
                params["employeeId"] = employeeId
            if employeeName:
                params["employeeName"] = employeeName

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}employees/availables",
                    client=client,
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("check_availability_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("check_availability_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("check_availability_error", error=str(e))
            }


class CreateBookingTool(BaseTool):
    """Tool để tạo booking mới"""

    @property
    def name(self) -> str:
        return "create_booking"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Tạo booking mới với thông tin khách hàng và booking",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Nguồn booking (ví dụ: 'phone')"},
                    # "twilioCallSid": {"type": "string", "description": "Twilio Call SID"},
                    "startTime": {"type": "string", "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"},
                    "endTime": {"type": "string", "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)"},
                    "serviceId": {"type": "string", "description": "ID của service"},
                    "employeeId": {"type": "string", "description": "ID của nhân viên"},
                    # "bookingStartTime": {"type": "string", "description": "Thời gian bắt đầu booking (format: YYYY-MM-DD HH:mm:ss)"},
                    "notes": {"type": "string", "description": "Ghi chú"},
                    "customerId": {"type": "string", "description": "ID khách hàng (tùy chọn)"},
                    "customerName": {"type": "string", "description": "Tên khách hàng (tùy chọn)"},
                    "furiganaName": {"type": "string", "description": "Tên furigana"},
                    "customerAge": {"type": "integer", "description": "Tuổi khách hàng (tùy chọn)"},
                    "customerGender": {"type": "string", "description": "Giới tính khách hàng (tùy chọn)"},
                    "phoneNumber": {"type": "string", "description": "Số điện thoại (tùy chọn)"},
                    "category": {"type": "string", "description": "Nhóm khách hàng (tùy chọn)"},
                    "note": {"type": "string", "description": "Ghi chú cho khách hàng (tùy chọn)"},
                    # "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên (tùy chọn)"}
                },
                "required": ["source", "startTime", "endTime", "serviceId", "employeeId"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        # twilioCallSid: str,
        startTime: str,
        endTime: str,
        serviceId: str,
        employeeId: str,
        # bookingStartTime: str,
        furiganaName: Optional[str] = None,
        source: str = 'phone',
        notes: Optional[str] = None,
        customerId: Optional[str] = None,
        customerName: Optional[str] = None,
        customerAge: Optional[int] = None,
        customerGender: Optional[str] = None,
        phoneNumber: Optional[str] = None,
        firstContactSource: Optional[str] = None,
        category: Optional[str] = None,
        note: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute create booking"""
        try:
            booking_info: BookingInfoDict = {
                "serviceId": serviceId,
                "employeeId": employeeId,
                "startTime": startTime,
                "endTime": endTime
            }
            if notes:
                booking_info["notes"] = notes

            customer_info: CustomerInfoDict = {
                "furiganaName": furiganaName
            }
            if customerId:
                customer_info["id"] = customerId
            if customerName:
                customer_info["name"] = customerName
            if customerAge:
                customer_info["age"] = customerAge
            if customerGender:
                customer_info["gender"] = customerGender
            if phoneNumber:
                customer_info["phoneNumber"] = phoneNumber
            if firstContactSource:
                customer_info["firstContactSource"] = firstContactSource
            if category:
                customer_info["category"] = category
            if note:
                customer_info["note"] = note

            payload = {
                "source": source,
                "twilioCallSid": session_manager.stream_sid,
                # "startTime": startTime,
                "bookingInfo": booking_info,
                "customerInfo": customer_info
            }
            
            # logger.info(f"Payload for create booking: {payload}")

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "POST",
                    f"{settings.API_HOST}bookings",
                    client=client,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("create_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("create_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("create_error", error=str(e))
            }


class UpdateBookingStatusTool(BaseTool):
    """Tool để cập nhật trạng thái booking"""

    @property
    def name(self) -> str:
        return "update_booking_status"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Cập nhật trạng thái booking (ví dụ: confirmed, cancelled)",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "ID của booking"},
                    "status": {"type": "string", "description": "Trạng thái mới (ví dụ: 'confirmed', 'cancelled')"}
                },
                "required": ["id", "status"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        id: str,
        status: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute update booking status"""
        try:
            payload = {"status": status}

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "PATCH",
                    f"{settings.API_HOST}bookings/{id}",
                    client=client,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("update_status_success", status=status)
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("update_status_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("update_status_error", error=str(e))
            }


class GetBookingCalendarTool(BaseTool):
    """Tool để lấy lịch booking theo ngày"""

    @property
    def name(self) -> str:
        return "get_booking_calendar"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy thông tin lịch đặt phòng cho một ngày cụ thể",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Ngày cần xem lịch (format: YYYY-MM-DD)"
                    }
                },
                "required": ["date"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        date: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute get booking calendar"""
        try:
            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}bookings/calendar",
                    client=client,
                    params={"date": date},
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_calendar_success")
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message("get_calendar_error", error=e.response.status_code)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_calendar_error", error=str(e))
            }
