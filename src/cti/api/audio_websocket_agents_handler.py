"""
Audio WebSocket Handler - Flexible handler for bidirectional audio streaming
"""

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple, cast

from agents.realtime import RealtimeRunner, RealtimeSession
from agents.realtime.config import RealtimeUserInputMessage
from agents.realtime.model import RealtimeModelConfig
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from cti.agents.booking_agents import FlowAgentContext, get_starting_agent
from cti.api.audio_types import AudioMessage, StartMessage, TextMessage
from cti.core.connection_context import (
    get_audio_record_folder,
    get_connection_language,
    record_audio,
    set_session_manager,
)
from cti.core.session_manager import SessionManager
from cti.services.audio_merge_service import AudioMergeService
from cti.services.dynamic_prompt_service import DynamicPromptService, FlowState

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
    recording_chunks: List[Tuple[str, str]] = field(default_factory=list)
    current_flow_state: FlowState = FlowState.GREETING
    booking_context: Dict[str, Any] = field(default_factory=dict)
    agent_state_by_name: Dict[str, FlowState] = field(default_factory=dict)
    # Agents SDK components
    runner: Optional[RealtimeRunner] = None
    session_context: Optional[RealtimeSession] = None
    realtime_session: Optional[RealtimeSession] = None


BOT_INTERRUPT_DELAY = 200


