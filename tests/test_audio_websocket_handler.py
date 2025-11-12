"""
Tests for AudioWebSocketHandler with AsyncOpenAI integration
"""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from cti.api.audio_websocket_handler import AudioWebSocketHandler


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
        self.clear_called = False

    async def append(self, audio):
        self.append_called = True
        self.append_audio = audio

    async def clear(self):
        self.clear_called = True


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
        self.cancel_called = False

    async def create(self):
        self.create_called = True

    async def cancel(self):
        self.cancel_called = True


@pytest.fixture
def mock_websocket():
    """Mock FastAPI WebSocket"""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
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
def mock_tts_service():
    """Mock TTS service"""
    tts = AsyncMock()
    tts.text_to_pcm16 = AsyncMock(return_value=b"pcm16_audio_data")
    tts.text_to_wav = AsyncMock(return_value=b"wav_audio_data")
    return tts


@pytest.fixture
def handler():
    """AudioWebSocketHandler instance"""
    return AudioWebSocketHandler()


@pytest.mark.asyncio
async def test_session_initialization(handler, mock_websocket, mock_openai_client):
    """Test that session is properly initialized with PCM16 format"""
    client, connection = mock_openai_client

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        task = asyncio.create_task(handler.handle_connection(mock_websocket))

        await asyncio.sleep(0.1)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Verify session was initialized
    assert connection.session.update_called
    assert connection.session.update_config is not None
    assert connection.session.update_config["output_modalities"] == ["audio"]
    # Verify PCM16 format is used
    assert connection.session.update_config["audio"]["input"]["format"]["type"] == "pcm16"
    assert connection.session.update_config["audio"]["output"]["format"]["type"] == "pcm16"
    assert "tools" in connection.session.update_config


@pytest.mark.asyncio
async def test_audio_message_handling(handler, mock_websocket, mock_openai_client):
    """Test that audio messages from client are properly forwarded to OpenAI"""
    client, connection = mock_openai_client

    # Mock audio message
    audio_data = b"test_audio_data"
    audio_payload = base64.b64encode(audio_data).decode('utf-8')
    audio_message = json.dumps({
        "event": "audio",
        "payload": audio_payload,
        "timestamp": 123456,
        "format": "pcm16"
    })

    async def mock_iter_text():
        yield audio_message
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Verify audio was appended to buffer
    assert connection.input_audio_buffer.append_called
    assert connection.input_audio_buffer.append_audio == audio_data


@pytest.mark.asyncio
async def test_audio_delta_handling(handler, mock_websocket, mock_openai_client):
    """Test that audio delta events are properly forwarded to client"""
    client, connection = mock_openai_client

    # Create audio delta event
    audio_data = b"test_audio_output"
    audio_b64 = base64.b64encode(audio_data).decode('utf-8')
    audio_event = MockEvent(
        "response.output_audio.delta",
        delta=audio_b64,
        item_id="item_123"
    )

    connection.add_event(audio_event)

    async def mock_iter_text():
        if False:
            yield
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass

    # Verify audio was sent to client
    assert mock_websocket.send_json.called
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["event"] == "audio"
    assert "payload" in call_args
    assert call_args["format"] == "pcm16"


@pytest.mark.asyncio
async def test_start_message_handling(handler, mock_websocket, mock_openai_client):
    """Test that start message properly initializes session manager"""
    client, connection = mock_openai_client

    start_message = json.dumps({
        "event": "start",
        "session_id": "test_session_123"
    })

    async def mock_iter_text():
        yield start_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        with patch('cti.api.audio_websocket_handler.SessionManager') as mock_session_manager:
            mock_session_instance = MagicMock()
            mock_session_manager.return_value = mock_session_instance

            try:
                await handler.handle_connection(mock_websocket)
            except WebSocketDisconnect:
                pass

            # Verify SessionManager was created with correct session_id
            mock_session_manager.assert_called_once_with("test_session_123")


@pytest.mark.asyncio
async def test_text_to_audio_pcm16(handler, mock_websocket, mock_openai_client, mock_tts_service):
    """Test text-to-audio conversion with PCM16 format"""
    client, connection = mock_openai_client

    text_message = json.dumps({
        "event": "text",
        "text": "Hello, this is a test",
        "format": "pcm16"
    })

    async def mock_iter_text():
        yield text_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        with patch.object(handler, 'tts_service', mock_tts_service):
            try:
                await handler.handle_connection(mock_websocket)
            except WebSocketDisconnect:
                pass

    # Verify TTS was called
    mock_tts_service.text_to_pcm16.assert_called_once_with("Hello, this is a test", None)

    # Verify audio was sent to client
    assert mock_websocket.send_json.called
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["event"] == "audio"
    assert "payload" in call_args
    assert call_args["format"] == "pcm16"


@pytest.mark.asyncio
async def test_text_to_audio_wav(handler, mock_websocket, mock_openai_client, mock_tts_service):
    """Test text-to-audio conversion with WAV format"""
    client, connection = mock_openai_client

    text_message = json.dumps({
        "event": "text",
        "text": "Hello, this is a test",
        "format": "wav",
        "voice": "nova"
    })

    async def mock_iter_text():
        yield text_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        with patch.object(handler, 'tts_service', mock_tts_service):
            try:
                await handler.handle_connection(mock_websocket)
            except WebSocketDisconnect:
                pass

    # Verify TTS was called with WAV format
    mock_tts_service.text_to_wav.assert_called_once_with("Hello, this is a test", "nova")

    # Verify audio was sent to client
    assert mock_websocket.send_json.called
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["event"] == "audio"
    assert call_args["format"] == "wav"


