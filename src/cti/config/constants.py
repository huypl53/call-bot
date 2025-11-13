"""
Constants cho KIAI Assistant
Chứa tất cả các hằng số được sử dụng trong hệ thống
"""

from cti.config.settings import Language, settings

# OpenAI Configuration
# OPENAI_MODEL = "gpt-realtime-mini-2025-10-06"
OPENAI_MODEL = "gpt-realtime-mini"
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
    'response.function_call_arguments.done',
    'response.output_text.delta'
]

SHOW_TIMING_MATH = False

# Twilio Configuration
# Language-specific translations
TWILIO_GREETING_MESSAGES = {
    Language.EN: (
        "Please wait while we connect your call to the A. I. voice assistant, "
        "powered by Twilio and the Open A I Realtime API"
    ),
    Language.VI: (
        "Vui lòng chờ trong khi chúng tôi kết nối cuộc gọi của bạn với trợ lý giọng nói A. I., "
        "được hỗ trợ bởi Twilio và Open A I Realtime API"
    ),
    Language.JP: (
        "お電話をA. I.音声アシスタントに接続中です。しばらくお待ちください。"
        "TwilioとOpen A I Realtime APIによって提供されています"
    ),
}

TWILIO_READY_MESSAGES = {
    Language.EN: "O.K. you can start talking!",
    Language.VI: "Được rồi, bạn có thể bắt đầu nói!",
    Language.JP: "了解しました。話し始めてください。",
}

TWILIO_GREETING_VOICES = {
    Language.EN: "Google.en-US-Chirp3-HD-Aoede",
    Language.VI: "Google.vi-VN-Wavenet-A",
    Language.JP: "Google.ja-JP-Wavenet-A",
}

# Get language-specific values from settings
def _get_twilio_greeting_message() -> str:
    """Get Twilio greeting message based on current language setting."""
    return TWILIO_GREETING_MESSAGES.get(settings.LANGUAGE, TWILIO_GREETING_MESSAGES[Language.EN])


def _get_twilio_ready_message() -> str:
    """Get Twilio ready message based on current language setting."""
    return TWILIO_READY_MESSAGES.get(settings.LANGUAGE, TWILIO_READY_MESSAGES[Language.EN])


def _get_twilio_greeting_voice() -> str:
    """Get Twilio greeting voice based on current language setting."""
    return TWILIO_GREETING_VOICES.get(settings.LANGUAGE, TWILIO_GREETING_VOICES[Language.EN])


# Exported constants (functions that return language-specific values)
TWILIO_GREETING_VOICE = _get_twilio_greeting_voice()
TWILIO_GREETING_MESSAGE = _get_twilio_greeting_message()
TWILIO_READY_MESSAGE = _get_twilio_ready_message()
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
