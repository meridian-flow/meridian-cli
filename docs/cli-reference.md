# CLI Reference

This page tracks the current CLI surface from `meridian --help`.

## Global Options

Use before subcommands:

| Flag | Description |
|---|---|
| `--json` | JSON output |
| `--porcelain` | Stable key/value output |
| `--format text\|json\|porcelain` | Explicit output format |
| `--config <path>` | Load user config overlay |
| `--yes` | Auto-confirm prompts where supported |
| `--no-input` | Fail instead of prompting |
| `--version` | Print version |

## Top-Level Commands

```text
completion  config  doctor  grep  init  models  run  serve  skills  space  start
```

## `meridian run`

### `run spawn`

Create and start a run.

```bash
meridian run spawn -p "Implement feature" -m gpt-5.3-codex
meridian run spawn --background -p "Long task" -m opus
meridian run spawn --dry-run -p "Plan only"
```

Common flags:

| Flag | Notes |
|---|---|
| `--prompt, -p` | Prompt text |
| `--prompt-var` | Repeatable `KEY=VALUE` prompt template vars (replaces `{{KEY}}`) |
| `--model, -m` | Model id or alias |
| `--skills, -s` | Repeatable skill names |
| `--file, -f` | Repeatable reference files |
| `--agent, -a` | Agent profile name |
| `--report-path` | Relative report path (default `report.md`) |
| `--dry-run` | Compose only, do not execute harness |
| `--background` | Return immediately with run ID |
| `--space-id`, `--space` | Explicit space scope |
| `--timeout-secs` | Runtime limit |
| `--permission` | `read-only`, `workspace-write`, `full-access`, `danger` (`danger` currently rejected for `run spawn`) |

Notes:

- `meridian run -p "..."` is shorthand for `meridian run spawn -p "..."`.
- If no space is selected, spawn auto-creates one and warns with the new `sN`.

### `run list`

```bash
meridian run list
meridian run list --space s12 --status failed
```

Flags: `--space-id/--space`, `--status`, `--model`, `--limit`, `--no-space`, `--failed`.

### `run show`

```bash
meridian run show r7
meridian run show r7 --report --include-files
```

Flags: `--report`, `--include-files`.

### `run continue`

```bash
meridian run continue r7 -p "Add tests"
meridian run continue r7 -p "Try alternative" --fork
```

Flags: `--prompt/-p` (required), `--model/-m`, `--fork`, `--timeout-secs`.

### `run wait`

```bash
meridian run wait r7
meridian run wait r7 r8 --report
```

Flags: `--timeout-secs`, `--report`, `--include-files`.

### `run stats`

```bash
meridian run stats
meridian run stats --space s12 --session c4
```

Flags: `--space-id/--space`, `--session`.

## `meridian space`

### `space start`

```bash
meridian space start --name auth-refactor
meridian space start --model claude-opus-4-6 --autocompact 70
```

Flags: `--name`, `--model`, `--autocompact`, `--dry-run`, `--harness-arg` (repeatable).

### `space resume`

```bash
meridian space resume
meridian space resume --space s12 --fresh
```

Flags: `--space-id/--space`, `--fresh`, `--model`, `--autocompact`, `--harness-arg`.

### `space list/show/close`

```bash
meridian space list --limit 20
meridian space show s12
meridian space close s12
```

## `meridian start`

Resolve or create a space and launch the primary harness.

```bash
meridian start
meridian start --new
meridian start --space s12
```

Flags: `--new`, `--space`, `--continue` (currently stubbed, errors), `--model`, `--autocompact`, `--dry-run`, `--harness-arg`.

## `meridian grep`

Search Meridian state files.

```bash
meridian grep "orphan_run"
meridian grep "failed" --space s12 --type runs
meridian grep "timeout" --space s12 --run r7 --type logs
```

Flags:

- `--space`: one space
- `--run`: one run (requires `--space`)
- `--type`: `output`, `logs`, `runs`, `sessions`

## `meridian config`

```bash
meridian config init
meridian config show
meridian config get defaults.max_depth
meridian config set permissions.default_tier workspace-write
meridian config reset permissions.default_tier
```

## `meridian skills`

```bash
meridian skills list
meridian skills search review
meridian skills show scratchpad
```

## `meridian models`

```bash
meridian models list
meridian models show codex
```

## `meridian doctor`

```bash
meridian doctor
```

Runs diagnostics and safe repairs for file-backed state.

## `meridian serve`

```bash
meridian serve
```

Starts the FastMCP stdio server.
