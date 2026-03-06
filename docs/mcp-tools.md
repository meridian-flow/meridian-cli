# MCP Tools

`meridian serve` exposes Meridian operations as FastMCP tools over stdio.

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

## Tool Set

Current MCP tools:

- `spawn_create`, `spawn_list`, `spawn_show`, `spawn_continue`, `spawn_cancel`, `spawn_wait`, `spawn_stats`
- `report_create`, `report_show`, `report_search`
- `models_list`, `models_show`
- `skills_list`, `skills_show`
- `doctor`

Not MCP-exposed (CLI-only): space_*, config_*, skills_search.

## Spawn Tools

### `spawn_create`

```json
{
  "prompt": "Refactor auth flow",
  "model": "gpt-5.3-codex",
  "files": ["docs/spec.md"],
  "template_vars": ["TARGET=auth"],
  "agent": "coder",
  "space": "s12",
  "permission_tier": "workspace-write"
}
```

### `spawn_show`

```json
{
  "spawn_id": "p7",
  "report": true,
  "include_files": true
}
```

`spawn_id` also accepts references: `@latest`, `@last-failed`, `@last-completed`.

### `spawn_wait`

```json
{
  "spawn_ids": ["p7", "p8"],
  "timeout": 30,
  "report": true,
  "include_files": false
}
```

Compatibility alias accepted: `spawn_id` (single string).

## Report Tools

### `report_create`

```json
{
  "content": "# Report\n\nDone.",
  "spawn_id": "p7",
  "space": "s12"
}
```

Defaults:
- If `spawn_id` is omitted, Meridian resolves from `MERIDIAN_SPAWN_ID`.

### `report_show`

```json
{
  "spawn_id": "@latest",
  "space": "s12"
}
```

### `report_search`

```json
{
  "query": "guardrail",
  "space": "s12",
  "limit": 20
}
```

Optional scope to one spawn:

```json
{
  "query": "timeout",
  "spawn_id": "@last-failed",
  "space": "s12"
}
```

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
