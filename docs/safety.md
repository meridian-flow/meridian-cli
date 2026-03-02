# Safety

Meridian safety layers:

1. Permission tiers
2. Cost budgets (execution-layer capability)
3. Guardrail scripts (execution-layer capability)
4. Secret redaction (execution-layer capability)
5. Depth limiting

Developer note:
- Canonical domain term is `spawn` (see [Developer Terminology](developer-terminology.md)).
- Command examples below use current CLI paths (`meridian spawn ...`) until migration completes.

## Permission Tiers

```bash
meridian spawn spawn -p "Read code" --permission read-only
meridian spawn spawn -p "Edit files" --permission workspace-write
meridian spawn spawn -p "Spawn broadly" --permission full-access
```

| Tier | Intent | Claude | Codex |
|---|---|---|---|
| `read-only` | read/search/git inspect | `--allowedTools Read,Glob,Grep,...` | `--sandbox read-only` |
| `workspace-write` | add edit/write + limited git write | adds `Edit,Write,Bash(git add),Bash(git commit)` | `--sandbox workspace-write` |
| `full-access` | broad shell + web tools | adds `WebFetch,WebSearch,Bash` | `--sandbox danger-full-access` |

Notes:

- `run spawn` does not expose an `--unsafe` override; requesting `--permission danger` is rejected.
- OpenCode has no danger-bypass flag; danger is validated and falls back to full-access behavior there in paths that still support it.

### Agent profile mapping

`sandbox` frontmatter maps to tiers:

- `read-only` -> `read-only`
- `workspace-write` -> `workspace-write`
- `danger-full-access` -> `full-access`
- `unrestricted` -> `full-access`

CLI `--permission` overrides profile defaults.

## Cost Budgets
`run spawn` no longer exposes budget flags. Budget enforcement is available only in execution-layer integrations that explicitly wire it.

## Guardrails
`run spawn` no longer exposes guardrail flags.

Guardrail env vars:

- `MERIDIAN_GUARDRAIL_RUN_ID`
- `MERIDIAN_GUARDRAIL_OUTPUT_LOG`
- `MERIDIAN_GUARDRAIL_REPORT_PATH`

Non-zero exit marks guardrail failure and feeds normal retry/error handling.

## Secret Redaction
`run spawn` no longer exposes secret injection flags.

Secret values are injected as `MERIDIAN_SECRET_<KEY>` and redacted in persisted outputs.

Redaction applies to:

- `spawns/<run-id>/output.jsonl`
- `spawns/<run-id>/stderr.log`
- `spawns/<run-id>/report.md`

Guardrail scripts do not receive `MERIDIAN_SECRET_*` values.

## Depth Limiting

```text
MERIDIAN_DEPTH=0 -> meridian spawn spawn (child depth 1)
  -> MERIDIAN_DEPTH=1 -> meridian spawn spawn (child depth 2)
  -> MERIDIAN_DEPTH=2 -> meridian spawn spawn (child depth 3)
  -> MERIDIAN_DEPTH=3 -> refused (max depth reached)
```

Target naming after migration: `meridian spawn` replaces `meridian spawn spawn`.

`MERIDIAN_MAX_DEPTH` controls the ceiling (default `3`).
