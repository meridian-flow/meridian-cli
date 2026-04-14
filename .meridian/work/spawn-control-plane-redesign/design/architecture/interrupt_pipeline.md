# Interrupt Pipeline

Realizes `spec/interrupt.md` (INT-001 .. INT-007).

## Module touch-list

```
src/meridian/lib/launch/streaming_runner.py
  _terminal_event_outcome      # narrow what counts as "spawn-terminal"
  _consume_subscriber_events   # unchanged but inherits new classification

src/meridian/lib/streaming/
  spawn_manager.py             # SpawnManager.interrupt gains per-spawn lock + noop semantics
  control_socket.py            # routes interrupt unchanged; mutex moves to SpawnManager
  inject_lock.py               # NEW — per-spawn asyncio lock registry (shared with inject)

src/meridian/lib/app/server.py # InjectRequest schema covers interrupt:true

src/meridian/cli/spawn_inject.py # unchanged; --interrupt routes to control socket
```

## Classifier change

Today `_terminal_event_outcome` returns a non-None outcome whenever a
`turn/completed` carries a non-`completed` status. That conflates "this turn
ended badly" with "this spawn is terminal". The new rule:

- A `turn/completed` event is **never** spawn-terminal on its own. The
  spawn ends only on:
  - a `session.error` / `session.terminated` event whose payload encodes
    "the harness is done with this spawn"
  - the harness exiting its event stream (drain ends naturally)
  - SIGTERM / SIGINT (handled in CAN-001)
  - the report-watchdog escalation
- The `turn` payload is recorded in `output.jsonl` and surfaced to
  observers, but the runner does not call `manager.stop_spawn(...)` because
  of it.

For codex specifically the rewrite is:

```python
if event.harness_id == HarnessId.CODEX.value and event.event_type == "turn/completed":
    # Per-turn outcome is logged via output.jsonl; spawn lifetime continues
    # until SIGTERM, drain end, or session.error.
    return None
```

For claude `result` and opencode `session.idle`/`session.error`, the existing
classification stays. Those payloads describe the **session**, not a turn.
The architect spawn (open feasibility item P10) confirmed that codex is the
only harness emitting per-turn terminal payloads on the session stream;
claude and opencode terminal events already correspond to spawn-end.

## Per-spawn FIFO

A new `inject_lock.py` module owns a small registry:

```python
_locks: dict[SpawnId, asyncio.Lock] = {}

def get_lock(spawn_id: SpawnId) -> asyncio.Lock:
    return _locks.setdefault(spawn_id, asyncio.Lock())

def drop_lock(spawn_id: SpawnId) -> None:
    _locks.pop(spawn_id, None)
```

Both `SpawnManager.inject` and `SpawnManager.interrupt` acquire the same
per-spawn lock, wrapping the (`record_inbound` + `send_*`) pair. Drop happens
in `_cleanup_completed_session` and `stop_spawn`.

This is the smallest change that makes ordering linearizable. We considered
moving serialization to the control socket layer; rejected because HTTP
inject would still race the control-socket inject otherwise. Centralizing in
`SpawnManager` covers all surfaces.

## INT-004: noop when no turn

`SpawnManager.interrupt` returns `InjectResult(success=True, noop=True)` when
the harness reports `current_turn_id is None`. The control socket reflects
the noop in the response (`{"ok": true, "noop": true}`); CLI text mode
prints "Interrupt acknowledged (no turn in flight)".

The control-socket reply schema gains an optional `noop: bool` field. CLI
JSON mode exposes it; CLI text mode summarizes it.

## INT-005 / INT-006: HTTP schema

`InjectRequest` becomes:

```python
class InjectRequest(BaseModel):
    text: str | None = None
    interrupt: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> "InjectRequest":
        text_set = self.text is not None and self.text.strip() != ""
        if text_set and self.interrupt:
            raise ValueError("text and interrupt are mutually exclusive")
        if not text_set and not self.interrupt:
            raise ValueError("provide text or interrupt: true")
        return self
```

`inject_message` HTTP handler dispatches to either `SpawnManager.inject`
or `SpawnManager.interrupt` based on which was set. Schema rejection at
parse time covers INT-006/INJ-005 violations.

## Test plan (gist)

- **Unit**: `_terminal_event_outcome` for codex `turn/completed`-`interrupted`
  returns None; for `turn/completed`-`completed` still returns success;
  for `session.error` still returns failed.
- **Unit**: per-spawn lock serializes two simultaneous coroutines.
- **Smoke**: scenario 2 (`spawn inject --interrupt`) — spawn stays running,
  follow-up text inject is acked, fresh assistant turn.
- **Smoke**: scenario 8 (double inject) — both messages ack with distinct
  `inbound_seq`, both appear in `output.jsonl` in send order.
- **Smoke**: scenarios 9b (HTTP interrupt parity).
