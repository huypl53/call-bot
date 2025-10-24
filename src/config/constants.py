"""
Constants cho KIAI Assistant
Chứa tất cả các hằng số được sử dụng trong hệ thống
"""

# OpenAI Configuration
OPENAI_MODEL = "gpt-realtime-mini-2025-10-06"
DEFAULT_TEMPERATURE = 0.8
DEFAULT_VOICE = "alloy"

# Server Configuration
DEFAULT_PORT = 5050

# Logging Configuration
LOG_EVENT_TYPES = [
    'error',
    'response.content.done',
    'rate_limits.updated',
    'response.done',
    'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started',
    'session.created',
    'session.updated',
    'response.function_call_arguments.done'
]

SHOW_TIMING_MATH = False

# Twilio Configuration
TWILIO_GREETING_VOICE = "Google.en-US-Chirp3-HD-Aoede"
TWILIO_GREETING_MESSAGE = (
    "Please wait while we connect your call to the A. I. voice assistant, "
    "powered by Twilio and the Open A I Realtime API"
)
TWILIO_READY_MESSAGE = "O.K. you can start talking!"
TWILIO_PAUSE_LENGTH = 1

# Session Configuration
SESSIONS_DIRECTORY = "sessions"

# Booking Fields
BOOKING_REQUIRED_FIELDS = 6  # Không bao gồm special_requests
BOOKING_FIELDS = {
    "full_name": "Họ tên",
    "age": "Tuổi",
    "gender": "Giới tính",
    "check_in_date": "Ngày đến",
    "check_out_date": "Ngày đi",
    "room_type": "Loại phòng",
    "special_requests": "Yêu cầu đặc biệt"
}

# Gender Options
GENDER_OPTIONS = {
    "male": "Nam",
    "female": "Nữ",
    "other": "Khác"
}

# Room Type Options
ROOM_TYPE_OPTIONS = {
    "standard": "Phòng thường",
    "vip": "Phòng VIP"
}

# Room Availability (Mock)
ROOM_AVAILABILITY_CHANCE = 0.7  # 70% chance of having rooms
MIN_AVAILABLE_ROOMS = 1
MAX_AVAILABLE_ROOMS = 5
