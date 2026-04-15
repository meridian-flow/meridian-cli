# Phase 3: ConnectionConfig and SpawnParams Split

**Risk:** Low  
**Design docs:** [overview.md](../design/overview.md), [streaming-runner.md](../design/streaming-runner.md)

## Scope

Separate transport concerns from command-building concerns in the bidirectional connection API. `ConnectionConfig` should stay transport-focused; `SpawnParams` remains the command/build payload already used by subprocess harnesses.

## Files to Modify

- `src/meridian/lib/harness/connections/base.py`
  Remove command-building fields from `ConnectionConfig` and change the connection `start()` protocol to accept both `ConnectionConfig` and `SpawnParams`.
- `src/meridian/lib/streaming/spawn_manager.py`
  Change `start_spawn()` to accept both config objects and pass both through to the connection implementation.
- `src/meridian/lib/harness/connections/codex_ws.py`
  Build process launch and initial turn state from `SpawnParams` instead of overloading `ConnectionConfig`.
- `src/meridian/lib/harness/connections/claude_ws.py`
  Same split for command construction and prompt/session inputs.
- `src/meridian/lib/harness/connections/opencode_http.py`
  Same split for serve command construction and session creation payloads.
- `src/meridian/lib/app/server.py`
  Build minimal `SpawnParams` for app-created spawns after the new signature lands.
- `src/meridian/cli/streaming_serve.py`
  Build minimal `SpawnParams` for direct streaming serves after the new signature lands.
- `tests/test_spawn_manager.py`
  Update fake connections and configs to the new `start(config, params)` contract.

## Dependencies

- Requires: none
- Produces: the stable start signature the streaming runner uses later
- Independent of: extraction protocol refactor, manager finalization handoff

## Interface Contract

`ConnectionConfig` should be reduced to transport essentials:

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

And the connection lifecycle should become:

```python
async def start(self, config: ConnectionConfig, params: SpawnParams) -> None: ...
```

## Patterns to Follow

- Keep using `SpawnParams` as the single command-building data model; do not copy its fields into a second config type.
- Follow the same field ownership already present in subprocess adapters: transport in the connection layer, launch policy in the runner/plan layer.

## Constraints and Boundaries

- No routing changes in this phase.
- No new finalization logic in this phase.
- Avoid widening the config surface again through optional escape hatches.

## Verification Criteria

- `uv run pytest tests/test_spawn_manager.py` passes.
- Connection implementation tests or smoke stubs still start with the new signature.
- `uv run pyright` passes.

## Staffing

- Builder: `@coder`
- Testers: `@verifier`

## Completion Signal

This phase is done when the connection layer accepts both transport config and launch params without duplicating the same fields across two objects.
