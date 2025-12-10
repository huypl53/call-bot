# WebSocket Call Center - Flow Documentation

This document describes the complete flow of the `WebSocketHandler` module, which bridges **Twilio Media Streams** with **OpenAI Realtime API** to create a voice-based AI call center.

---

## Architecture Overview

```
┌─────────────────┐      WebSocket       ┌─────────────────────────┐      WebSocket       ┌─────────────────┐
│                 │  (Twilio Protocol)   │                         │  (OpenAI Protocol)   │                 │
│  Twilio Phone   │ ◄──────────────────► │   WebSocketHandler      │ ◄──────────────────► │  OpenAI        │
│  Call (mulaw)   │                      │   (FastAPI Server)      │                      │  Realtime API   │
│                 │                      │                         │                      │                 │
└─────────────────┘                      └─────────────────────────┘                      └─────────────────┘
                                                    │
                                                    │ Uses
                                                    ▼
                                         ┌─────────────────────────┐
                                         │  SessionManager         │
                                         │  ToolService            │
                                         └─────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `WebSocketHandler` | `src/cti/api/websocket_handler_new.py` | Main bridge between Twilio and OpenAI |
| `SessionManager` | `src/cti/core/session_manager.py` | Manages booking session data per call |
| `ToolService` | `src/cti/services/tool_service.py` | Registry and executor for AI tools |
| `AsyncRealtimeConnection` | OpenAI SDK | Async WebSocket connection to OpenAI |

---

## Connection Lifecycle

### Phase 1: Connection Establishment

```
Twilio ──► FastAPI ──► OpenAI
```

1. **Twilio initiates WebSocket connection** to the FastAPI endpoint
2. **FastAPI accepts the connection**: `await websocket.accept()`
3. **OpenAI client is initialized** with `AsyncOpenAI`:
   ```python
   client = AsyncOpenAI(
       api_key=settings.OPENAI_API_KEY,
       websocket_base_url=websocket_base_url
   )
   ```
4. **OpenAI Realtime connection established**:
   ```python
   async with client.realtime.connect(model=deployment_name) as connection:
   ```

### Phase 2: Session Initialization

The `_initialize_session()` method configures the OpenAI session:

```python
session_config = {
    "type": "realtime",
    "model": settings.MODEL,
    "output_modalities": ["audio"],
    "audio": {
        "input": {
            "format": {"type": "audio/pcmu"},  # mulaw 8kHz from Twilio
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 200,
                "create_response": True,
                "interrupt_response": True,  # Enable barge-in
            },
        },
        "output": {
            "format": {"type": "audio/pcmu"},
            "voice": settings.VOICE
        },
    },
    "instructions": SYSTEM_MESSAGE,
    "tools": tool_service.get_tool_definitions(),
    "tool_choice": "auto",
}
```

**Key Configuration:**
- **Audio Format**: `audio/pcmu` (mulaw 8kHz) - matches Twilio's format
- **Server VAD**: Automatic voice activity detection with interruption support
- **Tools**: Registered via `ToolService` for function calling

### Phase 3: Concurrent Event Processing

Two async tasks run concurrently via `asyncio.gather()`:

```python
await asyncio.gather(
    receive_from_twilio(),  # Twilio → OpenAI
    send_to_twilio(),       # OpenAI → Twilio
    return_exceptions=True
)
```

### Phase 4: Connection Cleanup

On disconnect or error:
1. Flush remaining audio buffers
2. Save session data via `SessionManager.save_to_file()`
3. Record accumulated audio chunks
4. Close WebSocket connections

---

## Twilio Event Handling (`receive_from_twilio`)

This function processes incoming WebSocket messages from Twilio.

### Event Flow Diagram

```
Twilio WebSocket Message
         │
         ▼
    ┌────────────┐
    │ Parse JSON │
    └────────────┘
         │
         ▼
    ┌────────────────────────────────────────────────────────┐
    │                    Event Type Router                   │
    ├────────────┬───────────┬────────┬───────┬──────┬──────┤
    │ connected  │  start    │ media  │ mark  │ dtmf │ stop │
    └────────────┴───────────┴────────┴───────┴──────┴──────┘
