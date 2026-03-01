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

## Current Tool Set

From the operation registry, MCP exposes:

- `run_spawn`, `run_list`, `run_show`, `run_continue`, `run_wait`, `run_stats`
- `models_list`, `models_show`
- `skills_list`, `skills_show`
- `doctor`
- `grep`

Not MCP-exposed (CLI-only): `space_*`, `config_*`, `skills_search`.

## Run Tools

### `run_spawn`

Create and start a run.

```json
{
  "prompt": "Refactor auth flow",
  "model": "gpt-5.3-codex",
  "skills": ["scratchpad"],
  "files": ["docs/spec.md"],
  "template_vars": ["TARGET=auth"],
  "agent": "coder",
  "report_path": "report.md",
  "background": true,
  "space": "s12",
  "permission_tier": "workspace-write",
  "budget_per_run_usd": 5.0,
  "budget_per_space_usd": 20.0,
  "guardrails": ["./checks/lint.sh"],
  "secrets": ["API_KEY=sk-..."]
}
```

Notes:

- Default is blocking execution.
- Set `background: true` for non-blocking behavior, then call `run_wait`/`run_show`.

### `run_list`

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

### `run_show`

```json
{
  "run_id": "r7",
  "report": true,
  "include_files": true
}
```

### `run_continue`

```json
{
  "run_id": "r7",
  "prompt": "Also update tests",
  "model": "claude-opus-4-6",
  "fork": true
}
```

Uses `continue_harness_session_id` internally from the source run.

### `run_wait`

```json
{
  "run_ids": ["r7", "r8"],
  "timeout_secs": 300,
  "report": true,
  "include_files": false
}
```

Compatibility alias accepted: `run_id` (single string).

### `run_stats`

```json
{
  "space": "s12",
  "session": "c3"
}
```

`session` is Meridian `chat_id`.

## Search Tool

### `grep`

Searches state files (`output`, `logs`, `runs`, `sessions`) across spaces.

```json
{
  "pattern": "orphan_run",
  "space_id": "s12",
  "run_id": "r7",
  "file_type": "logs"
}
```

`run_id` requires `space_id`.

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
