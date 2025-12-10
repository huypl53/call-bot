# Client secrets | OpenAI API Reference
## 
Client secrets
REST API endpoint to generate ephemeral client secrets for use in client-side applications. Client secrets are short-lived tokens that can be passed to a client app, such as a web frontend or mobile client, which grants access to the Realtime API without leaking your main API key. You can configure a custom TTL for each client secret.
You can also attach session configuration options to the client secret, which will be applied to any sessions created using that client secret, but these can also be overridden by the client connection.
[Learn more about authentication with client secrets over WebRTC](/docs/guides/realtime-webrtc).
## 
Create client secret
post https://api.openai.com/v1/realtime/client\_secrets
Create a Realtime client secret with an associated session configuration.
#### Request body
[](#realtime_sessions_create_realtime_client_secret-expires_after)
expires\_after
object
Optional
Configuration for the client secret expiration. Expiration refers to the time after which a client secret will no longer be valid for creating sessions. The session itself may continue after that time once started. A secret can be used to create multiple sessions until it expires.
Show properties
[](#realtime_sessions_create_realtime_client_secret-session)
session
object
Optional
Session configuration to use for the client secret. Choose either a realtime session or a transcription session.
Show possible types
#### Returns
The created client secret and the effective session object. The client secret is a string that looks like `ek_1234`.
Example request
curl
```bash
curl -X POST https://api.openai.com/v1/realtime/client_secrets \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_after": {
      "anchor": "created_at",
      "seconds": 600
    },
    "session": {
      "type": "realtime",
      "model": "gpt-realtime",
      "instructions": "You are a friendly assistant."
    }
  }'
```
Response
```json
{
  "value": "ek_68af296e8e408191a1120ab6383263c2",
  "expires_at": 1756310470,
  "session": {
    "type": "realtime",
    "object": "realtime.session",
    "id": "sess_C9CiUVUzUzYIssh3ELY1d",
    "model": "gpt-realtime",
    "output_modalities": [
      "audio"
    ],
    "instructions": "You are a friendly assistant.",
    "tools": [],
    "tool_choice": "auto",
    "max_output_tokens": "inf",
    "tracing": null,
    "truncation": "auto",
    "prompt": null,
    "expires_at": 0,
    "audio": {
      "input": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        },
        "transcription": null,
        "noise_reduction": null,
        "turn_detection": {
          "type": "server_vad",
        }
      },
      "output": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        },
        "voice": "alloy",
        "speed": 1.0
      }
    },
    "include": null
  }
}
```
## 
Session response object
Response from creating a session and client secret for the Realtime API.
[](#realtime_sessions-create_secret_response-expires_at)
expires\_at
integer
Expiration timestamp for the client secret, in seconds since epoch.
[](#realtime_sessions-create_secret_response-session)
session
object
The session configuration for either a realtime or transcription session.
Show possible types
[](#realtime_sessions-create_secret_response-value)
value
string
The generated client secret value.
OBJECT Session response object
```json
{
  "value": "ek_68af296e8e408191a1120ab6383263c2",
  "expires_at": 1756310470,
  "session": {
    "type": "realtime",
    "object": "realtime.session",
    "id": "sess_C9CiUVUzUzYIssh3ELY1d",
    "model": "gpt-realtime-2025-08-25",
    "output_modalities": [
      "audio"
    ],
    "instructions": "You are a friendly assistant.",
    "tools": [],
    "tool_choice": "auto",
    "max_output_tokens": "inf",
    "tracing": null,
    "truncation": "auto",
    "prompt": null,
    "expires_at": 0,
    "audio": {
      "input": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        },
        "transcription": null,
        "noise_reduction": null,
        "turn_detection": {
          "type": "server_vad",
          "threshold": 0.5,
          "prefix_padding_ms": 300,
          "silence_duration_ms": 200,
          "idle_timeout_ms": null,
          "create_response": true,
          "interrupt_response": true
        }
      },
      "output": {
        "format": {
          "type": "audio/pcm",
          "rate": 24000
        },
        "voice": "alloy",
        "speed": 1.0
      }
    },
    "include": null
  }
}
```