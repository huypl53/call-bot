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

# Language-specific booking field translations
BOOKING_FIELDS_TRANSLATIONS = {
    Language.VI: {
        "full_name": "Họ tên",
        "age": "Tuổi",
        "gender": "Giới tính",
        "check_in_date": "Ngày đến",
        "check_out_date": "Ngày đi",
        "room_type": "Loại phòng",
        "special_requests": "Yêu cầu đặc biệt"
    },
    Language.EN: {
        "full_name": "Full Name",
        "age": "Age",
        "gender": "Gender",
        "check_in_date": "Check-in Date",
        "check_out_date": "Check-out Date",
        "room_type": "Room Type",
        "special_requests": "Special Requests"
    },
    Language.JP: {
        "full_name": "氏名",
        "age": "年齢",
        "gender": "性別",
        "check_in_date": "チェックイン日",
        "check_out_date": "チェックアウト日",
        "room_type": "部屋タイプ",
        "special_requests": "特別なリクエスト"
    },
}

# Language-specific gender option translations
GENDER_OPTIONS_TRANSLATIONS = {
    Language.VI: {
        "male": "Nam",
        "female": "Nữ",
        "other": "Khác"
    },
    Language.EN: {
        "male": "Male",
        "female": "Female",
        "other": "Other"
    },
    Language.JP: {
        "male": "男性",
        "female": "女性",
        "other": "その他"
    },
}

# Language-specific room type option translations
ROOM_TYPE_OPTIONS_TRANSLATIONS = {
    Language.VI: {
        "standard": "Phòng thường",
        "vip": "Phòng VIP"
    },
    Language.EN: {
        "standard": "Standard Room",
        "vip": "VIP Room"
    },
    Language.JP: {
        "standard": "スタンダードルーム",
        "vip": "VIPルーム"
    },
}


def _get_booking_fields() -> dict[str, str]:
    """Get booking fields translation based on current language setting."""
    return BOOKING_FIELDS_TRANSLATIONS.get(settings.LANGUAGE, BOOKING_FIELDS_TRANSLATIONS[Language.EN])


def _get_gender_options() -> dict[str, str]:
    """Get gender options translation based on current language setting."""
    return GENDER_OPTIONS_TRANSLATIONS.get(settings.LANGUAGE, GENDER_OPTIONS_TRANSLATIONS[Language.EN])


def _get_room_type_options() -> dict[str, str]:
    """Get room type options translation based on current language setting."""
    return ROOM_TYPE_OPTIONS_TRANSLATIONS.get(settings.LANGUAGE, ROOM_TYPE_OPTIONS_TRANSLATIONS[Language.EN])


# Exported constants (language-specific)
BOOKING_FIELDS = _get_booking_fields()
GENDER_OPTIONS = _get_gender_options()
ROOM_TYPE_OPTIONS = _get_room_type_options()

# Room Availability (Mock)
ROOM_AVAILABILITY_CHANCE = 0.7  # 70% chance of having rooms
MIN_AVAILABLE_ROOMS = 1
MAX_AVAILABLE_ROOMS = 5
