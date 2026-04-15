# Phase 2: Subprocess Projection Cutover

## Task

Reimplement each adapter's `build_command()` to resolve a spec first, then project it to CLI args via explicit code. After parity is proven, delete the strategy map machinery from `common.py`.

## Critical Requirement

**The new `build_command()` MUST produce byte-identical command lists to the current implementation for all inputs.** This is a refactor, not a behavior change. Get the arg ordering exactly right.

## What to Change

### 1. Rewrite `build_command()` in each adapter

Each adapter's `build_command()` should now:
1. Call `self.resolve_launch_spec(run, perms)` to get the spec
2. Build the CLI args from the spec fields explicitly

**Claude** (`src/meridian/lib/harness/claude.py`):

Current ordering from `build_harness_command()` + post-hoc appends:
```
claude -p --output-format stream-json --verbose [prompt: "-"] [model] [effort] [agent] <permission_flags> [--append-system-prompt val] [--agents val] [--resume id] [--fork-session] [extra_args]
```
For interactive mode:
```
claude [model] [effort] [agent] <permission_flags> [--append-system-prompt val] [--agents val] [--resume id] [--fork-session] [extra_args]
```

Note: Look at the ACTUAL current ordering carefully. The strategy-driven builder appends args in field iteration order from SpawnParams, then permission flags, then MCP, then subcommand, then extra_args. The post-hoc `--append-system-prompt`, `--agents`, `--resume`, `--fork-session` come AFTER the strategy loop output.

**Codex** (`src/meridian/lib/harness/codex.py`):

Current ordering:
```
codex exec --json [model] [effort] <permission_flags> [extra_args + -o report_path] [resume threadId] [prompt: "-"]
```
For interactive:
```
codex [model] [effort] <permission_flags> [resume threadId] [extra_args + guarded_prompt]
```

Note: Codex uses POSITIONAL prompt mode — extra_args come before prompt, and subcommand (resume) is appended after permission flags.

**OpenCode** (`src/meridian/lib/harness/opencode.py`):

Current ordering:
```
opencode run [model] [effort] <permission_flags> [extra_args] [--session id] [--fork] [prompt: "-"]
```

### 2. Delete strategy machinery from `common.py`

After all three adapters are rewritten:
- Remove `FlagEffect`, `FlagStrategy`, `StrategyMap`, `_SKIP_FIELDS`, `PromptMode`, `build_harness_command()`, `_append_cli_flag()`
- Remove imports of these from `claude.py`, `codex.py`, `opencode.py`
- Remove `STRATEGIES`, `PROMPT_MODE` class vars from adapters

### 3. Write parity tests in `tests/harness/test_launch_spec_parity.py`

Parameterized tests for each adapter that:
- Create a SpawnParams with various field combinations
- Create a mock PermissionResolver
- Call `build_command()` (new spec-based version)
- Assert the result matches the expected command list

Cover these cases for each harness:
- Fresh session (no continue_session_id)
- Resume session
- Fork session
- Effort set to each level
- With and without adhoc_agent_payload
- With and without appended_system_prompt
- With and without permission flags
- With and without extra_args
- Interactive mode

## How to Match Current Behavior

I'll describe the EXACT current behavior for reference. Study the current `build_harness_command()` function at `src/meridian/lib/harness/common.py` (line 551+).

The current flow is:
1. Build `strategy_args` by iterating `SpawnParams.model_fields` in declaration order
2. Start with `base_command` 
3. If FLAG prompt mode and prompt exists: append prompt
4. Append strategy_args
5. Append permission_flags from `perms.resolve_flags(harness_id)`
6. Append MCP config args (currently None)
7. Append subcommand (e.g., `resume threadId` for Codex)
8. If POSITIONAL prompt mode: append extra_args, then prompt
9. If FLAG prompt mode: append extra_args

Then each adapter post-processes:
- Claude: appends --append-system-prompt, --agents, --resume, --fork-session
- Codex: handles resume via subcommand, injects -o report_path into extra_args
- OpenCode: appends --session, --fork after command

## Verification

```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/harness/test_launch_spec.py tests/harness/test_launch_spec_parity.py tests/ops/test_spawn_prepare_fork.py -x -q
uv run pytest-llm tests/ -x -q
```

## Edge Cases
- Empty string effort should be treated as None (current behavior)
- None model should produce no --model flag
- Empty adhoc_agent_payload ("") should produce no --agents flag
- `continue_fork=True` without `continue_session_id` should produce no --fork-session/--fork
- Interactive mode changes the base command but not the arg logic
