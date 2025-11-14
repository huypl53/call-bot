"""
WebSocket Handler - Xử lý WebSocket connections giữa Twilio và OpenAI
"""

import asyncio
import base64
import json
from typing import Optional

import websockets
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from cti.config.constants import LOG_EVENT_TYPES, OPENAI_MODEL, SHOW_TIMING_MATH
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

        openai_url = (
            f"wss://api.openai.com/v1/realtime?"
            f"model={OPENAI_MODEL}&temperature={settings.TEMPERATURE}"
        )

        async with websockets.connect(
            openai_url,
            additional_headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        ) as openai_ws:
            await self._initialize_session(openai_ws)

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

                        if data['event'] == 'media' and openai_ws.state.name == 'OPEN':
                            latest_media_timestamp = int(data['media']['timestamp'])
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }))

                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Incoming stream has started {stream_sid}")
                            session_manager = SessionManager(stream_sid)

                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)

                except WebSocketDisconnect:
                    print("Client disconnected.")
                    if session_manager:
                        session_manager.save_to_file()
                    if openai_ws.state.name == 'OPEN':
                        await openai_ws.close()

            async def send_to_twilio():
                """Receive events from OpenAI and send audio to Twilio"""
                nonlocal last_assistant_item, response_start_timestamp_twilio

                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)

                        if response['type'] in LOG_EVENT_TYPES:
                            print(f"Received event: {response['type']}", response)

                        # Handle function call
                        if response.get('type') == 'response.function_call_arguments.done':
                            await self._handle_function_call(
                                response, openai_ws, session_manager
                            )

                        # Send audio delta
                        if response.get('type') == 'response.output_audio.delta' and 'delta' in response:
                            audio_payload = base64.b64encode(
                                base64.b64decode(response['delta'])
                            ).decode('utf-8')

                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload}
                            })

                            if response.get("item_id") and response["item_id"] != last_assistant_item:
                                response_start_timestamp_twilio = latest_media_timestamp
                                last_assistant_item = response["item_id"]

                            await self._send_mark(websocket, stream_sid, mark_queue)

                        # Handle interruption
                        if response.get('type') == 'input_audio_buffer.speech_started':
                            print("Speech started detected.")
                            if last_assistant_item:
                                print(f"Interrupting response with id: {last_assistant_item}")
                                await self._handle_speech_started(
                                    openai_ws, websocket, stream_sid,
                                    latest_media_timestamp, response_start_timestamp_twilio,
                                    last_assistant_item, mark_queue
                                )

                except Exception as e:
                    print(f"Error in send_to_twilio: {e}")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

    async def _initialize_session(self, openai_ws):
        """Initialize OpenAI session with tools"""
        session_update = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": "gpt-realtime",
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcmu"},
                        "turn_detection": {"type": "server_vad"}
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": settings.VOICE
                    }
                },
                "instructions": str(SYSTEM_MESSAGE),
                "tools": self.tool_service.get_tool_definitions(),
                "tool_choice": "auto"
            }
        }
        print('Sending session update:', json.dumps(session_update))
        await openai_ws.send(json.dumps(session_update))

    async def _handle_function_call(self, event, openai_ws, session_manager):
        """Handle function call from OpenAI"""
        print(f"\nFunction call received: {event}")

        call_id = event.get('call_id')
        function_name = event.get('name')
        arguments_str = event.get('arguments', '{}')

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
            await openai_ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False)
                }
            }))

            # Trigger response generation
            await openai_ws.send(json.dumps({"type": "response.create"}))

        except Exception as e:
            print(f"Error handling function call: {e}")
            await openai_ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps({"error": str(e), "success": False}, ensure_ascii=False)
                }
            }))
            await openai_ws.send(json.dumps({"type": "response.create"}))

    async def _send_mark(self, connection, stream_sid, mark_queue):
        """Send mark event to Twilio"""
        if stream_sid:
            await connection.send_json({
                "event": "mark",
                "streamSid": stream_sid,
                "mark": {"name": "responsePart"}
            })
            mark_queue.append('responsePart')

    async def _handle_speech_started(
        self, openai_ws, websocket, stream_sid,
        latest_media_timestamp, response_start_timestamp_twilio,
        last_assistant_item, mark_queue
    ):
        """Handle speech interruption"""
        if mark_queue and response_start_timestamp_twilio is not None:
            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

            if last_assistant_item:
                await openai_ws.send(json.dumps({
                    "type": "conversation.item.truncate",
                    "item_id": last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed_time
                }))

            await websocket.send_json({
                "event": "clear",
                "streamSid": stream_sid
            })

            mark_queue.clear()
