# Phase 3: Claude Streaming Spec Port

## Task

Switch the streaming pipeline from raw `SpawnParams` to resolved specs, and port Claude streaming onto `ClaudeLaunchSpec`. This changes the connection interface once — the other adapters will adapt in later phases.

## What to Change

### 1. `src/meridian/lib/harness/connections/base.py`

Change `HarnessLifecycle.start()` signature:

```python
# BEFORE:
async def start(self, config: ConnectionConfig, params: SpawnParams) -> None: ...

# AFTER:
async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None: ...
```

Add the import for `ResolvedLaunchSpec` (TYPE_CHECKING import). Keep `ConnectionConfig.model` for now — Codex and OpenCode still need it until their phases.

### 2. `src/meridian/lib/streaming/spawn_manager.py`

Change `start_spawn()` to accept `ResolvedLaunchSpec` instead of `SpawnParams`:

```python
async def start_spawn(
    self,
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec | None = None,
) -> HarnessConnection:
```

Pass the spec to `connection.start(config, spec or ResolvedLaunchSpec(prompt=config.prompt))`.

Also update any other references to `SpawnParams` in this file.

### 3. `src/meridian/lib/launch/streaming_runner.py`

Two places call `manager.start_spawn()` — both need updating:

1. In `run_streaming_spawn()` (around line 547): change to pass spec instead of params
2. In `_run_streaming_attempt()` (around line 652): change to pass spec instead of run_params

Also in `execute_with_streaming()` (around line 857):
- After constructing `run_params`, resolve the spec:
```python
spec = harness.resolve_launch_spec(run_params, plan.execution.permission_resolver)
```
- Pass `spec` instead of `run_params` to the downstream spawn calls.

For `run_streaming_spawn()` — this is a simpler entry point. It receives `SpawnParams` from callers. Here you need to either:
- Accept a spec directly (preferred if callers have access to the adapter), OR
- Create a base `ResolvedLaunchSpec` from the params (since this path doesn't have adapter access)

Look at the callers of `run_streaming_spawn()` to decide.

### 4. `src/meridian/lib/harness/connections/claude_ws.py`

Change `start()` to accept `ResolvedLaunchSpec` (it will receive `ClaudeLaunchSpec` at runtime):

```python
async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
```

Rewrite `_build_command()` to project from the spec:

```python
def _build_command(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> list[str]:
    command = [
        "claude", "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if spec.model:
        command.extend(["--model", spec.model])
    if spec.effort:
        command.extend(["--effort", spec.effort])
    # Claude-specific fields
    if isinstance(spec, ClaudeLaunchSpec):
        if spec.agent_name:
            command.extend(["--agent", spec.agent_name])
        if spec.appended_system_prompt:
            command.extend(["--append-system-prompt", spec.appended_system_prompt])
        if spec.agents_payload:
            command.extend(["--agents", spec.agents_payload])
    # Session continuation
    if spec.continue_session_id:
        command.extend(["--resume", spec.continue_session_id])
        if spec.continue_fork:
            command.append("--fork-session")
    # Permission flags
    if spec.permission_resolver:
        from meridian.lib.core.types import HarnessId
        command.extend(spec.permission_resolver.resolve_flags(HarnessId.CLAUDE))
    # Extra args
    if spec.extra_args:
        command.extend(spec.extra_args)
    return command
```

Also update `_start_subprocess()` to pass spec instead of params.

### 5. `src/meridian/lib/harness/connections/codex_ws.py` and `opencode_http.py`

These must ALSO update their `start()` signature to accept `ResolvedLaunchSpec` (since it's a protocol method), but they should still read from `config.model` and their own params for now. They'll be fully ported in Phases 4 and 5.

For now, make their `start()` accept the new signature but extract what they need from config and the base spec:

```python
async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
    # Still uses config.model and spec for basic fields
    # Will be fully ported in Phase 4/5
```

### 6. Update tests

- `tests/harness/test_claude_ws.py` — update command shape assertions
- `tests/exec/test_streaming_runner.py` — update for spec plumbing
- `tests/harness/test_codex_ws.py` — update signature
- `tests/test_spawn_manager.py` — update if it calls start_spawn

## Verification

```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/harness/test_claude_ws.py tests/exec/test_streaming_runner.py tests/harness/test_codex_ws.py tests/test_spawn_manager.py -x -q
uv run pytest-llm tests/ -x -q
```

## Key Edge Cases
- Codex and OpenCode streaming must still work after the protocol change
- `run_streaming_spawn()` callers may not have adapter access — handle gracefully
- `ClaudeLaunchSpec` fields only available via isinstance check in the connection
- Effort normalization already happened in the spec — emit verbatim
