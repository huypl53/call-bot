"""
Booking Saver Tool
"""

from typing import Any, Dict, Optional

from cti.config.constants import BOOKING_FIELDS
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class BookingSaverTool(BaseTool):
    """Tool để lưu thông tin đặt phòng"""

    @property
    def name(self) -> str:
        return "save_booking_info"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lưu thông tin đặt phòng của khách hàng vào hệ thống NGAY LẬP TỨC. PHẢI gọi tool này NGAY SAU KHI nhận được bất kỳ thông tin nào từ khách (tên, tuổi, giới tính, ngày, v.v.). KHÔNG ĐƯỢC đợi thu thập nhiều thông tin rồi mới lưu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string", "description": "Họ và tên đầy đủ của khách"},
                    "age": {"type": "integer", "description": "Tuổi của khách"},
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "other"],
                        "description": "Giới tính: 'male' (nam), 'female' (nữ), hoặc 'other' (khác)"
                    },
                    "check_in_date": {"type": "string", "description": "Ngày nhận phòng"},
                    "check_out_date": {"type": "string", "description": "Ngày trả phòng"},
                    "room_type": {
                        "type": "string",
                        "enum": ["standard", "vip"],
                        "description": "Loại phòng: 'standard' (phòng thường) hoặc 'vip' (phòng VIP)"
                    },
                    "special_requests": {"type": "string", "description": "Các yêu cầu đặc biệt của khách (nếu có)"}
                },
                "required": []
            }
        }

    async def execute(self, session_manager: SessionManager, **kwargs) -> Dict[str, Any]:
        """Execute save booking info"""
        session_manager.update_booking_info(**kwargs)
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
