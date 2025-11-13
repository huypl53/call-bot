"""
Room Availability Checker Tool
"""

import random
from typing import Annotated, Any, Dict

from cti.config.constants import (
    MAX_AVAILABLE_ROOMS,
    MIN_AVAILABLE_ROOMS,
    ROOM_AVAILABILITY_CHANCE,
    ROOM_TYPE_OPTIONS,
)
from cti.core.session_manager import SessionManager
from cti.tools.base import BaseTool


class RoomCheckerTool(BaseTool):
    """Tool để kiểm tra phòng trống trong khoảng thời gian. Trả về thông tin phòng có sẵn hay không."""

    @property
    def name(self) -> str:
        return "check_room_availability"

    async def execute(
        self,
        session_manager: SessionManager,
        check_in_date: Annotated[str, "Ngày nhận phòng (định dạng: YYYY-MM-DD hoặc DD/MM/YYYY)"],
        check_out_date: Annotated[str, "Ngày trả phòng (định dạng: YYYY-MM-DD hoặc DD/MM/YYYY)"],
        room_type: Annotated[str, "Loại phòng: 'standard' (phòng thường) hoặc 'vip' (phòng VIP)"],
        **kwargs
    ) -> Dict[str, Any]:
        """Kiểm tra phòng trống trong khoảng thời gian. Trả về thông tin phòng có sẵn hay không."""
        # Random availability
        is_available = random.random() < ROOM_AVAILABILITY_CHANCE

        # Get room type in Vietnamese
        room_type_vn = ROOM_TYPE_OPTIONS.get(room_type, room_type)

        if is_available:
            rooms_available = random.randint(MIN_AVAILABLE_ROOMS, MAX_AVAILABLE_ROOMS)
            result = {
                "available": True,
                "rooms_available": rooms_available,
                "room_type": room_type,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "message": f"Tuyệt vời! Chúng tôi còn {rooms_available} {room_type_vn} trống từ {check_in_date} đến {check_out_date}."
            }
        else:
            result = {
                "available": False,
                "rooms_available": 0,
                "room_type": room_type,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "message": f"Rất tiếc, {room_type_vn} đã hết cho khoảng thời gian từ {check_in_date} đến {check_out_date}. Quý khách có muốn thử ngày khác hoặc loại phòng khác không?"
            }

        # Save to session history
        session_manager.add_room_check(result.copy())

        return result
