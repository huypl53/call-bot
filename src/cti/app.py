"""
KIAI Assistant - Main Application
Entry point cho FastAPI application
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from cti.api.audio_websocket_handler import AudioWebSocketHandler

# from cti.api.audio_websocket_handler_new import AudioWebSocketHandler
from cti.api.routes import router

# from cti.api.websocket_handler import WebSocketHandler
from cti.api.websocket_handler_new import WebSocketHandler
from cti.config.settings import Language, settings
from cti.core.connection_context import ConnectionContext

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Add handler if none exists
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )

    # Console handler with filter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    def console_filter(record):
        """Only log to console if handler is not specified or is 'console'"""
        handler = getattr(record, "handler", None)
        return handler is None or handler == "console"

    console_handler.addFilter(console_filter)
    logger.addHandler(console_handler)

    # File handler with filter
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "app.log"
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    def file_filter(record):
        """Only log to file if handler is not specified or is 'file'"""
        handler = getattr(record, "handler", None)
        return handler is None or handler == "file"

    file_handler.addFilter(file_filter)
    logger.addHandler(file_handler)

# Initialize FastAPI app
app = FastAPI(
    title="KIAI Assistant API",
    description="Trợ lý ảo đặt phòng khách sạn sử dụng OpenAI Realtime API",
    version="2.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

# Serve the web client (HTML/JS) from /web
web_client_dir = Path(__file__).resolve().parents[2] / "web_client"
app.mount("/web", StaticFiles(directory=web_client_dir, html=True), name="web_client")

# Initialize WebSocket handlers
ws_handler = WebSocketHandler()
audio_ws_handler = AudioWebSocketHandler()


@app.websocket("/media-stream")
async def media_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.

    Args:
        websocket: FastAPI WebSocket connection
    """
    # Extract language from query parameters
    language = settings.LANGUAGE  # Default to settings
    language_param = websocket.query_params.get("language")
    if language_param:
        try:
            language = Language(language_param.lower())
        except ValueError:
            logger.warning(
                f"Invalid language parameter: {language_param}. Using default: {settings.LANGUAGE.value}"
            )

    with ConnectionContext(language=language):
        logger.info(
            "Media stream endpoint connected: %s, language: %s",
            websocket.client.host,
            language.value,
        )
        await ws_handler.handle_connection(websocket)


@app.websocket("/audio-stream")
async def audio_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for flexible bidirectional audio streaming.

    Args:
        websocket: FastAPI WebSocket connection
    """
    # Extract language from query parameters
    language = settings.LANGUAGE  # Default to settings
    language_param = websocket.query_params.get("language")
    if language_param:
        try:
            language = Language(language_param.lower())
        except ValueError:
            logger.warning(
                f"Invalid language parameter: {language_param}. Using default: {settings.LANGUAGE.value}"
            )

    with ConnectionContext(language=language):
        logger.info(
            "Audio stream endpoint connected: %s, language: %s",
            websocket.client.host,
            language.value,
        )
        await audio_ws_handler.handle_connection(websocket)


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    print("=" * 60)
    print("🚀 KIAI Assistant Starting...")
    print("=" * 60)
    print(f"📊 Settings: {settings}")
    print(f"🔧 Available tools: {ws_handler.tool_service.available_tools}")
    print(f"🌐 Server will run on port: {settings.PORT}")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    print("\n" + "=" * 60)
    print("👋 KIAI Assistant Shutting down...")
    print("=" * 60)
