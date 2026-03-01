# Safety

Meridian safety layers:

1. Permission tiers
2. Cost budgets
3. Guardrail scripts
4. Secret redaction
5. Depth limiting

## Permission Tiers

```bash
meridian run spawn -p "Read code" --permission read-only
meridian run spawn -p "Edit files" --permission workspace-write
meridian run spawn -p "Run broadly" --permission full-access
meridian run spawn -p "Bypass checks" --permission danger --unsafe
```

| Tier | Intent | Claude | Codex |
|---|---|---|---|
| `read-only` | read/search/git inspect | `--allowedTools Read,Glob,Grep,...` | `--sandbox read-only` |
| `workspace-write` | add edit/write + limited git write | adds `Edit,Write,Bash(git add),Bash(git commit)` | `--sandbox workspace-write` |
| `full-access` | broad shell + web tools | adds `WebFetch,WebSearch,Bash` | `--sandbox danger-full-access` |
| `danger` | explicit unsafe bypass | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` |

Notes:

- `danger` requires `--unsafe`.
- OpenCode has no danger-bypass flag; danger is validated and falls back to full-access behavior there.

### Agent profile mapping

`sandbox` frontmatter maps to tiers:

- `read-only` -> `read-only`
- `workspace-write` -> `workspace-write`
- `danger-full-access` -> `full-access`
- `unrestricted` -> `full-access`

CLI `--permission` overrides profile defaults.

## Cost Budgets

```bash
# Per run
meridian run spawn -p "..." --budget-per-run-usd 2.00

# Per space (cumulative)
meridian run spawn -p "..." --budget-per-space-usd 10.00

# Legacy alias for per-run
meridian run spawn -p "..." --budget-usd 2.00
```

Budget checks occur preflight, during stream parsing, and post-run finalization.

## Guardrails

```bash
meridian run spawn -p "..." \
  --guardrail ./checks/lint.sh \
  --guardrail ./checks/tests.sh
```

Guardrail env vars:

- `MERIDIAN_GUARDRAIL_RUN_ID`
- `MERIDIAN_GUARDRAIL_OUTPUT_LOG`
- `MERIDIAN_GUARDRAIL_REPORT_PATH`

Non-zero exit marks guardrail failure and feeds normal retry/error handling.

## Secret Redaction

```bash
meridian run spawn -p "Deploy" \
  --secret API_KEY=sk-abc123 \
  --secret DB_PASSWORD=hunter2
```

Secret values are injected as `MERIDIAN_SECRET_<KEY>` and redacted in persisted outputs.

Redaction applies to:

- `runs/<run-id>/output.jsonl`
- `runs/<run-id>/stderr.log`
- `runs/<run-id>/report.md`

Guardrail scripts do not receive `MERIDIAN_SECRET_*` values.

## Depth Limiting

```text
MERIDIAN_DEPTH=0 -> meridian run spawn (child depth 1)
  -> MERIDIAN_DEPTH=1 -> meridian run spawn (child depth 2)
  -> MERIDIAN_DEPTH=2 -> meridian run spawn (child depth 3)
  -> MERIDIAN_DEPTH=3 -> refused (max depth reached)
```

`MERIDIAN_MAX_DEPTH` controls the ceiling (default `3`).
