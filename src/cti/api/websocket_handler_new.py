"""
WebSocket Handler - Xử lý WebSocket connections giữa Twilio và OpenAI
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

from cti.config.constants import LOG_EVENT_TYPES
from cti.config.prompts import SYSTEM_MESSAGE
from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService

logger = getLogger(__name__)
# Logger inherits level from root logger configured in app.py


class WebSocketHandler:
    """Handle WebSocket connections between Twilio and OpenAI"""

    def __init__(self):
        """Initialize the websocket handler"""
        self.tool_service = ToolService()

    async def handle_connection(self, websocket: WebSocket):
        """
        Main handler for WebSocket connections.

        Args:
            websocket: FastAPI WebSocket connection
        """
        logger.info("Client connected")
        await websocket.accept()

        # Construct websocket_base_url for OpenAI Realtime API
        if settings.OPENAI_BASE_URL.startswith("wss://"):
            websocket_base_url = settings.OPENAI_BASE_URL
        else:
            # Remove https:// and trailing slashes
            endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
            # Construct websocket URL with API version and deployment for Azure
            deployment_name = settings.MODEL
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
            deployment_name = settings.MODEL
            async with client.realtime.connect(model=deployment_name) as connection:
                await self._initialize_session(connection)

                # Connection state
                stream_sid = None
                latest_media_timestamp = 0
                last_assistant_item = None
                mark_queue = []
                response_start_timestamp_twilio = None
                session_manager: Optional[SessionManager] = None
                last_interruption_time = 0
                interruption_cooldown_ms = (
                    1000  # 1 second cooldown between interruptions
                )
                is_response_active = False
                current_response_id: Optional[str] = None

                async def receive_from_twilio():
                    """Receive audio from Twilio and send to OpenAI"""
                    nonlocal stream_sid, latest_media_timestamp, session_manager, is_response_active, current_response_id

                    try:
                        async for message in websocket.iter_text():
                            try:
                                # Parse JSON message
                                try:
                                    data: dict = json.loads(message)
                                except json.JSONDecodeError as json_err:
                                    logger.error(
                                        f"Invalid JSON received: {str(json_err)}",
                                        extra={"handler": "file"},
                                    )
                                    # Twilio doesn't expect error responses, so we just log and continue
                                    continue

                                event_type = data.get("event")

                                if event_type == "connected":
                                    logger.info(f"Connected to Twilio: {data}")
                                elif (
                                    "start" in data and data.get("start") == "connected"
                                ):
                                    logger.info(f"Connected to Twilio: {data}")

                                elif event_type == "media":
                                    media_data = data.get("media", {})
                                    timestamp = media_data.get("timestamp")
                                    payload: str = media_data.get("payload")

                                    if timestamp is not None:
                                        latest_media_timestamp = int(timestamp)
                                    if payload:
                                        # Decode base64 and append to OpenAI input buffer
                                        # audio_data = base64.b64decode(payload)
                                        await connection.input_audio_buffer.append(
                                            audio=payload
                                        )

                                elif event_type == "start":
                                    start_data = data.get("start", {})
                                    stream_sid = start_data.get("streamSid")
                                    logger.info(
                                        f"Incoming stream has started: {stream_sid}"
                                    )
                                    if stream_sid:
                                        session_manager = SessionManager(stream_sid)

                                elif event_type == "closed":
                                    logger.info(f"Closed connection to Twilio: {data}")
                                elif event_type == "mark":
                                    if mark_queue:
                                        mark_queue.pop(0)

                            except (KeyError, ValueError, TypeError) as e:
                                # Safely convert exception to string, handling bytes if present
                                try:
                                    error_msg = str(e)
                                    # Ensure error message is JSON-serializable
                                    error_msg = error_msg.encode(
                                        "utf-8", errors="replace"
                                    ).decode("utf-8")
                                except Exception:
                                    error_msg = "Unknown error occurred"

                                logger.error(
                                    f"Error parsing message: {error_msg}",
                                    extra={"handler": "file"},
                                )
                                # Twilio doesn't expect error responses, so we just log and continue

                            except Exception as e:
                                # Safely convert exception to string, handling bytes if present
                                try:
                                    error_msg = str(e)
                                    # Ensure error message is JSON-serializable
                                    error_msg = error_msg.encode(
                                        "utf-8", errors="replace"
                                    ).decode("utf-8")
                                except Exception:
                                    error_msg = "Unknown error occurred"

                                logger.error(
                                    f"Error in receive_from_twilio: {error_msg}",
                                    extra={"handler": "file"},
                                )
                                # Twilio doesn't expect error responses, so we just log and continue

                    except WebSocketDisconnect:
                        logger.info("Client disconnected")
                        if session_manager:
                            session_manager.save_to_file()

                async def send_to_twilio():
                    """Receive events from OpenAI and send audio to Twilio"""
                    nonlocal last_assistant_item, response_start_timestamp_twilio, last_interruption_time, is_response_active, current_response_id, latest_media_timestamp

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
                                logger.info(
                                    "Response started", extra={"handler": "file"}
                                )
                            elif event.type == "response.done":
                                is_response_active = False
                                current_response_id = None
                                logger.info(
                                    "Response done detected", extra={"handler": "file"}
                                )
                                # await websocket.send_json(
                                #     {"event": "clear", "streamSid": stream_sid}
                                # )
                            elif event.type == "response.cancelled":
                                is_response_active = False
                                current_response_id = None
                                logger.info(
                                    "Response cancelled", extra={"handler": "file"}
                                )
                                # Clear mark queue on cancellation
                                mark_queue.clear()

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
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {"payload": audio_payload},
                                    }
                                )

                                if (
                                    hasattr(event, "item_id")
                                    and event.item_id
                                    and event.item_id != last_assistant_item
                                ):
                                    response_start_timestamp_twilio = (
                                        latest_media_timestamp
                                    )
                                    last_assistant_item = event.item_id

                                await self._send_mark(websocket, stream_sid, mark_queue)

                            # Handle interruption - OpenAI will handle it automatically, but we track it
                            if event.type == "input_audio_buffer.speech_started":
                                logger.info(
                                    "Speech started detected",
                                    extra={"handler": "file"},
                                )
                                if is_response_active and last_assistant_item:
                                    logger.info(
                                        f"User interrupting active response with id: {last_assistant_item}",
                                        extra={"handler": "file"},
                                    )
                                    if current_response_id:
                                        try:
                                            await connection.response.cancel()
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to cancel response: {e}",
                                                extra={"handler": "file"},
                                            )
                                    await self._handle_speech_started(
                                        connection,
                                        websocket,
                                        stream_sid,
                                        latest_media_timestamp,
                                        response_start_timestamp_twilio,
                                        last_assistant_item,
                                        mark_queue,
                                    )
                    except Exception as e:
                        logger.error(
                            f"Error in send_to_twilio: {e}", extra={"handler": "file"}
                        )
                        import traceback

                        traceback.print_exc()

                await asyncio.gather(receive_from_twilio(), send_to_twilio())

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
        """Initialize OpenAI session with tools"""
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
                        "interrupt_response": True,  # Enable automatic interruption
                    },
                },
                "output": {"format": {"type": "audio/pcmu"}, "voice": settings.VOICE},
            },
            "instructions": SYSTEM_MESSAGE,
            "tools": self.tool_service.get_tool_definitions(),
            "tool_choice": "auto",
        }
        logger.info(
            f"Sending session update: {json.dumps(session_config, ensure_ascii=False)}",
            extra={"handler": "file"},  # Only log to file, not console
        )
        await connection.session.update(session=session_config)

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

    async def _send_mark(self, websocket, stream_sid, mark_queue):
        """Send mark event to Twilio"""
        if stream_sid:
            await websocket.send_json(
                {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"},
                }
            )
            mark_queue.append("responsePart")

    async def _handle_speech_started(
        self,
        connection: AsyncRealtimeConnection,
        websocket: WebSocket,
        stream_sid: Optional[str],
        latest_media_timestamp: int,
        response_start_timestamp_twilio: Optional[int],
        last_assistant_item: Optional[str],
        mark_queue: list,
    ):
        """Handle speech interruption"""
        if response_start_timestamp_twilio is not None and last_assistant_item:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

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
                        extra={"handler": "file"},
                    )
                    # Continue anyway - the interruption will still be handled

        # Send clear event to Twilio to stop playback
        if stream_sid:
            await websocket.send_json({"event": "clear", "streamSid": stream_sid})

        # Clear mark queue on interruption
        mark_queue.clear()
