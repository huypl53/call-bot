"""
Session Manager - Moved from root to src/core/
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from src.config.constants import SESSIONS_DIRECTORY


class SessionManager:
    """Quản lý session data cho mỗi cuộc gọi đặt phòng."""

    def __init__(self, stream_sid: str):
        self.stream_sid = stream_sid
        self.start_time = datetime.now().isoformat()
        self.end_time: Optional[str] = None

        # Cấu trúc dữ liệu booking (keys tiếng Anh)
        self.booking_info: Dict[str, Any] = {
            "full_name": None,
            "age": None,
            "gender": None,
            "check_in_date": None,
            "check_out_date": None,
            "room_type": None,
            "special_requests": None
        }

        # Lịch sử các lần check phòng
        self.room_checks: list = []

        # Đảm bảo thư mục sessions tồn tại
        self._ensure_sessions_directory()

    def _ensure_sessions_directory(self):
        """Tạo thư mục sessions nếu chưa tồn tại."""
        os.makedirs(SESSIONS_DIRECTORY, exist_ok=True)

    def update_booking_info(self, **kwargs):
        """Cập nhật thông tin đặt phòng và auto-save."""
        has_changes = False
        updated_fields = []

        for key, value in kwargs.items():
            if key in self.booking_info and value is not None:
                self.booking_info[key] = value
                has_changes = True
                updated_fields.append(f"{key}={value}")

        if has_changes:
            print(f"📝 Updated: {', '.join(updated_fields)}")
            self.save_to_file()

    def add_room_check(self, check_data: Dict[str, Any]):
        """Thêm một lần check phòng vào lịch sử và auto-save."""
        check_data["timestamp"] = datetime.now().isoformat()
        self.room_checks.append(check_data)
        self.save_to_file()

    def get_booking_summary(self) -> Dict[str, Any]:
        """Lấy tổng hợp thông tin đã thu thập."""
        return {
            "booking_info": self.booking_info,
            "completion_status": self._get_completion_status()
        }

    def _get_completion_status(self) -> Dict[str, Any]:
        """Kiểm tra các field nào đã được điền."""
        required_fields = {k: v for k, v in self.booking_info.items() if k != "special_requests"}
        total_fields = len(required_fields)
        filled_fields = sum(1 for v in required_fields.values() if v is not None)
        missing_fields = [k for k, v in self.booking_info.items() if v is None and k != "special_requests"]

        return {
            "total_fields": total_fields,
            "filled_fields": filled_fields,
            "missing_fields": missing_fields,
            "is_complete": filled_fields == total_fields
        }

    def save_to_file(self):
        """Lưu session data ra file JSON."""
        self.end_time = datetime.now().isoformat()
        filename = f"{SESSIONS_DIRECTORY}/{self.stream_sid}.json"

        completion = self._get_completion_status()
        session_data = {
            "stream_sid": self.stream_sid,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "last_updated": self.end_time,
            "booking_info": self.booking_info,
            "room_checks": self.room_checks,
            "completion_status": completion
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        print(f"💾 Auto-saved → {filename} ({completion['filled_fields']}/{completion['total_fields']} fields)")
        return filename

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển session data thành dictionary."""
        return {
            "stream_sid": self.stream_sid,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "booking_info": self.booking_info,
            "room_checks": self.room_checks
        }
