"""
Audio WebSocket Handler - Flexible handler for bidirectional audio streaming
"""

import asyncio
import base64
import json
from logging import getLogger
from typing import Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from openai import AsyncOpenAI
from openai.resources.realtime.realtime import AsyncRealtimeConnection
from openai.types.realtime import RealtimeServerEvent, session_update_event_param

from cti.api.audio_types import (
    AudioMessage,
    ControlMessage,
    StartMessage,
    TextMessage,
)
from cti.config.constants import LOG_EVENT_TYPES
from cti.config.prompts import SYSTEM_MESSAGE
from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService
from cti.services.tts_service import TTSService

logger = getLogger(__name__)
# Logger inherits level from root logger configured in app.py


class AudioWebSocketHandler:
    """Handle bidirectional audio WebSocket connections with OpenAI Realtime API"""

    def __init__(self):
        """Initialize the audio websocket handler"""
        self.tool_service = ToolService()
        self.tts_service = TTSService()

    async def handle_connection(self, websocket: WebSocket):
        """
        Main handler for WebSocket connections.

        Args:
            websocket: FastAPI WebSocket connection
        """
        logger.info("Audio client connected")
        await websocket.accept()

        # Construct websocket_base_url for OpenAI Realtime API
        if settings.OPENAI_BASE_URL.startswith("wss://"):
            websocket_base_url = settings.OPENAI_BASE_URL
        else:
            # Remove https:// and trailing slashes
            endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
            # Construct websocket URL with API version and deployment for Azure
            deployment_name = "gpt-realtime-mini"
            websocket_base_url = (
                f"wss://{endpoint}/openai/v1/realtime?"
                f"api-version=2024-10-01-preview&deployment={deployment_name}"
            )

        try:
            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY, websocket_base_url=websocket_base_url
            )
        except Exception as e:
            logger.info(f"❌ Failed to initialize OpenAI client: {e}")
            await websocket.close(
                code=1011, reason="OpenAI client initialization failed"
            )
            return

        try:
            deployment_name = "gpt-realtime-mini"
            async with client.realtime.connect(model=deployment_name) as connection:
                await self._initialize_session(connection)

                # Connection state
                session_id: Optional[str] = None
                latest_media_timestamp = 0
                last_assistant_item: Optional[str] = None
                response_start_timestamp = None
                session_manager: Optional[SessionManager] = None
                is_paused = False
                last_interruption_time = 0
                interruption_cooldown_ms = 1000  # 1 second cooldown between interruptions
                is_response_active = False
                current_response_id: Optional[str] = None

                async def receive_from_client():
                    """Receive audio/text from client and forward to OpenAI"""
                    nonlocal session_id, latest_media_timestamp, session_manager, is_paused, is_response_active, current_response_id

                    try:
                        while True:
                            try:
                                # Receive message - handle both text and bytes
                                raw_message = await websocket.receive()
                                
                                # FastAPI WebSocket returns dict with 'type' and 'text' or 'bytes'
                                if raw_message.get("type") == "websocket.receive":
                                    if "text" in raw_message:
                                        message_text = raw_message["text"]
                                    elif "bytes" in raw_message:
                                        # If bytes received, try to decode as UTF-8
                                        try:
                                            message_text = raw_message["bytes"].decode("utf-8")
                                        except UnicodeDecodeError:
                                            logger.error("Received binary data that cannot be decoded as UTF-8", extra={"handler": "file"})
                                            await websocket.send_json({
                                                "event": "error",
                                                "message": "Invalid message format: binary data received"
                                            })
                                            continue
                                    else:
                                        logger.warning("Received message without text or bytes", extra={"handler": "file"})
                                        continue
                                elif raw_message.get("type") == "websocket.disconnect":
                                    break
                                else:
                                    # Skip other message types
                                    continue
                                
                                # Parse JSON message
                                try:
                                    data: dict = json.loads(message_text)
                                except json.JSONDecodeError as json_err:
                                    logger.error(f"Invalid JSON received: {str(json_err)}", extra={"handler": "file"})
                                    await websocket.send_json({
                                        "event": "error",
                                        "message": f"Invalid JSON format: {str(json_err)}"
                                    })
                                    continue
                                
                                event_type = data.get("event")

                                if event_type == "audio":
                                    if is_paused:
                                        continue

                                    audio_msg: AudioMessage = data
                                    payload = audio_msg.get("payload", "")
                                    timestamp = audio_msg.get("timestamp", 0)

                                    if payload:
                                        latest_media_timestamp = (
                                            timestamp or latest_media_timestamp
                                        )
                                        # OpenAI API expects base64-encoded string, not bytes
                                        # Pass the payload directly (it's already base64-encoded)
                                        await connection.input_audio_buffer.append(
                                            audio=payload
                                        )

                                elif event_type == "start":
                                    start_msg: StartMessage = data
                                    session_id = start_msg.get("session_id")
                                    logger.info(f"Session started: {session_id}")
                                    if session_id:
                                        session_manager = SessionManager(session_id)

                                elif event_type == "text":
                                    # Handle text-to-audio conversion
                                    text_msg: TextMessage = data
                                    await self._handle_text_message(
                                        text_msg, websocket, connection
                                    )

                                elif event_type in ("pause", "resume", "stop", "clear"):
                                    control_msg: ControlMessage = data
                                    await self._handle_control_message(
                                        control_msg, connection, is_paused
                                    )
                                    if event_type == "pause":
                                        is_paused = True
                                    elif event_type == "resume":
                                        is_paused = False
                                    elif event_type == "stop":
                                        # Stop current response immediately
                                        try:
                                            await connection.response.cancel()
                                        except Exception as e:
                                            logger.warning(f"Failed to cancel response on stop: {e}", extra={"handler": "file"})
                                        await websocket.send_json({"event": "clear"})

                            except (KeyError, ValueError, TypeError) as e:
                                # Safely convert exception to string, handling bytes if present
                                try:
                                    error_msg = str(e)
                                    # Ensure error message is JSON-serializable
                                    error_msg = error_msg.encode('utf-8', errors='replace').decode('utf-8')
                                except Exception:
                                    error_msg = "Unknown error occurred"
                                
                                logger.error(f"Error parsing message: {error_msg}", extra={"handler": "file"})
                                try:
                                    await websocket.send_json({
                                        "event": "error",
                                        "message": f"Invalid message format: {error_msg}"
                                    })
                                except Exception as send_error:
                                    logger.error(f"Failed to send error message: {send_error}", extra={"handler": "file"})
                                
                            except Exception as e:
                                # Safely convert exception to string, handling bytes if present
                                try:
                                    error_msg = str(e)
                                    # Ensure error message is JSON-serializable
                                    error_msg = error_msg.encode('utf-8', errors='replace').decode('utf-8')
                                except Exception:
                                    error_msg = "Unknown error occurred"
                                
                                logger.error(f"Error in receive_from_client: {error_msg}", extra={"handler": "file"})
                                try:
                                    await websocket.send_json({
                                        "event": "error",
                                        "message": f"Server error: {error_msg}"
                                    })
                                except Exception as send_error:
                                    logger.error(f"Failed to send error message: {send_error}", extra={"handler": "file"})

                    except WebSocketDisconnect:
                        logger.info("Client disconnected")
                        if session_manager:
                            session_manager.save_to_file()

                async def send_to_client():
                    """Receive events from OpenAI and send audio to client"""
                    nonlocal last_assistant_item, response_start_timestamp, last_interruption_time, is_response_active, current_response_id

                    try:
                        async for event in connection:
                            if event.type == "session.created":
                                logger.info(
                                    f"Session created: {event.model_dump_json()}",
                                    extra={"handler": "file"},
                                )
                            if event.type in LOG_EVENT_TYPES:
                                logger.info(
                                    f"Received event: {event.type}: {event.model_dump_json()}",
                                    extra={"handler": "file"},
                                )

                            # Track response state
                            if event.type == "response.created":
                                is_response_active = True
                                if hasattr(event, "response_id"):
                                    current_response_id = event.response_id
                                logger.info("Response started", extra={"handler": "file"})
                            elif event.type == "response.done":
                                is_response_active = False
                                current_response_id = None
                                logger.info("Response done detected")
                                await websocket.send_json({"event": "response.done"})
                            elif event.type == "response.cancelled":
                                is_response_active = False
                                current_response_id = None
                                logger.info("Response cancelled")
                                await websocket.send_json({"event": "response.cancelled"})
                                # Clear audio queue on cancellation
                                await websocket.send_json({"event": "clear"})

                            # Handle function call
                            if event.type == "response.function_call_arguments.done":
                                await self._handle_function_call(
                                    event, connection, session_manager
                                )

                            # Send audio delta
                            if event.type == "response.output_audio.delta" and hasattr(
                                event, "delta"
                            ):
                                # Encode audio delta as base64
                                audio_payload = base64.b64encode(
                                    base64.b64decode(event.delta)
                                ).decode("utf-8")

                                await websocket.send_json(
                                    {
                                        "event": "audio",
                                        "payload": audio_payload,
                                        "timestamp": latest_media_timestamp,
                                        "format": "pcm16",
                                    }
                                )

                                if (
                                    hasattr(event, "item_id")
                                    and event.item_id
                                    and event.item_id != last_assistant_item
                                ):
                                    response_start_timestamp = latest_media_timestamp
                                    last_assistant_item = event.item_id

                            # Handle interruption - OpenAI will handle it automatically, but we track it
                            if event.type == "input_audio_buffer.speech_started":
                                current_time = latest_media_timestamp
                                time_since_last_interruption = current_time - last_interruption_time
                                
                                # Only log if cooldown period has passed
                                if time_since_last_interruption >= interruption_cooldown_ms:
                                    logger.info("Speech started detected", extra={"handler": "file"})
                                    if is_response_active and last_assistant_item:
                                        logger.info(
                                            f"User interrupting active response with id: {last_assistant_item}",
                                            extra={"handler": "file"}
                                        )
                                        last_interruption_time = current_time
                                        # Cancel the current response if it's still active
                                        if current_response_id:
                                            try:
                                                await connection.response.cancel()
                                            except Exception as e:
                                                logger.warning(f"Failed to cancel response: {e}", extra={"handler": "file"})
                                        # Send clear event to client to stop playback
                                        await websocket.send_json({"event": "clear"})
                                else:
                                    logger.debug(
                                        f"Ignoring speech_started event (cooldown: {interruption_cooldown_ms - time_since_last_interruption}ms remaining)",
                                        extra={"handler": "file"}
                                    )

                    except Exception as e:
                        logger.info(f"Error in send_to_client: {e}")

                await asyncio.gather(receive_from_client(), send_to_client())

        except Exception as e:
            logger.info(f"❌ Error in OpenAI connection: {e}")
            import traceback

            traceback.print_exc()
            try:
                await websocket.close(
                    code=1011, reason=f"OpenAI connection error: {str(e)}"
                )
            except Exception:
                pass

    async def _initialize_session(self, connection: AsyncRealtimeConnection):
        """Initialize OpenAI session with PCM16/WAV format"""
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
                        "silence_duration_ms": 200,
                        "create_response": True,
                        "interrupt_response": True,  # Enable automatic interruption
                    },
                },
                "output": {
                    "voice": settings.VOICE,
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    },
                },
            },
            "instructions": SYSTEM_MESSAGE,
            # "tools": self.tool_service.get_tool_definitions(),
            "tool_choice": "auto",
        }
        logger.info(
            f"Sending session update: {json.dumps(session_config, ensure_ascii=False)}",
            extra={"handler": "file"},  # Only log to file, not console
        )
        await connection.session.update(session=session_config)

    async def _handle_text_message(
        self,
        text_msg: TextMessage,
        websocket: WebSocket,
        connection: AsyncRealtimeConnection,
    ):
        """Handle text message by sending it to the conversation"""
        text = text_msg.get("text", "")

        if not text:
            await websocket.send_json(
                {"event": "error", "message": "Text message is required"}
            )
            return

        try:
            # Send text message to conversation
            logger.info(f"Sending text message: {text}")
            await connection.conversation.item.create(
                item={
                    "type": "message",
                    "content": [{"text": text, "type": "input_text"}],
                    "role": "user",
                }
            )

            # Trigger response generation
            await connection.response.create()

        except Exception as e:
            logger.info(f"Error sending text message: {e}")
            await websocket.send_json(
                {"event": "error", "message": f"Failed to send message: {str(e)}"}
            )

    async def _handle_control_message(
        self, control_msg: ControlMessage, connection: AsyncRealtimeConnection, is_paused: bool
    ):
        """Handle control messages (pause, resume, stop, clear)"""
        event_type = control_msg.get("event")

        if event_type == "stop":
            # Stop current response immediately
            try:
                await connection.response.cancel()
            except Exception as e:
                logger.warning(f"Error cancelling response: {e}", extra={"handler": "file"})
        elif event_type == "clear":
            # Clear input buffer
            try:
                if hasattr(connection, "input_audio_buffer"):
                    await connection.input_audio_buffer.clear()
            except Exception as e:
                logger.warning(f"Error clearing input buffer: {e}", extra={"handler": "file"})

    async def _handle_function_call(
        self,
        event: RealtimeServerEvent,
        connection: AsyncRealtimeConnection,
        session_manager: Optional[SessionManager],
    ):
        """Handle function call from OpenAI"""
        logger.info(f"\nFunction call received: {event}")

        call_id = getattr(event, "call_id", None)
        function_name = getattr(event, "name", None)
        arguments_str = getattr(event, "arguments", "{}")

        try:
            arguments = json.loads(arguments_str)
            logger.info(f"Executing tool: {function_name} with args: {arguments}")

            if session_manager:
                result = await self.tool_service.execute_tool(
                    function_name, arguments, session_manager
                )
            else:
                result = {"error": "Session manager not initialized", "success": False}

            logger.info(f"Tool result: {result}")

            # Send result back to OpenAI
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

            # Trigger response generation
            await connection.response.create()

        except Exception as e:
            logger.info(f"Error handling function call: {e}")
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {"error": str(e), "success": False}, ensure_ascii=False
                    ),
                }
            )
            await connection.response.create()

    async def _handle_speech_started(
        self,
        connection,
        websocket: WebSocket,
        latest_media_timestamp: int,
        response_start_timestamp: Optional[int],
        last_assistant_item: Optional[str],
        send_clear: bool = False,
    ):
        """Handle speech interruption"""
        if response_start_timestamp is not None and last_assistant_item:
            elapsed_time = latest_media_timestamp - response_start_timestamp

            # Only truncate if elapsed_time is positive and reasonable
            if elapsed_time > 0:
                try:
                    await connection.conversation.item.truncate(
                        item_id=last_assistant_item,
                        content_index=0,
                        audio_end_ms=elapsed_time,
                    )
                except Exception as e:
                    # Handle case where audio is shorter than elapsed_time
                    # This can happen if timestamps are inaccurate or audio finished early
                    logger.warning(
                        f"Failed to truncate audio at {elapsed_time}ms: {e}",
                        extra={"handler": "file"}
                    )
                    # Continue anyway - the interruption will still be handled

            # Only send clear event if explicitly requested
            if send_clear:
                await websocket.send_json({"event": "clear"})
