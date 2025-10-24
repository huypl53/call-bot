"""
Room Availability Checker Tool
"""

import random
from typing import Dict, Any, Optional
from src.tools.base import BaseTool
from src.config.constants import (
    ROOM_AVAILABILITY_CHANCE,
    MIN_AVAILABLE_ROOMS,
    MAX_AVAILABLE_ROOMS,
    ROOM_TYPE_OPTIONS
)


class RoomCheckerTool(BaseTool):
    """Tool để kiểm tra phòng trống (mock data)"""

    @property
    def name(self) -> str:
        return "check_room_availability"

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": "Kiểm tra phòng trống trong khoảng thời gian. Trả về thông tin phòng có sẵn hay không.",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_in_date": {
                        "type": "string",
                        "description": "Ngày nhận phòng (định dạng: YYYY-MM-DD hoặc DD/MM/YYYY)"
                    },
                    "check_out_date": {
                        "type": "string",
                        "description": "Ngày trả phòng (định dạng: YYYY-MM-DD hoặc DD/MM/YYYY)"
                    },
                    "room_type": {
                        "type": "string",
                        "enum": ["standard", "vip"],
                        "description": "Loại phòng: 'standard' (phòng thường) hoặc 'vip' (phòng VIP)"
                    }
                },
                "required": ["check_in_date", "check_out_date", "room_type"]
            }
        }

    async def execute(
        self,
        check_in_date: str,
        check_out_date: str,
        room_type: str,
        session_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute room availability check"""
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

        # Save to session history if provided
        if session_manager:
            session_manager.add_room_check(result.copy())

        return result