```

### Event Types

#### `connected`
First message after WebSocket handshake.
```json
{ 
  "event": "connected",
  "protocol": "Call", 
  "version": "1.0.0"
}
```
**Handler**: Logs connection confirmation.

#### `start`
Stream metadata, sent once at stream start.
```json
{
  "event": "start",
  "start": {
    "streamSid": "MZXXXXXX",
    "accountSid": "ACXXXXXX",
    "callSid": "CAXXXXXX",
    "mediaFormat": { 
      "encoding": "audio/x-mulaw", 
      "sampleRate": 8000, 
      "channels": 1 
    }
  }
}
```
**Handler**:
```python
stream_sid = start_data.get("streamSid")
session_manager = SessionManager(stream_sid)
```

#### `media`
Raw audio data (base64-encoded mulaw).
```json
{ 
  "event": "media",
  "media": { 
    "track": "inbound", 
    "timestamp": "5",
    "payload": "no+JhoaJjpz..."  # base64 mulaw audio
  }
}
```
**Handler**:
```python
# Update timestamp for sync
latest_media_timestamp = int(timestamp)
# Accumulate for recording
twilio_audio_chunks.append(payload)
# Forward to OpenAI
await connection.input_audio_buffer.append(audio=payload)
```

#### `mark`
Acknowledgment that audio has been played.
```json
{ 
  "event": "mark",
  "mark": { "name": "responsePart" }
}
```
**Handler**:
```python
mark_acknowledged.add(mark_name)
if mark_queue and mark_queue[0] == mark_name:
    mark_queue.pop(0)
```

#### `dtmf`
Touch-tone keypad press.
```json
{ 
  "event": "dtmf",
  "dtmf": { "track": "inbound_track", "digit": "1" }
}
```
**Handler**: Logs the digit (can be extended for IVR flows).

#### `stop` / `closed`
Stream ended or connection closed.
**Handler**:
```python
# Record complete audio
if twilio_audio_chunks:
    complete_audio = "".join(twilio_audio_chunks)
    record_audio(complete_audio, "twilio", latest_media_timestamp)
    twilio_audio_chunks.clear()
```

---

## OpenAI Event Handling (`send_to_twilio`)

This function processes events from OpenAI Realtime API and sends audio to Twilio.

### Event Flow Diagram

```
OpenAI Realtime Event
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │                        Event Type Router                            │
    ├──────────────┬──────────────┬───────────────────┬──────────────────┤
    │   Session    │   Response   │   Input Buffer    │   Function Call  │
    │   Events     │   Events     │   Events          │   Events         │
    └──────────────┴──────────────┴───────────────────┴──────────────────┘
```

### Session Events

#### `session.created`
Connection to OpenAI established successfully.
```json
{
  "type": "session.created",
  "session": { "id": "sess_XXX", "model": "gpt-realtime-..." }
}
```
**Handler**: Sets `connection_healthy = True`, logs session details.

#### `error`
Error from OpenAI (most are recoverable).
```json
{
  "type": "error",
  "error": { "type": "invalid_request_error", "message": "..." }
}
```
**Handler**: Logs error, sets `connection_healthy = False` for critical errors.

### Response Lifecycle Events

#### `response.created`
New response generation started.
```json
{
  "type": "response.created",
  "response": { "id": "resp_XXX", "status": "in_progress" }
}
```
**Handler**:
```python
is_response_active = True
response_status = "in_progress"
current_response_id = event.response.id
response_start_time = time.time()
openai_audio_chunks.clear()  # Clear for new response
```

#### `response.output_audio.delta`
Streaming audio chunk from OpenAI.
```json
{
  "type": "response.output_audio.delta",
  "delta": "Base64EncodedAudioDelta",
  "item_id": "item_XXX"
}
```
**Handler**:
```python
# Track latency
if first_audio_time is None:
    first_audio_time = time.time()
    time_to_first_audio = first_audio_time - response_start_time

# Accumulate for recording
openai_audio_chunks.append(audio_payload)

# Buffer for batching (optimize network)
audio_chunk_buffer.append(audio_payload)
audio_chunk_buffer_size += len(audio_payload)

