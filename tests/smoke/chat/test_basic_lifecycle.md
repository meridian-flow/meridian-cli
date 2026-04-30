# Chat backend basic lifecycle smoke test

1. Start local backend with current source once `meridian chat` CLI is wired:
   `uv run meridian chat --host 127.0.0.1 --port 8765`.
2. Create chat: `curl -s -X POST http://127.0.0.1:8765/chat -H 'content-type: application/json' -d '{}'`.
3. Connect event stream: `websocat ws://127.0.0.1:8765/ws/chat/<chat_id>`.
4. Send prompt through REST and verify WebSocket emits ordered `ChatEvent` frames.
5. Send a WebSocket command frame with `command_type`, verify an `ack` frame with matching `command_id`.
6. Reconnect with and without `last_seq`; verify replay starts after `last_seq` when supplied.
7. Open two WebSocket clients; verify both receive the same ordered events.
8. Cancel, close, then verify post-close commands reject with `chat_closed` and closed-chat replay still works.
