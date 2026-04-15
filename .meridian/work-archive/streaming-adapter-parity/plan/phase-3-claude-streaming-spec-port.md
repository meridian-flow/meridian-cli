# Phase 3: Claude Streaming Spec Port

## Scope

Switch the streaming pipeline from raw `SpawnParams` to resolved specs, then port Claude streaming onto `ClaudeLaunchSpec`.

This is the protocol-change phase. It changes the connection interface once, updates the streaming runner and spawn manager to pass specs, and fully ports Claude before any other streaming adapter moves.

## Files to Modify

- `src/meridian/lib/harness/connections/base.py`
  Change `HarnessLifecycle.start()` and `HarnessConnection` to accept `ResolvedLaunchSpec` instead of `SpawnParams`.
- `src/meridian/lib/streaming/spawn_manager.py`
  Accept the spec from callers and forward it unchanged to the connection instance.
- `src/meridian/lib/launch/streaming_runner.py`
  Resolve the spec with `plan.execution.permission_resolver`, pass it to `SpawnManager.start_spawn()`, and keep `ConnectionConfig.model` for the still-unported adapters.
- `src/meridian/lib/harness/connections/claude_ws.py`
  Project `ClaudeLaunchSpec` into the streaming CLI args, forward effort/agent/system-prompt/native-agent/permission flags, and capture `session_id` from Claude output when available.
- `tests/harness/test_claude_ws.py`
  Expand command-shape assertions to cover every Claude-specific spec field.
- `tests/exec/test_streaming_runner.py`
  Cover the new spec plumbing path and confirm `permission_resolver` reaches the Claude connection.
- `tests/harness/test_extraction.py`
  Add a Claude streaming session-id extraction regression if the fix lands in this phase.

## Dependencies

- Requires: Phase 2
- Produces: the shared streaming protocol contract and the first spec-backed transport
- Blocks: Phase 4, Phase 5, Phase 6

## Interface Contract

After this phase:

```python
async def start(
    self,
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> None: ...
```

And the streaming runner must do:

```python
spec = adapter.resolve_launch_spec(run_params, plan.execution.permission_resolver)
await manager.start_spawn(config, spec)
```

`ConnectionConfig.model` stays for now so Codex and OpenCode keep working until their own phases land.

## Patterns to Follow

- Keep Claude prompt delivery on stdin JSON; only CLI arg projection changes.
- Use explicit projection code in `claude_ws.py`, not ad hoc `SpawnParams` field-picking.
- If `report_output_path` remains unsupported in Claude streaming, document it in the projection guard.

## Verification Criteria

- [ ] `uv run pytest-llm tests/harness/test_claude_ws.py tests/exec/test_streaming_runner.py`
- [ ] `uv run pytest-llm tests/harness/test_extraction.py`
- [ ] `uv run pyright`
- [ ] Smoke: `uv run meridian streaming serve --harness claude --model claude-sonnet-4-6 --prompt "Reply READY and stop."`
- [ ] Smoke lane confirms the Claude streaming launch path now includes effort, native-agent, and append-system-prompt flags when configured

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@smoke-tester` on `gpt-5.4`

## Constraints

- Do not port Codex or OpenCode in this phase.
- Do not remove `ConnectionConfig.model` in this phase.
- If session-id extraction cannot be fixed cleanly, leave a documented follow-up in the final parity phase rather than mixing speculative parsing into unrelated code.
