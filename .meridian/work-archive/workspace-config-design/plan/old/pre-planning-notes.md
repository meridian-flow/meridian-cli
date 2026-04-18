# Pre-Planning Notes — R06 Hexagonal Launch Core

## Baseline verification (2026-04-15)

- pyright: 0 errors (v1.1.408)
- ruff: all checks passed
- pytest: 658 passed in 12.28s
- git: working tree clean (1 untracked file: prompts/impl-r06.md)

## Key structural observations from code reading

### Two `RuntimeContext` types
1. `src/meridian/lib/launch/context.py:42` — frozen dataclass, used by `prepare_launch_context()` for spawn child env.
2. `src/meridian/lib/core/context.py:13` — pydantic BaseModel, used by execute.py and other spawn ops for reading current env state.

These have different shapes: launch's has `repo_root`/`state_root` as required Path, plus `parent_chat_id`/`parent_depth`/`fs_dir`/`work_id`/`work_dir`. Core's has `spawn_id`/`depth`/`repo_root`/`state_root`/`chat_id`/`work_id` with most optional/defaulted. Unification needs to merge both field sets. The launch version owns `child_context()` (output for child processes), the core version owns `from_environment()` (reading current state) and `to_env_overrides()`.

### `prepare_launch_context()` is the proto-factory
`context.py:148-223` already does most of what `build_launch_context()` needs for the spawn path: preflight, SpawnParams construction, spec resolution, env building. The planner should evolve this into the factory rather than starting from scratch.

### `SpawnParams` field analysis
Current `SpawnParams` at `adapter.py:147-166` mixes user-facing and resolved fields:
- User-facing: prompt, model, effort, skills (refs), agent, extra_args, interactive, mcp_tools
- Resolved/internal: repo_root (as posix string), continue_harness_session_id, continue_fork, report_output_path, appended_system_prompt, adhoc_agent_payload

The split must move resolved fields to the factory internals.

### Primary launch path
`plan.py:resolve_primary_launch_plan()` at ~lines 149-343 independently resolves policies, builds permissions, constructs SpawnParams, calls resolve_launch_spec, builds env. This is the main duplication with the spawn path.

### App streaming path
`server.py:268-365` builds SpawnParams at ~line 296, constructs TieredPermissionResolver at line 316, calls adapter.resolve_launch_spec at line 338. Another independent composition site.

### `streaming_serve.py`
CLI entry point at `streaming_serve.py:85-98` hardcodes TieredPermissionResolver and calls run_streaming_spawn. This dead path needs deletion.

### Fork materialization sites
1. `launch/process.py:68-105` — primary launch fork
2. `ops/spawn/prepare.py:296-311` — spawn fork

Both call adapter.fork_session(), mutate SpawnParams via model_copy, rebuild command. Identical logic.

### Session ID observation
Currently scattered:
- Primary PTY: scraping in `process.py` or `streaming_runner.py` 
- Streaming Codex: `connections/codex_ws.py:190,270`
- Streaming OpenCode: `connections/opencode_http.py:137,166`
- Also via `detect_primary_session_id` on adapter and `extract_session_id` via artifacts

## Phasing hypothesis

The design's 8-phase decomposition looks right. Key dependencies:

1. SpawnRequest/SpawnParams split — standalone, touches adapter.py and all SpawnParams constructors
2. RuntimeContext unification — standalone, touches context.py and core/context.py
3. Domain core (factory + LaunchContext sum type + pipeline stages + LaunchResult/LaunchOutcome + observe_session_id) — the big phase
4-6. Rewire driving adapters (primary, worker, app) — sequential after phase 3, each depends on factory
7. Deletions (run_streaming_spawn, SpawnManager fallback) — after phase 6
8. MERIDIAN_HARNESS_COMMAND bypass — after phase 3, can parallel with 4-6

However, phases 1 and 2 can be parallelized with each other. Phase 8 can potentially be folded into phase 3 since the bypass logic is part of the factory.

The CI invariants script should land in phase 3 (with the factory) or as a final phase.

## Probe gaps

- Need to verify exact `run_streaming_spawn` call graph before deletion phase
- Need to verify `SpawnManager.start_spawn` spec parameter usage across all callers
- Need to check what imports `from meridian.lib.harness.claude_preflight` in launch/ modules

## Constraints

- Tests must be updated in the same commit as source changes (R06 exit criteria)
- Each phase must leave pyright 0 errors, ruff clean, pytest passing
- Commit after each phase per CLAUDE.md
- `MERIDIAN_HARNESS_COMMAND` bypass is tested in smoke tests — don't break it during intermediate phases
