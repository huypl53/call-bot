"""
WebSocket Handler - Xử lý WebSocket connections giữa Twilio và OpenAI
Enhanced for production-ready voice call bot with improved barge-in, error recovery, and latency optimization
"""

import asyncio
import json
import time
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
from cti.core.connection_context import record_audio
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
                mark_queue = []  # Queue of sent mark names waiting for acknowledgment
                mark_acknowledged = set()  # Set of acknowledged mark names
                response_start_timestamp_twilio = None
                session_manager: Optional[SessionManager] = None
                last_interruption_time = 0
                is_response_active = False
                current_response_id: Optional[str] = None
                response_status: Optional[str] = (
                    None  # 'in_progress', 'completed', 'cancelled', 'interrupted', 'incomplete', 'failed'
                )
                is_interrupting = (
                    False  # Track if we're currently handling an interruption
                )
                connection_healthy = True  # Track connection health
                last_mark_send_time = 0  # Track last mark send time for rate limiting
                mark_send_interval = 0.3  # Minimum interval between marks (300ms)
                audio_chunk_buffer: list[str] = (
                    []
                )  # Buffer for batching small audio chunks
                audio_chunk_buffer_size = 0  # Total size of buffered chunks
                max_chunk_buffer_size = (
                    4800  # Max buffer size before sending (~200ms at 8kHz mulaw)
                )
                # Audio accumulation for complete responses
                openai_audio_chunks: list[str] = []  # Accumulate base64 audio chunks
                twilio_audio_chunks: list[str] = []  # Accumulate Twilio audio chunks
                # Latency tracking
                response_start_time: Optional[float] = None
                first_audio_time: Optional[float] = None

                async def receive_from_twilio():
                    """Receive audio from Twilio and send to OpenAI"""
                    nonlocal stream_sid, latest_media_timestamp, session_manager, is_response_active, current_response_id, twilio_audio_chunks, mark_queue, mark_acknowledged

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
                                    logger.info(
                                        f"Connected to Twilio: {data}",
                                    )
                                elif (
                                    "start" in data and data.get("start") == "connected"
                                ):
                                    logger.info(
                                        f"Connected to Twilio: {data}",
                                    )

                                elif event_type == "media":
                                    media_data = data.get("media", {})
                                    timestamp = media_data.get("timestamp")
                                    payload: str = media_data.get("payload")

                                    if timestamp is not None:
                                        latest_media_timestamp = int(timestamp)
                                    if payload:
                                        # Accumulate audio chunks (don't record individual chunks)
                                        twilio_audio_chunks.append(payload)

                                        # Decode base64 and append to OpenAI input buffer
                                        # audio_data = base64.b64decode(payload)
                                        await connection.input_audio_buffer.append(
                                            audio=payload
                                        )

                                elif event_type == "start":
                                    start_data = data.get("start", {})
                                    stream_sid = start_data.get("streamSid")
                                    logger.info(
                                        f"Incoming stream has started: {stream_sid}",
                                    )
                                    if stream_sid:
                                        session_manager = SessionManager(stream_sid)

                                elif event_type == "closed":
                                    logger.info(
                                        f"Closed connection to Twilio: {data}",
                                    )
                                    # Record complete Twilio audio when connection closes
                                    if twilio_audio_chunks:
                                        complete_audio = "".join(twilio_audio_chunks)
                                        record_audio(
                                            complete_audio,
                                            "twilio",
                                            latest_media_timestamp,
                                        )
                                        twilio_audio_chunks.clear()
                                elif event_type == "mark":
                                    mark_data = data.get("mark", {})
                                    mark_name = mark_data.get("name")
                                    if mark_name:
                                        mark_acknowledged.add(mark_name)
                                        if mark_queue and mark_queue[0] == mark_name:
                                            mark_queue.pop(0)
                                        logger.debug(
                                            f"Mark acknowledged: {mark_name}",
                                            extra={"handler": "file"},
                                        )
                                elif event_type == "stop":
                                    logger.info(
                                        f"Stream stopped: {data}",
                                        extra={"handler": "file"},
                                    )
                                    # Record complete Twilio audio when stream stops
                                    if twilio_audio_chunks:
                                        complete_audio = "".join(twilio_audio_chunks)
                                        record_audio(
                                            complete_audio,
                                            "twilio",
                                            latest_media_timestamp,
                                        )
                                        twilio_audio_chunks.clear()
                                elif event_type == "dtmf":
                                    dtmf_data = data.get("dtmf", {})
                                    digit = dtmf_data.get("digit")
                                    logger.info(
                                        f"DTMF received: {digit}",
                                        extra={"handler": "file"},
                                    )
                                    # DTMF can be handled here if needed for booking system

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
                        logger.info(
                            "Client disconnected",
                        )
                        if session_manager:
                            session_manager.save_to_file()

                async def send_to_twilio():
                    """Receive events from OpenAI and send audio to Twilio"""
                    nonlocal last_assistant_item, response_start_timestamp_twilio, last_interruption_time
                    nonlocal is_response_active, current_response_id, latest_media_timestamp
                    nonlocal openai_audio_chunks, response_status, is_interrupting, connection_healthy
                    nonlocal last_mark_send_time, audio_chunk_buffer, audio_chunk_buffer_size
                    nonlocal response_start_time, first_audio_time

                    try:
                        async for event in connection:
                            # Handle errors from OpenAI
                            if event.type == "error":
                                connection_healthy = False
                                error_data = getattr(event, "error", {})
                                error_type = getattr(error_data, "type", "unknown")
                                error_message = getattr(
                                    error_data, "message", "Unknown error"
                                )
                                logger.error(
                                    f"OpenAI error: {error_type} - {error_message}",
                                    extra={"handler": "file"},
                                )
                                # Try to recover from non-critical errors
                                if error_type not in [
                                    "invalid_request_error",
                                    "authentication_error",
                                ]:
                                    connection_healthy = True
                                continue

                            if event.type == "session.created":
                                connection_healthy = True
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
                                response_status = "in_progress"
                                is_interrupting = False
                                response_start_time = time.time()
                                first_audio_time = None
                                if hasattr(event, "response") and hasattr(
                                    event.response, "id"
                                ):
                                    current_response_id = event.response.id
                                elif hasattr(event, "response_id"):
                                    current_response_id = event.response_id
                                # Clear audio chunks for new response
                                openai_audio_chunks.clear()
                                audio_chunk_buffer.clear()
                                audio_chunk_buffer_size = 0
                                logger.info(
                                    f"Response started: {current_response_id}",
                                    extra={"handler": "file"},
                                )
                            elif event.type == "response.done":
                                is_response_active = False
                                response_status = "completed"
                                if hasattr(event, "response") and hasattr(
                                    event.response, "status"
                                ):
                                    response_status = event.response.status
                                elif hasattr(event, "response"):
                                    response_status = getattr(
                                        event.response, "status", "completed"
                                    )

                                # Flush any remaining buffered audio
                                await self._flush_audio_buffer(
                                    websocket, stream_sid, audio_chunk_buffer
                                )

                                # Calculate and log latency metrics
                                if response_start_time:
                                    total_latency = time.time() - response_start_time
                                    logger.info(
                                        f"Response completed: {current_response_id}, "
                                        f"status: {response_status}, "
                                        f"total_latency: {total_latency:.3f}s",
                                        extra={"handler": "file"},
                                    )

                                current_response_id = None
                                response_start_time = None
                                first_audio_time = None

                                # Record complete audio response
                                if openai_audio_chunks:
                                    complete_audio = "".join(openai_audio_chunks)
                                    record_audio(
                                        complete_audio, "openai", latest_media_timestamp
                                    )
                                    openai_audio_chunks.clear()

                            elif event.type == "response.cancelled":
                                is_response_active = False
                                response_status = "cancelled"
                                is_interrupting = False
                                logger.info(
                                    f"Response cancelled: {current_response_id}",
                                    extra={"handler": "file"},
                                )
                                # Clear accumulated audio chunks on cancellation
                                openai_audio_chunks.clear()
                                audio_chunk_buffer.clear()
                                audio_chunk_buffer_size = 0
                                # Clear mark queue on cancellation
                                mark_queue.clear()
                                current_response_id = None
                                response_start_time = None
                                first_audio_time = None

                            # Handle response status changes
                            elif event.type == "response.interrupted":
                                response_status = "interrupted"
                                is_interrupting = True
                                logger.info(
                                    f"Response interrupted: {current_response_id}",
                                    extra={"handler": "file"},
                                )
                            elif event.type == "response.incomplete":
                                response_status = "incomplete"
                                logger.warning(
                                    f"Response incomplete: {current_response_id}",
                                    extra={"handler": "file"},
                                )
                            elif event.type == "response.failed":
                                response_status = "failed"
                                is_response_active = False
                                logger.error(
                                    f"Response failed: {current_response_id}",
                                    extra={"handler": "file"},
                                )
                                openai_audio_chunks.clear()
                                audio_chunk_buffer.clear()
                                audio_chunk_buffer_size = 0
                                mark_queue.clear()
                                current_response_id = None

                            # Handle function call
                            if event.type == "response.function_call_arguments.done":
                                await self._handle_function_call(
                                    event, connection, session_manager
                                )

                            # Handle input audio buffer events
                            if event.type == "input_audio_buffer.cleared":
                                logger.info(
                                    "Input audio buffer cleared (barge-in detected)",
                                    extra={"handler": "file"},
                                )
                                is_interrupting = True
                                # Clear any buffered output audio
                                audio_chunk_buffer.clear()
                                audio_chunk_buffer_size = 0

                            elif event.type == "input_audio_buffer.speech_stopped":
                                item_id = getattr(event, "item_id", None)
                                audio_end_ms = getattr(event, "audio_end_ms", None)
                                logger.info(
                                    f"Speech stopped: item_id={item_id}, audio_end_ms={audio_end_ms}",
                                    extra={"handler": "file"},
                                )
                                is_interrupting = False

                            elif event.type == "input_audio_buffer.timeout_triggered":
                                item_id = getattr(event, "item_id", None)
                                audio_start_ms = getattr(event, "audio_start_ms", None)
                                audio_end_ms = getattr(event, "audio_end_ms", None)
                                logger.info(
                                    f"Idle timeout triggered: item_id={item_id}, "
                                    f"audio_start_ms={audio_start_ms}, audio_end_ms={audio_end_ms}",
                                    extra={"handler": "file"},
                                )

                            # Send audio delta
                            if event.type == "response.output_audio.delta" and hasattr(
                                event, "delta"
                            ):
                                # Track first audio time for latency measurement
                                if first_audio_time is None and response_start_time:
                                    first_audio_time = time.time()
                                    time_to_first_audio = (
                                        first_audio_time - response_start_time
                                    )
                                    logger.info(
                                        f"Time to first audio: {time_to_first_audio:.3f}s",
                                        extra={"handler": "file"},
                                    )

                                # Fix: event.delta is already base64-encoded, don't double-encode
                                audio_payload = event.delta

                                # Accumulate audio chunks (don't record individual chunks)
                                openai_audio_chunks.append(audio_payload)

                                # Buffer audio chunks for batching (optimize for latency)
                                audio_chunk_buffer.append(audio_payload)
                                audio_chunk_buffer_size += len(audio_payload)

                                # Send buffered chunks if buffer is full or if we're not interrupting
                                if (
                                    audio_chunk_buffer_size >= max_chunk_buffer_size
                                    or not is_interrupting
                                ):
                                    await self._flush_audio_buffer(
                                        websocket, stream_sid, audio_chunk_buffer
                                    )
                                    audio_chunk_buffer_size = 0

                                if (
                                    hasattr(event, "item_id")
                                    and event.item_id
                                    and event.item_id != last_assistant_item
                                ):
                                    response_start_timestamp_twilio = (
                                        latest_media_timestamp
                                    )
                                    last_assistant_item = event.item_id
                                    # Send mark when starting new item (rate-limited)
                                    last_mark_send_time = (
                                        await self._send_mark_rate_limited(
                                            websocket,
                                            stream_sid,
                                            mark_queue,
                                            last_mark_send_time,
                                            mark_send_interval,
                                        )
                                    )

                            # Handle interruption - OpenAI will handle it automatically, but we track it
                            if (
                                event.type == "input_audio_buffer.speech_started"
                                or event.type == "input_audio_buffer.committed"
                            ):
                                item_id = getattr(event, "item_id", None)
                                audio_start_ms = getattr(event, "audio_start_ms", None)
                                logger.info(
                                    f"Speech started detected: item_id={item_id}, audio_start_ms={audio_start_ms}",
                                    extra={"handler": "file"},
                                )
                                is_interrupting = True

                                # Always handle interruption if there's an active response
                                # (regardless of whether we have last_assistant_item)
                                if is_response_active:
                                    logger.info(
                                        f"User interrupting active response: {current_response_id}, "
                                        f"item: {last_assistant_item}",
                                        extra={"handler": "file"},
                                    )

                                    # Cancel response first, then clear Twilio buffer
                                    if current_response_id:
                                        try:
                                            await connection.response.cancel(
                                                response_id=current_response_id
                                            )
                                            logger.info(
                                                f"Response cancellation requested: {current_response_id}",
                                                extra={"handler": "file"},
                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to cancel response: {e}",
                                                extra={"handler": "file"},
                                            )

                                    # Discard buffered audio - no point sending it if we're clearing immediately
                                    if audio_chunk_buffer:
                                        logger.info(
                                            f"Discarding {len(audio_chunk_buffer)} buffered audio chunks on interruption",
                                            extra={"handler": "file"},
                                        )
                                    audio_chunk_buffer.clear()
                                    audio_chunk_buffer_size = 0

                                    # Always send clear event to Twilio to stop any playing audio
                                    # Truncation is optional and only happens if we have last_assistant_item
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
                        connection_healthy = False
                        logger.error(
                            f"Error in send_to_twilio: {e}",
                            extra={"handler": "file"},
                            exc_info=True,
                        )
                        # Try to recover - clear state and continue
                        is_response_active = False
                        current_response_id = None
                        audio_chunk_buffer.clear()
                        audio_chunk_buffer_size = 0
                        mark_queue.clear()

                # Run both coroutines concurrently
                try:
                    await asyncio.gather(
                        receive_from_twilio(), send_to_twilio(), return_exceptions=True
                    )
                except Exception as e:
                    logger.error(
                        f"Error in gather: {e}",
                        extra={"handler": "file"},
                        exc_info=True,
                    )
                finally:
                    # Cleanup: flush any remaining audio and save session
                    # Note: audio_chunk_buffer is managed inside send_to_twilio,
                    # so we only save session here
                    if session_manager:
                        try:
                            session_manager.save_to_file()
                            logger.info(
                                f"Session saved: {session_manager.stream_sid}",
                                extra={"handler": "file"},
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to save session: {e}",
                                extra={"handler": "file"},
                            )

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
            "instructions": str(SYSTEM_MESSAGE),
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
        """Handle function call from OpenAI with enhanced logging"""
        call_id = getattr(event, "call_id", None)
        function_name = getattr(event, "name", None)
        arguments_str = getattr(event, "arguments", "{}")
        item_id = getattr(event, "item_id", None)

        logger.info(
            f"Function call received: name={function_name}, call_id={call_id}, item_id={item_id}",
            extra={"handler": "file"},
        )

        try:
            arguments = json.loads(arguments_str)
            logger.info(
                f"Executing tool: {function_name} with args: {arguments}",
                extra={"handler": "file"},
            )

            function_start_time = time.time()
            if session_manager:
                result = await self.tool_service.execute_tool(
                    function_name, arguments, session_manager
                )
            else:
                result = {
                    "error": "Session manager not initialized",
                    "success": False,
                }

            function_duration = time.time() - function_start_time
            logger.info(
                f"Tool execution completed: {function_name}, "
                f"duration: {function_duration:.3f}s, "
                f"result: {result}",
                extra={"handler": "file"},
            )

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

        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to parse function call arguments: {e}, arguments_str: {arguments_str}",
                extra={"handler": "file"},
            )
            await connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        {
                            "error": f"Invalid JSON arguments: {str(e)}",
                            "success": False,
                        },
                        ensure_ascii=False,
                    ),
                }
            )
            await connection.response.create()
        except Exception as e:
            logger.error(
                f"Error handling function call: {e}",
                extra={"handler": "file"},
                exc_info=True,
            )
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

    async def _send_mark(
        self, websocket, stream_sid, mark_queue, mark_name: str = "responsePart"
    ):
        """Send mark event to Twilio"""
        if stream_sid:
            await websocket.send_json(
                {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": mark_name},
                }
            )
            mark_queue.append(mark_name)
            logger.debug(
                f"Mark sent: {mark_name}, queue size: {len(mark_queue)}",
                extra={"handler": "file"},
            )

    async def _send_mark_rate_limited(
        self,
        websocket,
        stream_sid,
        mark_queue,
        last_mark_send_time_ref,
        min_interval: float,
    ):
        """Send mark event with rate limiting"""
        current_time = time.time()
        if current_time - last_mark_send_time_ref >= min_interval:
            await self._send_mark(websocket, stream_sid, mark_queue)
            # Update the reference (note: this modifies the nonlocal variable indirectly)
            # We'll need to return the updated time
            return current_time
        return last_mark_send_time_ref

    async def _flush_audio_buffer(
        self, websocket: WebSocket, stream_sid: Optional[str], buffer: list[str]
    ):
        """Flush buffered audio chunks to Twilio"""
        if not buffer or not stream_sid:
            return

        # Send all buffered chunks
        for audio_payload in buffer:
            try:
                await websocket.send_json(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": audio_payload},
                    }
                )
            except Exception as e:
                logger.error(
                    f"Failed to send audio chunk: {e}",
                    extra={"handler": "file"},
                )
                # Continue sending remaining chunks even if one fails

        buffer.clear()

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
        """Handle speech interruption with proper cleanup"""
        logger.info(
            f"Handling speech interruption: item={last_assistant_item}, "
            f"timestamp={latest_media_timestamp}, "
            f"response_start={response_start_timestamp_twilio}",
            extra={"handler": "file"},
        )

        # Truncate the assistant's audio item to match what was actually played
        if response_start_timestamp_twilio is not None and last_assistant_item:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

            # Only truncate if elapsed_time is positive and reasonable (max 10 seconds)
            if 0 < elapsed_time < 10000:
                try:
                    await connection.conversation.item.truncate(
                        item_id=last_assistant_item,
                        content_index=0,
                        audio_end_ms=elapsed_time,
                    )
                    logger.info(
                        f"Truncated audio item {last_assistant_item} at {elapsed_time}ms",
                        extra={"handler": "file"},
                    )
                except Exception as e:
                    # Handle case where audio is shorter than elapsed_time
                    # This can happen if timestamps are inaccurate or audio finished early
                    logger.warning(
                        f"Failed to truncate audio at {elapsed_time}ms: {e}",
                        extra={"handler": "file"},
                    )
                    # Continue anyway - the interruption will still be handled
            elif elapsed_time >= 10000:
                logger.warning(
                    f"Elapsed time too large for truncation: {elapsed_time}ms",
                    extra={"handler": "file"},
                )

        # Send clear event to Twilio to stop playback
        if stream_sid:
            try:
                await websocket.send_json({"event": "clear", "streamSid": stream_sid})
                logger.info(
                    f"Sent clear event to Twilio for stream: {stream_sid}",
                    # extra={"handler": "file"},
                )
            except Exception as e:
                logger.error(
                    f"Failed to send clear event: {e}",
                    extra={"handler": "file"},
                )

        # Clear mark queue on interruption - marks for unplayed audio are no longer valid
        if mark_queue:
            logger.info(
                f"Clearing {len(mark_queue)} unacknowledged marks on interruption",
                extra={"handler": "file"},
            )
            mark_queue.clear()