# Flush when buffer full or not interrupting
if audio_chunk_buffer_size >= max_chunk_buffer_size or not is_interrupting:
    await _flush_audio_buffer(websocket, stream_sid, audio_chunk_buffer)
```

**Sending to Twilio** (via `_flush_audio_buffer`):
```python
await websocket.send_json({
    "event": "media",
    "streamSid": stream_sid,
    "media": {"payload": audio_payload}
})
```

#### `response.done`
Response generation completed.
```json
{
  "type": "response.done",
  "response": { "id": "resp_XXX", "status": "completed" }
}
```
**Handler**:
```python
is_response_active = False
response_status = event.response.status  # completed/cancelled/failed/incomplete

# Flush remaining audio
await _flush_audio_buffer(websocket, stream_sid, audio_chunk_buffer)

# Log latency
total_latency = time.time() - response_start_time

# Record complete audio
if openai_audio_chunks:
    complete_audio = "".join(openai_audio_chunks)
    record_audio(complete_audio, "openai", latest_media_timestamp)
```

### Input Audio Buffer Events (VAD)

#### `input_audio_buffer.speech_started`
User started speaking (VAD detected voice).
```json
{
  "type": "input_audio_buffer.speech_started",
  "audio_start_ms": 1000,
  "item_id": "msg_003"
}
```
**Handler** (Barge-in / Interruption):
```python
is_interrupting = True

if is_response_active:
    # Cancel current response
    if current_response_id:
        await connection.response.cancel(response_id=current_response_id)
    
    # Discard buffered audio
    audio_chunk_buffer.clear()
    
    # Handle speech interruption (truncate + clear Twilio buffer)
    await _handle_speech_started(...)
```

#### `input_audio_buffer.speech_stopped`
User stopped speaking.
```json
{
  "type": "input_audio_buffer.speech_stopped",
  "audio_end_ms": 2000,
  "item_id": "msg_003"
}
```
**Handler**: Sets `is_interrupting = False`.

#### `input_audio_buffer.committed`
Audio buffer committed (creates user message item).
```json
{
  "type": "input_audio_buffer.committed",
  "item_id": "msg_002"
}
```
**Handler**: Triggers similar handling as `speech_started` if response is active.

#### `input_audio_buffer.cleared`
Buffer was cleared (typically after barge-in).
**Handler**: Sets `is_interrupting = True`, clears output audio buffer.

#### `input_audio_buffer.timeout_triggered`
Idle timeout triggered (no speech detected).
**Handler**: Logs timeout event.

### Function Call Events

#### `response.function_call_arguments.done`
Function call arguments fully received.
```json
{
  "type": "response.function_call_arguments.done",
  "call_id": "call_001",
  "name": "check_room_availability",
  "arguments": "{\"date\": \"2024-01-15\"}"
}
```
**Handler** (`_handle_function_call`):
```python
# Parse arguments
arguments = json.loads(arguments_str)

# Execute tool
result = await tool_service.execute_tool(function_name, arguments, session_manager)

# Send result back to OpenAI
await connection.conversation.item.create(
    item={
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(result)
    }
)

# Trigger new response with tool result
await connection.response.create()
```

---

## Interruption Handling (Barge-in)

When a user speaks while the AI is responding:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Barge-in Flow                                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. OpenAI detects speech: input_audio_buffer.speech_started             │
│                     │                                                    │
│                     ▼                                                    │
│  2. Cancel response: connection.response.cancel(response_id)             │
│                     │                                                    │
│                     ▼                                                    │
│  3. Discard buffered audio: audio_chunk_buffer.clear()                   │
│                     │                                                    │
│                     ▼                                                    │
│  4. Truncate audio item: connection.conversation.item.truncate()         │
│                     │                                                    │
│                     ▼                                                    │
│  5. Clear Twilio playback: websocket.send_json({"event": "clear"})       │
│                     │                                                    │
│                     ▼                                                    │
│  6. Clear mark queue: mark_queue.clear()                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### `_handle_speech_started` Method

```python
async def _handle_speech_started(self, connection, websocket, stream_sid,
                                  latest_media_timestamp, response_start_timestamp_twilio,
                                  last_assistant_item, mark_queue):
    
    # Truncate assistant's audio to match what was actually played
    if response_start_timestamp_twilio is not None and last_assistant_item:
        elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
        
        if 0 < elapsed_time < 10000:  # Sanity check
            await connection.conversation.item.truncate(
                item_id=last_assistant_item,
                content_index=0,
                audio_end_ms=elapsed_time,
            )
    
    # Send clear event to Twilio to stop playback immediately
    if stream_sid:
        await websocket.send_json({"event": "clear", "streamSid": stream_sid})
    
    # Clear pending marks (they're for audio that won't be played)
    mark_queue.clear()
