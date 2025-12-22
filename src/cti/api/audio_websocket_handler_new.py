"""
Audio WebSocket Handler - Flexible handler for bidirectional audio streaming
"""

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass, field
from logging import getLogger
from typing import Dict, List, Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from openai import AsyncOpenAI
from openai.resources.realtime.realtime import AsyncRealtimeConnection
from openai.types.realtime import (
    RealtimeServerEvent,
    RealtimeToolsConfigParam,
    session_update_event_param,
    RealtimeFunctionToolParam,
)

from cti.api.audio_types import (
    AudioMessage,
    ControlMessage,
    StartMessage,
    TextMessage,
)
from cti.agents.realtime_agent_orchestrator import RealtimeAgentOrchestrator
from cti.config.constants import LOG_EVENT_TYPES
from cti.config.prompts import SYSTEM_MESSAGE
from cti.config.settings import settings
from cti.core.connection_context import (
    get_audio_record_folder,
    get_connection_language,
    record_audio,
)
from cti.core.session_manager import SessionManager
from cti.services.audio_merge_service import AudioMergeService
from cti.services.tool_service import ToolService
from cti.tools.delegation import DelegateToAgentTool
from langsmith.wrappers import wrap_openai

logger = getLogger(__name__)


@dataclass
class ConnectionState:
    """State container for a WebSocket connection."""

    session_id: Optional[str] = None
    latest_media_timestamp: int = 0
    session_manager: Optional[SessionManager] = None
    last_assistant_item: Optional[str] = None
    response_start_timestamp: Optional[int] = None
    is_paused: bool = False
    last_interruption_time: int = 0
    interruption_cooldown_ms: int = 500
    is_response_active: bool = False
    current_response_id: Optional[str] = None
    openai_audio_chunks: List[str] = field(default_factory=list)
    client_audio_chunks: List[str] = field(default_factory=list)


BOT_INTERRUPT_DELAY = 200


