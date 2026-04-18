# Phase 2: Workspace Model and Inspection

Implement the workspace topology model and inspection surfaces on top of phase 1's shared config surface.

## Scope Summary

1. **Workspace file parsing** (`workspace.local.toml`)
   - Parse `[[context-roots]]` entries with required `path` and optional `enabled` fields
   - Preserve unknown keys for forward compatibility
   - Resolve relative paths relative to the workspace file, not process cwd
   - Produce `WorkspaceConfig` dataclass

2. **Workspace snapshot evaluation**
   - Build `WorkspaceSnapshot` from `WorkspaceConfig` + filesystem state
   - Status enum: `none` (no file), `present` (valid file), `invalid` (parse/schema error)
   - Track per-root: `declared_path`, `resolved_path`, `enabled`, `exists`
   - Capture unknown keys and findings

3. **`workspace init` command**
   - Create commented-example `workspace.local.toml` if absent
   - Add gitignore coverage in `.meridian/.gitignore`
   - Idempotent: report "already exists" if file present

4. **Config/doctor surfacing**
   - Extend `ConfigSurface` with workspace snapshot
   - `config show --json`: expose `workspace: {status, path?, roots: {count, enabled, missing}}`
   - `config show` text: flat grep-friendly lines
   - `doctor`: surface invalid-workspace, unknown-key, and missing-root findings

5. **Invalid-workspace gating**
   - Workspace-dependent commands fail before harness launch when workspace file is invalid
   - Inspection commands (`config show`, `doctor`) continue and surface the invalid status

## Key Design Constraints

- `workspace.local.toml` is LOCAL-ONLY (gitignored), lives next to `.meridian/`
- Absent workspace = `status=none` = quiet healthy state, no warnings
- Use existing `ConfigSurface` builder pattern from phase 1
- Match the dataclass shapes from `design/architecture/workspace-model.md`

## Claimed EARS Statements

WS-1.u1, WS-1.u2, WS-1.u3, WS-1.u4, WS-1.s1, WS-1.e1, WS-1.e2, WS-1.c1
SURF-1.u1, SURF-1.e1, SURF-1.e2
BOOT-1.e2

## Exit Criteria

- `workspace.local.toml` is the only workspace filename recognized
- `workspace init` creates commented-example file, adds gitignore, is idempotent
- Relative paths resolve relative to the workspace file
- `config show --json` exposes workspace summary
- `doctor` surfaces invalid-workspace, unknown-key, missing-root findings
- `workspace.status = none` remains quiet (no warnings for single-repo users)
- Invalid workspace = fatal for workspace-dependent commands, non-fatal for inspection
- `uv run ruff check .` and `uv run pyright` clean
- Targeted tests pass

## Module Layout

Create:
- `src/meridian/lib/config/workspace.py` — workspace parsing + snapshot model
- `src/meridian/lib/ops/workspace.py` — workspace init ops
- `src/meridian/cli/workspace.py` — workspace CLI registration

Modify:
- `src/meridian/lib/ops/config_surface.py` — add workspace snapshot to surface
- `src/meridian/lib/ops/config.py` — extend config show/get for workspace
- `src/meridian/lib/ops/diag.py` — extend doctor for workspace findings
- `src/meridian/cli/main.py` — register workspace command group
- `.meridian/.gitignore` (template) — add workspace.local.toml pattern

## Do Not Touch

- Harness-specific projection mechanics (phase 3)
- Launch-time applicability diagnostics (phase 3)
- `MERIDIAN_WORKSPACE` env override (deferred out of v1)

Run verification after implementation:
```bash
uv run ruff check .
uv run pyright
uv run pytest-llm tests/lib/config/ tests/ops/test_diag.py
```
