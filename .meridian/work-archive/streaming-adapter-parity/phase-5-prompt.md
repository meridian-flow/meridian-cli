# Phase 5: OpenCode Streaming Spec Port

## Task

Port OpenCode streaming to `OpenCodeLaunchSpec` and make unsupported HTTP-session fields explicit rather than invisible.

## What to Change

### 1. `src/meridian/lib/harness/connections/opencode_http.py`

The `start()` method already accepts `ResolvedLaunchSpec` (from Phase 3). Now make OpenCode fully use it:

**Session creation** (`_create_session()`):
- Accept spec instead of config+params
- Read `spec.model` instead of `config.model` — the model is already normalized (opencode- prefix stripped)
- Read agent and skills from spec if it's `OpenCodeLaunchSpec`:
  ```python
  if isinstance(spec, OpenCodeLaunchSpec):
      if spec.agent_name:
          payload["agent"] = spec.agent_name
      if spec.skills:
          payload["skills"] = list(spec.skills)
  ```
- Read `spec.continue_session_id` instead of `params.continue_harness_session_id`
- If `spec.effort` is set, log a debug warning about unsupported effort in OpenCode streaming (D16)
- If `spec.continue_fork` is True, log a debug warning about unsupported fork in OpenCode streaming (D16)

**Update `_create_session_with_retry()`** to pass spec instead of config+params.

**Launch process** (`_launch_process()`):
- The `opencode serve --port` command stays the same
- Forward `spec.extra_args` instead of `params.extra_args`

### 2. Tests

**`tests/harness/test_opencode_http.py`** (new file):
- Test session creation payload uses spec model (not config.model)
- Test model normalization (opencode- prefix already stripped in spec)
- Test agent and skills forwarded from OpenCodeLaunchSpec
- Test unsupported fields logged (effort, fork)

### 3. `tests/exec/test_streaming_runner.py`

Add OpenCode regression if not already covered.

## Verification

```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/harness/test_opencode_http.py tests/exec/test_streaming_runner.py -x -q
uv run pytest-llm tests/ -x -q
```

## Key Points
- Do NOT remove `ConnectionConfig.model` yet
- Model normalization (opencode- prefix strip) already happened in the spec — use `spec.model` verbatim
- Log unsupported features rather than silently dropping them (D16)
- The HTTP path probing behavior should stay unchanged
