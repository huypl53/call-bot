"""
WebSocket Payload Types - TypedDict definitions for audio streaming
"""

from typing import Literal, Optional, TypedDict, Union


class AudioMessage(TypedDict):
    """Audio message with base64-encoded audio payload"""
    event: Literal["audio"]
    payload: str  # base64-encoded audio data
    timestamp: Optional[int]  # Optional timestamp in milliseconds
    format: Optional[str]  # Optional audio format (e.g., "pcm16", "wav")


class StartMessage(TypedDict):
    """Connection initialization message"""
    event: Literal["start"]
    session_id: Optional[str]  # Optional session identifier
    audio_format: Optional[str]  # Optional preferred audio format


class TextMessage(TypedDict):
    """Text-to-audio conversion request"""
    event: Literal["text"]
    text: str  # Text to convert to audio
    voice: Optional[str]  # Optional voice selection
    format: Optional[str]  # Optional output format


class ControlMessage(TypedDict):
    """Control commands for the audio stream"""
    event: Literal["pause", "resume", "stop", "clear"]
    reason: Optional[str]  # Optional reason for the control action


# Union type for all possible message types
WebSocketMessage = Union[AudioMessage, StartMessage, TextMessage, ControlMessage]

