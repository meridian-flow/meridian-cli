# S041: `send_cancel` is idempotent across transports

- **Source:** design/edge-cases.md E41 + decisions.md K8 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
An active `HarnessConnection[SpecT]` instance — tested once for subprocess, once for streaming Claude, once for streaming Codex, once for streaming OpenCode (four fixtures total).

## When
`send_cancel()` is awaited twice in succession on the same connection.

## Then
- The first `send_cancel()` call transitions the connection to a cancelled state and emits exactly one `cancelled` terminal spawn event into the event stream.
- The second `send_cancel()` call is a no-op — no additional event, no second terminal status, no exception.
- The spawn store persists exactly one terminal status (`cancelled`) for the spawn id.
- The behavior is identical across all four connection types.

## Verification
- Unit tests per connection type with mocked transport layer: drive `connection.start(...)`, then `await connection.send_cancel()` twice, inspect emitted events and terminal status.
- Assert `events` emitted by the connection include exactly one `cancelled` frame.
- Assert the connection's `stop()` call count, if any, is not increased by the second `send_cancel`.
- Cross-transport test: parameterize on all four connection classes registered in `HarnessBundle.connections` for each harness.

## Result (filled by tester)
verified

Evidence:
- Connection-level idempotency (transport call occurs once, second call no-op, no raise):
  - `tests/exec/test_lifecycle.py::test_claude_connection_cancel_interrupt_are_idempotent`
  - `tests/exec/test_lifecycle.py::test_codex_connection_cancel_interrupt_are_idempotent`
  - `tests/exec/test_lifecycle.py::test_opencode_connection_cancel_interrupt_are_idempotent`
- Manager-level cancelled terminal event is emitted once even if stop invoked twice:
  - `tests/test_spawn_manager.py::test_spawn_manager_stop_spawn_cancel_emits_single_terminal_cancelled_event`
- Regression run: `uv run pytest-llm tests/test_spawn_manager.py tests/exec/test_lifecycle.py -v` passed.

Exploratory note (beyond scenario): calling `send_cancel()` before `start()` currently raises `ConnectionNotReady` for Claude/Codex/OpenCode (state=`created` requires `connected`).
