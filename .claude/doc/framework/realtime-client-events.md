# Client events | OpenAI API Reference
## 
Client events
These are events that the OpenAI Realtime WebSocket server will accept from the client.
## 
session.update
Send this event to update the session’s configuration. The client may send this event at any time to update any field except for `voice` and `model`. `voice` can be updated only if there have been no other audio outputs yet.
When the server receives a `session.update`, it will respond with a `session.updated` event showing the full, effective configuration. Only the fields that are present in the `session.update` are updated. To clear a field like `instructions`, pass an empty string. To clear a field like `tools`, pass an empty array. To clear a field like `turn_detection`, pass `null`.
[](#realtime_client_events-session-update-event_id)
event\_id
string
Optional client-generated ID used to identify this event. This is an arbitrary string that a client may assign. It will be passed back if there is an error with the event, but the corresponding `session.updated` event will not include it.
[](#realtime_client_events-session-update-session)
session
object
Update the Realtime session. Choose either a realtime session or a transcription session.
Show possible types
[](#realtime_client_events-session-update-type)
type
string
The event type, must be `session.update`.
OBJECT session.update
```json
{
  "type": "session.update",
  "session": {
    "type": "realtime",
    "instructions": "You are a creative assistant that helps with design tasks.",
    "tools": [
      {
        "type": "function",
        "name": "display_color_palette",
        "description": "Call this function when a user asks for a color palette.",
        "parameters": {
          "type": "object",
          "properties": {
            "theme": {
              "type": "string",
              "description": "Description of the theme for the color scheme."
            },
            "colors": {
              "type": "array",
              "description": "Array of five hex color codes based on the theme.",
              "items": {
                "type": "string",
                "description": "Hex color code"
              }
            }
          },
          "required": [
            "theme",
            "colors"
          ]
        }
      }
    ],
    "tool_choice": "auto"
  }
}
```
## 
input\_audio\_buffer.append
Send this event to append audio bytes to the input audio buffer. The audio buffer is temporary storage you can write to and later commit. A "commit" will create a new user message item in the conversation history from the buffer content and clear the buffer. Input audio transcription (if enabled) will be generated when the buffer is committed.
If VAD is enabled the audio buffer is used to detect speech and the server will decide when to commit. When Server VAD is disabled, you must commit the audio buffer manually. Input audio noise reduction operates on writes to the audio buffer.
The client may choose how much audio to place in each event up to a maximum of 15 MiB, for example streaming smaller chunks from the client may allow the VAD to be more responsive. Unlike most other client events, the server will not send a confirmation response to this event.
[](#realtime_client_events-input_audio_buffer-append-audio)
audio
string
Base64-encoded audio bytes. This must be in the format specified by the `input_audio_format` field in the session configuration.
[](#realtime_client_events-input_audio_buffer-append-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-input_audio_buffer-append-type)
type
string
The event type, must be `input_audio_buffer.append`.
OBJECT input\_audio\_buffer.append
```json
{
    "event_id": "event_456",
    "type": "input_audio_buffer.append",
    "audio": "Base64EncodedAudioData"
}
```
## 
input\_audio\_buffer.commit
Send this event to commit the user input audio buffer, which will create a new user message item in the conversation. This event will produce an error if the input audio buffer is empty. When in Server VAD mode, the client does not need to send this event, the server will commit the audio buffer automatically.
Committing the input audio buffer will trigger input audio transcription (if enabled in session configuration), but it will not create a response from the model. The server will respond with an `input_audio_buffer.committed` event.
[](#realtime_client_events-input_audio_buffer-commit-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-input_audio_buffer-commit-type)
type
string
The event type, must be `input_audio_buffer.commit`.
OBJECT input\_audio\_buffer.commit
```json
{
    "event_id": "event_789",
    "type": "input_audio_buffer.commit"
}
```
## 
input\_audio\_buffer.clear
Send this event to clear the audio bytes in the buffer. The server will respond with an `input_audio_buffer.cleared` event.
[](#realtime_client_events-input_audio_buffer-clear-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-input_audio_buffer-clear-type)
type
string
The event type, must be `input_audio_buffer.clear`.
OBJECT input\_audio\_buffer.clear
```json
{
    "event_id": "event_012",
    "type": "input_audio_buffer.clear"
}
```
## 
conversation.item.create
Add a new Item to the Conversation's context, including messages, function calls, and function call responses. This event can be used both to populate a "history" of the conversation and to add new items mid-stream, but has the current limitation that it cannot populate assistant audio messages.
If successful, the server will respond with a `conversation.item.created` event, otherwise an `error` event will be sent.
[](#realtime_client_events-conversation-item-create-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-conversation-item-create-item)
item
object
A single item within a Realtime conversation.
Show possible types
[](#realtime_client_events-conversation-item-create-previous_item_id)
previous\_item\_id
string
The ID of the preceding item after which the new item will be inserted. If not set, the new item will be appended to the end of the conversation. If set to `root`, the new item will be added to the beginning of the conversation. If set to an existing ID, it allows an item to be inserted mid-conversation. If the ID cannot be found, an error will be returned and the item will not be added.
[](#realtime_client_events-conversation-item-create-type)
type
string
The event type, must be `conversation.item.create`.
OBJECT conversation.item.create
```json
{
  "type": "conversation.item.create",
  "item": {
    "type": "message",
    "role": "user",
    "content": [
      {
        "type": "input_text",
        "text": "hi"
      }
    ]
  },
  "event_id": "b904fba0-0ec4-40af-8bbb-f908a9b26793",
}
```
## 
conversation.item.retrieve
Send this event when you want to retrieve the server's representation of a specific item in the conversation history. This is useful, for example, to inspect user audio after noise cancellation and VAD. The server will respond with a `conversation.item.retrieved` event, unless the item does not exist in the conversation history, in which case the server will respond with an error.
[](#realtime_client_events-conversation-item-retrieve-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-conversation-item-retrieve-item_id)
item\_id
string
The ID of the item to retrieve.
[](#realtime_client_events-conversation-item-retrieve-type)
type
string
The event type, must be `conversation.item.retrieve`.
OBJECT conversation.item.retrieve
```json
{
    "event_id": "event_901",
    "type": "conversation.item.retrieve",
    "item_id": "item_003"
}
```
## 
conversation.item.truncate
Send this event to truncate a previous assistant message’s audio. The server will produce audio faster than realtime, so this event is useful when the user interrupts to truncate audio that has already been sent to the client but not yet played. This will synchronize the server's understanding of the audio with the client's playback.
Truncating audio will delete the server-side text transcript to ensure there is not text in the context that hasn't been heard by the user.
If successful, the server will respond with a `conversation.item.truncated` event.
[](#realtime_client_events-conversation-item-truncate-audio_end_ms)
audio\_end\_ms
integer
Inclusive duration up to which audio is truncated, in milliseconds. If the audio\_end\_ms is greater than the actual audio duration, the server will respond with an error.
[](#realtime_client_events-conversation-item-truncate-content_index)
content\_index
integer
The index of the content part to truncate. Set this to `0`.
[](#realtime_client_events-conversation-item-truncate-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-conversation-item-truncate-item_id)
item\_id
string
The ID of the assistant message item to truncate. Only assistant message items can be truncated.
[](#realtime_client_events-conversation-item-truncate-type)
type
string
The event type, must be `conversation.item.truncate`.
OBJECT conversation.item.truncate
```json
{
    "event_id": "event_678",
    "type": "conversation.item.truncate",
    "item_id": "item_002",
    "content_index": 0,
    "audio_end_ms": 1500
}
```
## 
conversation.item.delete
Send this event when you want to remove any item from the conversation history. The server will respond with a `conversation.item.deleted` event, unless the item does not exist in the conversation history, in which case the server will respond with an error.
[](#realtime_client_events-conversation-item-delete-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-conversation-item-delete-item_id)
item\_id
string
The ID of the item to delete.
[](#realtime_client_events-conversation-item-delete-type)
type
string
The event type, must be `conversation.item.delete`.
OBJECT conversation.item.delete
```json
{
    "event_id": "event_901",
    "type": "conversation.item.delete",
    "item_id": "item_003"
}
```
## 
response.create
This event instructs the server to create a Response, which means triggering model inference. When in Server VAD mode, the server will create Responses automatically.
A Response will include at least one Item, and may have two, in which case the second will be a function call. These Items will be appended to the conversation history by default.
The server will respond with a `response.created` event, events for Items and content created, and finally a `response.done` event to indicate the Response is complete.
The `response.create` event includes inference configuration like `instructions` and `tools`. If these are set, they will override the Session's configuration for this Response only.
Responses can be created out-of-band of the default Conversation, meaning that they can have arbitrary input, and it's possible to disable writing the output to the Conversation. Only one Response can write to the default Conversation at a time, but otherwise multiple Responses can be created in parallel. The `metadata` field is a good way to disambiguate multiple simultaneous Responses.
Clients can set `conversation` to `none` to create a Response that does not write to the default Conversation. Arbitrary input can be provided with the `input` field, which is an array accepting raw Items and references to existing Items.
[](#realtime_client_events-response-create-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-response-create-response)
response
object
Create a new Realtime response with these parameters
Show properties
[](#realtime_client_events-response-create-type)
type
string
The event type, must be `response.create`.
OBJECT response.create
```json
// Trigger a response with the default Conversation and no special parameters
{
  "type": "response.create",
}
// Trigger an out-of-band response that does not write to the default Conversation
{
  "type": "response.create",
  "response": {
    "instructions": "Provide a concise answer.",
    "tools": [], // clear any session tools
    "conversation": "none",
    "output_modalities": ["text"],
    "metadata": {
      "response_purpose": "summarization"
    },
    "input": [
      {
        "type": "item_reference",
        "id": "item_12345",
      },
      {
        "type": "message",
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": "Summarize the above message in one sentence."
          }
        ]
      }
    ],
  }
}
```
## 
response.cancel
Send this event to cancel an in-progress response. The server will respond with a `response.done` event with a status of `response.status=cancelled`. If there is no response to cancel, the server will respond with an error. It's safe to call `response.cancel` even if no response is in progress, an error will be returned the session will remain unaffected.
[](#realtime_client_events-response-cancel-event_id)
event\_id
string
Optional client-generated ID used to identify this event.
[](#realtime_client_events-response-cancel-response_id)
response\_id
string
A specific response ID to cancel - if not provided, will cancel an in-progress response in the default conversation.
[](#realtime_client_events-response-cancel-type)
type
string
The event type, must be `response.cancel`.
OBJECT response.cancel
```json
{
    "type": "response.cancel"
    "response_id": "resp_12345",
}
```
## 
output\_audio\_buffer.clear
**WebRTC/SIP Only:** Emit to cut off the current audio response. This will trigger the server to stop generating audio and emit a `output_audio_buffer.cleared` event. This event should be preceded by a `response.cancel` client event to stop the generation of the current response. [Learn more](/docs/guides/realtime-conversations#client-and-server-events-for-audio-in-webrtc).
[](#realtime_client_events-output_audio_buffer-clear-event_id)
event\_id
string
The unique ID of the client event used for error handling.
[](#realtime_client_events-output_audio_buffer-clear-type)
type
string
The event type, must be `output_audio_buffer.clear`.
OBJECT output\_audio\_buffer.clear
```json
{
    "event_id": "optional_client_event_id",
    "type": "output_audio_buffer.clear"
}
```