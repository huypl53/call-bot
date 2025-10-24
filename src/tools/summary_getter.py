"""
Booking Summary Getter Tool
"""

from typing import Dict, Any
from src.tools.base import BaseTool
from src.config.constants import BOOKING_FIELDS, GENDER_OPTIONS, ROOM_TYPE_OPTIONS


class SummaryGetterTool(BaseTool):
    """Tool để lấy tổng hợp thông tin đặt phòng"""

    @property
    def name(self) -> str:
        return "get_booking_summary"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Lấy tổng hợp thông tin đặt phòng đã thu thập được từ khách. Dùng để kiểm tra thông tin nào đã có, thông tin nào còn thiếu.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    async def execute(self, session_manager: Any, **kwargs) -> Dict[str, Any]:
        """Execute get booking summary"""
        summary = session_manager.get_booking_summary()
        booking_info = summary["booking_info"]
        status = summary["completion_status"]

        # Format thông tin cho dễ đọc
        info_display = []
        for key, value in booking_info.items():
            key_vn = BOOKING_FIELDS.get(key, key)

            # Convert values to Vietnamese
            if key == "gender" and value:
                value_vn = GENDER_OPTIONS.get(value, value)
            elif key == "room_type" and value:
                value_vn = ROOM_TYPE_OPTIONS.get(value, value)
            else:
                value_vn = value if value is not None else "(chưa có)"

            info_display.append(f"{key_vn}: {value_vn}")

        message = "THÔNG TIN ĐẶT PHÒNG HIỆN TẠI:\n" + "\n".join(info_display)
        message += f"\n\nTrạng thái: {status['filled_fields']}/{status['total_fields']} thông tin đã đầy đủ"

        if status["is_complete"]:
            message += "\n✓ Đã thu thập đủ thông tin!"
        else:
            missing_vn = [BOOKING_FIELDS.get(f, f) for f in status['missing_fields']]
            message += f"\n⚠ Còn thiếu: {', '.join(missing_vn)}"

        return {
            "booking_info": booking_info,
            "completion_status": status,
            "message": message
        }
