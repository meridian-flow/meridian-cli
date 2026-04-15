# Phase 6: Runner Cleanup, Parity, and Smoke Matrix

## Task

Finish the migration by:
1. Extracting duplicated Claude runner preflight into `claude_preflight.py`
2. Removing `ConnectionConfig.model` (all adapters now read from spec)
3. Expanding parity test coverage
4. Adding a smoke test guide

## What to Change

### 1. New file: `src/meridian/lib/launch/claude_preflight.py`

Extract from both `runner.py` and `streaming_runner.py`:
- `_read_parent_claude_permissions()` — reads parent Claude settings for child permission forwarding
- `_merge_allowed_tools_flag()` — merges allowedTools flags
- `_dedupe_nonempty()` — deduplicates non-empty string values
- `_split_csv_entries()` — splits CSV entries

These functions are currently duplicated identically in both runners. Move them to the new module and have both runners import from it.

Also extract `ensure_claude_session_accessible()` import from `runner.py` — the streaming runner already imports it from there, so just ensure it's a clean re-export or direct import.

### 2. Remove `ConnectionConfig.model` from `src/meridian/lib/harness/connections/base.py`

All three connection adapters now read model from the spec. Remove the `model` field from `ConnectionConfig`:

```python
@dataclass(frozen=True)
class ConnectionConfig:
    spawn_id: SpawnId
    harness_id: HarnessId
    prompt: str
    repo_root: Path
    env_overrides: dict[str, str]
    timeout_seconds: float | None = None
    ws_bind_host: str = "127.0.0.1"
    ws_port: int = 0
    debug_tracer: DebugTracer | None = None
```

Then update ALL callers that construct `ConnectionConfig`:
- `src/meridian/lib/launch/streaming_runner.py` — remove `model=` from `ConnectionConfig()`
- `src/meridian/lib/app/server.py` — if it constructs ConnectionConfig, remove model
- `tests/` — update test fixtures that construct ConnectionConfig

Also clean up any remaining references to `config.model` in:
- `codex_ws.py` — should use `spec.model` exclusively now
- `opencode_http.py` — should use `spec.model` exclusively now
- `claude_ws.py` — should use `spec.model` exclusively now

### 3. Update `runner.py` and `streaming_runner.py`

Replace the duplicated Claude preflight helper functions with imports from `claude_preflight.py`. Delete the local copies.

### 4. Expand `tests/harness/test_launch_spec_parity.py`

Add cross-transport parity cases:
- For each harness, verify that subprocess `build_command()` and streaming `_build_command()` project the same semantic fields
- Document known asymmetries (OpenCode effort/fork unsupported in streaming)

### 5. New file: `tests/smoke/streaming-adapter-parity.md`

Add a repeatable smoke test guide with steps to manually verify:
- Claude subprocess vs streaming with effort, agent, skills
- Codex subprocess vs streaming with effort, approval modes
- OpenCode subprocess vs streaming with model normalization

## Verification

```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/ -x -q
```

## Key Points
- Delete duplicated helpers, don't leave wrappers behind
- `ConnectionConfig.model` must be fully gone — not just unused
- Parity tests should focus on semantic equivalence, not wire-format equality

## Critical Context from Codebase Scan

### `config.model` references that MUST be updated:

1. **`src/meridian/lib/launch/streaming_runner.py:547`** — `run_spec` construction uses `config.model` as fallback:
   ```python
   model=str(params.model).strip() if params.model else config.model,
   ```
   Change to use `params.model` only (no config fallback). If params.model is None, pass None.

2. **`src/meridian/lib/launch/streaming_runner.py:911`** — passes `model=` to `ConnectionConfig()`

3. **`src/meridian/cli/streaming_serve.py:74`** — passes `model=normalized_model or None` to `ConnectionConfig()`

4. **`src/meridian/lib/app/server.py:187`** — passes `model=` to `ConnectionConfig()`

5. **`tests/test_spawn_manager.py:44`** — test fixture passes `model=` to `ConnectionConfig()`

6. **`tests/exec/test_streaming_runner.py:364,511,589`** — three test fixtures pass `model=` to `ConnectionConfig()`

7. **`tests/harness/test_opencode_http.py:42`** — test fixture passes `model=` to `ConnectionConfig()`

8. **`tests/harness/test_claude_ws.py:21`** — test fixture passes `model=` to `ConnectionConfig()`

9. **`tests/harness/test_codex_ws.py:60`** — test fixture passes `model=` to `ConnectionConfig()`

### All `ConnectionConfig()` construction sites (complete list):
- `src/meridian/lib/launch/streaming_runner.py:908`
- `src/meridian/lib/app/server.py:184`
- `src/meridian/cli/streaming_serve.py:71`
- `tests/test_spawn_manager.py:44`
- `tests/exec/test_streaming_runner.py:364,511,589`
- `tests/harness/test_opencode_http.py:42`
- `tests/harness/test_claude_ws.py:21`
- `tests/harness/test_codex_ws.py:60`

### Claude preflight helpers — duplicate locations:
Both `runner.py` and `streaming_runner.py` define these identically. Grep confirmed.
