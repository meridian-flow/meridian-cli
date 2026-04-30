# Chat backend basic lifecycle smoke test

1. Start local backend with current source:
   `uv run meridian chat --host 127.0.0.1 --port 8765`.
2. Create chat: `curl -s -X POST http://127.0.0.1:8765/chat -H 'content-type: application/json' -d '{}'`.
   Verify the response includes a `chat_id` and initial `state` of `idle`.
3. Connect event stream: `websocat ws://127.0.0.1:8765/ws/chat/<chat_id>`.
4. `GET /chat/<chat_id>/state`, then send the first prompt through REST and verify the state changes to `active` and WebSocket emits ordered `ChatEvent` frames including `turn.started`.
5. While that turn is still `active`, send a WebSocket `prompt` command frame with `command_type` and verify an `ack` frame with matching `command_id` is rejected as `concurrent_prompt`.
6. After the first turn completes and state returns to `idle`, send a later prompt through the WebSocket command path and verify an `ack` frame with matching `command_id` is accepted and the turn lifecycle matches the REST path.
7. Reconnect with and without `last_seq`; verify replay starts after `last_seq` when supplied.
8. Open two WebSocket clients; verify both receive the same ordered events. Cancel, close, then verify post-close commands reject with `chat_closed`, `GET /chat/<chat_id>/state` reports `closed`, and closed-chat replay still works.
