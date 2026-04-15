# Phase 3: Delete report create (B-05)

## Scope
Remove the `meridian spawn report create` CLI command and `report_create` MCP tool. Make auto-extracted report from final assistant message canonical.

## Files Touched
- `src/meridian/lib/launch/prompt.py` — `build_report_instruction()` 
- `src/meridian/cli/report_cmd.py` — remove `report.create` handler and default_handler
- `src/meridian/lib/ops/manifest.py` — remove `report.create` spec entry
- `src/meridian/lib/ops/report.py` — remove `ReportCreateInput`, `ReportCreateOutput`, `report_create_sync`, `report_create`
- `docs/commands.md` — remove report create row
- `docs/mcp-tools.md` — remove `report_create` section and references

## Changes

### prompt.py
Replace `build_report_instruction()` to tell agents to emit the report as their final assistant message, NOT to call `meridian spawn report create`. The fallback extraction already handles this.

### report_cmd.py
- Remove `_report_create` function
- Remove `"report.create"` from `handlers` dict
- Remove `default_handler=partial(_report_create, emit)` 
- Remove `ReportCreateInput` and `report_create_sync` imports
- Keep `_report_show` and `_report_search`

### manifest.py
- Remove the `report.create` `_spec(...)` entry
- Remove `report_create` and `report_create_sync` from imports

### report.py
- Remove `ReportCreateInput`, `ReportCreateOutput`, `report_create_sync`, `report_create`
- Keep `ReportShowInput/Output`, `ReportSearchInput/Output/Result`, and their handlers
- Keep `_report_path`, `_report_snippet`, `_resolve_spawn`, `_resolve_target_spawn_id`

### docs/commands.md
- Remove the `meridian spawn report create` row from the table

### docs/mcp-tools.md
- Remove `report_create` from the tool list
- Remove the `report_create` example section

### .agents/ skill sources (OUT OF SCOPE for direct edit)
- `.agents/skills/meridian-spawn/resources/advanced-commands.md` lines 56-60 need updating
- Per AGENTS.md, edit the source repo (`~/gitrepos/prompts/meridian-base`), not `.agents/` directly
- Document what needs to change; defer actual edit

## Exit Criteria
- `uv run ruff check .` passes
- `uv run pyright` passes
- `uv run pytest-llm` passes
- `meridian spawn report create` is no longer a valid CLI command
- `meridian spawn report show` still works
