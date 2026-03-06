# Developer Terminology: Spawn

This document defines the canonical language for Meridian contributors.

## Why this exists

Historically, Meridian used `run` for both:

- domain concept (a delegated child-agent task), and
- implementation detail (executing a subprocess).

That overlap caused ambiguous UX (`meridian spawn spawn`) and confusing code review discussions.

## Canonical Definitions

- `Primary agent`: the interactive agent launched by a human (`meridian` or `meridian space start`).
- `Spawn`: a delegated child-agent task created by a primary agent.
- `Harness process`: the concrete CLI process (`claude`, `codex`, `opencode`) used to execute one spawn.
- `Space`: the coordination boundary containing spawn/session/filesystem state.

## Naming Rules by Layer

Use these rules for all new code and refactors:

1. Public/domain surfaces MUST use `spawn` terminology.
2. Low-level process execution code MAY use `run` only when it means "execute a process", not domain identity.
3. Do not introduce new user-facing `run` nouns after migration starts.

### Public/domain surfaces (must be `spawn`)

- CLI commands and help text
- MCP tool names
- Operation names in registry
- Dataclasses and DTOs representing domain entities
- State filenames/directories intended as domain records
- User-facing error messages and docs

Examples:

- `spawn.create`, `spawn.list`, `spawn.wait`
- `SpawnId`, `SpawnRecord`, `spawn_store.py`
- `spawns.jsonl`, `spawns.lock`, `.spaces/<id>/spawns/`

### Internal execution surfaces (can keep `run` if purely mechanical)

- Local loop variables around subprocess invocation
- Utility methods literally describing process execution mechanics

Examples:

- `subprocess.run(...)`
- comments like "run the child process"

Not allowed:

- internal names that leak into public API/help/tool names as `run_*` once migrated.

## Explicit Space Context Rule

Spawns resolve space context in this order:

- If `--space` / `space` input is provided, Meridian uses that.
- Otherwise, if `MERIDIAN_SPACE_ID` is set, Meridian uses that.
- If neither is set, spawn auto-creates a space and prints a hint to export `MERIDIAN_SPACE_ID`.

Best practice: set `MERIDIAN_SPACE_ID` explicitly when you want repeatable routing to one space.
