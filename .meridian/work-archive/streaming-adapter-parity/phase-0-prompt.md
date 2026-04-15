# Phase 0: Fix Effort Plumbing

## Task

Fix the upstream child-spawn bug where `effort` is resolved during prepare time but then disappears before either runner rebuilds `SpawnParams`.

## What to Change

### 1. `src/meridian/lib/ops/spawn/plan.py`
Add `effort: str | None = None` to `PreparedSpawnPlan`, between `harness_id` and `prompt`.

### 2. `src/meridian/lib/ops/spawn/prepare.py`
In `build_create_payload()`, the `PreparedSpawnPlan(...)` construction call (around line 357) needs to include `effort=resolved.effort`. The `resolved` object already has `effort` available — it's just not being passed through to the plan.

### 3. `src/meridian/lib/launch/runner.py`
Find where `SpawnParams` is constructed from the plan. Include `effort=plan.effort` in the SpawnParams construction. Search for `SpawnParams(` in the file.

### 4. `src/meridian/lib/launch/streaming_runner.py`
Same as runner.py — find the `SpawnParams(` construction (around line 857) and add `effort=plan.effort`.

## Constraints
- No behavior change beyond plumbing the effort field.
- Do NOT introduce `ResolvedLaunchSpec` yet — that's Phase 1.
- Do NOT touch `launch/plan.py` for primary launches.
- Keep the change minimal and focused.

## Verification
After making changes, run:
```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/ops/test_spawn_prepare_fork.py tests/exec/test_lifecycle.py tests/exec/test_streaming_runner.py -x -q
```

All must pass. If any existing test breaks, fix the test fixture to match the new field (the `PreparedSpawnPlan` constructor will now require effort awareness in test fixtures that construct one).

## Edge Cases
- `effort=None` means "don't set effort" — must pass through as `None`, not as empty string.
- The preview command built in `prepare.py` already includes effort (because it builds SpawnParams with `effort=resolved.effort` for the preview). After this fix, the actual execution path agrees with the preview.
