"""
Audio WebSocket Handler - Flexible handler for bidirectional audio streaming
"""

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

# Imports removed - now using agents SDK

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
from cti.core.connection_context import get_connection_language, record_audio
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService
from cti.tools.delegation import DelegateToAgentTool
from langsmith.wrappers import wrap_openai

# Import agents SDK components
from agents.realtime import RealtimeRunner
from agents.realtime.model import RealtimeModelConfig
from agents.realtime.config import RealtimeUserInputMessage
from cti.agents.math_agents import get_starting_agent

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
    interruption_cooldown_ms: int = 1000
    is_response_active: bool = False
    current_response_id: Optional[str] = None
    openai_audio_chunks: List[str] = field(default_factory=list)
    client_audio_chunks: List[str] = field(default_factory=list)
    # Agents SDK components
    runner: Optional[RealtimeRunner] = None
    session_context: Optional[Any] = None
    realtime_session: Optional[Any] = None


BOT_INTERRUPT_DELAY = 500


class AudioWebSocketHandler:
    """Handle bidirectional audio WebSocket connections with OpenAI Realtime API."""

    def __init__(self):
        """Initialize the audio websocket handler."""
        # self.tool_service = ToolService()
        self.websocket_base_url = self._build_websocket_base_url()
        # self.agent_orchestrator = RealtimeAgentOrchestrator(
        #     self.tool_service, self.websocket_base_url
        # )
        # self.tool_service.register_tool(DelegateToAgentTool(self.agent_orchestrator))

        # Use Vietnamese instructions for math operations
        self.root_agent_instructions = (
            "Bạn là trợ lý toán học, hãy lắng nghe yêu cầu và giúp người dùng thực hiện các phép tính cơ bản. "
            "Bạn có thể thực hiện: cộng (+), trừ (-), nhân (×), chia (÷). "
            "Khi nghe yêu cầu, hãy xác nhận phép toán và thực hiện. "
            "Ví dụ: '5 cộng 3', '10 trừ 2', '4 nhân 6', '15 chia 3'. "
            "Hãy luôn trả lời bằng tiếng Việt một cách thân thiện và rõ ràng."
        )
        # self.root_agent_instructions = str(SYSTEM_MESSAGE)
        # self.root_agent_instructions = (
        #     "Bạn là Root Call Agent, chịu trách nhiệm thoại với khách và giữ websocket ổn định. "
        #     "Bám sát luồng call-flow: (1) bắt máy, hỏi có đặt cho hôm nay không; (2) nếu hôm nay: hỏi nhân viên ưa thích (gợi ý nữ), hỏi giờ bắt đầu và thời lượng dịch vụ, hỏi ưu tiên địa điểm; "
        #     "(3) nếu ngày khác: hỏi ngày/giờ mong muốn; (4) vào bước kiểm tra khả dụng, báo khách chờ; "
        #     "(5) nếu trống: xin tên + thông tin liên lạc, nhắc lại chi tiết để xác nhận; "
        #     "(6) nếu không trống: đề xuất khung giờ khác trong ngày, nếu hết chỗ thì hỏi có muốn đặt ngày khác. "
        #     "Handoff qua delegate_to_agent: availability_agent (kiểm tra slot, gợi ý giờ thay thế), booking_agent (dựng và gửi payload đặt lịch), data_agent (tra cứu dịch vụ/nhân viên/chi nhánh/khách). "
        #     "Không đọc JSON thô; luôn tóm tắt ngắn gọn, thân thiện."
        # )

    async def handle_connection(self, websocket: WebSocket):
        """Main handler for WebSocket connections using agents SDK."""
        logger.info("=== Audio client connected ===")
        await websocket.accept()

        state = ConnectionState()

        try:
            # Initialize the agents SDK runner
            agent = get_starting_agent()
            logger.info(f"Starting agent: {agent.name}")
            logger.info(
                f"Agent tools: {[tool.name for tool in agent.tools] if agent.tools else 'None'}"
            )
            logger.info(
                f"Agent handoffs: {[h.name for h in agent.handoffs] if agent.handoffs else 'None'}"
            )

            state.runner = RealtimeRunner(agent)

            # Configure model with audio settings
            model_config: RealtimeModelConfig = {
                "initial_model_settings": {
                    "turn_detection": {
                        "type": "server_vad",
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200,
                        "interrupt_response": True,
                        "create_response": True,
                    },
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "transcription": {"model": "whisper-1"},
                        },
                    },
                },
            }

            # Start the session
            logger.info("Starting RealtimeRunner session...")
            state.session_context = await state.runner.run(model_config=model_config)
            state.realtime_session = await state.session_context.__aenter__()
            logger.info("Session initialized successfully")

            tasks = [
                asyncio.create_task(
                    self._agent_session_loop(state.realtime_session, websocket, state)
                ),
                asyncio.create_task(
                    self._client_message_loop(websocket, state.realtime_session, state)
                ),
            ]

            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    task.cancel()

        except Exception as exc:
            logger.info(f"❌ Error in agent connection: {exc}", exc_info=True)
            try:
                await websocket.close(
                    code=1011, reason=f"Agent connection error: {exc}"
                )
            except Exception:
                pass
        finally:
            if state.session_context:
                try:
                    await state.session_context.__aexit__(None, None, None)
                except Exception:
                    pass
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

    async def _agent_session_loop(
        self,
        session: Any,  # RealtimeSession from agents SDK
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Listen for events from the agents SDK session."""
        try:
            async for event in session:
                await self._handle_agent_event(event, websocket, state)
        except Exception as exc:
            logger.error(f"Error in agent session loop: {exc}", exc_info=True)

    async def _client_message_loop(
        self,
        websocket: WebSocket,
        session: Any,  # RealtimeSession from agents SDK
        state: ConnectionState,
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
                        message, session, websocket, state
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

    async def _handle_agent_event(
        self,
        event: Any,  # RealtimeSessionEvent from agents SDK
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle events from the agents SDK session."""
        event_type = getattr(event, "type", "")

        # Log important events with enhanced details
        if event_type in [
            "tool_start",
            "tool_end",
            "agent_start",
            "agent_end",
            "handoff",
        ]:
            logger.info(f"Event received: {event_type}", extra={"handler": "file"})

        # Handle agent events
        if event_type == "agent_start":
            logger.info(
                f"  Agent started: {event.agent.name}", extra={"handler": "file"}
            )
            await websocket.send_json(
                {"event": "agent_start", "agent": event.agent.name}
            )

        elif event_type == "agent_end":
            logger.info(f"  Agent ended: {event.agent.name}", extra={"handler": "file"})
            await websocket.send_json({"event": "agent_end", "agent": event.agent.name})

        elif event_type == "handoff":
            logger.info(
                f"  Handoff: {event.from_agent.name} -> {event.to_agent.name}",
                extra={"handler": "file"},
            )
            await websocket.send_json(
                {
                    "event": "handoff",
                    "from": event.from_agent.name,
                    "to": event.to_agent.name,
                }
            )

        elif event_type == "tool_start":
            logger.info(f"  Tool started: {event.tool.name}", extra={"handler": "file"})
            await websocket.send_json({"event": "tool_start", "tool": event.tool.name})

        elif event_type == "tool_end":
            output_preview = str(event.output)[:100] if event.output else "None"
            logger.info(
                f"  Tool ended: {event.tool.name}, Output: {output_preview}",
                extra={"handler": "file"},
            )
            await websocket.send_json(
                {
                    "event": "tool_end",
                    "tool": event.tool.name,
                    "output": str(event.output),
                }
            )

        elif event_type == "audio":
            # Send audio to client
            audio_payload = base64.b64encode(event.audio.data).decode("utf-8")
            state.openai_audio_chunks.append(audio_payload)

            await websocket.send_json(
                {
                    "event": "audio",
                    "payload": audio_payload,
                    "timestamp": state.latest_media_timestamp,
                    "format": "pcm16",
                }
            )

        elif event_type == "audio_interrupted":
            logger.info("Audio interrupted", extra={"handler": "file"})
            state.is_response_active = False
            state.current_response_id = None
            await websocket.send_json({"event": "clear"})

        elif event_type == "audio_end":
            # Response is complete
            state.is_response_active = False
            state.current_response_id = None
            logger.info("Audio response ended", extra={"handler": "file"})

            # Save audio if needed
            if state.openai_audio_chunks:
                complete_audio = "".join(state.openai_audio_chunks)
                record_audio(complete_audio, "openai", state.latest_media_timestamp)
                state.openai_audio_chunks.clear()

            if state.client_audio_chunks:
                complete_client_audio = "".join(state.client_audio_chunks)
                record_audio(
                    complete_client_audio, "client", state.latest_media_timestamp
                )
                state.client_audio_chunks.clear()

        elif event_type == "error":
            logger.error(f"Agent error: {event.error}", extra={"handler": "file"})
            await websocket.send_json({"event": "error", "message": str(event.error)})

        elif event_type == "input_audio_timeout_triggered":
            logger.info("Input audio timeout triggered", extra={"handler": "file"})

    async def _handle_client_message(
        self,
        message: Dict,
        session: Any,  # RealtimeSession from agents SDK
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Handle incoming messages from client."""
        event_type = message.get("event")

        if event_type == "audio":
            await self._handle_audio_event(message, session, state)
        elif event_type == "start":
            await self._handle_start_event(message, state)
        elif event_type == "text":
            await self._handle_text_message(message, websocket, session)
        elif event_type in ("pause", "resume", "stop", "clear"):
            await self._handle_control_message(message, session, websocket, state)

    async def _handle_audio_event(
        self,
        message: Dict,
        session: Any,  # RealtimeSession from agents SDK
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
            await session.send_audio(base64.b64decode(payload))

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
        session: Any,  # RealtimeSession from agents SDK
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
            user_msg: RealtimeUserInputMessage = {
                "type": "message",
                "role": "user",
                "content": [{"text": text, "type": "input_text"}],
            }
            await session.send_user_message(user_msg)
        except Exception as exc:
            logger.info(f"Error sending text message: {exc}")
            await websocket.send_json(
                {"event": "error", "message": f"Failed to send message: {exc}"}
            )

    async def _handle_control_message(
        self,
        message: Dict,
        session: Any,  # RealtimeSession from agents SDK
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
                await session.interrupt()
            except Exception as exc:
                logger.warning(
                    f"Failed to cancel response on stop: {exc}",
                    extra={"handler": "file"},
                )
            await websocket.send_json({"event": "clear"})
        elif event_type == "clear":
            # Agents SDK doesn't have a direct clear method, but interrupt will stop current response
            try:
                await session.interrupt()
            except Exception as exc:
                logger.warning(
                    f"Error clearing session: {exc}", extra={"handler": "file"}
                )

    async def _handle_speech_started(
        self,
        session: Any,  # RealtimeSession from agents SDK
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
            await asyncio.sleep(BOT_INTERRUPT_DELAY)
            await websocket.send_json({"event": "clear"})

        asyncio.create_task(_interrupt_bot_voice())

        logger.info("Speech started detected", extra={"handler": "file"})

        if state.is_response_active and state.last_assistant_item:
            logger.info(
                f"User interrupting active response with id: {state.last_assistant_item}",
                extra={"handler": "file"},
            )
            state.last_interruption_time = current_time

            if state.current_response_id:
                try:
                    await session.interrupt()
                except Exception as exc:
                    logger.warning(
                        f"Failed to cancel response: {exc}", extra={"handler": "file"}
                    )

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
