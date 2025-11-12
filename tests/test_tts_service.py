"""
Tests for TTSService
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cti.services.tts_service import TTSService


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI TTS response"""
    response = AsyncMock()
    response.read = AsyncMock(return_value=b"fake_audio_data_pcm16")
    return response


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Mock AsyncOpenAI client"""
    client = MagicMock()
    client.audio.speech.create = AsyncMock(return_value=mock_openai_response)
    return client


@pytest.fixture
def tts_service():
    """TTSService instance"""
    return TTSService()


@pytest.mark.asyncio
async def test_text_to_audio_basic(tts_service, mock_openai_client):
    """Test basic text-to-audio conversion"""
    with patch.object(tts_service, 'client', mock_openai_client):
        result = await tts_service.text_to_audio("Hello", voice="alloy", format="pcm")
    
    assert result == b"fake_audio_data_pcm16"
    mock_openai_client.audio.speech.create.assert_called_once_with(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input="Hello",
        response_format="pcm"
    )


@pytest.mark.asyncio
async def test_text_to_audio_default_voice(tts_service, mock_openai_client):
    """Test text-to-audio with default voice from settings"""
    with patch.object(tts_service, 'client', mock_openai_client):
        result = await tts_service.text_to_audio("Test message")
    
    assert result == b"fake_audio_data_pcm16"
    call_args = mock_openai_client.audio.speech.create.call_args[1]
    assert call_args["input"] == "Test message"
    assert call_args["response_format"] == "pcm"


@pytest.mark.asyncio
async def test_text_to_pcm16(tts_service, mock_openai_client):
    """Test text_to_pcm16 convenience method"""
    with patch.object(tts_service, 'client', mock_openai_client):
        result = await tts_service.text_to_pcm16("Short text")
    
    assert result == b"fake_audio_data_pcm16"
    # When voice=None, service uses default from settings (typically "alloy")
    call_args = mock_openai_client.audio.speech.create.call_args[1]
    assert call_args["input"] == "Short text"
    assert call_args["response_format"] == "pcm"
    assert call_args["model"] == "gpt-4o-mini-tts"


@pytest.mark.asyncio
async def test_text_to_wav(tts_service, mock_openai_client):
    """Test text_to_wav converts PCM to WAV format"""
    with patch.object(tts_service, 'client', mock_openai_client):
        result = await tts_service.text_to_wav("Test")
    
    # WAV should have header + PCM data
    assert result.startswith(b"RIFF")
    assert b"WAVE" in result
    assert b"fake_audio_data_pcm16" in result


@pytest.mark.asyncio
async def test_text_to_audio_error_handling(tts_service, mock_openai_client):
    """Test error handling in text_to_audio"""
    mock_openai_client.audio.speech.create = AsyncMock(side_effect=Exception("API Error"))
    
    with patch.object(tts_service, 'client', mock_openai_client):
        with pytest.raises(Exception, match="API Error"):
            await tts_service.text_to_audio("Test")

