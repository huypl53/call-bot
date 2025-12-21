"""
Booking API Tools
Tools for interacting with the Booking API
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

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
    notes: Optional[str]
    storeName: Optional[str]
    extensionMinutes: Optional[int]
    meetingPoint: Optional[str]
    departmentId: Optional[str]
    room: Optional[str]
    options: Optional[List[str]]
    driverDropoff: Optional[str]
    driverPickup: Optional[str]


class CustomerInfoDict(TypedDict, total=False):
    """TypedDict for customerInfo in CreateBookingTool"""

    id: Optional[str]
    name: Optional[str]
    furiganaName: str
    age: Optional[int]
    gender: Optional[str]
    phoneNumber: Optional[str]
    firstContactSource: Optional[str]
    category: Optional[str]
    note: Optional[str]


class PaymentInfoDict(TypedDict, total=False):
    """TypedDict for paymentInfo in CreateBookingTool"""

    paymentMethod: Optional[str]
    totalFee: Optional[float]
    changePrepared: Optional[float]
    cashReceivedCustomer: Optional[float]
    cashReceivedStaff: Optional[float]
    discount: Optional[float]
    finalPayment: Optional[float]
    travelFee: Optional[float]
    receivedBy: Optional[str]


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
                    "page": {
                        "type": "integer",
                        "description": "Số trang (mặc định: 1)",
                    },
                    "size": {
                        "type": "integer",
                        "description": "Số lượng items mỗi trang (mặc định: 5)",
                    },
                    "startTime": {
                        "type": "string",
                        "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)",
                    },
                    "endTime": {
                        "type": "string",
                        "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)",
                    },
                    "employeeId": {"type": "string", "description": "ID của nhân viên"},
                    "employeeName": {"type": "string", "description": "Tên nhân viên"},
                },
                "required": [],
            },
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
        **kwargs,
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
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_list_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message(
                    "get_list_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_list_error", error=str(e)),
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
                "required": ["id"],
            },
        }

    async def execute(
        self, session_manager: SessionManager, id: str, **kwargs
    ) -> Dict[str, Any]:
        """Execute get booking detail"""
        try:
            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}bookings/{id}",
                    client=client,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_detail_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message(
                    "get_detail_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_detail_error", error=str(e)),
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
                    "source": {
                        "type": "string",
                        "description": "Nguồn booking (ví dụ: 'phone')",
                    },
                    # "twilioCallSid": {"type": "string", "description": "Twilio Call SID"},
                    "startTime": {
                        "type": "string",
                        "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)",
                    },
                    "endTime": {
                        "type": "string",
                        "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)",
                    },
                    "serviceId": {"type": "string", "description": "ID của service"},
                    "employeeId": {"type": "string", "description": "ID của nhân viên"},
                    # "bookingStartTime": {"type": "string", "description": "Thời gian bắt đầu booking (format: YYYY-MM-DD HH:mm:ss)"},
                    "notes": {"type": "string", "description": "Ghi chú"},
                    "customerId": {
                        "type": "string",
                        "description": "ID khách hàng (tùy chọn)",
                    },
                    "customerName": {
                        "type": "string",
                        "description": "Tên khách hàng ",
                    },
                    "furiganaName": {"type": "string", "description": "Tên furigana"},
                    "customerAge": {
                        "type": "integer",
                        "description": "Tuổi khách hàng (tùy chọn)",
                    },
                    "customerGender": {
                        "type": "string",
                        "description": "Giới tính khách hàng (tùy chọn)",
                    },
                    "phoneNumber": {
                        "type": "string",
                        "description": "Số điện thoại (tùy chọn)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Nhóm khách hàng (tùy chọn)",
                    },
                    "note": {
                        "type": "string",
                        "description": "Ghi chú cho khách hàng (tùy chọn)",
                    },
                    "bookingStartTime": {
                        "type": "string",
                        "description": "Thời gian bắt đầu booking (format: YYYY-MM-DD HH:mm:ss)",
                    },
                    "storeName": {
                        "type": "string",
                        "description": "Tên cửa hàng (tùy chọn)",
                    },
                    # "extensionMinutes": {
                    #     "type": "integer",
                    #     "description": "Thời gian gia hạn (phút)",
                    # },
                    # "meetingPoint": {
                    #     "type": "string",
                    #     "description": "Điểm hẹn (tùy chọn)",
                    # },
                    "departmentId": {
                        "type": "string",
                        "description": "ID phòng ban (tùy chọn)",
                    },
                    "room": {"type": "string", "description": "Phòng (tùy chọn)"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Các lựa chọn bổ sung (tùy chọn)",
                    },
                    # "driverDropoff": {
                    #     "type": "string",
                    #     "description": "Điểm trả khách (tùy chọn)",
                    # },
                    # "driverPickup": {
                    #     "type": "string",
                    #     "description": "Điểm đón khách (tùy chọn)",
                    # },
                    "paymentMethod": {
                        "type": "string",
                        "description": "Phương thức thanh toán (tùy chọn)",
                        "enum": [
                            "cash",
                            "credit_card",
                            "debit_card",
                            "bank_transfer",
                            "paypay",
                        ],
                    },
                    "totalFee": {
                        "type": "number",
                        "description": "Tổng chi phí (tùy chọn)",
                    },
                    "changePrepared": {
                        "type": "number",
                        "description": "Tiền thối chuẩn bị (tùy chọn)",
                    },
                    "cashReceivedCustomer": {
                        "type": "number",
                        "description": "Tiền khách thanh toán (tùy chọn)",
                    },
                    # "cashReceivedStaff": {
                    #     "type": "number",
                    #     "description": "Tiền nhân viên nhận (tùy chọn)",
                    # },
                    # "discount": {
                    #     "type": "number",
                    #     "description": "Chiết khấu (tùy chọn)",
                    # },
                    # "finalPayment": {
                    #     "type": "number",
                    #     "description": "Số tiền thanh toán cuối cùng (tùy chọn)",
                    # },
                    "travelFee": {
                        "type": "number",
                        "description": "Phí di chuyển (tùy chọn)",
                    },
                    "receivedBy": {
                        "type": "string",
                        "description": "Người nhận tiền (tùy chọn)",
                    },
                    # "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên (tùy chọn)"}
                },
                "required": [
                    "source",
                    "startTime",
                    "endTime",
                    "serviceId",
                    "employeeId",
                    "customerName",
                ],
            },
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
        customerName: str,
        furiganaName: Optional[str] = None,
        source: str = "phone",
        notes: Optional[str] = None,
        customerId: Optional[str] = None,
        customerAge: Optional[int] = None,
        customerGender: Optional[str] = None,
        phoneNumber: Optional[str] = None,
        firstContactSource: Optional[str] = None,
        category: Optional[str] = None,
        note: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute create booking"""
        try:
            booking_info: BookingInfoDict = {
                "serviceId": serviceId,
                "employeeId": employeeId,
                "startTime": kwargs.get("bookingStartTime") or startTime,
            }
            if notes:
                booking_info["notes"] = notes

            for field in [
                "storeName",
                "extensionMinutes",
                "meetingPoint",
                "departmentId",
                "room",
                "driverDropoff",
                "driverPickup",
            ]:
                value = kwargs.get(field)
                if value is not None:
                    booking_info[field] = value

            options = kwargs.get("options")
            if options:
                booking_info["options"] = options

            customer_info: CustomerInfoDict = {}
            if furiganaName:
                customer_info["furiganaName"] = furiganaName
            if customerId:
                customer_info["id"] = customerId
            if customerName:
                customer_info["name"] = customerName
            if customerAge is not None:
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

            payment_info: PaymentInfoDict = {}
            raw_payment_info = kwargs.get("paymentInfo")
            if isinstance(raw_payment_info, dict):
                payment_info.update(raw_payment_info)

            for field in [
                "paymentMethod",
                "totalFee",
                "changePrepared",
                "cashReceivedCustomer",
                "cashReceivedStaff",
                "discount",
                "finalPayment",
                "travelFee",
                "receivedBy",
            ]:
                value = kwargs.get(field)
                if value is not None:
                    payment_info[field] = value

            payload = {
                "source": source,
                "twilioCallSid": session_manager.stream_sid,
                "startTime": startTime,
                "endTime": endTime,
                "bookingInfo": booking_info,
                "customerInfo": customer_info,
            }
            if payment_info:
                payload["paymentInfo"] = payment_info

            # logger.info(f"Payload for create booking: {payload}")

            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "POST",
                    f"{settings.API_HOST}bookings",
                    client=client,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("create_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": e,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                # "message": _get_booking_message("create_error", error=str(e)),
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
                    "status": {
                        "type": "string",
                        "description": "Trạng thái mới (ví dụ: 'confirmed', 'cancelled')",
                    },
                },
                "required": ["id", "status"],
            },
        }

    async def execute(
        self, session_manager: SessionManager, id: str, status: str, **kwargs
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
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("update_status_success", status=status),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message(
                    "update_status_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("update_status_error", error=str(e)),
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
                        "description": "Ngày cần xem lịch (format: YYYY-MM-DD)",
                    }
                },
                "required": ["date"],
            },
        }

    async def execute(
        self, session_manager: SessionManager, date: str, **kwargs
    ) -> Dict[str, Any]:
        """Execute get booking calendar"""
        try:
            async with httpx.AsyncClient() as client:
                response = await logged_request(
                    "GET",
                    f"{settings.API_HOST}bookings/calendar",
                    client=client,
                    params={"date": date},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": _get_booking_message("get_calendar_success"),
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": _get_booking_message(
                    "get_calendar_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("get_calendar_error", error=str(e)),
            }
