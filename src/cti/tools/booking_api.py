"""
Booking API tool for creating new bookings.
"""

from typing import Any, Dict, List, Optional, TypedDict

import httpx

from cti.config.settings import Language, settings
from cti.core.session_manager import SessionManager
from cti.tools.api_logger import logged_request
from cti.tools.base import BaseTool

# Language-specific booking API messages used by CreateBookingTool
BOOKING_MESSAGES = {
    Language.VI: {
        "create_success": "Tạo booking thành công",
        "create_error": "Lỗi khi tạo booking: {error}",
    },
    Language.EN: {
        "create_success": "Successfully created booking",
        "create_error": "Error creating booking: {error}",
    },
    Language.JP: {
        "create_success": "予約の作成に成功しました",
        "create_error": "予約の作成中にエラーが発生しました: {error}",
    },
}


def _get_booking_message(key: str, **kwargs) -> str:
    """Get booking message based on current language setting."""
    messages = BOOKING_MESSAGES.get(settings.LANGUAGE, BOOKING_MESSAGES[Language.EN])
    message = messages.get(key, BOOKING_MESSAGES[Language.EN].get(key, ""))
    return message.format(**kwargs) if kwargs else message


class BookingInfoDict(TypedDict, total=False):
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
    id: Optional[str]
    name: Optional[str]
    furiganaName: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    phoneNumber: Optional[str]
    firstContactSource: Optional[str]
    category: Optional[str]
    note: Optional[str]


class PaymentInfoDict(TypedDict, total=False):
    paymentMethod: Optional[str]
    totalFee: Optional[float]
    changePrepared: Optional[float]
    cashReceivedCustomer: Optional[float]
    cashReceivedStaff: Optional[float]
    discount: Optional[float]
    finalPayment: Optional[float]
    travelFee: Optional[float]
    receivedBy: Optional[str]


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
                    "notes": {"type": "string", "description": "Ghi chú"},
                    # "customerId": {
                    #     "type": "string",
                    #     "description": "ID khách hàng (tùy chọn)",
                    # },
                    "customerName": {
                        "type": "string",
                        "description": "Tên khách hàng",
                    },
                    # "furiganaName": {
                    #     "type": "string",
                    #     "description": "Tên furigana (tùy chọn)",
                    # },
                    # "customerAge": {
                    #     "type": "integer",
                    #     "description": "Tuổi khách hàng (tùy chọn)",
                    # },
                    # "customerGender": {
                    #     "type": "string",
                    #     "description": "Giới tính khách hàng (tùy chọn)",
                    # },
                    # "phoneNumber": {
                    #     "type": "string",
                    #     "description": "Số điện thoại (tùy chọn)",
                    # },
                    # "firstContactSource": {
                    #     "type": "string",
                    #     "description": "Nguồn liên hệ đầu tiên (tùy chọn)",
                    # },
                    # "category": {
                    #     "type": "string",
                    #     "description": "Nhóm khách hàng (tùy chọn)",
                    # },
                    "note": {
                        "type": "string",
                        "description": "Ghi chú cho khách hàng (tùy chọn)",
                    },
                    # "bookingStartTime": {
                    #     "type": "string",
                    #     "description": "Thời gian bắt đầu booking (format: YYYY-MM-DD HH:mm:ss)",
                    # },
                    # "storeName": {"type": "string", "description": "Tên cửa hàng"},
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
                    # "room": {"type": "string", "description": "Phòng (tùy chọn)"},
                    # "driverDropoff": {
                    #     "type": "string",
                    #     "description": "Điểm trả khách (tùy chọn)",
                    # },
                    # "driverPickup": {
                    #     "type": "string",
                    #     "description": "Điểm đón khách (tùy chọn)",
                    # },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "ローター",
                                "アイマスク",
                                "パンスト",
                                "コスプレ",
                                "口内発射",
                                "パイプ",
                                "オナニー",
                                "電マ",
                                "顔無し撮影",
                                "顔有撮影",
                            ],
                        },
                        "description": "Các lựa chọn bổ sung (tùy chọn)",
                    },
                    "paymentMethod": {
                        "type": "string",
                        "description": "Phương thức thanh toán (tùy chọn)",
                        "enum": ["cash", "credit_card"],
                    },
                    # "totalFee": {
                    #     "type": "number",
                    #     "description": "Tổng chi phí (tùy chọn)",
                    # },
                    # "changePrepared": {
                    #     "type": "number",
                    #     "description": "Tiền thối chuẩn bị (tùy chọn)",
                    # },
                    # "cashReceivedCustomer": {
                    #     "type": "number",
                    #     "description": "Tiền khách thanh toán (tùy chọn)",
                    # },
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
                    # "travelFee": {
                    #     "type": "number",
                    #     "description": "Phí di chuyển (tùy chọn)",
                    # },
                    # "receivedBy": {
                    #     "type": "string",
                    #     "description": "Người nhận tiền (tùy chọn)",
                    # },
                    # "paymentInfo": {
                    #     "type": "object",
                    #     "description": "Chi tiết thanh toán bổ sung (tùy chọn)",
                    # },
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
        startTime: str,
        endTime: str,
        serviceId: str,
        employeeId: str,
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
        **kwargs: Any,
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
                "message": _get_booking_message(
                    "create_error", error=e.response.status_code
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": _get_booking_message("create_error", error=str(e)),
            }