```

---

## Audio Buffering Strategy

### Buffer Configuration

```python
audio_chunk_buffer: list[str] = []           # Buffer for batching
audio_chunk_buffer_size = 0                   # Current buffer size
max_chunk_buffer_size = 4800                  # ~200ms at 8kHz mulaw
```

### Why Buffer?
- **Reduce network overhead**: Fewer WebSocket messages
- **Optimize latency**: Balance between responsiveness and efficiency
- **Handle interruptions**: Discard buffered audio on barge-in

### Flush Logic

```python
# Flush when buffer full OR not currently handling interruption
if audio_chunk_buffer_size >= max_chunk_buffer_size or not is_interrupting:
    await _flush_audio_buffer(websocket, stream_sid, audio_chunk_buffer)
```

---

## Mark Synchronization

Marks track which audio has been played by Twilio.

### Flow

```
Server ──► Twilio: media + mark (after each response part)
Twilio ──► Server: mark acknowledgment (when audio played)
```

### Rate Limiting

```python
mark_send_interval = 0.3  # Minimum 300ms between marks

async def _send_mark_rate_limited(self, ...):
    current_time = time.time()
    if current_time - last_mark_send_time >= min_interval:
        await _send_mark(websocket, stream_sid, mark_queue)
        return current_time
    return last_mark_send_time
```

---

## State Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `stream_sid` | `str` | Unique identifier for Twilio stream |
| `latest_media_timestamp` | `int` | Last audio timestamp from Twilio |
| `last_assistant_item` | `str` | ID of last assistant audio item |
| `mark_queue` | `list` | Pending mark names |
| `mark_acknowledged` | `set` | Confirmed mark names |
| `response_start_timestamp_twilio` | `int` | When response audio started |
| `is_response_active` | `bool` | Whether AI is generating response |
| `current_response_id` | `str` | Active response ID |
| `response_status` | `str` | `in_progress`, `completed`, `cancelled`, etc. |
| `is_interrupting` | `bool` | Whether handling barge-in |
| `connection_healthy` | `bool` | OpenAI connection status |
| `openai_audio_chunks` | `list[str]` | Accumulated OpenAI audio |
| `twilio_audio_chunks` | `list[str]` | Accumulated Twilio audio |
| `response_start_time` | `float` | For latency measurement |
| `first_audio_time` | `float` | Time to first audio byte |

---

## Error Handling

### Twilio Side
- Invalid JSON: Log and continue (Twilio doesn't expect error responses)
- Parse errors: Log with safe string encoding

### OpenAI Side
- Critical errors (`invalid_request_error`, `authentication_error`): Mark unhealthy
- Recoverable errors: Log and continue
- Connection errors: Clear state, attempt recovery

### Cleanup on Error

```python
except Exception as e:
    connection_healthy = False
    is_response_active = False
    current_response_id = None
    audio_chunk_buffer.clear()
    mark_queue.clear()
```

---

## Latency Metrics

The handler tracks two key metrics:

1. **Time to First Audio**: `first_audio_time - response_start_time`
2. **Total Response Latency**: `time.time() - response_start_time`

These are logged for each completed response:
```
Response completed: resp_XXX, status: completed, total_latency: 1.234s
Time to first audio: 0.456s
```

---

## Related Documentation

- [Twilio Media Streams WebSocket Messages](./twilio-media-streams-websocket-messages.md)
- [OpenAI Realtime Client Events](./realtime-client-events.md)
- [OpenAI Realtime Server Events](./realtime-server-events.md)
- [OpenAI Realtime Client Secrets](./realtime-client-secrets.md)
