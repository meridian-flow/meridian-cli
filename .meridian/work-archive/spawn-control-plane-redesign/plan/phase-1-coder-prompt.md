# Phase 1: Foundation Primitives

You are implementing Phase 1 of the spawn control plane redesign for meridian-cli. This phase lands shared mechanical substrate that later phases build on.

## What to Build

### R-01: Extract heartbeat helper
Create `src/meridian/lib/streaming/heartbeat.py`:
```python
async def heartbeat_loop(state_root: Path, spawn_id: SpawnId, interval: float = 30.0):
    sentinel = paths.heartbeat_path(state_root, spawn_id)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    while True:
        sentinel.touch()
        await asyncio.sleep(interval)
```
- Move inline heartbeat loops from `runner.py` and `streaming_runner.py` to use this helper.
- Do NOT move heartbeat ownership to SpawnManager yet — that's Phase 4.

### R-02: Centralize inject/interrupt serialization
Create `src/meridian/lib/streaming/inject_lock.py`:
```python
_locks: dict[SpawnId, asyncio.Lock] = {}

def get_lock(spawn_id: SpawnId) -> asyncio.Lock:
    return _locks.setdefault(spawn_id, asyncio.Lock())

def drop_lock(spawn_id: SpawnId) -> None:
    _locks.pop(spawn_id, None)
```

Modify `SpawnManager`:
1. Change `_record_inbound(...)` to return the zero-based line index (inbound_seq).
2. Add `InjectResult` dataclass: `success: bool, inbound_seq: int | None = None, noop: bool = False, error: str | None = None`.
3. Wrap `inject()` and `interrupt()` with the per-spawn lock. Lock scope MUST cover `record_inbound + send_* + return result`.
4. Add `on_result` callback parameter so control-socket can emit ack inside lock scope (for ack ordering guarantee per D-18).
5. Call `drop_lock(spawn_id)` from `stop_spawn` and `_cleanup_completed_session`.

Modify `control_socket.py`:
- Update inject/interrupt handlers to use `on_result` callback for ack emission inside lock scope.

### R-11: Extend launch_mode schema
In `src/meridian/lib/state/spawn_store.py`:
- Change `LaunchMode = Literal["background", "foreground"]` to `LaunchMode = Literal["background", "foreground", "app"]`.
- Tighten `SpawnStartEvent.launch_mode` from `str | None` to `LaunchMode | None`.
- Ensure `SpawnUpdateEvent.launch_mode` is also `LaunchMode | None`.

## EARS Statements This Phase Claims

- **INJ-001**: Inject text delivered to harness without finalization
- **INJ-002**: Concurrent injects linearizable per spawn (via lock + inbound_seq)
- **INJ-003**: Inject acks per-message inbound_seq
- **INJ-004**: Inject rejects when spawn is terminal
- **INT-007**: Per-spawn interrupt-and-inject ordering is linearizable

## Key Design Decisions

- D-05: Per-spawn asyncio.Lock with extended scope covering ack emission
- D-18: Control socket ack ordering guaranteed; HTTP uses inbound_seq
- D-24: inbound_seq comes from _record_inbound return value

## Files to Read First

- `src/meridian/lib/streaming/spawn_manager.py` — main target for R-02
- `src/meridian/lib/streaming/control_socket.py` — ack emission changes
- `src/meridian/lib/launch/runner.py` — heartbeat extraction source
- `src/meridian/lib/launch/streaming_runner.py` — heartbeat extraction source
- `src/meridian/lib/state/spawn_store.py` — LaunchMode type
- `src/meridian/lib/state/paths.py` — heartbeat_path helper

## What NOT to Change

- Do NOT add AuthorizationGuard (Phase 2)
- Do NOT change cancel behavior (Phase 5)
- Do NOT move heartbeat ownership to SpawnManager (Phase 4)
- Do NOT change _terminal_event_outcome (Phase 3)
- Do NOT change HTTP endpoints (Phase 6)
- Do NOT change app_cmd.py or AF_UNIX transport (Phase 2)

## Verification

After implementation, run:
```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
All must pass clean.
