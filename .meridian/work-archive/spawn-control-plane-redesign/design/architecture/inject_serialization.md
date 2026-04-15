# Inject Serialization (v2r2)

Realizes `spec/inject.md` (INJ-002, INJ-003) and the linearizability
half of `spec/interrupt.md` (INT-006, INT-007).

## Problem recap

Two concurrent calls to `SpawnManager.inject` (or one inject + one
interrupt) can interleave between `record_inbound(...)` and
`connection.send_user_message(...)`. Additionally, the control socket
writes the JSON ack AFTER `SpawnManager` returns, allowing ack order to
diverge from inbound order (v1 review finding P13).

## Module

New file: `src/meridian/lib/streaming/inject_lock.py`.

```python
"""Per-spawn inject/interrupt ordering lock.

SpawnManager is a multi-spawn registry. Its inject/interrupt methods are
awaitable from arbitrary callers (control socket, HTTP, test harness).
Serializing (record_inbound + send_* + return result) on a single
asyncio.Lock keyed by spawn_id collapses every caller into one FIFO.
"""

import asyncio
from meridian.lib.state.types import SpawnId

_locks: dict[SpawnId, asyncio.Lock] = {}

def get_lock(spawn_id: SpawnId) -> asyncio.Lock:
    lock = _locks.get(spawn_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[spawn_id] = lock
    return lock

def drop_lock(spawn_id: SpawnId) -> None:
    _locks.pop(spawn_id, None)
```

v2 correction: the docstring describes `SpawnManager` as a multi-spawn
registry (matching the actual type at `spawn_manager.py:98`), not a
per-spawn object as v1 incorrectly stated (minor finding from p1792).

## `_record_inbound` return contract (v2r2 — new)

The existing `_record_inbound` returns `None`. R-02 must change it to
return the zero-based `inbound_seq` (line index in `inbound.jsonl`).
This is the monotonic sequence number that INJ-003 promises clients.

```python
async def _record_inbound(self, spawn_id, kind, payload, source) -> int:
    """Append to inbound.jsonl and return the zero-based line index."""
    # ... existing write logic ...
    return line_index
```

Additionally, add `InjectResult` as a new dataclass:

```python
@dataclass
class InjectResult:
    success: bool
    inbound_seq: int | None = None
    noop: bool = False
    error: str | None = None
```

## SpawnManager integration (v2 — extended lock scope)

```python
async def inject(self, spawn_id: SpawnId, text: str, source: str) -> InjectResult:
    async with inject_lock.get_lock(spawn_id):
        seq = await self._record_inbound(
            spawn_id, kind="user_message",
            payload={"text": text}, source=source,
        )
        session = self._sessions.get(spawn_id)
        if session is None:
            return InjectResult(success=False, error="no active session")
        await session.connection.send_user_message(text)
        return InjectResult(success=True, inbound_seq=seq)

async def interrupt(self, spawn_id: SpawnId, source: str) -> InjectResult:
    async with inject_lock.get_lock(spawn_id):
        session = self._sessions.get(spawn_id)
        if session is None:
            return InjectResult(success=False, error="no active session")
        if session.connection.current_turn_id is None:
            return InjectResult(success=True, noop=True)
        seq = await self._record_inbound(
            spawn_id, kind="interrupt", payload={}, source=source,
        )
        await session.connection.send_interrupt()
        return InjectResult(success=True, inbound_seq=seq, noop=False)
```

**v2 key change.** The lock must cover ack emission, not just
`record_inbound + send_*`. The chosen `on_result` callback lets callers
emit replies inside the lock scope without exposing lock internals:

```python
async def inject(self, spawn_id, text, source, on_result=None) -> InjectResult:
    async with inject_lock.get_lock(spawn_id):
        seq = await self._record_inbound(...)
        await session.connection.send_user_message(text)
        result = InjectResult(success=True, inbound_seq=seq)
        if on_result:
            await on_result(result)
        return result
```

The control socket passes `on_result=lambda r: self._write(writer, ...)`.
The HTTP handler doesn't need the callback — HTTP responses travel on
independent connections, so ack arrival order is NOT guaranteed to match
`inbound.jsonl` order. Clients use `inbound_seq` in the response to
reconstruct ordering (D-18).

**v2r2 ack ordering contract (D-18):**
- **Control socket clients:** ack arrival order matches `inbound.jsonl`
  order (lock scope covers ack emission via `on_result` callback).
- **HTTP clients:** ack arrival order is NOT guaranteed to match
  `inbound.jsonl` order (independent connections). `inbound_seq` is
  sufficient for clients to reconstruct ordering.

## Cleanup

`drop_lock(spawn_id)` called from:
- `SpawnManager.stop_spawn`
- `_cleanup_completed_session`

Late inject on a stopped spawn: lock exists, `inject()` acquires it,
`connection.send_user_message` raises, returns `InjectResult(success=False)`.
Lock becomes garbage after `drop_lock`.

## Why asyncio.Lock, not a queue

Queue adds a pump task per spawn, doubles task accounting at shutdown,
splits error handling across caller and worker. Lock is fewer lines, same
guarantee.

## Test plan

### Unit tests
- Two coroutines calling `inject("A")` and `inject("B")` against a fake
  connection: verify `inbound.jsonl` seqs are monotonic and harness wire
  order matches.
- Same with `inject("A")` and `interrupt()`: verify linearization.
- Callback `on_result` fires inside lock scope (verified by attempting
  a second inject from within the callback — it should deadlock/timeout).

### Smoke tests
- Scenario 8: two simultaneous injects → distinct `inbound_seq`;
  control-socket ack order matches `inbound.jsonl`.
- Scenario 11: inject + interrupt simultaneously → `inbound.jsonl` order
  matches harness delivery order.

### Fault-injection tests
- **Three concurrent injects**: verify all three acked in inbound order,
  no drops on the control socket; HTTP callers receive distinct
  `inbound_seq` values they can reorder client-side.
