"""
Booking Saver Tool
"""

from typing import Annotated, Any, Dict, Optional

from cti.config.constants import BOOKING_FIELDS
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class BookingSaverTool(BaseTool):
    """Tool để lưu thông tin đặt phòng của khách hàng vào hệ thống NGAY LẬP TỨC. PHẢI gọi tool này NGAY SAU KHI nhận được bất kỳ thông tin nào từ khách (tên, tuổi, giới tính, ngày, v.v.). KHÔNG ĐƯỢC đợi thu thập nhiều thông tin rồi mới lưu."""

    @property
    def name(self) -> str:
        return "save_booking_info"

    async def execute(
        self,
        session_manager: SessionManager,
        full_name: Annotated[Optional[str], "Họ và tên đầy đủ của khách"] = None,
        age: Annotated[Optional[int], "Tuổi của khách"] = None,
        gender: Annotated[Optional[str], "Giới tính: 'male' (nam), 'female' (nữ), hoặc 'other' (khác)"] = None,
        check_in_date: Annotated[Optional[str], "Ngày nhận phòng"] = None,
        check_out_date: Annotated[Optional[str], "Ngày trả phòng"] = None,
        room_type: Annotated[Optional[str], "Loại phòng: 'standard' (phòng thường) hoặc 'vip' (phòng VIP)"] = None,
        special_requests: Annotated[Optional[str], "Các yêu cầu đặc biệt của khách (nếu có)"] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Lưu thông tin đặt phòng của khách hàng vào hệ thống NGAY LẬP TỨC. PHẢI gọi tool này NGAY SAU KHI nhận được bất kỳ thông tin nào từ khách (tên, tuổi, giới tính, ngày, v.v.). KHÔNG ĐƯỢC đợi thu thập nhiều thông tin rồi mới lưu."""
        booking_data = {
            "full_name": full_name,
            "age": age,
            "gender": gender,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "room_type": room_type,
            "special_requests": special_requests,
        }
        # Filter out None values and merge with kwargs
        booking_data = {k: v for k, v in booking_data.items() if v is not None}
        booking_data.update(kwargs)
        session_manager.update_booking_info(**booking_data)
        summary = session_manager.get_booking_summary()

        filled = summary["completion_status"]["filled_fields"]
        total = summary["completion_status"]["total_fields"]
        missing = summary["completion_status"]["missing_fields"]

        message_parts = [f"Đã lưu thông tin thành công! ({filled}/{total} thông tin đã đầy đủ)"]

        if missing:
            missing_vn = [BOOKING_FIELDS.get(f, f) for f in missing]
            message_parts.append(f"Còn thiếu: {', '.join(missing_vn)}")

        return {
            "success": True,
            "booking_info": session_manager.booking_info,
            "completion_status": summary["completion_status"],
            "message": ". ".join(message_parts)
        }