class AudioWebSocketHandler:
    """Handle bidirectional audio WebSocket connections with OpenAI Realtime API."""

    def __init__(self):
        """Initialize the audio websocket handler."""
        self.tool_service = ToolService()
        self.websocket_base_url = self._build_websocket_base_url()
        # self.agent_orchestrator = RealtimeAgentOrchestrator(
        #     self.tool_service, self.websocket_base_url
        # )
        # self.tool_service.register_tool(DelegateToAgentTool(self.agent_orchestrator))
        self.root_agent_instructions = str(SYSTEM_MESSAGE)

    async def handle_connection(self, websocket: WebSocket):
        """Main handler for WebSocket connections."""
        logger.info("Audio client connected")
        await websocket.accept()

        # Get connection_id for audio download URL
        audio_folder = get_audio_record_folder()
        connection_id = audio_folder.name if audio_folder else None

        try:
            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                websocket_base_url=self.websocket_base_url,
            )
            client = wrap_openai(client)
        except Exception as exc:
            logger.info(f"❌ Failed to initialize OpenAI client: {exc}")
            await websocket.close(
                code=1011, reason="OpenAI client initialization failed"
            )
            return

        state = ConnectionState()

        try:
            deployment_name = settings.MODEL
            async with client.realtime.connect(model=deployment_name) as connection:
                await self._initialize_session(connection)

                tasks = [
                    asyncio.create_task(
                        self._realtime_session_loop(connection, websocket, state)
                    ),
                    asyncio.create_task(
                        self._client_message_loop(
                            websocket, connection, state, connection_id
                        )
                    ),
                ]

                try:
                    await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        task.cancel()

        except Exception as exc:
            logger.info(f"❌ Error in OpenAI connection: {exc}", exc_info=True)
            try:
                await websocket.close(
                    code=1011, reason=f"OpenAI connection error: {exc}"
                )
            except Exception:
                pass
        finally:
            if state.session_manager:
                try:
                    state.session_manager.save_to_file()
                    logger.info(
                        f"Session saved: {state.session_id}",
                        extra={"handler": "file"},
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to save session: {exc}", extra={"handler": "file"}
                    )

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

    async def _client_message_loop(
        self,
        websocket: WebSocket,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
        connection_id: Optional[str] = None,
    ):
        """Listen for messages from client WebSocket and handle them."""
        try:
            while True:
                try:
                    raw_message = await websocket.receive()

                    if raw_message.get("type") == "websocket.receive":
                        if "text" in raw_message:
                            message_text = raw_message["text"]
                        elif "bytes" in raw_message:
                            try:
                                message_text = raw_message["bytes"].decode("utf-8")
                            except UnicodeDecodeError:
                                logger.error(
                                    "Received binary data that cannot be decoded as UTF-8",
                                    extra={"handler": "file"},
                                )
                                await websocket.send_json(
                                    {
                                        "event": "error",
                                        "message": "Invalid message format: binary data received",
                                    }
                                )
                                continue
                        else:
                            logger.warning(
                                "Received message without text or bytes",
                                extra={"handler": "file"},
                            )
                            continue
                    elif raw_message.get("type") == "websocket.disconnect":
                        break
                    else:
                        continue

                    try:
                        message: Dict = json.loads(message_text)
                    except json.JSONDecodeError as exc:
                        logger.error(
                            f"Failed to parse client message as JSON: {exc}",
                            extra={"handler": "file"},
                        )
                        await websocket.send_json(
                            {"event": "error", "message": f"Invalid JSON format: {exc}"}
                        )
                        continue

                    await self._handle_client_message(
                        message, connection, websocket, state, connection_id
                    )

                except (KeyError, ValueError, TypeError) as exc:
                    error_msg = self._safe_error_message(exc)
                    logger.error(
                        f"Error parsing message: {error_msg}",
                        extra={"handler": "file"},
                    )
                    try:
                        await websocket.send_json(
                            {
                                "event": "error",
                                "message": f"Invalid message format: {error_msg}",
                            }
                        )
                    except Exception as send_error:
                        logger.error(
                            f"Failed to send error message: {send_error}",
                            extra={"handler": "file"},
                        )

                except Exception as exc:
                    error_msg = self._safe_error_message(exc)
                    logger.error(
                        f"Error in client message loop: {error_msg}",
                        extra={"handler": "file"},
                    )
                    try:
                        await websocket.send_json(
                            {"event": "error", "message": f"Server error: {error_msg}"}
                        )
                    except Exception as send_error:
                        logger.error(
                            f"Failed to send error message: {send_error}",
                            extra={"handler": "file"},
                        )

        except WebSocketDisconnect:
            logger.info("Client disconnected")
        except Exception as exc:
            logger.error(f"Error in client message loop: {exc}", exc_info=True)

    async def _handle_realtime_event(
        self,
        event: RealtimeServerEvent,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle events from the realtime session."""
        event_type = getattr(event, "type", "")

        if event_type == "session.created":
            logger.info(
                f"Session created: {event.model_dump_json()}",
                extra={"handler": "file"},
            )

        if event_type in LOG_EVENT_TYPES:
            try:
                logger.info(
                    f"Received event: {event_type}: {event.model_dump_json()}",
                    extra={"handler": "file"},
                )
            except Exception:
                logger.info(f"Received event: {event_type}", extra={"handler": "file"})

        if event_type == "response.created":
            state.is_response_active = True
            if hasattr(event, "response_id"):
                state.current_response_id = getattr(event, "response_id")
            state.openai_audio_chunks.clear()
            logger.info("Response started", extra={"handler": "file"})
            return

        if event_type == "response.done":
            state.is_response_active = False
            state.current_response_id = None
            logger.info(
                f"Response done detected. OpenAI chunks: {len(state.openai_audio_chunks)}, Client chunks: {len(state.client_audio_chunks)}"
            )

            if state.openai_audio_chunks:
                # Decode each base64 chunk, concatenate bytes, then re-encode
                complete_audio_bytes = b"".join(
                    base64.b64decode(chunk) for chunk in state.openai_audio_chunks
                )
                complete_audio = base64.b64encode(complete_audio_bytes).decode("utf-8")
                record_audio(complete_audio, "openai", state.latest_media_timestamp)
                logger.info(
                    f"Saved OpenAI audio: {len(complete_audio_bytes)} bytes from {len(state.openai_audio_chunks)} chunks"
                )
                state.openai_audio_chunks.clear()

            if state.client_audio_chunks:
                # Decode each base64 chunk, concatenate bytes, then re-encode
                complete_audio_bytes = b"".join(
                    base64.b64decode(chunk) for chunk in state.client_audio_chunks
                )
                complete_client_audio = base64.b64encode(complete_audio_bytes).decode(
                    "utf-8"
                )
                record_audio(
                    complete_client_audio, "client", state.latest_media_timestamp
                )
                logger.info(
                    f"Saved client audio: {len(complete_audio_bytes)} bytes from {len(state.client_audio_chunks)} chunks"
                )
                state.client_audio_chunks.clear()
            else:
                logger.warning("No client audio chunks to save on response.done")
            return

        if event_type == "response.cancelled":
            state.is_response_active = False
            state.current_response_id = None
            logger.info("Response cancelled")
            state.openai_audio_chunks.clear()
            await websocket.send_json({"event": "response.cancelled"})
            await websocket.send_json({"event": "clear"})
            return

        if event_type == "response.function_call_arguments.done":
            await self._handle_function_call(event, connection, state.session_manager)
            return

        if event_type == "response.output_audio.delta" and hasattr(event, "delta"):
            audio_payload = base64.b64encode(base64.b64decode(event.delta)).decode(
                "utf-8"
            )

            state.openai_audio_chunks.append(audio_payload)

            await websocket.send_json(
                {
                    "event": "audio",
                    "payload": audio_payload,
                    "timestamp": state.latest_media_timestamp,
                    "format": "pcm16",
                }
            )

            if (
                hasattr(event, "item_id")
                and event.item_id
                and event.item_id != state.last_assistant_item
            ):
                state.response_start_timestamp = state.latest_media_timestamp
                state.last_assistant_item = event.item_id
            return

        if event_type == "input_audio_buffer.speech_started":
            logger.info("input_audio_buffer.speech_started")
            await self._handle_speech_started(connection, websocket, state)
            return

    async def _handle_client_message(
        self,
        message: Dict,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
        connection_id: str = None,
    ):
        """Handle incoming messages from client."""
        event_type = message.get("event")

        if event_type == "audio":
            await self._handle_audio_event(message, connection, state)
        elif event_type == "start":
            await self._handle_start_event(message, state)
        elif event_type == "text":
            await self._handle_text_message(message, websocket, connection)
        elif event_type == "disconnect":
            await self._handle_disconnect_event(websocket, state, connection_id)
        elif event_type in ("pause", "resume", "stop", "clear"):
            await self._handle_control_message(message, connection, websocket, state)

    async def _handle_audio_event(
        self,
        message: Dict,
        connection: AsyncRealtimeConnection,
        state: ConnectionState,
    ):
        """Handle audio data from client."""
        if state.is_paused:
            return

        audio_msg: AudioMessage = message
        payload = audio_msg.get("payload", "")
        timestamp = audio_msg.get("timestamp", 0)

        if payload:
            state.latest_media_timestamp = timestamp or state.latest_media_timestamp
            state.client_audio_chunks.append(payload)
            # Log every 10th chunk to avoid flooding
            # if len(state.client_audio_chunks) % 10 == 1:
            #     logger.info(f"Client audio chunks accumulated: {len(state.client_audio_chunks)}")
            await connection.input_audio_buffer.append(audio=payload)

    async def _handle_start_event(self, message: Dict, state: ConnectionState):
        """Handle session start event."""
        start_msg: StartMessage = message
        state.session_id = start_msg.get("session_id")
        if not state.session_id:
            state.session_id = str(uuid.uuid4())
        logger.info(
            f"Session started: {state.session_id}, language: {get_connection_language().value}"
        )
        state.session_manager = SessionManager(state.session_id)

    async def _handle_text_message(
        self,
        message: Dict,
        websocket: WebSocket,
        connection: AsyncRealtimeConnection,
    ):
        """Handle text message by sending it to the conversation."""
        text_msg: TextMessage = message
        text = text_msg.get("text", "")

        if not text:
            await websocket.send_json(
                {"event": "error", "message": "Text message is required"}
            )
            return

        try:
            logger.info(f"Sending text message: {text}")
            await connection.conversation.item.create(
                item={
                    "type": "message",
                    "content": [{"text": text, "type": "input_text"}],
                    "role": "user",
                }
            )
            await connection.response.create()
        except Exception as exc:
            logger.info(f"Error sending text message: {exc}")
            await websocket.send_json(
                {"event": "error", "message": f"Failed to send message: {exc}"}
            )

    async def _handle_control_message(
        self,
        message: Dict,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle control messages (pause, resume, stop, clear)."""
        event_type = message.get("event")

        if event_type == "pause":
            state.is_paused = True
        elif event_type == "resume":
            state.is_paused = False
        elif event_type == "stop":
            try:
                await connection.response.cancel()
            except Exception as exc:
                logger.warning(
                    f"Failed to cancel response on stop: {exc}",
                    extra={"handler": "file"},
                )
            await websocket.send_json({"event": "clear"})
        elif event_type == "clear":
            try:
                if hasattr(connection, "input_audio_buffer"):
                    await connection.input_audio_buffer.clear()
            except Exception as exc:
                logger.warning(
                    f"Error clearing input buffer: {exc}", extra={"handler": "file"}
                )

    async def _handle_disconnect_event(
        self,
        websocket: WebSocket,
        state: ConnectionState,
        connection_id: str = None,
    ):
        """Handle disconnect event from client - merge audio and send download URL."""
        logger.info("Received disconnect event from client")

        # Save any remaining audio chunks before merging
        if state.openai_audio_chunks:
            # Decode each base64 chunk, concatenate bytes, then re-encode
            complete_audio_bytes = b"".join(
                base64.b64decode(chunk) for chunk in state.openai_audio_chunks
            )
            complete_audio = base64.b64encode(complete_audio_bytes).decode("utf-8")
            record_audio(complete_audio, "openai", state.latest_media_timestamp)
            state.openai_audio_chunks.clear()
            logger.info("Saved remaining OpenAI audio chunks")

        if state.client_audio_chunks:
            # Decode each base64 chunk, concatenate bytes, then re-encode
            complete_audio_bytes = b"".join(
                base64.b64decode(chunk) for chunk in state.client_audio_chunks
            )
            complete_client_audio = base64.b64encode(complete_audio_bytes).decode(
                "utf-8"
            )
            record_audio(complete_client_audio, "client", state.latest_media_timestamp)
            state.client_audio_chunks.clear()
            logger.info("Saved remaining client audio chunks")

        if connection_id:
            try:
                audio_service = AudioMergeService()
                merged_path = audio_service.merge_audio_files(connection_id)

                if merged_path:
                    audio_url = f"/audio/{connection_id}/download"
                    await websocket.send_json(
                        {
                            "event": "session.ended",
                            "audio_download_url": audio_url,
                            "connection_id": connection_id,
                        }
                    )
                    logger.info(f"Sent audio download URL: {audio_url}")
                else:
                    await websocket.send_json(
                        {
                            "event": "session.ended",
                            "audio_download_url": None,
                            "connection_id": connection_id,
                        }
                    )
                    logger.info(
                        "No audio files to merge, sent session.ended without URL"
                    )
            except Exception as exc:
                logger.error(f"Failed to merge audio or send URL: {exc}")
                await websocket.send_json(
                    {
                        "event": "session.ended",
                        "audio_download_url": None,
                        "connection_id": connection_id,
                        "error": str(exc),
                    }
                )
        else:
            await websocket.send_json(
                {
                    "event": "session.ended",
                    "audio_download_url": None,
                }
            )

    async def _handle_speech_started(
        self,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle speech interruption from user."""
        current_time = state.latest_media_timestamp
        time_since_last_interruption = current_time - state.last_interruption_time

        if time_since_last_interruption < state.interruption_cooldown_ms:
            logger.info(
                f"Ignoring speech_started event (cooldown: {state.interruption_cooldown_ms - time_since_last_interruption}ms remaining)",
                extra={"handler": "file"},
            )
            return

        async def _interrupt_bot_voice():
            # await asyncio.sleep(BOT_INTERRUPT_DELAY)
            await websocket.send_json({"event": "clear"})

        logger.info("Speech started detected", extra={"handler": "file"})

        asyncio.create_task(_interrupt_bot_voice())

        # if state.is_response_active and state.last_assistant_item:
        if True:
            logger.info(
                f"User interrupting active response with id: {state.last_assistant_item}",
                extra={"handler": "file"},
            )
            state.last_interruption_time = current_time

            if state.current_response_id:
                try:
                    await connection.response.cancel()
                except Exception as exc:
                    logger.warning(
                        f"Failed to cancel response: {exc}", extra={"handler": "file"}
                    )

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

    async def _initialize_session(self, connection: AsyncRealtimeConnection):
        """Initialize OpenAI session with PCM16/WAV format."""
        tools: RealtimeToolsConfigParam = self.tool_service.get_tool_definitions()
        session_config: session_update_event_param.Session = {
            "type": "realtime",
            "model": settings.MODEL,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "transcription": {
                        "model": "whisper-1",
                    },
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },
            },
            # "output": {
            #     "voice": settings.VOICE,
            #     "format": {
            #         "type": "audio/pcm",
            #         "rate": 24000,
            #     },
            # },
            "instructions": self.root_agent_instructions,
            "tools": tools,
            "tool_choice": "auto",
        }
        # session_config= session_update_event_param.Session(
        # "type": "realtime",
        # model= settings.MODEL,
        # output_modalities= ["audio"],
        # "audio": {
        #     "input": {
        #         "transcription": {
        #             "model": "whisper-1",
        #         },
        #         "format": {
        #             "type": "audio/pcm",
        #             "rate": 24000,
        #         },
        #         "turn_detection": {
        #             "type": "server_vad",
        #             "threshold": 0.5,
        #             "prefix_padding_ms": 300,
        #             "silence_duration_ms": 200,
        #             "create_response": True,
        #             "interrupt_response": True,
        #         },
        #     },
        #     "output": {
        #         "voice": settings.VOICE,
        #         "format": {
        #             "type": "audio/pcm",
        #             "rate": 24000,
        #         },
        #     },
        # },
        # "instructions": self.root_agent_instructions,
        # "tools": self.tool_service.get_tool_definitions(),
        # "tool_choice": "auto")

        logger.info(
            f"Sending session update: {json.dumps(session_config, ensure_ascii=False)}",
            extra={"handler": "file"},
        )
        await connection.session.update(session=session_config)

    def _build_websocket_base_url(self) -> str:
        """Build WebSocket base URL for OpenAI Realtime API."""
        if settings.OPENAI_BASE_URL.startswith("wss://"):
            return settings.OPENAI_BASE_URL
        endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
        deployment_name = settings.MODEL
        return (
            f"wss://{endpoint}/openai/v1/realtime?"
            f"api-version=2024-10-01-preview&deployment={deployment_name}"
        )

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        """Convert exception to a safe, JSON-serializable error message."""
        try:
            error_msg = str(exc)
            return error_msg.encode("utf-8", errors="replace").decode("utf-8")
        except Exception:
            return "Unknown error occurred"
