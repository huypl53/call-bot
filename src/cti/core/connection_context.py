"""
Connection Context Manager - Manages per-connection context with audio recording and logging
"""

import base64
import contextvars
import logging
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

from cti.config.settings import Language, settings

# Context variables
audio_record_folder: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "audio_record_folder", default=None
)
context_logger: contextvars.ContextVar[Optional[logging.Logger]] = contextvars.ContextVar(
    "context_logger", default=None
)
connection_language: contextvars.ContextVar[Optional[Language]] = contextvars.ContextVar(
    "connection_language", default=None
)


class ConnectionContext:
    """Context manager for WebSocket connections with audio recording and logging"""

    def __init__(self, connection_id: Optional[str] = None, language: Optional[Language] = None):
        """
        Initialize connection context.

        Args:
            connection_id: Optional connection ID. If not provided, a UUID will be generated.
            language: Optional language for this connection. If not provided, uses settings.LANGUAGE.
        """
        self.connection_id = connection_id or str(uuid.uuid4())
        self.record_folder: Optional[Path] = None
        self.logger: Optional[logging.Logger] = None
        self.language = language or settings.LANGUAGE
        self.original_language: Optional[Language] = None
        self.original_language_str: Optional[str] = None

    def __enter__(self):
        """Enter context and set up folder and logger"""
        # Create record folder
        base_dir = Path("audio_records")
        base_dir.mkdir(exist_ok=True)
        self.record_folder = base_dir / self.connection_id
        self.record_folder.mkdir(exist_ok=True)

        # Create context logger
        self.logger = logging.getLogger(f"connection.{self.connection_id}")
        self.logger.setLevel(logging.DEBUG)
        # Prevent propagation to root logger to avoid duplicate logs
        self.logger.propagate = False

        # Create file handler for this connection
        log_file = self.record_folder / "connection.log"
        file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # Use same format as main logger
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Create a handler that forwards all root logger messages to context logger
        class ContextForwardHandler(logging.Handler):
            """Handler that forwards logs to context logger"""
            
            def emit(self, record: logging.LogRecord):
                """Forward log record to context logger"""
                ctx_logger = context_logger.get()
                if ctx_logger:
                    try:
                        # Skip if this record was already processed by context logger
                        # to avoid duplicates
                        if hasattr(record, 'from_context_logger'):
                            return
                        
                        # Create a new record with context logger name
                        new_record = logging.LogRecord(
                            name=ctx_logger.name,
                            level=record.levelno,
                            pathname=record.pathname,
                            lineno=record.lineno,
                            msg=record.getMessage(),
                            args=(),
                            exc_info=record.exc_info,
                        )
                        new_record.from_context_logger = True
                        ctx_logger.handle(new_record)
                    except Exception:
                        pass  # Silently ignore errors in forwarding

        # Add handler to root logger to capture all logs
        root_logger = logging.getLogger()
        self.context_forward_handler = ContextForwardHandler()
        self.context_forward_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(self.context_forward_handler)

        # Save original language and update global settings
        self.original_language = settings.LANGUAGE
        self.original_language_str = settings.language_str
        
        # Update global settings.LANGUAGE if different
        if self.language != self.original_language:
            settings.LANGUAGE = self.language
            settings.language_str = self.language.value
            self.logger.info(f"Updated global settings.LANGUAGE from {self.original_language.value} to {self.language.value}")

        # Set context variables
        audio_record_folder.set(self.record_folder)
        context_logger.set(self.logger)
        connection_language.set(self.language)

        self.logger.info(f"Connection context initialized: {self.connection_id}, language: {self.language.value}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and clean up"""
        if self.logger:
            self.logger.info(f"Connection context closing: {self.connection_id}")
            # Remove handlers to prevent memory leaks
            for handler in self.logger.handlers[:]:
                handler.close()
                self.logger.removeHandler(handler)

        # Remove context forward handler from root logger
        if hasattr(self, "context_forward_handler"):
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.context_forward_handler)
            self.context_forward_handler.close()

        # Restore original language in global settings
        if self.original_language is not None and self.original_language_str is not None:
            settings.LANGUAGE = self.original_language
            settings.language_str = self.original_language_str
            if self.logger:
                self.logger.info(f"Restored global settings.LANGUAGE to {self.original_language.value}")

        # Clear context variables
        audio_record_folder.set(None)
        context_logger.set(None)
        connection_language.set(None)

        return False  # Don't suppress exceptions


def get_audio_record_folder() -> Optional[Path]:
    """Get the current audio record folder from context"""
    return audio_record_folder.get()


def get_context_logger() -> Optional[logging.Logger]:
    """Get the current context logger from context"""
    return context_logger.get()


def get_connection_language() -> Language:
    """
    Get the current connection language from context.
    
    Returns:
        Language enum value. Falls back to settings.LANGUAGE if not set.
    """
    # Since we update global settings.LANGUAGE, we can use it directly
    return settings.LANGUAGE


def log_to_context(level: str, message: str, *args, **kwargs):
    """
    Log to both regular logger and context logger if available.
    
    Args:
        level: Log level ('info', 'debug', 'error', 'warning', 'warn')
        message: Log message
        *args: Additional positional arguments for message formatting
        **kwargs: Additional keyword arguments for logging
    """
    ctx_logger = context_logger.get()
    if ctx_logger:
        log_func = getattr(ctx_logger, level.lower(), None)
        if log_func:
            try:
                if args:
                    log_func(message % args, **kwargs)
                else:
                    log_func(message, **kwargs)
            except Exception:
                # Fallback if formatting fails
                log_func(str(message), **kwargs)


def record_audio(audio_data: str, source: str, timestamp: Optional[int] = None):
    """
    Record audio data to file using current context.

    Args:
        audio_data: Base64-encoded audio data
        source: Source of audio ('client', 'twilio', or 'openai')
        timestamp: Optional timestamp in milliseconds
    """
    folder = audio_record_folder.get()
    logger = context_logger.get()
    
    if not folder or not logger:
        return

    # Normalize source name
    if source in ("client", "twilio"):
        source_key = "client"
    elif source == "openai":
        source_key = "openai"
    else:
        source_key = source

    # Get current timestamp
    now = datetime.now()

    # Create filename with timestamp and counter
    # Use a simple counter file to track per-source counters
    counter_file = folder / f".{source_key}_counter"
    try:
        if counter_file.exists():
            counter = int(counter_file.read_text().strip()) + 1
        else:
            counter = 1
        counter_file.write_text(str(counter))
    except Exception:
        counter = 1

    # Format: YYYY-MM-DD_HH-MM-SS_mmm_source_counter.wav (human-readable)
    filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{now.microsecond//1000:03d}_{source_key}_{counter:04d}.wav"
    audio_file = folder / filename

    try:
        # Decode base64 audio data to PCM16 bytes
        pcm_data = base64.b64decode(audio_data)
        
        # Convert PCM16 to WAV format using wave module
        # Parameters: (nchannels, sampwidth, framerate, nframes, comptype, compname)
        # nchannels=1 for mono, sampwidth=2 for 16-bit (2 bytes per sample)
        sample_rate = 24000  # OpenAI uses 24000 Hz
        with wave.open(str(audio_file), 'wb') as wav_file:
            wav_file.setparams((1, 2, sample_rate, 0, 'NONE', 'NONE'))
            wav_file.writeframes(pcm_data)

        logger.debug(
            f"Recorded audio chunk: {filename} (source={source}, size={len(pcm_data)} bytes PCM, {len(audio_data)} bytes base64)"
        )
    except Exception as e:
        logger.error(f"Failed to record audio: {e}", exc_info=True)

