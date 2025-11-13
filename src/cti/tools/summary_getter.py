"""
Booking Summary Getter Tool
"""

from typing import Any, Dict

from cti.config.constants import BOOKING_FIELDS, GENDER_OPTIONS, ROOM_TYPE_OPTIONS
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class SummaryGetterTool(BaseTool):
    """Tool để lấy tổng hợp thông tin đặt phòng đã thu thập được từ khách. Dùng để kiểm tra thông tin nào đã có, thông tin nào còn thiếu."""

    @property
    def name(self) -> str:
        return "get_booking_summary"

    async def execute(self, session_manager: SessionManager, **kwargs) -> Dict[str, Any]:
        """Lấy tổng hợp thông tin đặt phòng đã thu thập được từ khách. Dùng để kiểm tra thông tin nào đã có, thông tin nào còn thiếu."""
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
