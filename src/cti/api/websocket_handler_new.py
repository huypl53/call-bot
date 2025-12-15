"""
WebSocket Handler - streamlined Twilio/OpenAI bridge following the realtime flow demo
"""

import asyncio
import base64
import json
import os
import time
from dataclasses import dataclass, field
from logging import getLogger
from typing import Dict, List, Optional, Tuple

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from openai import AsyncOpenAI
from openai.resources.realtime.realtime import AsyncRealtimeConnection
from openai.types.realtime import RealtimeServerEvent, session_update_event_param

from cti.config.constants import LOG_EVENT_TYPES
from cti.config.prompts import SYSTEM_MESSAGE
from cti.config.settings import settings
from cti.core.connection_context import record_audio
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService

logger = getLogger(__name__)


@dataclass
class ConnectionState:
    stream_sid: Optional[str] = None
    latest_media_timestamp: int = 0
    session_manager: Optional[SessionManager] = None
    mark_counter: int = 0
    mark_data: Dict[str, Tuple[Optional[str], int, int]] = field(default_factory=dict)
    audio_buffer: bytearray = field(default_factory=bytearray)
    startup_buffer: bytearray = field(default_factory=bytearray)
    startup_target_bytes: int = 0
    startup_warmed: bool = False
    last_buffer_send_time: float = field(default_factory=time.time)
    twilio_audio_chunks: List[str] = field(default_factory=list)
    openai_audio_chunks: List[str] = field(default_factory=list)


