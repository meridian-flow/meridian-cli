# Inject Serialization

Realizes `spec/inject.md` (INJ-002, INJ-003) and the linearizability half of
`spec/interrupt.md` (INT-006, INT-007).

## Problem recap

Two concurrent calls to `SpawnManager.inject` (or one inject + one interrupt)
can interleave between `record_inbound(...)` and `connection.send_user_message(...)`.
The net effect today:

- `inbound.jsonl` ordering does not match harness send ordering.
- In rare cases both callers observe `success=True` but one of their bytes
  never reaches the harness (second ack overwrites the queued sender
  future). Issue #31 captures this.

## Module

New file: `src/meridian/lib/streaming/inject_lock.py`.

```python
"""Per-spawn inject/interrupt ordering lock.

SpawnManager is a per-spawn object, but its inject / interrupt methods are
awaitable from arbitrary callers (control socket handler, HTTP endpoint,
test harness). Serializing the (record_inbound + send_*) pair on a single
asyncio.Lock keyed by spawn_id collapses every caller into one FIFO.
"""

from __future__ import annotations

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

## SpawnManager integration

```python
async def inject(self, text: str) -> InjectResult:
    async with inject_lock.get_lock(self._spawn_id):
        seq = spawn_store.record_inbound(
            self._state_root, self._spawn_id, kind="user_message", payload={"text": text},
        )
        await self._connection.send_user_message(text)
        return InjectResult(success=True, inbound_seq=seq)

async def interrupt(self) -> InjectResult:
    async with inject_lock.get_lock(self._spawn_id):
        if self._connection.current_turn_id is None:
            return InjectResult(success=True, noop=True)
        seq = spawn_store.record_inbound(
            self._state_root, self._spawn_id, kind="interrupt", payload={},
        )
        await self._connection.send_interrupt()
        return InjectResult(success=True, inbound_seq=seq, noop=False)
```

Both functions await holding the lock; the `send_*` coroutine runs to
completion before the next caller's `record_inbound` runs. This makes
`inbound.jsonl` order + harness wire order identical, which is the invariant
the test suite will verify.

## Cleanup

`drop_lock(spawn_id)` is called from:

- `SpawnManager.stop_spawn` right before the spawn's session closes.
- `_cleanup_completed_session` in the FastAPI background finalizer.

A race where a late inject grabs a lock for an already-stopped spawn is
benign: the lock exists, the `inject` call acquires it, and
`connection.send_user_message` raises because the connection closed. The
existing error-path returns `InjectResult(success=False, ...)` and the lock
becomes garbage after the next `drop_lock` (or lives for process lifetime —
the registry size is bounded by active-spawn count, which is small).

## Why asyncio.Lock, not a queue

We considered a per-spawn `asyncio.Queue[Command]` with a dedicated worker
task. Rejected: the queue adds a pump task per active spawn, doubling task
accounting during shutdown, and it splits error-handling across the caller
and the worker (the caller needs a future to await for the ack). The lock
is fewer lines, the same ordering guarantee, and the current single-method
signature stays intact.

We also considered per-caller serialization (a lock on `HarnessConnection`).
Rejected: a future connection pool could share a connection across spawns,
and we'd rather the invariant be "one spawn, one FIFO" than "one connection,
one FIFO".

## Test plan

- **Unit**: spin up two coroutines calling `inject("A")` and `inject("B")`
  against a fake `HarnessConnection` whose `send_user_message` awaits an
  event; verify `inbound.jsonl` sequences are monotonic and the order
  observed at the fake matches.
- **Unit**: same scenario with `inject("A")` and `interrupt()`; verify
  linearization.
- **Smoke**: scenario 8 — two simultaneous inject calls return distinct
  `inbound_seq` values and both messages appear in harness output.
- **Smoke**: scenario 11 — inject + interrupt simultaneously; interrupt
  either lands before or after inject, but the `inbound.jsonl` order and
  harness ordering agree.
