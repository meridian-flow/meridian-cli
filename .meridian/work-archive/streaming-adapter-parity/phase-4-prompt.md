# Phase 4: Codex Streaming Spec Port

## Task

Port Codex streaming to `CodexLaunchSpec`, including bootstrap projection and approval-mode handling.

## What to Change

### 1. `src/meridian/lib/harness/connections/codex_ws.py`

The `start()` method already accepts `ResolvedLaunchSpec` (from Phase 3). Now make Codex fully use it:

**Bootstrap thread request** (`_thread_bootstrap_request()` and `_bootstrap_thread()`):
- Accept spec instead of config+params
- Read `spec.model` instead of `config.model`
- Read `spec.continue_session_id` instead of `params.continue_harness_session_id`
- Read `spec.continue_fork` instead of `params.continue_fork`
- If `spec.effort` is set and the spec is a CodexLaunchSpec, include effort in bootstrap payload (as `{"config": {"model_reasoning_effort": spec.effort}}` or similar if the app-server API supports it — if unclear, log a debug warning about unsupported effort and skip)

**Approval request handling** (`_handle_server_request()`):
- Store the spec on the instance so `_handle_server_request` can access it
- For `requestApproval` methods:
  - If spec is `CodexLaunchSpec` and `spec.approval_mode` is "confirm", reject the approval (send error response) and log a warning
  - Otherwise accept (current behavior for yolo/auto/default)

**Server launch command** — the `codex app-server --listen ws://...` launch stays the same; `extra_args` from the spec are forwarded (current behavior).

### 2. Tests

**`tests/harness/test_codex_ws.py`** — expand coverage:
- Bootstrap request includes model from spec
- Effort is forwarded in bootstrap if CodexLaunchSpec
- Confirm mode rejects approval requests (new test case)

## Verification

```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/harness/test_codex_ws.py tests/exec/test_streaming_runner.py -x -q
uv run pytest-llm tests/ -x -q
```

## Key Points
- Do NOT remove `ConnectionConfig.model` yet — that's Phase 6
- Access spec fields via isinstance check for CodexLaunchSpec-specific fields
- The critical new behavior is approval-mode rejection for "confirm" mode
