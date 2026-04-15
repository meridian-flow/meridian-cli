# Phase 1 Fix: INJ-004 Terminal Rejection

The verifier found that `SpawnManager.inject()` and `.interrupt()` don't reject when the spawn is already terminal but session cleanup hasn't run yet. Fix this.

## The Problem

In `SpawnManager.inject()` and `.interrupt()`, the code checks if the session exists in `self._sessions`. But when a spawn reaches terminal status (e.g., via `turn/completed` → finalize), the session entry may still be present until `_cleanup_completed_session` runs. A caller can inject into a terminal spawn during this window.

## The Fix

Add an explicit terminal status check at the top of `inject()` and `interrupt()`:

```python
async def inject(self, spawn_id: SpawnId, text: str, source: str, ...) -> InjectResult:
    # Check spawn is not terminal before proceeding
    record = spawn_store.get_spawn(self._state_root, spawn_id)
    if record is not None and record.status in TERMINAL_SPAWN_STATUSES:
        return InjectResult(success=False, error=f"spawn not running: {record.status}")
    
    async with inject_lock.get_lock(spawn_id):
        # ... existing logic ...
```

Do the same for `interrupt()`.

Import `TERMINAL_SPAWN_STATUSES` from `meridian.lib.core.spawn_lifecycle` (already used elsewhere in the codebase).

## Verification

After the fix:
```bash
uv run ruff check .
uv run pyright
uv run pytest-llm
```
All must pass.
