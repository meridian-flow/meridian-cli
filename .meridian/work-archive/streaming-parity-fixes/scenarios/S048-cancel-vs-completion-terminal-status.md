# S048: Cancel vs completion race — exactly one terminal status persisted

- **Source:** design/edge-cases.md E41 + decisions.md K8 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A spawn whose harness finishes naturally (emits a `completed` event) at roughly the same time the runner receives a cancellation intent. The ordering is non-deterministic — the test deliberately exercises both orderings.

## When
- Case A: `send_cancel()` resolves before the `completed` event reaches the spawn store.
- Case B: the `completed` event reaches the spawn store before `send_cancel()` resolves.

## Then
- Exactly one terminal status is persisted for the spawn id.
- The first terminal write wins. The second write is dropped by the spawn store's atomic tmp+rename behavior, or explicitly rejected by the spawn store's terminal-status idempotency check.
- No `AssertionError` or `ValueError` in the runner, regardless of ordering.
- The spawn event log contains both the cancel event and the completed event (both are audit-visible), but only one terminal status transition.

## Verification
- Unit test: drive a fake connection that emits `completed` on a controlled `asyncio.Event`; trigger `send_cancel` in parallel; assert terminal status consistency.
- Run the test with both orderings (cancel-first, completion-first) by parameterizing which event fires first.
- Assert `meridian spawn show` reports exactly one terminal status and the first-wins ordering.
- Assert the spawn store's terminal-status write path is idempotent: a second write with a different status is a no-op, not an exception.

## Result (filled by tester)
verified

Evidence:
- Cancel-vs-completion ordering exercised at the SpawnManager layer (event audit visibility + single terminal outcome):
  - `tests/test_spawn_manager.py::test_spawn_manager_cancel_vs_completion_race_emits_both_events_and_first_terminal_wins[cancel_first-cancelled]`
  - `tests/test_spawn_manager.py::test_spawn_manager_cancel_vs_completion_race_emits_both_events_and_first_terminal_wins[completion_first-succeeded]`
  - Asserts output log contains both `item.completed` and `cancelled`, with exactly one `cancelled` terminal event.
- Spawn store terminal projection is first-wins and finalize events are audit-visible in `spawns.jsonl`:
  - `tests/test_state/test_spawn_store.py::test_terminal_status_first_wins_cancelled_then_succeeded_audit_visible`
  - `tests/test_state/test_spawn_store.py::test_terminal_status_first_wins_succeeded_then_cancelled_audit_visible`
  - Each test reads `spawns.jsonl` and confirms both finalize events were appended while derived status remains the first terminal write.
- Gates:
  - `uv run ruff check .` ✅
  - `uv run pyright` ✅
  - `uv run pytest-llm tests/ --ignore=tests/smoke -q` ✅