class AudioWebSocketHandler:
    """Handle bidirectional audio WebSocket connections with OpenAI Realtime API."""

    def __init__(self):
        """Initialize the audio websocket handler."""
        self.prompt_service = DynamicPromptService()

    async def handle_connection(self, websocket: WebSocket):
        """Main handler for WebSocket connections using agents SDK."""
        logger.info("=== Audio client connected ===")
        await websocket.accept()

        audio_folder = get_audio_record_folder()
        connection_id = audio_folder.name if audio_folder else None

        state = ConnectionState()

        try:
            # Initialize the agents SDK runner
            agent, agents_by_state = get_starting_agent(self.prompt_service)
            flow_context = FlowAgentContext(
                state=state,
                prompt_service=self.prompt_service,
                agents_by_state=agents_by_state,
            )
            state.agent_state_by_name = {
                agent_instance.name: flow_state
                for flow_state, agent_instance in agents_by_state.items()
            }
            logger.info(f"Starting agent: {agent.name}")
            logger.info(
                f"Agent tools: {[tool.name for tool in agent.tools] if agent.tools else 'None'}"
            )
            logger.info(
                f"Flow agents: {[flow_state.value for flow_state in agents_by_state]}"
            )

            # Initialize session manager early so tools can access it
            state.session_id = str(uuid.uuid4())
            state.session_manager = SessionManager(state.session_id)
            set_session_manager(state.session_manager)
            logger.info(f"Session manager initialized: {state.session_id}")

            state.runner = RealtimeRunner(
                starting_agent=agent,
                config={
                    "model_settings": {
                        "model_name": "gpt-realtime",
                        "voice": "ash",
                        "modalities": ["audio"],
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "input_audio_transcription": {
                            "model": "gpt-4o-mini-transcribe"
                        },
                        "turn_detection": {
                            "type": "semantic_vad",
                            "interrupt_response": True,
                        },
                    }
                },
            )

            # Configure model with audio settings
            model_config: RealtimeModelConfig = cast(
                RealtimeModelConfig,
                {
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
                },
            )

            # Start the session
            logger.info("Starting RealtimeRunner session...")
            session_context: RealtimeSession = await state.runner.run(
                context=flow_context, model_config=model_config
            )
            state.session_context = session_context
            state.realtime_session = await state.session_context.__aenter__()
            flow_context.session = state.realtime_session
            logger.info("Session initialized successfully")

            tasks = [
                asyncio.create_task(
                    self._agent_session_loop(state.realtime_session, websocket, state)
                ),
                asyncio.create_task(
                    self._client_message_loop(
                        websocket, state.realtime_session, state, connection_id
                    )
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
        session: RealtimeSession,  # RealtimeSession from agents SDK
        websocket: WebSocket,
        state: ConnectionState,
    ):
        """Listen for events from the agents SDK session."""
        try:
            async for event in session:
                await self._handle_agent_event(event, session, websocket, state)
        except Exception as exc:
            logger.error(f"Error in agent session loop: {exc}", exc_info=True)

    async def _client_message_loop(
        self,
        websocket: WebSocket,
        session: RealtimeSession,  # RealtimeSession from agents SDK
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
                        await session.close()
                        logger.debug("Session closed due to websocket disconnected")
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
                        message, session, websocket, state, connection_id
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
        session: RealtimeSession,  # RealtimeSession from agents SDK
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
            target_state = state.agent_state_by_name.get(event.to_agent.name)
            if target_state and target_state != state.current_flow_state:
                previous_state = state.current_flow_state
                state.current_flow_state = target_state
                await websocket.send_json(
                    {
                        "event": "state_changed",
                        "previous_state": previous_state.value,
                        "new_state": target_state.value,
                        "reason": "handoff",
                    }
                )

        elif event_type == "tool_start":
            logger.info(f"  Tool started: {event.tool.name}", extra={"handler": "file"})
            await websocket.send_json({"event": "tool_start", "tool": event.tool.name})

        elif event_type == "tool_end":
            output_preview = str(event.output) if event.output else "None"
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
            state.is_response_active = True
            # Send audio to client
            audio_payload = base64.b64encode(event.audio.data).decode("utf-8")
            state.openai_audio_chunks.append(audio_payload)
            state.recording_chunks.append(("openai", audio_payload))

            item_id = getattr(event, "item_id", None)
            if item_id and item_id != state.last_assistant_item:
                state.response_start_timestamp = state.latest_media_timestamp
                state.last_assistant_item = item_id
            elif not item_id and state.last_assistant_item is None:
                state.last_assistant_item = "assistant_audio"

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
            # state.is_response_active = False
            state.current_response_id = None
            await self._flush_recording_buffer(state)
            await websocket.send_json({"event": "response.cancelled"})
            await websocket.send_json({"event": "clear"})

        elif event_type == "audio_end":
            # Response is complete
            state.is_response_active = False
            state.current_response_id = None
            logger.info("Audio response ended", extra={"handler": "file"})
            await self._flush_recording_buffer(state)

        elif event_type == "conversation.item.input_audio_transcription.completed" and (
            transcript := getattr(event, "transcript", None)
        ):
            logger.info(f"USER transcription: {transcript}")
            try:
                await websocket.send_json(
                    {
                        "event": "transcription",
                        "transcript": f"USER:\t{transcript}",
                        "timestamp": state.latest_media_timestamp,
                    }
                )
            except Exception as exc:
                logger.info(f"Failed to forward USER transcription: {exc}")

        elif event_type == "response.output_audio_transcript.done" and (
            transcript := getattr(event, "transcript", None)
        ):
            logger.info(f"AI transcription: {transcript}")
            try:
                await websocket.send_json(
                    {
                        "event": "transcription",
                        "transcript": f"AI:\t{transcript}",
                        "timestamp": state.latest_media_timestamp,
                    }
                )
            except Exception as exc:
                logger.info(f"Failed to forward AI transcription: {exc}")

        elif event_type == "input_audio_buffer.speech_started":
            logger.info("input_audio_buffer.speech_started", extra={"handler": "file"})
            await self._handle_speech_started(session, websocket, state)

        elif event_type == "error":
            logger.error(f"Agent error: {event.error}", extra={"handler": "file"})
            await websocket.send_json({"event": "error", "message": str(event.error)})

        elif event_type == "input_audio_timeout_triggered":
            logger.info("Input audio timeout triggered", extra={"handler": "file"})

        elif event_type == "history_updated":
            # Send full sanitized conversation history
            history = getattr(event, "history", [])
            sanitized_history = [self._sanitize_history_item(item) for item in history]
            logger.debug(f"history_updated: {sanitized_history}")
            await websocket.send_json(
                {"event": "history_updated", "history": sanitized_history}
            )

        elif event_type == "history_added":
            # Send individual item as it's added (for incremental UI updates)
            item = getattr(event, "item", None)
            if item:
                try:
                    sanitized_item = self._sanitize_history_item(item)
                    await websocket.send_json(
                        {"event": "history_added", "item": sanitized_item}
                    )
                    logger.debug(f"history_updated: {sanitized_item}")
                except Exception as exc:
                    logger.warning(f"Failed to sanitize history item: {exc}")
                    await websocket.send_json({"event": "history_added", "item": None})

    def _sanitize_history_item(self, item: Any) -> Dict[str, Any]:
        """Remove large binary payloads from history items while keeping transcripts."""
        # Handle both dict and object with model_dump method
        if hasattr(item, "model_dump"):
            item_dict: Dict[str, Any] = item.model_dump()
        elif isinstance(item, dict):
            item_dict = item.copy()
        else:
            item_dict = {"raw": str(item)}

        content = item_dict.get("content")
        if isinstance(content, list):
            sanitized_content: List[Any] = []
            for part in content:
                if isinstance(part, dict):
                    sanitized_part = part.copy()
                    # Remove binary audio data but keep transcripts
                    if sanitized_part.get("type") in {"audio", "input_audio"}:
                        sanitized_part.pop("audio", None)
                    sanitized_content.append(sanitized_part)
                else:
                    sanitized_content.append(part)
            item_dict["content"] = sanitized_content
        return item_dict

    async def _handle_client_message(
        self,
        message: Dict,
        session: RealtimeSession,  # RealtimeSession from agents SDK
        websocket: WebSocket,
        state: ConnectionState,
        connection_id: Optional[str] = None,
    ):
        """Handle incoming messages from client."""
        event_type = message.get("event")

        if event_type == "audio":
            await self._handle_audio_event(message, session, state)
        elif event_type == "start":
            await self._handle_start_event(message, state)
        elif event_type == "text":
            await self._handle_text_message(message, websocket, session)
        elif event_type == "disconnect":
            await self._handle_disconnect_event(websocket, state, connection_id)
        elif event_type in ("pause", "resume", "stop", "clear"):
            await self._handle_control_message(message, session, websocket, state)

    async def _handle_audio_event(
        self,
        message: Dict,
        session: RealtimeSession,  # RealtimeSession from agents SDK
        state: ConnectionState,
    ):
        """Handle audio data from client."""
        if state.is_paused:
            return

        audio_msg = cast(AudioMessage, message)
        payload = audio_msg.get("payload", "")
        timestamp = audio_msg.get("timestamp", 0)

        if payload:
            state.latest_media_timestamp = timestamp or state.latest_media_timestamp
            state.client_audio_chunks.append(payload)
            state.recording_chunks.append(("client", payload))
            await session.send_audio(base64.b64decode(payload))

    async def _flush_recording_buffer(self, state: ConnectionState):
        """Persist accumulated mixed audio (client + openai) in arrival order."""
        if not state.recording_chunks:
            state.openai_audio_chunks.clear()
            state.client_audio_chunks.clear()
            return

        try:
            combined_bytes = b"".join(
                base64.b64decode(chunk) for _, chunk in state.recording_chunks
            )
            encoded_audio = base64.b64encode(combined_bytes).decode("utf-8")
            record_audio(encoded_audio, "conversation", state.latest_media_timestamp)
            # logger.info(
            #     "Saved conversation audio: %s bytes from %s chunks",
            #     len(combined_bytes),
            #     len(state.recording_chunks),
            # )
        except Exception as exc:
            logger.warning(f"Failed to flush recording buffer: {exc}")
        finally:
            state.recording_chunks.clear()
            state.openai_audio_chunks.clear()
            state.client_audio_chunks.clear()

    async def _handle_start_event(self, message: Dict, state: ConnectionState):
        """Handle session start event."""
        start_msg = cast(StartMessage, message)
        client_session_id = start_msg.get("session_id")

        # Update session_id if client provides one
        if client_session_id and client_session_id != state.session_id:
            state.session_id = client_session_id
            state.session_manager = SessionManager(state.session_id)
            set_session_manager(state.session_manager)

        state.current_flow_state = FlowState.GREETING
        state.booking_context.clear()
        logger.info(
            f"Session started: {state.session_id}, "
            f"language: {get_connection_language().value}, "
            f"flow_state: {state.current_flow_state.value}"
        )

    async def _handle_text_message(
        self,
        message: Dict,
        websocket: WebSocket,
        session: RealtimeSession,  # RealtimeSession from agents SDK
    ):
        """Handle text message by sending it to the conversation."""
        text_msg = cast(TextMessage, message)
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
            await session.send_message(user_msg)
        except Exception as exc:
            logger.info(f"Error sending text message: {exc}")
            await websocket.send_json(
                {"event": "error", "message": f"Failed to send message: {exc}"}
            )

    async def _handle_control_message(
        self,
        message: Dict,
        session: RealtimeSession,  # RealtimeSession from agents SDK
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

    async def _handle_disconnect_event(
        self,
        websocket: WebSocket,
        state: ConnectionState,
        connection_id: Optional[str] = None,
    ):
        """Handle disconnect event from client - merge audio and send download URL."""
        logger.info("Received disconnect event from client")

        await self._flush_recording_buffer(state)

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
                            "final_state": state.current_flow_state.value,
                            "booking_context": state.booking_context,
                        }
                    )
                    logger.info(f"Sent audio download URL: {audio_url}")
                else:
                    await websocket.send_json(
                        {
                            "event": "session.ended",
                            "audio_download_url": None,
                            "connection_id": connection_id,
                            "final_state": state.current_flow_state.value,
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
                        "final_state": state.current_flow_state.value,
                    }
                )
        else:
            await websocket.send_json(
                {
                    "event": "session.ended",
                    "audio_download_url": None,
                    "final_state": state.current_flow_state.value,
                }
            )

    async def _handle_speech_started(
        self,
        session: RealtimeSession,  # RealtimeSession from agents SDK
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
            try:
                await websocket.send_json({"event": "clear"})
            except Exception as exc:
                logger.debug(str(exc))

        logger.info("Speech started detected", extra={"handler": "file"})

        if state.is_response_active and state.last_assistant_item:
            await _interrupt_bot_voice()
            logger.info(
                f"User interrupting active response with id: {state.last_assistant_item}",
                extra={"handler": "file"},
            )
            state.last_interruption_time = current_time
            state.is_response_active = False

            if state.current_response_id:
                try:
                    await session.interrupt()
                except Exception as exc:
                    logger.warning(
                        f"Failed to cancel response: {exc}", extra={"handler": "file"}
                    )

    # def _build_websocket_base_url(self) -> str:
    #     """Build WebSocket base URL for OpenAI Realtime API."""
    #     if settings.OPENAI_BASE_URL.startswith("wss://"):
    #         return settings.OPENAI_BASE_URL
    #     endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
    #     deployment_name = settings.MODEL
    #     return (
    #         f"wss://{endpoint}/openai/v1/realtime?"
    #         f"api-version=2024-10-01-preview&deployment={deployment_name}"
    #     )

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        """Convert exception to a safe, JSON-serializable error message."""
        try:
            error_msg = str(exc)
            return error_msg.encode("utf-8", errors="replace").decode("utf-8")
        except Exception:
            return "Unknown error occurred"
