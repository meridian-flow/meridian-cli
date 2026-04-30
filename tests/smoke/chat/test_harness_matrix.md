# Chat harness matrix smoke

1. Start chat backend with Claude, Codex, and OpenCode in separate chats.
2. Send one prompt that produces assistant text in each chat.
3. Verify each stream emits `turn.started`, `content.delta`, and `turn.completed`.
4. Trigger or inspect a file write in each harness.
5. Verify each stream emits canonical `files.persisted` with changed file paths.
6. For Codex only, trigger approval/user-input and verify `request.opened` or `user_input.requested` is surfaced.
7. For OpenCode, verify runtime HITL is reported unsupported cleanly; do not expect fake approve/reject flow.
8. Reconnect/replay each chat and verify the same normalized event families are persisted.
