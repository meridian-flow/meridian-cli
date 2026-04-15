# Phase 3: ConnectionConfig and SpawnParams Split

## Goal

Separate transport concerns from command-building concerns in the bidirectional connection API. `ConnectionConfig` should shrink to transport-only fields. `HarnessConnection.start()` takes both `ConnectionConfig` and `SpawnParams`. All current callers are updated.

This is a no-behavior-change refactor — connections do the same thing, but get their command-building inputs from `SpawnParams` instead of `ConnectionConfig`.

## Changes Required

### 1. `src/meridian/lib/harness/connections/base.py`

Remove command-building fields from `ConnectionConfig`:
- Remove `agent` (command-building, already in SpawnParams)
- Remove `extra_args` (command-building, already in SpawnParams)
- Remove `skills` (command-building, already in SpawnParams)
- Remove `continue_session_id` (command-building, already in SpawnParams as `continue_harness_session_id`)

Result — `ConnectionConfig` stays transport-focused:
```python
@dataclass(frozen=True)
class ConnectionConfig:
    spawn_id: SpawnId
    harness_id: HarnessId
    model: str | None
    prompt: str
    repo_root: Path
    env_overrides: dict[str, str]
    timeout_seconds: float | None = None
    ws_bind_host: str = "127.0.0.1"
    ws_port: int = 0
```

Change `HarnessLifecycle.start()` signature:
```python
class HarnessLifecycle(Protocol):
    async def start(self, config: ConnectionConfig, params: SpawnParams) -> None: ...
```

Import `SpawnParams` from `meridian.lib.harness.adapter`.

### 2. `src/meridian/lib/harness/connections/codex_ws.py`

Update `start(self, config: ConnectionConfig, params: SpawnParams)`:
- Use `params.extra_args` instead of `config.extra_args` for codex app-server launch
- The initial turn still uses `config.prompt` (transport concern — what to send initially)

### 3. `src/meridian/lib/harness/connections/claude_ws.py`

Update `start(self, config: ConnectionConfig, params: SpawnParams)`:
- Use `params.extra_args` instead of `config.extra_args` for claude subprocess args
- Use `config.model` for the --model flag (it's both transport and identity)

### 4. `src/meridian/lib/harness/connections/opencode_http.py`

Update `start(self, config: ConnectionConfig, params: SpawnParams)`:
- Use `params.extra_args` instead of `config.extra_args` for opencode serve command
- Use `params.agent` instead of `config.agent` in session creation
- Use `params.skills` instead of `config.skills` in session creation
- Use `params.continue_harness_session_id` instead of `config.continue_session_id`

### 5. `src/meridian/lib/streaming/spawn_manager.py`

Update `start_spawn()` signature to accept both:
```python
async def start_spawn(self, config: ConnectionConfig, params: SpawnParams | None = None) -> HarnessConnection:
```

Pass both through to `connection.start(config, params or SpawnParams(prompt=config.prompt))`.

Make `params` optional with a default constructed from `config.prompt` so existing callers that only have config (like tests) don't break — they just pass `params=None` and get a minimal SpawnParams.

### 6. `src/meridian/lib/app/server.py`

Build a minimal `SpawnParams` for app-created spawns. The app currently creates `ConnectionConfig` with `agent`, `skills`, etc. Move those to `SpawnParams`:

```python
params = SpawnParams(
    prompt=prompt,
    model=ModelId(body.model.strip()) if body.model and body.model.strip() else None,
    agent=body.agent.strip() if body.agent else None,
)
config = ConnectionConfig(
    spawn_id=spawn_id,
    harness_id=harness_id,
    model=(body.model.strip() or None) if body.model is not None else None,
    prompt=prompt,
    repo_root=repo_root,
    env_overrides={},
)
connection = await spawn_manager.start_spawn(config, params)
```

### 7. `src/meridian/cli/streaming_serve.py`

Build a minimal `SpawnParams` for streaming serve. Move `agent`, `skills`, `extra_args`, `continue_session_id` from config to params:

```python
params = SpawnParams(
    prompt=prompt,
    model=ModelId(model.strip()) if model and model.strip() else None,
    agent=agent.strip() if agent else None,
)
config = ConnectionConfig(
    spawn_id=spawn_id,
    harness_id=harness_id,
    model=(model.strip() or None) if model is not None else None,
    prompt=prompt,
    repo_root=repo_root,
    env_overrides={},
)
await manager.start_spawn(config, params)
```

### 8. `tests/test_spawn_manager.py`

Update test fixtures:
- `_build_config()` should return a trimmed `ConnectionConfig` without the removed fields
- `FakeConnection.start()` should accept `(config, params)` signature
- Pass `params` to `manager.start_spawn(config, params)` or let it default

### 9. `tests/test_streaming_serve.py`

Update FakeManager's `start_spawn` to accept the new signature if needed.

## Edge Cases

- **Backward compatibility**: Make `SpawnParams` param optional in `start_spawn()` so tests and simple callers can pass just config. Default to `SpawnParams(prompt=config.prompt)`.
- **Model on both**: `model` appears on both `ConnectionConfig` and `SpawnParams`. This is intentional — `config.model` identifies the transport/connection, `params.model` is for command building. They're the same value in practice.
- **prompt on both**: Same rationale — `config.prompt` is what to send initially, `params.prompt` is the full prompt for command building.

## Files to Read First

- `src/meridian/lib/harness/connections/base.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/harness/adapter.py` (SpawnParams definition)
- `tests/test_spawn_manager.py`
- `tests/test_streaming_serve.py`

## Verification

- `uv run pytest tests/test_spawn_manager.py tests/test_streaming_serve.py -x` passes
- `uv run pytest tests/ -x` (full suite)
- `uv run pyright` passes (0 errors)
- `uv run ruff check .` passes
