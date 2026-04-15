# Fix: MERIDIAN_WORK_DIR not exported into harness sessions

GitHub issue #12. `MERIDIAN_WORK_DIR` is documented as available to spawned agents but is always empty because no code path actually injects it.

## Root Cause

There are two spawn execution paths, both broken:

### 1. Background spawns (`execute.py`)

`_spawn_child_env()` at line ~133 receives `work_id` but explicitly discards it:

```python
def _spawn_child_env(
    spawn_id: str | None = None,
    *,
    work_id: str | None = None,
    state_root: Path | None = None,
    autocompact: int | None = None,
    ctx: RuntimeContext | None = None,
) -> dict[str, str]:
    _ = spawn_id, work_id, state_root, ctx  # <-- DISCARDED
    child_env: dict[str, str] = {}
    if autocompact is not None:
        child_env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact)
    return child_env
```

The comment says `RuntimeContext.child_context()` in `launch/context.py` is the sole producer of `MERIDIAN_*` overrides, but that context doesn't have the work_id either.

### 2. Foreground/streaming spawns (`launch/context.py`)

`RuntimeContext.from_environment()` reads `work_dir` from `os.getenv("MERIDIAN_WORK_DIR")`, which is empty in the parent process. So `child_context()` never emits it.

### 3. The `_normalize_meridian_work_dir` fallback in `env.py`

This fallback resolves from `MERIDIAN_STATE_ROOT` + `MERIDIAN_CHAT_ID` by looking up the parent session's active work item. This is unreliable:
- The `MERIDIAN_CHAT_ID` is the **parent's** chat id, not the child's
- If the child runs in a different repo (e.g., spawned from meridian-cli but working in mars-agents), it resolves the work dir under the wrong state root

## The Fix

The spawn pipeline already resolves `work_id` correctly at multiple points:
- `execute.py` line ~415: `work_id=session_context.work_id or spawn_record.work_id`
- `execute.py` line ~572: `work_id=context.work_id`

This resolved `work_id` needs to flow into the child environment as both:
- `MERIDIAN_WORK_ID` — the slug (e.g., `mars-alias-merge-order`)
- `MERIDIAN_WORK_DIR` — the resolved path (e.g., `/repo/.meridian/work/mars-alias-merge-order`)

**Approach:** The `launch/context.py` `RuntimeContext` is the designated sole producer of `MERIDIAN_*` overrides. The fix should flow through there:

1. `RuntimeContext.from_environment()` already reads `work_dir` from env — that's fine for inheritance.
2. But when spawning, the caller needs to **override** `work_dir` on the RuntimeContext with the resolved value from the spawn record, so `child_context()` emits it.
3. Check all call sites of `RuntimeContext.from_environment()` in the launch path and ensure the work_dir override is plumbed through.

Alternatively, the simpler fix: make `_spawn_child_env` stop ignoring `work_id` and have it emit `MERIDIAN_WORK_DIR` and `MERIDIAN_WORK_ID` directly. This technically violates the "RuntimeContext is sole producer" comment, but that comment describes an aspiration that was never fully implemented. Update the comment to reflect reality.

**Important constraints:**
- `MERIDIAN_WORK_DIR` must resolve relative to the **child's** state root, not the parent's
- The child's state root is determined by `MERIDIAN_STATE_ROOT` in the child env (which IS correctly set)
- Use `resolve_work_scratch_dir(state_root, work_id)` to get the path
- Both background spawn path AND foreground/streaming path must be fixed

## Files to touch

- `src/meridian/lib/ops/spawn/execute.py` — `_spawn_child_env()` is the primary fix site
- `src/meridian/lib/launch/context.py` — may need work_dir override plumbing for the foreground path
- `src/meridian/lib/launch/env.py` — the `_normalize_meridian_work_dir` fallback may need adjustment or can stay as belt-and-suspenders

## Verification

After the fix, this should work:
```bash
meridian work start test-export
meridian spawn -m haiku -p 'echo "MERIDIAN_WORK_DIR=$MERIDIAN_WORK_DIR" && echo "MERIDIAN_WORK_ID=$MERIDIAN_WORK_ID"'
# Should print non-empty values pointing to .meridian/work/test-export
```

Also verify: `uv run ruff check .` and `uv run pyright` must pass.
