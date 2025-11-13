"""
Booking API Tools
Tools for interacting with the Booking API
"""

from typing import Annotated, Any, Dict, Optional, TypedDict

import httpx

from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


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
    """Tool để lấy danh sách bookings với phân trang và các bộ lọc tùy chọn"""

    @property
    def name(self) -> str:
        return "get_booking_list"

    async def execute(
        self,
        session_manager: SessionManager,
        page: Annotated[Optional[int], "Số trang (mặc định: 1)"] = None,
        size: Annotated[Optional[int], "Số lượng items mỗi trang (mặc định: 5)"] = None,
        startTime: Annotated[Optional[str], "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"] = None,
        endTime: Annotated[Optional[str], "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)"] = None,
        employeeId: Annotated[Optional[str], "ID của nhân viên"] = None,
        employeeName: Annotated[Optional[str], "Tên nhân viên"] = None,
    ) -> Dict[str, Any]:
        """Lấy danh sách bookings với phân trang và các bộ lọc tùy chọn"""
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
    """Tool để lấy chi tiết booking theo ID"""

    @property
    def name(self) -> str:
        return "get_booking_detail"

    async def execute(
        self,
        session_manager: SessionManager,
        id: Annotated[str, "ID của booking"],
    ) -> Dict[str, Any]:
        """Lấy chi tiết booking theo ID"""
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
    """Tool để kiểm tra booking có sẵn trong khoảng thời gian"""

    @property
    def name(self) -> str:
        return "check_booking_availability"

    async def execute(
        self,
        session_manager: SessionManager,
        startTime: Annotated[str, "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"],
        endTime: Annotated[str, "Thời gian kết thúc (format: YYYY-MM-DD HH:mm:ss)"],
        employeeId: Annotated[Optional[str], "ID của nhân viên (tùy chọn)"] = None,
        employeeName: Annotated[Optional[str], "Tên nhân viên (tùy chọn)"] = None,
    ) -> Dict[str, Any]:
        """Kiểm tra booking có sẵn trong khoảng thời gian"""
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
    """Tool để tạo booking mới với thông tin khách hàng và booking"""

    @property
    def name(self) -> str:
        return "create_booking"

    async def execute(
        self,
        session_manager: SessionManager,
        startTime: Annotated[str, "Thời gian bắt đầu (format: YYYY-MM-DD HH:mm:ss)"],
        serviceId: Annotated[str, "ID của service"],
        employeeId: Annotated[str, "ID của nhân viên"],
        furiganaName: Annotated[str, "Tên furigana"],
        twilioCallSid: Annotated[Optional[str], "Twilio Call SID (tùy chọn)"] = None,
        source: Annotated[str, "Nguồn booking (ví dụ: 'phone')"] = 'phone',
        notes: Annotated[Optional[str], "Ghi chú (tùy chọn)"] = None,
        customerId: Annotated[Optional[str], "ID khách hàng (tùy chọn)"] = None,
        customerName: Annotated[Optional[str], "Tên khách hàng (tùy chọn)"] = None,
        customerAge: Annotated[Optional[str], "Tuổi khách hàng (tùy chọn)"] = None,
        customerGender: Annotated[Optional[str], "Giới tính khách hàng (tùy chọn)"] = None,
        phoneNumber: Annotated[Optional[str], "Số điện thoại (tùy chọn)"] = None,
        firstContactSource: Annotated[Optional[str], "Nguồn liên hệ đầu tiên (tùy chọn)"] = None,
    ) -> Dict[str, Any]:
        """Tạo booking mới với thông tin khách hàng và booking"""
        try:
            booking_info: BookingInfoDict = {
                "serviceId": serviceId,
                "employeeId": employeeId,
                # "startTime": bookingStartTime
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
                "twilioCallSid": twilioCallSid or 'TEST_CALL_SID_123',
                "startTime": startTime,
                "bookingInfo": booking_info,
                "customerInfo": customer_info
            }

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{settings.API_HOST}bookings",
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

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
    """Tool để cập nhật trạng thái booking (ví dụ: confirmed, cancelled)"""

    @property
    def name(self) -> str:
        return "update_booking_status"

    async def execute(
        self,
        session_manager: SessionManager,
        id: Annotated[str, "ID của booking"],
        status: Annotated[str, "Trạng thái mới (ví dụ: 'confirmed', 'cancelled')"],
    ) -> Dict[str, Any]:
        """Cập nhật trạng thái booking (ví dụ: confirmed, cancelled)"""
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