class WebSocketHandler:
    """Handle WebSocket connections between Twilio and OpenAI."""

    def __init__(self):
        self.tool_service = ToolService()
        self.CHUNK_LENGTH_S = 0.05  # 50ms chunks
        self.SAMPLE_RATE = 8000
        self.BUFFER_SIZE_BYTES = int(self.SAMPLE_RATE * self.CHUNK_LENGTH_S)

        try:
            self.STARTUP_BUFFER_CHUNKS = max(
                0, int(os.getenv("TWILIO_STARTUP_BUFFER_CHUNKS", "3"))
            )
        except Exception:
            self.STARTUP_BUFFER_CHUNKS = 3

        try:
            self.STARTUP_DELAY_S = float(os.getenv("TWILIO_STARTUP_DELAY_S", "0.0"))
        except Exception:
            self.STARTUP_DELAY_S = 0.0

    async def handle_connection(self, websocket: WebSocket):
        """Main handler for WebSocket connections."""
        logger.info("Client connected")
        await websocket.accept()

        websocket_base_url = self._build_websocket_base_url()

        try:
            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY, websocket_base_url=websocket_base_url
            )
        except Exception as exc:
            logger.info(f"❌ Failed to initialize OpenAI client: {exc}")
            await websocket.close(code=1011, reason="OpenAI client initialization failed")
            return

        state = self._build_state()

        try:
            deployment_name = settings.MODEL
            async with client.realtime.connect(model=deployment_name) as connection:
                await self._initialize_session(connection)

                if self.STARTUP_DELAY_S > 0:
                    await asyncio.sleep(self.STARTUP_DELAY_S)

                tasks = [
                    asyncio.create_task(
                        self._realtime_session_loop(connection, websocket, state)
                    ),
                    asyncio.create_task(
                        self._twilio_message_loop(websocket, connection, state)
                    ),
                    asyncio.create_task(self._buffer_flush_loop(connection, state)),
                ]

                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        task.cancel()

        except Exception as exc:
            logger.info(f"❌ Error in OpenAI connection: {exc}", exc_info=True)
            try:
                await websocket.close(code=1011, reason=f"OpenAI connection error: {exc}")
            except Exception:
                pass
        finally:
            if state.session_manager:
                try:
                    state.session_manager.save_to_file()
                    logger.info(
                        f"Session saved: {state.session_manager.stream_sid}",
                        extra={"handler": "file"},
                    )
                except Exception as exc:
                    logger.error(f"Failed to save session: {exc}", extra={"handler": "file"})

    async def _realtime_session_loop(
        self,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Listen for events from the realtime session."""
        try:
            async for event in connection:
                await self._handle_realtime_event(event, connection, websocket, state)
        except Exception as exc:
            logger.error(f"Error in realtime session loop: {exc}", exc_info=True)

    async def _twilio_message_loop(
        self,
        websocket: WebSocket,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Listen for messages from Twilio WebSocket and handle them."""
        try:
            async for message_text in websocket.iter_text():
                try:
                    message = json.loads(message_text)
                except json.JSONDecodeError as exc:
                    logger.error(f"Failed to parse Twilio message as JSON: {exc}")
                    continue
                await self._handle_twilio_message(message, connection, state)
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        except Exception as exc:
            logger.error(f"Error in Twilio message loop: {exc}", exc_info=True)

    async def _handle_realtime_event(
        self,
        event: RealtimeServerEvent,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle events from the realtime session."""
        event_type = getattr(event, "type", "")

        if event_type in LOG_EVENT_TYPES:
            try:
                logger.info(
                    f"Received event: {event_type}: {event.model_dump_json()}",
                    extra={"handler": "file"},
                )
            except Exception:
                logger.info(f"Received event: {event_type}", extra={"handler": "file"})

        if event_type == "response.function_call_arguments.done":
            await self._handle_function_call(event, connection, state.session_manager)
            return

        if event_type == "response.output_audio.delta" and hasattr(event, "delta"):
            audio_payload = event.delta
            state.openai_audio_chunks.append(audio_payload)

            if state.stream_sid:
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": state.stream_sid,
                        "media": {"payload": audio_payload},
                    }
                )

                state.mark_counter += 1
                mark_id = str(state.mark_counter)
                try:
                    byte_count = len(base64.b64decode(audio_payload))
                except Exception:
                    byte_count = 0
                state.mark_data[mark_id] = (
                    getattr(event, "item_id", None),
                    getattr(event, "content_index", 0),
                    byte_count,
                )

                await websocket.send_json(
                    {
                        "event": "mark",
                        "streamSid": state.stream_sid,
                        "mark": {"name": mark_id},
                    }
                )
            return

        if event_type == "input_audio_buffer.cleared" and state.stream_sid:
            await websocket.send_json({"event": "clear", "streamSid": state.stream_sid})
            return

        if event_type == "response.done":
            if state.openai_audio_chunks:
                complete_audio = "".join(state.openai_audio_chunks)
                record_audio(complete_audio, "openai", state.latest_media_timestamp)
                state.openai_audio_chunks.clear()
            return

    async def _handle_twilio_message(
        self,
        message: Dict,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Handle incoming messages from Twilio Media Stream."""
        event = message.get("event")

        if event == "connected":
            logger.info("Twilio media stream connected")
        elif event == "start":
            start_data = message.get("start", {})
            state.stream_sid = start_data.get("streamSid")
            logger.info(f"Media stream started with SID: {state.stream_sid}")
            if state.stream_sid:
                state.session_manager = SessionManager(state.stream_sid)
        elif event == "media":
            await self._handle_media_event(message, connection, state)
        elif event == "mark":
            await self._handle_mark_event(message, state)
        elif event in ("stop", "closed"):
            logger.info("Media stream stopped")
            if state.twilio_audio_chunks:
                complete_audio = "".join(state.twilio_audio_chunks)
                record_audio(complete_audio, "twilio", state.latest_media_timestamp)
                state.twilio_audio_chunks.clear()

    async def _handle_media_event(
        self,
        message: Dict,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Handle audio data from Twilio - buffer it before sending to OpenAI."""
        media = message.get("media", {})
        payload = media.get("payload", "")
        timestamp = media.get("timestamp")

        if timestamp is not None:
            try:
                state.latest_media_timestamp = int(timestamp)
            except Exception:
                state.latest_media_timestamp = 0

        if not payload:
            return

        state.twilio_audio_chunks.append(payload)

        try:
            ulaw_bytes = base64.b64decode(payload)
        except Exception as exc:
            logger.error(f"Error decoding audio from Twilio: {exc}")
            return

        state.audio_buffer.extend(ulaw_bytes)

        if len(state.audio_buffer) >= self.BUFFER_SIZE_BYTES:
            await self._flush_audio_buffer(connection, state)

    async def _handle_mark_event(self, message: Dict, state: ConnectionState):
        """Handle mark events from Twilio to update playback tracker."""
        mark_data = message.get("mark", {})
        mark_id = mark_data.get("name", "")

        if mark_id in state.mark_data:
            state.mark_data.pop(mark_id, None)

    async def _flush_audio_buffer(
        self,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Send buffered audio to OpenAI with deterministic startup warm-up."""
        if not state.audio_buffer:
            return

        buffer_data = bytes(state.audio_buffer)
        state.audio_buffer.clear()
        state.last_buffer_send_time = time.time()

        if not state.startup_warmed:
            state.startup_buffer.extend(buffer_data)
            if len(state.startup_buffer) < state.startup_target_bytes:
                return

            audio_payload = base64.b64encode(bytes(state.startup_buffer)).decode("utf-8")
            state.startup_buffer.clear()
            state.startup_warmed = True
        else:
            audio_payload = base64.b64encode(buffer_data).decode("utf-8")

        try:
            await connection.input_audio_buffer.append(audio=audio_payload)
        except Exception as exc:
            logger.error(f"Error sending buffered audio to OpenAI: {exc}")

    async def _buffer_flush_loop(
        self,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Periodically flush audio buffer to prevent stale data."""
        try:
            while True:
                await asyncio.sleep(self.CHUNK_LENGTH_S)
                current_time = time.time()
                if (
                    state.audio_buffer
                    and current_time - state.last_buffer_send_time > self.CHUNK_LENGTH_S * 2
                ):
                    await self._flush_audio_buffer(connection, state)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error(f"Error in buffer flush loop: {exc}", exc_info=True)

    async def _initialize_session(self, connection: AsyncRealtimeConnection):
        """Initialize OpenAI session with tools."""
        session_config: session_update_event_param.Session = {
            "type": "realtime",
            "model": settings.MODEL,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },
                "output": {"format": {"type": "audio/pcmu"}, "voice": settings.VOICE},
            },
            "instructions": str(SYSTEM_MESSAGE),
            "tools": self.tool_service.get_tool_definitions(),
            "tool_choice": "auto",
        }
        logger.info(
            f"Sending session update: {json.dumps(session_config, ensure_ascii=False)}",
            extra={"handler": "file"},
        )
        await connection.session.update(session=session_config)

    async def _handle_function_call(
        self,
        event: RealtimeServerEvent,
        connection: AsyncRealtimeConnection,
        session_manager: Optional[SessionManager],
    ):
        """Handle function call from OpenAI."""
        call_id = getattr(event, "call_id", None)
        function_name = getattr(event, "name", None)
        arguments_str = getattr(event, "arguments", "{}")

        logger.info(
            f"Function call received: name={function_name}, call_id={call_id}",
            extra={"handler": "file"},
        )

        try:
            arguments = json.loads(arguments_str)
            if session_manager:
                result = await self.tool_service.execute_tool(
                    function_name, arguments, session_manager
                )
            else:
                result = {"error": "Session manager not initialized", "success": False}

            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )
            await connection.response.create()
        except json.JSONDecodeError as exc:
            logger.error(
                f"Failed to parse function call arguments: {exc}",
                extra={"handler": "file"},
            )
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": f"Invalid JSON arguments: {exc}", "success": False},
                        ensure_ascii=False,
                    ),
                }
            )
            await connection.response.create()
        except Exception as exc:
            logger.error(f"Error handling function call: {exc}", exc_info=True)
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": str(exc), "success": False}, ensure_ascii=False
                    ),
                }
            )
            await connection.response.create()

    def _build_state(self) -> ConnectionState:
        state = ConnectionState()
        state.startup_warmed = self.STARTUP_BUFFER_CHUNKS == 0
        state.startup_target_bytes = self.BUFFER_SIZE_BYTES * max(
            0, self.STARTUP_BUFFER_CHUNKS
        )
        return state

    def _build_websocket_base_url(self) -> str:
        if settings.OPENAI_BASE_URL.startswith("wss://"):
            return settings.OPENAI_BASE_URL
        endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
        deployment_name = settings.MODEL
        return (
            f"wss://{endpoint}/openai/v1/realtime?"
            f"api-version=2024-10-01-preview&deployment={deployment_name}"
        )
