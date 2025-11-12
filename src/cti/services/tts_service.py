"""
Text-to-Speech Service - Convert text to audio using OpenAI TTS API
"""

from typing import Optional

from openai import AsyncOpenAI

from cti.config.settings import settings


class TTSService:
    """Service for converting text to audio using OpenAI TTS API"""

    def __init__(self):
        """Initialize TTS service with OpenAI client"""
        # For Azure OpenAI, base_url should be just the base endpoint
        # The SDK will construct the path, but Azure needs /deployments/{model}/audio/speech
        # So we set base_url to point to the deployment endpoint (without /audio/speech)
        base_url = settings.OPENAI_BASE_URL.rstrip("/")
        if not base_url.endswith("/openai/deployments/gpt-4o-mini-tts"):
            base_url = f"{base_url}/openai/deployments/gpt-4o-mini-tts"
        
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=base_url,
            default_query={"api-version": "2025-03-01-preview"}
        )

    async def text_to_audio(
        self, text: str, voice: Optional[str] = None, format: str = "pcm"
    ) -> bytes:
        """
        Convert text to audio using OpenAI TTS API.

        Args:
            text: Text to convert to speech
            voice: Voice to use (defaults to settings.VOICE)
            format: Audio format - "pcm" for 16-bit PCM, "mp3", "opus", "aac", "flac"

        Returns:
            Audio data as bytes (PCM16 format for "pcm")
        """
        if voice is None:
            voice = settings.VOICE

        try:
            response = await self.client.audio.speech.create(
                model="gpt-4o-mini-tts",  # or "tts-1-hd" for higher quality
                voice=voice,
                input=text,
                response_format=format,
            )

            # Read the audio data
            # OpenAI TTS API response has a read() method that returns bytes
            audio_data = response.read()

            return audio_data

        except Exception as e:
            print(f"Error in TTS conversion: {e}")
            raise

    async def text_to_pcm16(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        Convert text to PCM16 audio format.

        Args:
            text: Text to convert to speech
            voice: Voice to use (defaults to settings.VOICE)

        Returns:
            PCM16 audio data as bytes
        """
        return await self.text_to_audio(text, voice, format="pcm")

    async def text_to_wav(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        Convert text to WAV format (PCM16 wrapped in WAV header).

        Args:
            text: Text to convert to speech
            voice: Voice to use (defaults to settings.VOICE)

        Returns:
            WAV audio data as bytes
        """
        pcm_data = await self.text_to_pcm16(text, voice)
        return self._pcm_to_wav(pcm_data)

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000) -> bytes:
        """
        Convert PCM16 data to WAV format by adding WAV header.

        Args:
            pcm_data: Raw PCM16 audio data
            sample_rate: Sample rate in Hz (OpenAI TTS uses 24000 Hz)

        Returns:
            WAV formatted audio data
        """
        import struct

        num_channels = 1  # Mono
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_data)
        file_size = 36 + data_size

        # WAV header
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            file_size,
            b"WAVE",
            b"fmt ",
            16,  # fmt chunk size
            1,  # audio format (PCM)
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )

        return wav_header + pcm_data
