"""
WebSocket Handler - Xử lý WebSocket connections giữa Twilio và OpenAI
"""

import asyncio
import base64
import json
from typing import Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from openai import AsyncOpenAI

from cti.config.constants import LOG_EVENT_TYPES
from cti.config.prompts import SYSTEM_MESSAGE
from cti.config.settings import settings
from cti.core.session_manager import SessionManager
from cti.services.tool_service import ToolService


class WebSocketHandler:
    """Handle WebSocket connections between Twilio and OpenAI"""

    def __init__(self):
        self.tool_service = ToolService()

    async def handle_connection(self, websocket: WebSocket):
        """
        Main handler for WebSocket connections.

        Args:
            websocket: FastAPI WebSocket connection
        """
        print("Client connected")
        await websocket.accept()

        # For Azure OpenAI, construct websocket_base_url from base_url
        # If base_url is already a websocket URL, use it directly
        if settings.OPENAI_BASE_URL.startswith("wss://"):
            websocket_base_url = settings.OPENAI_BASE_URL
        else:
            # Remove https:// and trailing slashes
            endpoint = settings.OPENAI_BASE_URL.replace("https://", "").rstrip("/")
            # Construct websocket URL with API version and deployment for Azure
            # Extract deployment name from model (remove version suffix if present)
            # e.g., "gpt-realtime-mini-2025-10-06" -> "gpt-realtime-mini"
            deployment_name = "gpt-realtime-mini"
            websocket_base_url = f"wss://{endpoint}/openai/v1/realtime?api-version=2024-10-01-preview&deployment={deployment_name}"
        
        try:
            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                websocket_base_url=websocket_base_url
            )
        except Exception as e:
            print(f"❌ Failed to initialize OpenAI client: {e}")
            await websocket.close(code=1011, reason="OpenAI client initialization failed")
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
                            data = json.loads(message)

                            if data["event"] == "media":
                                latest_media_timestamp = int(data["media"]["timestamp"])
                                await connection.input_audio_buffer.append(
                                    audio=data["media"]["payload"]
                                )

                            elif data["event"] == "start":
                                stream_sid = data["start"]["streamSid"]
                                print(f"Incoming stream has started {stream_sid}")
                                session_manager = SessionManager(stream_sid)

                            elif data["event"] == "mark":
                                if mark_queue:
                                    mark_queue.pop(0)

                    except WebSocketDisconnect:
                        print("Client disconnected.")
                        if session_manager:
                            session_manager.save_to_file()

                async def send_to_twilio():
                    """Receive events from OpenAI and send audio to Twilio"""
                    nonlocal last_assistant_item, response_start_timestamp_twilio

                    try:
                        async for event in connection:
                            if event.type in LOG_EVENT_TYPES:
                                print(f"Received event: {event.type}", event)

                            # Handle function call
                            if event.type == "response.function_call_arguments.done":
                                await self._handle_function_call(
                                    event, connection, session_manager
                                )

                            # Send audio delta
                            if event.type == "response.output_audio.delta" and hasattr(
                                event, "delta"
                            ):
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
                                print("Speech started detected.")
                                if last_assistant_item:
                                    print(
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
                        print(f"Error in send_to_twilio: {e}")

                await asyncio.gather(receive_from_twilio(), send_to_twilio())
        except Exception as e:
            print(f"❌ Error in OpenAI connection: {e}")
            import traceback
            traceback.print_exc()
            try:
                await websocket.close(code=1011, reason=f"OpenAI connection error: {str(e)}")
            except Exception:
                pass

    async def _initialize_session(self, connection):
        """Initialize OpenAI session with tools"""
        session_config = {
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
        print("Sending session update:", json.dumps(session_config))
        await connection.session.update(session=session_config)

    async def _handle_function_call(self, event, connection, session_manager):
        """Handle function call from OpenAI"""
        print(f"\nFunction call received: {event}")

        call_id = getattr(event, "call_id", None)
        function_name = getattr(event, "name", None)
        arguments_str = getattr(event, "arguments", "{}")

        try:
            arguments = json.loads(arguments_str)
            print(f"Executing tool: {function_name} with args: {arguments}")

            if session_manager:
                result = await self.tool_service.execute_tool(
                    function_name, arguments, session_manager
                )
            else:
                result = {"error": "Session manager not initialized", "success": False}

            print(f"Tool result: {result}")

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
            print(f"Error handling function call: {e}")
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
        connection,
        websocket,
        stream_sid,
        latest_media_timestamp,
        response_start_timestamp_twilio,
        last_assistant_item,
        mark_queue,
    ):
        """Handle speech interruption"""
        if mark_queue and response_start_timestamp_twilio is not None:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

            if last_assistant_item:
                await connection.conversation.item.truncate(
                    item_id=last_assistant_item,
                    content_index=0,
                    audio_end_ms=elapsed_time,
                )

            await websocket.send_json({"event": "clear", "streamSid": stream_sid})

            mark_queue.clear()
