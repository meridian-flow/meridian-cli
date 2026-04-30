# Chat backend restart recovery smoke test

1. Create a chat and start a turn.
2. Stop the server without closing the chat.
3. Restart the server against the same Meridian runtime root.
4. Verify `GET /chat/<chat_id>/state` returns `idle`.
5. Reconnect `WS /ws/chat/<chat_id>` and verify persisted history replays plus a `runtime.error` for lost backend recovery.
