# Safety

Meridian safety layers:

1. Permission tiers
2. Cost budgets (execution-layer capability)
3. Guardrail scripts (execution-layer capability)
4. Secret redaction (execution-layer capability)
5. Depth limiting

Developer note:
- Canonical domain term is `spawn` (see [Developer Terminology](developer-terminology.md)).
- Command examples below use the current CLI paths.

## Permission Tiers

```bash
meridian spawn -p "Read code" --permission read-only
meridian spawn -p "Edit files" --permission workspace-write
meridian spawn -p "Spawn broadly" --permission full-access
```

| Tier | Intent | Claude | Codex |
|---|---|---|---|
| `read-only` | read/search/git inspect | `--allowedTools Read,Glob,Grep,...` | `--sandbox read-only` |
| `workspace-write` | add edit/write + limited git write | adds `Edit,Write,Bash(git add),Bash(git commit)` | `--sandbox workspace-write` |
| `full-access` | broad shell + web tools | adds `WebFetch,WebSearch,Bash` | `--sandbox danger-full-access` |

Notes:

- `--approval auto` is available on the root `meridian` command (primary launch), not on `meridian spawn`; for supported harnesses it maps to Claude `--dangerously-skip-permissions` or Codex `--dangerously-bypass-approvals-and-sandbox`.

### Agent profile mapping

`sandbox` frontmatter maps to tiers:

- `read-only` -> `read-only`
- `workspace-write` -> `workspace-write`
- `full-access` -> `full-access`
- `danger-full-access` -> `full-access`
- `unrestricted` -> `full-access`

CLI `--permission` overrides profile defaults.

## Approval Mode

Permission and approval are separate controls:

- `--permission` controls tool access tier (`read-only`, `workspace-write`, `full-access`).
- `--approval` controls whether the harness asks before acting.
- `--approval confirm` (default): harness asks before acting.
- `--approval auto`: harness auto-approves all tool use.
- `--yolo` is shorthand for `--permission full-access --approval auto`.

These flags are only on the root `meridian` command for primary-agent launch. Subagent `meridian spawn` runs are unattended and do not have an approval mode.

## Cost Budgets
`spawn` no longer exposes budget flags. Budget enforcement is available only in execution-layer integrations that explicitly wire it.

## Guardrails
`spawn` no longer exposes guardrail flags.

Guardrail env vars:

- `MERIDIAN_GUARDRAIL_RUN_ID`
- `MERIDIAN_GUARDRAIL_OUTPUT_LOG`
- `MERIDIAN_GUARDRAIL_REPORT_PATH`

Non-zero exit marks guardrail failure and feeds normal retry/error handling.

## Secret Redaction
`spawn` no longer exposes secret injection flags.

Secret values are injected as `MERIDIAN_SECRET_<KEY>` and redacted in persisted outputs.

Redaction applies to:

- `spawns/<spawn-id>/output.jsonl`
- `spawns/<spawn-id>/stderr.log`
- `spawns/<spawn-id>/report.md`

Guardrail scripts do not receive `MERIDIAN_SECRET_*` values.

## Depth Limiting

```text
MERIDIAN_DEPTH=0 -> meridian spawn (child depth 1)
  -> MERIDIAN_DEPTH=1 -> meridian spawn (child depth 2)
  -> MERIDIAN_DEPTH=2 -> meridian spawn (child depth 3)
  -> MERIDIAN_DEPTH=3 -> refused (max depth reached)
```

`MERIDIAN_MAX_DEPTH` controls the ceiling (default `3`).
