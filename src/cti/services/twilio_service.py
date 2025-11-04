"""
Twilio Service - Handle TwiML generation
"""

from twilio.twiml.voice_response import Connect, VoiceResponse

from cti.config.constants import (
    TWILIO_GREETING_MESSAGE,
    TWILIO_GREETING_VOICE,
    TWILIO_PAUSE_LENGTH,
    TWILIO_READY_MESSAGE,
)


class TwilioService:
    """Service for Twilio operations"""

    @staticmethod
    def generate_twiml(websocket_url: str) -> str:
        """
        Generate TwiML response for incoming call.

        Args:
            websocket_url: WebSocket URL to connect to

        Returns:
            TwiML XML string
        """
        response = VoiceResponse()

        # Greeting message
        response.say(
            TWILIO_GREETING_MESSAGE,
            voice=TWILIO_GREETING_VOICE
        )

        response.pause(length=TWILIO_PAUSE_LENGTH)

        # Ready message
        response.say(
            TWILIO_READY_MESSAGE,
            voice=TWILIO_GREETING_VOICE
        )

        # Connect to Media Stream
        connect = Connect()
        connect.stream(url=websocket_url)
        response.append(connect)

        return str(response)
