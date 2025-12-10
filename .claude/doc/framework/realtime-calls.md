# Calls | OpenAI API Reference
## 
Calls
REST endpoints for controlling WebRTC or SIP calls with the Realtime API. Accept or reject an incoming call, transfer it to another destination, or hang up the call once you are finished.
## 
Accept call
post https://api.openai.com/v1/realtime/calls/{call\_id}/accept
Accept an incoming SIP call and configure the realtime session that will handle it.
#### Path parameters
[](#realtime_calls_accept_call-call_id)
call\_id
string
Required
The identifier for the call provided in the [`realtime.call.incoming`](/docs/api-reference/webhook-events/realtime/call/incoming) webhook.
#### Request body
[](#realtime_calls_accept_call-type)
type
string
Required
The type of session to create. Always `realtime` for the Realtime API.
[](#realtime_calls_accept_call-audio)
audio
object
Optional
Configuration for input and output audio.
Show properties
[](#realtime_calls_accept_call-include)
include
array
Optional
Additional fields to include in server outputs.
`item.input_audio_transcription.logprobs`: Include logprobs for input audio transcription.
[](#realtime_calls_accept_call-instructions)
instructions
string
Optional
The default system instructions (i.e. system message) prepended to model calls. This field allows the client to guide the model on desired responses. The model can be instructed on response content and format, (e.g. "be extremely succinct", "act friendly", "here are examples of good responses") and on audio behavior (e.g. "talk quickly", "inject emotion into your voice", "laugh frequently"). The instructions are not guaranteed to be followed by the model, but they provide guidance to the model on the desired behavior.
Note that the server sets default instructions which will be used if this field is not set and are visible in the `session.created` event at the start of the session.
[](#realtime_calls_accept_call-max_output_tokens)
max\_output\_tokens
integer or "inf"
Optional
Maximum number of output tokens for a single assistant response, inclusive of tool calls. Provide an integer between 1 and 4096 to limit output tokens, or `inf` for the maximum available tokens for a given model. Defaults to `inf`.
[](#realtime_calls_accept_call-model)
model
string
Optional
The Realtime model used for this session.
[](#realtime_calls_accept_call-output_modalities)
output\_modalities
array
Optional
Defaults to audio
The set of modalities the model can respond with. It defaults to `["audio"]`, indicating that the model will respond with audio plus a transcript. `["text"]` can be used to make the model respond with text only. It is not possible to request both `text` and `audio` at the same time.
[](#realtime_calls_accept_call-prompt)
prompt
object
Optional
Reference to a prompt template and its variables. [Learn more](/docs/guides/text?api-mode=responses#reusable-prompts).
Show properties
[](#realtime_calls_accept_call-tool_choice)
tool\_choice
string or object
Optional
Defaults to auto
How the model chooses tools. Provide one of the string modes or force a specific function/MCP tool.
Show possible types
[](#realtime_calls_accept_call-tools)
tools
array
Optional
Tools available to the model.
Show possible types
[](#realtime_calls_accept_call-tracing)
tracing
"auto" or object
Optional
Defaults to null
Realtime API can write session traces to the [Traces Dashboard](/logs?api=traces). Set to null to disable tracing. Once tracing is enabled for a session, the configuration cannot be modified.
`auto` will create a trace for the session with default values for the workflow name, group id, and metadata.
Show possible types
[](#realtime_calls_accept_call-truncation)
truncation
string or object
Optional
When the number of tokens in a conversation exceeds the model's input token limit, the conversation be truncated, meaning messages (starting from the oldest) will not be included in the model's context. A 32k context model with 4,096 max output tokens can only include 28,224 tokens in the context before truncation occurs.
Clients can configure truncation behavior to truncate with a lower max token limit, which is an effective way to control token usage and cost.
Truncation will reduce the number of cached tokens on the next turn (busting the cache), since messages are dropped from the beginning of the context. However, clients can also configure truncation to retain messages up to a fraction of the maximum context size, which will reduce the need for future truncations and thus improve the cache rate.
Truncation can be disabled entirely, which means the server will never truncate but would instead return an error if the conversation exceeds the model's input token limit.
Show possible types
#### Returns
Returns `200 OK` once OpenAI starts ringing the SIP leg with the supplied session configuration.
Example request
curl
```bash
curl -X POST https://api.openai.com/v1/realtime/calls/$CALL_ID/accept \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "type": "realtime",
        "model": "gpt-realtime",
        "instructions": "You are Alex, a friendly concierge for Example Corp.",
      }'
```
## 
Reject call
post https://api.openai.com/v1/realtime/calls/{call\_id}/reject
Decline an incoming SIP call by returning a SIP status code to the caller.
#### Path parameters
[](#realtime_calls_reject_call-call_id)
call\_id
string
Required
The identifier for the call provided in the [`realtime.call.incoming`](/docs/api-reference/webhook-events/realtime/call/incoming) webhook.
#### Request body
[](#realtime_calls_reject_call-status_code)
status\_code
integer
Optional
SIP response code to send back to the caller. Defaults to `603` (Decline) when omitted.
#### Returns
Returns `200 OK` after OpenAI sends the SIP status code to the caller.
Example request
curl
```bash
curl -X POST https://api.openai.com/v1/realtime/calls/$CALL_ID/reject \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status_code": 486}'
```
## 
Refer call
post https://api.openai.com/v1/realtime/calls/{call\_id}/refer
Transfer an active SIP call to a new destination using the SIP REFER verb.
#### Path parameters
[](#realtime_calls_refer_call-call_id)
call\_id
string
Required
The identifier for the call provided in the [`realtime.call.incoming`](/docs/api-reference/webhook-events/realtime/call/incoming) webhook.
#### Request body
[](#realtime_calls_refer_call-target_uri)
target\_uri
string
Required
URI that should appear in the SIP Refer-To header. Supports values like `tel:+14155550123` or `sip:agent@example.com`.
#### Returns
Returns `200 OK` once the REFER is handed off to your SIP provider.
Example request
curl
```bash
curl -X POST https://api.openai.com/v1/realtime/calls/$CALL_ID/refer \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target_uri": "tel:+14155550123"}'
```
## 
Hang up call
post https://api.openai.com/v1/realtime/calls/{call\_id}/hangup
End an active Realtime API call, whether it was initiated over SIP or WebRTC.
#### Path parameters
[](#realtime_calls_hangup_call-call_id)
call\_id
string
Required
The identifier for the call. For SIP calls, use the value provided in the [`realtime.call.incoming`](/docs/api-reference/webhook-events/realtime/call/incoming) webhook. For WebRTC sessions, reuse the call ID returned in the `Location` header when creating the call with [`POST /v1/realtime/calls`](/docs/api-reference/realtime/create-call).
#### Returns
Returns `200 OK` when OpenAI begins terminating the realtime call.
Example request
curl
```bash
curl -X POST https://api.openai.com/v1/realtime/calls/$CALL_ID/hangup \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```
## Embedded Content