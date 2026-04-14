# Decisions — Dead Code Sweep

## D-01 — Explorer-flagged orphans: import verification before deletion

Verified all 11 explorer-flagged modules via `rg` for inbound imports. Result: 5 dead (agui_types, stream_capture, terminal, timeout, reaper_config), 3 live (context_ref, execute, prepare — imported by production code), 2 entry points (__main__, pytests), 1 requires import update before deletion (claude_preflight — live import from harness/claude.py needs redirect to canonical path).

## D-02 — MCP tool surface: only spawn_cancel exposed

Interrupt is not a separate MCP tool — it's part of the inject tool. Requirements say remove cancel and interrupt tool exposures. Action: remove `spawn_cancel` from manifest MCP surface. For interrupt: check if inject MCP tool exposes interrupt capability and remove that parameter from MCP surface if so.
