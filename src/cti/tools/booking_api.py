"""
Booking API Tools
Tools for interacting with the Booking API
"""

import logging
from typing import Any, Dict, Optional, TypedDict

import httpx

from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool

logger = logging.getLogger(__name__)


class BookingInfoDict(TypedDict, total=False):
    """TypedDict for bookingInfo in CreateBookingTool"""
    serviceId: str
    employeeId: str
    startTime: str
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
                response = await client.get(
                    f"{settings.API_HOST}bookings",
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": "Lấy danh sách bookings thành công"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi lấy danh sách bookings: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi lấy danh sách bookings: {str(e)}"
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
                response = await client.get(
                    f"{settings.API_HOST}bookings/{id}",
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": "Lấy chi tiết booking thành công"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi lấy chi tiết booking: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi lấy chi tiết booking: {str(e)}"
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
                        "description": "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"
                    },
                    "endTime": {
                        "type": "string",
                        "description": "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)"
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
                response = await client.get(
                    f"{settings.API_HOST}bookings/availables",
                    params=params,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": "Kiểm tra booking availability thành công"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi kiểm tra booking availability: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi kiểm tra booking availability: {str(e)}"
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
                    # "firstContactSource": {"type": "string", "description": "Nguồn liên hệ đầu tiên (tùy chọn)"}
                },
                "required": ["source", "startTime", "serviceId", "employeeId"]
            }
        }

    async def execute(
        self,
        session_manager: SessionManager,
        # twilioCallSid: str,
        startTime: str,
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
        **kwargs
    ) -> Dict[str, Any]:
        """Execute create booking"""
        try:
            booking_info: BookingInfoDict = {
                "serviceId": serviceId,
                "employeeId": employeeId,
                "startTime": startTime
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

            payload = {
                "source": source,
                "twilioCallSid": session_manager.stream_sid,
                # "startTime": startTime,
                "bookingInfo": booking_info,
                "customerInfo": customer_info
            }
            
            logger.info(f"Payload for create booking: {payload}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.API_HOST}bookings",
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json() if response.content else None

            return {
                "success": True,
                "data": data,
                "message": "Tạo booking thành công"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi tạo booking: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi tạo booking: {str(e)}"
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
                response = await client.patch(
                    f"{settings.API_HOST}bookings/{id}",
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            return {
                "success": True,
                "data": data,
                "message": f"Cập nhật trạng thái booking thành công: {status}"
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error: {e.response.status_code}",
                "message": f"Lỗi khi cập nhật trạng thái booking: {e.response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi khi cập nhật trạng thái booking: {str(e)}"
            }

