# Pre-Planning Notes — Dead Code Sweep

## Probe Results: Explorer-Flagged Orphaned Modules

Import-graph verification of all explorer-flagged "orphaned" modules:

| Module | Verdict | Evidence |
|--------|---------|----------|
| `__main__.py` | KEEP | Legitimate entry point (`python -m meridian`) |
| `dev/pytests.py` | KEEP | Legitimate entry point (test runner) |
| `lib/app/agui_types.py` | DEAD — zero inbound imports in src/ | Safe to delete |
| `lib/launch/claude_preflight.py` | LIVE — imported by `harness/claude.py` + test | But requirements say safe-delete (backcompat re-export). The live import is from production `harness/claude.py` — must update that import to use the canonical path before deleting |
| `lib/launch/stream_capture.py` | DEAD — zero inbound imports | Safe to delete |
| `lib/launch/terminal.py` | DEAD — zero inbound imports | Safe to delete |
| `lib/launch/timeout.py` | DEAD — zero inbound imports | Safe to delete |
| `lib/ops/spawn/context_ref.py` | LIVE — imported by prepare.py | DO NOT DELETE |
| `lib/ops/spawn/execute.py` | LIVE — imported by api.py | DO NOT DELETE |
| `lib/ops/spawn/prepare.py` | LIVE — imported by runner.py, streaming_runner.py | DO NOT DELETE |
| `lib/state/reaper_config.py` | DEAD — zero inbound imports | Safe to delete |

## Auth Deletion Scope

Files importing from `authorization.py`:
- `lib/app/ws_endpoint.py` — uses authorize, caller_from_env
- `lib/app/server.py` — uses authorize, caller_from_env  
- `lib/ops/spawn/api.py` — uses authorize, caller_from_env
- `lib/streaming/control_socket.py` — uses authorize
- `cli/spawn_inject.py` — uses authorize
- `cli/spawn.py` — imports authorize, caller_from_env
- `lib/launch/errors.py` — references peercred

The `authorization.py` module itself is the primary target.

## MCP Tool Surface

Only `spawn_cancel` has an MCP tool exposure (mcp_name="spawn_cancel" in manifest.py).
Interrupt is part of inject, not a separate MCP tool.
Requirements say: remove cancel and interrupt from MCP tool surface. Inject stays.
- Remove `spawn_cancel` from manifest MCP surface
- The inject MCP tool should lose its `interrupt: true` capability if it's exposed

## Phase Structure Hypothesis

Three natural phases:
1. **Auth deletion + cancel/interrupt MCP removal** (Part A + cancel surface removal) — biggest blast radius, clears most dead code dependencies
2. **Dead code safe-delete** (Part B items 1-13 + verified orphaned modules) — cleanup after auth removal  
3. **Fence marker rename + verification** — `missing_worker_pid` → `missing_runner_pid`

Then non-code phases:
4. **Reinstall binary** (Part D) — mechanical
5. **Smoke retest** (Part C) — two parallel lanes

Phases 1 and 2 are sequential (2 depends on auth removal). Phase 3 is independent of 2.
Phases 4-5 are sequential (5 depends on 4).

## Design Artifacts

No design package for this work item — it's a cleanup/deletion task driven by requirements.md.
The planner should use requirements.md as the authoritative scope document.
Archived design docs at `.meridian/work-archive/spawn-control-plane-redesign/design/` provide context for what was built.

## Constraints

- `claude_preflight.py` deletion requires updating the live import in `harness/claude.py` first
- `event_store.py` `store_name` param removal touches call sites in `spawn_store.py` and `session_store.py`
- After all deletions: `uv run ruff check . && uv run pyright && uv run pytest-llm` must pass
- Before smoke retest: `uv tool install --reinstall .`
