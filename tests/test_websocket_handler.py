"""
Tests for WebSocketHandler with AsyncOpenAI integration
"""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from cti.api.websocket_handler import WebSocketHandler


class MockEvent:
    """Mock event object for OpenAI realtime events"""
    
    def __init__(self, event_type, **kwargs):
        self.type = event_type
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockConnection:
    """Mock OpenAI realtime connection"""
    
    def __init__(self):
        self.session = MockSession()
        self.input_audio_buffer = MockInputAudioBuffer()
        self.conversation = MockConversation()
        self.response = MockResponse()
        self._events = []
        self._event_index = 0
    
    def add_event(self, event):
        """Add event to the event stream"""
        self._events.append(event)
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self._event_index < len(self._events):
            event = self._events[self._event_index]
            self._event_index += 1
            return event
        raise StopAsyncIteration


class MockSession:
    """Mock session object"""
    
    def __init__(self):
        self.update_called = False
        self.update_config = None
    
    async def update(self, session):
        self.update_called = True
        self.update_config = session


class MockInputAudioBuffer:
    """Mock input audio buffer"""
    
    def __init__(self):
        self.append_called = False
        self.append_audio = None
    
    async def append(self, audio):
        self.append_called = True
        self.append_audio = audio


class MockConversation:
    """Mock conversation object"""
    
    def __init__(self):
        self.item = MockConversationItem()


class MockConversationItem:
    """Mock conversation item"""
    
    def __init__(self):
        self.create_called = False
        self.create_item = None
        self.truncate_called = False
        self.truncate_params = None
    
    async def create(self, item):
        self.create_called = True
        self.create_item = item
    
    async def truncate(self, item_id, content_index, audio_end_ms):
        self.truncate_called = True
        self.truncate_params = {
            "item_id": item_id,
            "content_index": content_index,
            "audio_end_ms": audio_end_ms
        }


class MockResponse:
    """Mock response object"""
    
    def __init__(self):
        self.create_called = False
    
    async def create(self):
        self.create_called = True


@pytest.fixture
def mock_websocket():
    """Mock FastAPI WebSocket"""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    # iter_text will be set per test with MagicMock to return async generators
    return ws


@pytest.fixture
def mock_openai_client():
    """Mock AsyncOpenAI client"""
    client = MagicMock()
    connection = MockConnection()
    
    # Create a context manager mock
    context_manager = AsyncMock()
    context_manager.__aenter__ = AsyncMock(return_value=connection)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    
    # Make connect return the context manager
    client.realtime.connect = MagicMock(return_value=context_manager)
    
    return client, connection


@pytest.fixture
def handler():
    """WebSocketHandler instance"""
    return WebSocketHandler()


@pytest.mark.asyncio
async def test_session_initialization(handler, mock_websocket, mock_openai_client):
    """Test that session is properly initialized with AsyncOpenAI"""
    client, connection = mock_openai_client
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        # Create a task that will be cancelled after a short delay
        task = asyncio.create_task(handler.handle_connection(mock_websocket))
        
        # Wait a bit for initialization
        await asyncio.sleep(0.1)
        
        # Cancel the task since we're just testing initialization
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Verify session was initialized
    assert connection.session.update_called
    assert connection.session.update_config is not None
    assert connection.session.update_config["output_modalities"] == ["audio"]
    assert "tools" in connection.session.update_config


@pytest.mark.asyncio
async def test_audio_buffer_append(handler, mock_websocket, mock_openai_client):
    """Test that audio from Twilio is properly appended to OpenAI buffer"""
    client, connection = mock_openai_client
    
    # Mock Twilio media message
    media_payload = base64.b64encode(b"test_audio_data").decode('utf-8')
    twilio_message = json.dumps({
        "event": "media",
        "media": {
            "payload": media_payload,
            "timestamp": "123456"
        }
    })
    
    # Mock websocket to return media message then disconnect
    async def mock_iter_text():
        yield twilio_message
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass
    
    # Verify audio was appended
    assert connection.input_audio_buffer.append_called
    assert connection.input_audio_buffer.append_audio == media_payload


