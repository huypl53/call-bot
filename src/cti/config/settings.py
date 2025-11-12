"""
Settings cho KIAI Assistant
Sử dụng Pydantic để validate và load từ environment variables
"""

import os
from typing import Optional

from dotenv import load_dotenv

# Load .env file
load_dotenv(override=True)


class Settings:
    """
    Application settings loaded from environment variables.
    Type-safe và có validation.
    """

    def __init__(self):
        # Required settings
        self.OPENAI_API_KEY: str = self._get_required_env("AZURE_OPENAI_API_KEY")
        self.OPENAI_BASE_URL: str = self._get_required_env("AZURE_OPENAI_BASE_URL")
        self.MODEL: str = 'gpt-realtime-mini'

        # Optional settings with defaults
        self.PORT: int = int(os.getenv("PORT", "5050"))
        self.TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.8"))
        self.VOICE: str = os.getenv("VOICE", "alloy")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

        # Validate settings
        self._validate()

    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(
                f"Missing required environment variable: {key}. "
                f"Please set it in the .env file."
            )
        return value

    def _validate(self):
        """Validate settings."""
        if self.PORT < 1 or self.PORT > 65535:
            raise ValueError(f"Invalid PORT: {self.PORT}. Must be between 1-65535.")

        if self.TEMPERATURE < 0 or self.TEMPERATURE > 2:
            raise ValueError(
                f"Invalid TEMPERATURE: {self.TEMPERATURE}. Must be between 0-2."
            )

        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        if self.VOICE not in valid_voices:
            raise ValueError(
                f"Invalid VOICE: {self.VOICE}. Must be one of {valid_voices}"
            )

    def __repr__(self) -> str:
        """String representation (hide sensitive data)."""
        return (
            f"Settings("
            f"PORT={self.PORT}, "
            f"TEMPERATURE={self.TEMPERATURE}, "
            f"VOICE={self.VOICE}, "
            f"DEBUG={self.DEBUG})"
        )


# Global settings instance
settings = Settings()
