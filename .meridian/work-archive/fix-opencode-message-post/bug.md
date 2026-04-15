# Bug: OpenCode adapter crashes on message POST response

## Symptom

`meridian spawn` with OpenCode harness crashes during `start()` when posting the initial message:

```
aiohttp.client_exceptions.ClientPayloadError: Response payload is not completed:
<TransferEncodingError: 400, message='Not enough data to satisfy transfer length header.'>
```

## Root Cause

`opencode_http.py` `_post_json()` (line 427) calls `response.text()` expecting a complete HTTP response body. The OpenCode server's response to the message POST uses a transfer encoding that `aiohttp` can't read completely — likely a chunked/streaming response that our code treats as a regular response.

## Stack Trace

```
streaming_runner.py:453 run_streaming_spawn
  → spawn_manager.py:97 start_spawn
    → opencode_http.py:149 start
      → opencode_http.py:368 _post_session_message
        → opencode_http.py:393 _post_session_action
          → opencode_http.py:427 _post_json
            → response.text()  ← CRASH
```

## Reproduction

```bash
uv run meridian streaming serve --harness opencode \
  --model "qwen/qwen3-coder-480b-a35b-instruct:free" \
  -p "Say hello"
```

Requires OpenCode configured with an OpenRouter provider.

## Impact

- OpenCode spawns fail on initial message POST — the connection starts (session created, events streaming) but the spawn crashes before becoming usable
- Control socket never appears, inject never works
- Codex and Claude harnesses are unaffected

## Fix Direction

`_post_json` and `_post_session_action` need to handle the response format that OpenCode actually returns for message POSTs. Options:
1. The response may be streaming/chunked — read it differently than `response.text()`
2. The POST may not need the response body at all — fire-and-forget, read events from SSE instead
3. Add resilience for truncated responses — catch `ClientPayloadError`, check if the message was delivered via the event stream

Probe the real OpenCode server first to understand what the response actually looks like.
