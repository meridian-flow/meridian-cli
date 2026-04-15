# Interrupt Pipeline (v2)

Realizes `spec/interrupt.md` (INT-001..INT-007).

## Module touch-list

```
src/meridian/lib/launch/streaming_runner.py
  _terminal_event_outcome      # narrow what counts as "spawn-terminal"
  _consume_subscriber_events   # unchanged but inherits new classification

src/meridian/lib/streaming/
  spawn_manager.py             # interrupt gains per-spawn lock + noop
  control_socket.py            # routes interrupt; ack inside lock scope
  inject_lock.py               # NEW — per-spawn asyncio lock registry

src/meridian/lib/app/server.py # InjectRequest schema covers interrupt:true

src/meridian/cli/spawn_inject.py # --interrupt routes to control socket
```

## Classifier change

Today `_terminal_event_outcome` returns a non-None outcome whenever a
`turn/completed` carries a non-`completed` status. The new rule:

- A `turn/completed` event is **never** spawn-terminal on its own. The
  spawn ends only on:
  - `session.error` / `session.terminated` — harness is done
  - The harness exiting its event stream (drain ends naturally)
  - SIGTERM / SIGINT (CAN-001)
  - Report-watchdog escalation
- `turn` payloads are recorded in `output.jsonl` and surfaced to
  observers, but do not trigger `manager.stop_spawn(...)`.

For codex:

```python
if event.harness_id == HarnessId.CODEX.value and event.event_type == "turn/completed":
    # Per-turn outcome; spawn lifetime continues until SIGTERM, drain
    # end, or session.error. Fixes #28.
    return None
```

For claude `result` and opencode `session.idle`/`session.error`, existing
classification stays. Those payloads describe the **session**, not a turn.

P10 confirmed: codex is the only harness emitting per-turn terminal
payloads on the session stream. Claude and opencode terminal events
correspond to spawn-end. All three harnesses keep connections alive after
interrupt.

## Per-spawn FIFO

`inject_lock.py` — per-spawn asyncio lock registry:

```python
_locks: dict[SpawnId, asyncio.Lock] = {}

def get_lock(spawn_id: SpawnId) -> asyncio.Lock:
    return _locks.setdefault(spawn_id, asyncio.Lock())

def drop_lock(spawn_id: SpawnId) -> None:
    _locks.pop(spawn_id, None)
```

Both `SpawnManager.inject` and `SpawnManager.interrupt` acquire the lock.

**v2 change (D-05 extension).** Lock scope now covers ack emission:
the control socket calls a new `SpawnManager.inject_with_reply` /
`interrupt_with_reply` method that holds the lock across
`record_inbound + send_* + return result`. The control socket handler
writes the JSON reply from the returned result while still inside the
caller's logical scope, ensuring control-socket ack order matches
`inbound.jsonl` order. HTTP callers do not share that transport
guarantee and rely on `inbound_seq`. See `inject_serialization.md` for
full details.

## INT-004: noop when no turn

`SpawnManager.interrupt` returns `InjectResult(success=True, noop=True)`
when `connection.current_turn_id is None`. Control socket reflects as
`{"ok": true, "noop": true}`.

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

Handler dispatches to `SpawnManager.inject` or `.interrupt` based on
which field was set. Schema rejection at parse time covers INT-006/INJ-005.

## Test plan

### Unit tests
- `_terminal_event_outcome` for codex `turn/completed interrupted` →
  `None`.
- `_terminal_event_outcome` for codex `turn/completed completed` →
  `None` (turn events are never spawn-terminal).
- `_terminal_event_outcome` for `session.error` → `failed`.
- Per-spawn lock serializes two coroutines; control-socket ack order
  matches inbound order.

### Smoke tests
- Scenario 2: `spawn inject --interrupt` → spawn stays running,
  follow-up text inject, fresh turn.
- Scenario 8: double inject → distinct `inbound_seq`; control-socket ack
  order matches inbound order.
- Scenario 9b: HTTP interrupt parity.
- Scenario 11: inject + interrupt simultaneously → `inbound.jsonl` order
  matches harness delivery order.

### Fault-injection tests
- **Interrupt during no-turn**: noop ack, no state change.
- **Rapid interrupt+inject**: ordering preserved, spawn alive.