@pytest.mark.asyncio
async def test_audio_delta_handling(handler, mock_websocket, mock_openai_client):
    """Test that audio delta events are properly forwarded to Twilio"""
    client, connection = mock_openai_client
    
    # Create audio delta event
    audio_data = b"test_audio_output"
    audio_b64 = base64.b64encode(audio_data).decode('utf-8')
    audio_event = MockEvent(
        "response.output_audio.delta",
        delta=audio_b64,
        item_id="item_123"
    )
    
    # Add event to connection and stop iteration
    connection.add_event(audio_event)
    
    # Mock empty Twilio messages - need to yield to make it an async generator
    async def mock_iter_text():
        # Yield nothing but immediately raise to stop iteration
        if False:
            yield  # Make this an async generator
        await asyncio.sleep(0.1)  # Let event processing happen
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass
    
    # Verify audio was sent to Twilio
    assert mock_websocket.send_json.called
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["event"] == "media"
    assert "media" in call_args
    assert "payload" in call_args["media"]


@pytest.mark.asyncio
async def test_function_call_handling(handler, mock_websocket, mock_openai_client):
    """Test that function calls are properly handled"""
    client, connection = mock_openai_client
    
    # Create function call event
    function_event = MockEvent(
        "response.function_call_arguments.done",
        call_id="call_123",
        name="test_tool",
        arguments='{"param1": "value1"}'
    )
    
    connection.add_event(function_event)
    
    # Mock empty Twilio messages - need to yield to make it an async generator
    async def mock_iter_text():
        # Yield nothing but immediately raise to stop iteration
        if False:
            yield  # Make this an async generator
        await asyncio.sleep(0.2)  # Let function call processing happen
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass
    
    # Verify function call output was created
    assert connection.conversation.item.create_called
    assert connection.response.create_called
    create_item = connection.conversation.item.create_item
    assert create_item["type"] == "function_call_output"
    assert create_item["call_id"] == "call_123"


@pytest.mark.asyncio
async def test_speech_started_interruption(handler, mock_websocket, mock_openai_client):
    """Test that speech interruption is properly handled"""
    client, connection = mock_openai_client
    
    # First add an audio event to set last_assistant_item
    audio_event = MockEvent(
        "response.output_audio.delta",
        delta=base64.b64encode(b"audio").decode('utf-8'),
        item_id="item_123"
    )
    connection.add_event(audio_event)
    
    # Then add speech started event
    speech_event = MockEvent("input_audio_buffer.speech_started")
    connection.add_event(speech_event)
    
    # Mock Twilio start message to set stream_sid
    async def mock_iter_text():
        yield json.dumps({
            "event": "start",
            "start": {"streamSid": "stream_123"}
        })
        await asyncio.sleep(0.2)  # Let event processing happen
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass
    
    # Verify truncation was called
    assert connection.conversation.item.truncate_called
    truncate_params = connection.conversation.item.truncate_params
    assert truncate_params["item_id"] == "item_123"
    assert truncate_params["content_index"] == 0


@pytest.mark.asyncio
async def test_stream_start_initialization(handler, mock_websocket, mock_openai_client):
    """Test that stream start properly initializes session manager"""
    client, connection = mock_openai_client
    
    # Mock Twilio start message
    start_message = json.dumps({
        "event": "start",
        "start": {"streamSid": "test_stream_123"}
    })
    
    async def mock_iter_text():
        yield start_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        with patch('cti.api.websocket_handler.SessionManager') as mock_session_manager:
            mock_session_instance = MagicMock()
            mock_session_manager.return_value = mock_session_instance
            
            try:
                await handler.handle_connection(mock_websocket)
            except WebSocketDisconnect:
                pass
            
            # Verify SessionManager was created with correct stream_sid
            mock_session_manager.assert_called_once_with("test_stream_123")


@pytest.mark.asyncio
async def test_mark_event_handling(handler, mock_websocket, mock_openai_client):
    """Test that mark events are properly handled"""
    client, connection = mock_openai_client
    
    # Create audio event to trigger mark sending
    audio_event = MockEvent(
        "response.output_audio.delta",
        delta=base64.b64encode(b"audio").decode('utf-8'),
        item_id="item_123"
    )
    connection.add_event(audio_event)
    
    # Mock Twilio messages with start and mark
    async def mock_iter_text():
        yield json.dumps({
            "event": "start",
            "start": {"streamSid": "stream_123"}
        })
        await asyncio.sleep(0.1)
        yield json.dumps({"event": "mark"})
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()
    
    mock_websocket.iter_text = lambda: mock_iter_text()
    
    with patch('cti.api.websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass
    
    # Verify mark was sent to Twilio
    mark_calls = [
        call[0][0] for call in mock_websocket.send_json.call_args_list
        if call[0][0].get("event") == "mark"
    ]
    assert len(mark_calls) > 0
    assert mark_calls[0]["streamSid"] == "stream_123"