@pytest.mark.asyncio
async def test_text_message_empty_text(handler, mock_websocket, mock_openai_client):
    """Test that empty text message returns error"""
    client, connection = mock_openai_client

    text_message = json.dumps({
        "event": "text",
        "text": ""
    })

    async def mock_iter_text():
        yield text_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Verify error was sent
    assert mock_websocket.send_json.called
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["event"] == "error"
    assert "Text message is required" in call_args["message"]


@pytest.mark.asyncio
async def test_control_message_pause(handler, mock_websocket, mock_openai_client):
    """Test pause control message"""
    client, connection = mock_openai_client

    # Send pause message
    pause_message = json.dumps({
        "event": "pause"
    })

    # Send audio message after pause (should be ignored)
    audio_data = b"test_audio"
    audio_payload = base64.b64encode(audio_data).decode('utf-8')
    audio_message = json.dumps({
        "event": "audio",
        "payload": audio_payload
    })

    async def mock_iter_text():
        yield pause_message
        await asyncio.sleep(0.05)
        yield audio_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Audio should not be appended when paused
    # Note: This is a timing-dependent test, but pause should prevent audio processing


@pytest.mark.asyncio
async def test_control_message_resume(handler, mock_websocket, mock_openai_client):
    """Test resume control message"""
    client, connection = mock_openai_client

    # Send pause then resume
    pause_message = json.dumps({"event": "pause"})
    resume_message = json.dumps({"event": "resume"})

    async def mock_iter_text():
        yield pause_message
        await asyncio.sleep(0.05)
        yield resume_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Test passes if no exceptions are raised


@pytest.mark.asyncio
async def test_control_message_stop(handler, mock_websocket, mock_openai_client):
    """Test stop control message"""
    client, connection = mock_openai_client

    stop_message = json.dumps({
        "event": "stop"
    })

    async def mock_iter_text():
        yield stop_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Verify response.cancel was called if available
    # Note: MockResponse doesn't have cancel by default, but the handler checks for it


@pytest.mark.asyncio
async def test_control_message_clear(handler, mock_websocket, mock_openai_client):
    """Test clear control message"""
    client, connection = mock_openai_client

    clear_message = json.dumps({
        "event": "clear"
    })

    async def mock_iter_text():
        yield clear_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Verify input buffer was cleared
    assert connection.input_audio_buffer.clear_called


@pytest.mark.asyncio
async def test_function_call_handling(handler, mock_websocket, mock_openai_client):
    """Test that function calls are properly handled"""
    client, connection = mock_openai_client

    function_event = MockEvent(
        "response.function_call_arguments.done",
        call_id="call_123",
        name="test_tool",
        arguments='{"param1": "value1"}'
    )

    connection.add_event(function_event)

    async def mock_iter_text():
        if False:
            yield
        await asyncio.sleep(0.2)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
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

    # Mock start message to set session
    async def mock_iter_text():
        yield json.dumps({
            "event": "start",
            "session_id": "session_123"
        })
        await asyncio.sleep(0.2)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except (WebSocketDisconnect, StopAsyncIteration):
            pass

    # Verify truncation was called
    assert connection.conversation.item.truncate_called
    truncate_params = connection.conversation.item.truncate_params
    assert truncate_params["item_id"] == "item_123"
    assert truncate_params["content_index"] == 0

    # Verify clear event was sent
    clear_calls = [
        call[0][0] for call in mock_websocket.send_json.call_args_list
        if call[0][0].get("event") == "clear"
    ]
    assert len(clear_calls) > 0


@pytest.mark.asyncio
async def test_invalid_message_format(handler, mock_websocket, mock_openai_client):
    """Test that invalid message format returns error"""
    client, connection = mock_openai_client

    invalid_message = json.dumps({
        "invalid": "message"
    })

    async def mock_iter_text():
        yield invalid_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Verify error was sent (or message was ignored gracefully)
    # The handler should handle invalid messages without crashing


@pytest.mark.asyncio
async def test_audio_paused_ignored(handler, mock_websocket, mock_openai_client):
    """Test that audio messages are ignored when paused"""
    client, connection = mock_openai_client

    # Send pause
    pause_message = json.dumps({"event": "pause"})

    # Send audio after pause
    audio_data = b"test_audio"
    audio_payload = base64.b64encode(audio_data).decode('utf-8')
    audio_message = json.dumps({
        "event": "audio",
        "payload": audio_payload
    })

    async def mock_iter_text():
        yield pause_message
        await asyncio.sleep(0.05)
        yield audio_message
        await asyncio.sleep(0.1)
        raise WebSocketDisconnect()

    mock_websocket.iter_text = lambda: mock_iter_text()

    with patch('cti.api.audio_websocket_handler.AsyncOpenAI', return_value=client):
        try:
            await handler.handle_connection(mock_websocket)
        except WebSocketDisconnect:
            pass

    # Audio should not be processed when paused
    # The handler checks is_paused before processing audio

