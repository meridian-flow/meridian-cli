# Decisions — Dead Code Sweep

## D-01 — Explorer-flagged orphans: import verification before deletion

Verified all 11 explorer-flagged modules via `rg` for inbound imports. Result: 5 dead (agui_types, stream_capture, terminal, timeout, reaper_config), 3 live (context_ref, execute, prepare — imported by production code), 2 entry points (__main__, pytests), 1 requires import update before deletion (claude_preflight — live import from harness/claude.py needs redirect to canonical path).

## D-02 — MCP tool surface: only spawn_cancel exposed

Interrupt is not a separate MCP tool — it's part of the inject tool. Requirements say remove cancel and interrupt tool exposures. Action: remove `spawn_cancel` from manifest MCP surface. For interrupt: check if inject MCP tool exposes interrupt capability and remove that parameter from MCP surface if so.

## D-03 — Pre-existing test failure accepted

`test_execute_with_finalization_continues_when_terminal_heartbeat_touch_fails` fails with `OSError: no space left on device` on both clean and modified trees. Pre-existing, not caused by our changes. Accepted.

## D-04 — AF_UNIX smoke lane blocked by app deps distribution

`meridian app` requires `uv sync --extra app` deps that `uv tool install` doesn't include. All AF_UNIX/liveness scenarios blocked at the install baseline. This is a pre-existing distribution limitation, not caused by our changes. The same blocker existed in p1822 (which used repo-local `.venv/bin/meridian` as a workaround).

## D-05 — spawn_inject MCP tool also absent

Smoke retest found `spawn_inject` is absent from the MCP tool list (not just `spawn_cancel`). This means inject was already not in MCP, which is consistent — the inject MCP tool was never registered with an `mcp_name` in the manifest. The requirements say inject stays, but it was never exposed via MCP to begin with, only via CLI.

## D-06 — docs/mcp-tools.md is stale

Smoke tester noted `docs/mcp-tools.md` still lists `spawn_cancel`. This is a doc-only issue, not a code issue — out of scope for this work item.
