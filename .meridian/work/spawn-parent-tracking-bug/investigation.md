# Spawn Parent Tracking Bug — Investigation Notes

## Symptom

All child spawns from orchestrator sessions are attributed to the **root session spawn** instead of their actual parent spawn. This makes `meridian spawn children <orchestrator-id>` return empty, and all children appear as direct children of the root.

### Evidence from session c1538 (root spawn p1621)

- p1673 (docs-orchestrator, Claude opus) spawned p1678 (reviewer, codex)
- p1678's spawn record shows `parent_id: p1621` — should be `parent_id: p1673`
- `meridian spawn children p1673` returns `(no spawns)`
- `meridian spawn children p1621` lists ALL spawns (~47), including ones created by nested orchestrators
- Same pattern for p1645 (impl orchestrator that spawned 14 children) — all children show parent p1621

### Raw evidence

```
$ grep "p1678" .meridian/spawns.jsonl | head -1 | jq '{id, parent_id, chat_id, harness}'
{
  "id": "p1678",
  "parent_id": "p1621",   # WRONG — should be p1673
  "chat_id": "c1538",
  "harness": "codex"
}
```

## Root Cause Analysis

### How parent_id is set

1. **`execute.py:229`** — When creating a spawn, parent_id comes from `resolved_context.spawn_id`:
   ```python
   parent_id=str(resolved_context.spawn_id) if resolved_context.spawn_id else None,
   ```

2. **`resolved_context`** comes from `runtime_context(ctx)` which calls `RuntimeContext.from_environment()`, reading `MERIDIAN_SPAWN_ID` from the process env.

3. So the question is: **what value does `MERIDIAN_SPAWN_ID` have when a Claude-hosted agent calls `meridian spawn`?**

### How MERIDIAN_SPAWN_ID is set for child processes

In `launch/command.py:35-44`:
```python
runtime_context = RuntimeContext(
    depth=current_context.depth,
    repo_root=repo_root.resolve(),
    state_root=resolve_state_paths(repo_root).root_dir.resolve(),
    chat_id=resolved_chat_id,
    work_id=resolved_work_id,
    # NOTE: spawn_id and parent_spawn_id are NOT set here
)
env_overrides = runtime_context.to_env_overrides()
if spawn_id is not None and spawn_id.strip():
    env_overrides["MERIDIAN_SPAWN_ID"] = spawn_id.strip()
```

So `MERIDIAN_SPAWN_ID=p1673` IS set in the env passed to the Claude harness process.

### The likely gap: Claude harness env propagation

In `launch/context.py:201-207`:
```python
runtime_ctx = RuntimeContext.from_environment(
    repo_root=execution_cwd,
    state_root=state_root,
).with_work_id(runtime_work_id)
merged_overrides = merge_env_overrides(
    plan_overrides=plan_overrides,
    runtime_overrides=runtime_ctx.child_context(),
    preflight_overrides=preflight.extra_env,
)
```

`RuntimeContext.from_environment()` reads `MERIDIAN_SPAWN_ID` from `os.environ`. But this runs in the **runner process**, not in the Claude agent's subprocess. The key question is:

**Does the Claude Code harness propagate `MERIDIAN_SPAWN_ID` from its launch env into the environment that Bash tool calls see?**

If Claude Code starts a fresh shell for each tool call and doesn't inherit the full parent env, `MERIDIAN_SPAWN_ID` would be lost. The agent would call `meridian spawn` in a shell where `MERIDIAN_SPAWN_ID` is either:
- Not set at all (parent defaults to None)
- Set to whatever was in the grandparent's env (p1621)

### Two possible failure modes

**Mode A: Claude doesn't propagate MERIDIAN_SPAWN_ID at all.**
Then `resolved_context.spawn_id` would be None in the child's `meridian spawn` call, and parent_id would be None. But we see `parent_id: p1621`, not None — so this isn't it.

**Mode B: Claude inherits from its own process env, which has MERIDIAN_SPAWN_ID=p1621.**
Wait — the Claude process for p1673 should have `MERIDIAN_SPAWN_ID=p1673` (set in command.py:44). But the Claude Code harness may set up its own session environment from the **project directory's** env, not from the process launch env. If `.claude/` or the session context preserves env vars from the initial session launch (which was p1621), tool calls would see `MERIDIAN_SPAWN_ID=p1621`.

**Mode B is the most likely explanation.** Claude Code sessions inherit env from the project context, and the project context was established by the root session (p1621). Nested spawns launch new Claude processes with the correct env, but the Claude session's tool execution environment may not honor the process-level env override.

## Key Files

| File | Relevance |
|---|---|
| `src/meridian/lib/ops/spawn/execute.py:229` | Where parent_id is read from context |
| `src/meridian/lib/core/context.py:25-50` | RuntimeContext.from_environment() — reads MERIDIAN_SPAWN_ID |
| `src/meridian/lib/launch/command.py:35-44` | Where MERIDIAN_SPAWN_ID is set for child processes |
| `src/meridian/lib/launch/context.py:148-226` | prepare_launch_context — builds env for runner |
| `src/meridian/lib/launch/runner.py:460-475` | Runner entry point — passes env_overrides to launch context |
| `src/meridian/lib/harness/connections/claude_ws.py:347` | Claude harness subprocess launch — check cwd and env |
| `src/meridian/lib/harness/connections/codex_ws.py:235` | Codex harness subprocess launch |

## What to Investigate Next

1. **Verify the hypothesis:** Check whether `MERIDIAN_SPAWN_ID` in p1673's Claude process env matches p1673 or p1621. Can probe by looking at the actual env passed to the subprocess in `claude_ws.py` or by having a Claude spawn run `echo $MERIDIAN_SPAWN_ID` as its first action.

2. **Check codex behavior:** p1678 was a codex spawn created by p1673 (Claude). Does the codex harness have the same issue? The env for the `meridian spawn` CLI call that creates p1678 comes from p1673's Claude session's Bash tool, not from the codex process itself.

3. **Check if this is Claude-specific:** If Claude Code sessions don't propagate process-level env vars into tool calls, the fix might need to be: write `MERIDIAN_SPAWN_ID` into a file that the child reads, or pass it via the system prompt/CLAUDE.md injection rather than relying on env propagation.

4. **Check `MERIDIAN_PARENT_SPAWN_ID`:** In `command.py:35-41`, the RuntimeContext is built WITHOUT spawn_id/parent_spawn_id, so `to_env_overrides()` never emits `MERIDIAN_PARENT_SPAWN_ID`. This is a secondary bug — even if spawn_id propagation works, parent_spawn_id is never set.

## Session Context

- Discovered during investigation of c1538 (session efd3ba13-74ec-4314-a5b8-320bb832617e)
- c1538 was a long-running orchestration session that spawned 47+ agents across multiple phases
- The parent tracking bug made it impossible to trace which orchestrator owned which children
- Related to but distinct from the CWD drift bug (fixed in 251d03d) and report extraction bug (fixed in 62fc33a)
