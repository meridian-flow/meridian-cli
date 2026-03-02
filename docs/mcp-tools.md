# MCP Tools

`meridian serve` exposes Meridian operations as FastMCP tools over stdio.

Developer note:
- Canonical domain term is `spawn` (see [Developer Terminology](developer-terminology.md)).
- Current MCP tool names still use `run_*` until migration is complete.
- Keep docs/tests explicit about whether they describe current or target names.

## Migration Naming Map (Target)

| Current | Target |
|---|---|
| `spawn_create` | `spawn_create` |
| `spawn_list` | `spawn_list` |
| `spawn_show` | `spawn_show` |
| `spawn_continue` | `spawn_continue` |
| `spawn_wait` | `spawn_wait` |
| `spawn_stats` | `spawn_stats` |

## Start Server

```bash
meridian serve
```

Minimal MCP config:

```json
{
  "mcpServers": {
    "meridian": {
      "command": "meridian",
      "args": ["serve"]
    }
  }
}
```

## Current Tool Set

From the operation registry, MCP exposes:

- `spawn_create`, `spawn_list`, `spawn_show`, `spawn_continue`, `spawn_wait`, `spawn_stats`
- `models_list`, `models_show`
- `skills_list`, `skills_show`
- `doctor`
- `grep`

Target state after migration:
- `spawn_create`, `spawn_list`, `spawn_show`, `spawn_continue`, `spawn_wait`, `spawn_stats`
- `models_list`, `models_show`
- `skills_list`, `skills_show`
- `doctor`

Not MCP-exposed (CLI-only): `space_*`, `config_*`, `skills_search`.

## Spawn Tools

### `spawn_create`

Create and start a run.

```json
{
  "prompt": "Refactor auth flow",
  "model": "gpt-5.3-codex",
  "files": ["docs/spec.md"],
  "template_vars": ["TARGET=auth"],
  "agent": "coder",
  "report_path": "report.md",
  "background": true,
  "space": "s12",
  "permission_tier": "workspace-write"
}
```

Notes:

- Default is blocking execution.
- Set `background: true` for non-blocking behavior, then call `spawn_wait`/`spawn_show`.

### `spawn_list`

```json
{
  "space": "s12",
  "status": "failed",
  "model": "gpt-5.3-codex",
  "limit": 10,
  "no_space": false,
  "failed": true
}
```

### `spawn_show`

```json
{
  "spawn_id": "r7",
  "report": true,
  "include_files": true
}
```

### `spawn_continue`

```json
{
  "spawn_id": "r7",
  "prompt": "Also update tests",
  "model": "claude-opus-4-6",
  "fork": true
}
```

Uses `continue_harness_session_id` internally from the source run.

### `spawn_wait`

```json
{
  "spawn_ids": ["r7", "r8"],
  "timeout_secs": 300,
  "report": true,
  "include_files": false
}
```

Compatibility alias accepted: `spawn_id` (single string).

### `spawn_stats`

```json
{
  "space": "s12",
  "session": "c3"
}
```

`session` is Meridian `chat_id`.

## Search Tool

### `grep`

Searches state files (`output`, `logs`, `spawns`, `sessions`) across spaces.

```json
{
  "pattern": "orphan_run",
  "space_id": "s12",
  "spawn_id": "r7",
  "file_type": "logs"
}
```

`spawn_id` requires `space_id`.

## Models and Skills

### `models_list`

```json
{}
```

### `models_show`

```json
{ "model": "codex" }
```

### `skills_list`

```json
{}
```

### `skills_show`

```json
{ "name": "scratchpad" }
```

## Diagnostics

### `doctor`

```json
{}
```

Runs health checks and safe repairs for file-backed space/run/session state.
