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
            # Use deployment_name for Azure OpenAI, not full model name
            deployment_name = "gpt-realtime-mini"
            async with client.realtime.connect(model=deployment_name) as connection:
                await self._initialize_session(connection)

                # Connection state
                stream_sid = None
                latest_media_timestamp = 0
                last_assistant_item = None
                mark_queue = []
                response_start_timestamp_twilio = None
                session_manager: Optional[SessionManager] = None

                async def receive_from_twilio():
                    """Receive audio from Twilio and send to OpenAI"""
                    nonlocal stream_sid, latest_media_timestamp, session_manager

                    try:
                        async for message in websocket.iter_text():
                            try:
                                data: dict = json.loads(message)
                                event_type = data.get("event")

                                if event_type == "connected":
                                    logger.info(f"Connected to Twilio: {data}")
                                elif "start" in data and data.get("start") == "connected":
                                    logger.info(f"Connected to Twilio: {data}")

                                elif event_type == "media":
                                    media_data = data.get("media", {})
                                    timestamp = media_data.get("timestamp")
                                    payload = media_data.get("payload")

                                    if timestamp is not None:
                                        latest_media_timestamp = int(timestamp)
                                    if payload:
                                        # Decode base64 and append to OpenAI input buffer
                                        audio_data = base64.b64decode(payload)
                                        await connection.input_audio_buffer.append(
                                            audio=audio_data
                                        )

                                elif event_type == "start":
                                    start_data = data.get("start", {})
                                    stream_sid = start_data.get("streamSid")
                                    logger.info(f"Incoming stream has started: {stream_sid}")
                                    if stream_sid:
                                        session_manager = SessionManager(stream_sid)

                                elif event_type == "closed":
                                    logger.info(f"Closed connection to Twilio: {data}")
                                elif event_type == "mark":
                                    if mark_queue:
                                        mark_queue.pop(0)

                            except (KeyError, ValueError, TypeError) as e:
                                logger.error(f"Error parsing message: {e}", extra={"handler": "file"})
                                
                            except Exception as e:
                                logger.error(f"Error in receive_from_twilio: {e}", extra={"handler": "file"})

                    except WebSocketDisconnect:
                        logger.info("Client disconnected")
                        if session_manager:
                            session_manager.save_to_file()

                async def send_to_twilio():
                    """Receive events from OpenAI and send audio to Twilio"""
                    nonlocal last_assistant_item, response_start_timestamp_twilio

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
                                    response_start_timestamp_twilio = latest_media_timestamp
                                    last_assistant_item = event.item_id

                                await self._send_mark(websocket, stream_sid, mark_queue)

                            # Handle interruption
                            if event.type == "input_audio_buffer.speech_started":
                                logger.info("Speech started detected")
                                if last_assistant_item:
                                    logger.info(
                                        f"Interrupting response with id: {last_assistant_item}"
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
                        logger.info(f"Error in send_to_twilio: {e}")

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
            "model": "gpt-realtime",
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {"type": "server_vad"},
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
        if mark_queue and response_start_timestamp_twilio is not None and last_assistant_item:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

            await connection.conversation.item.truncate(
                item_id=last_assistant_item,
                content_index=0,
                audio_end_ms=elapsed_time,
            )

            await websocket.send_json({"event": "clear", "streamSid": stream_sid})

            mark_queue.clear()
