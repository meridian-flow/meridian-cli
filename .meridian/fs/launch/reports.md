# launch/reports — Report Creation and Extraction

## Overview

Reports are the primary way spawn results are persisted and surfaced. Every spawn should produce a `report.md`. The system has a preference hierarchy: explicit agent-written report > harness-extracted assistant message > last JSONL output line.

## How Agents Write Reports

The prompt always includes a report instruction telling agents to run:

```
meridian report create --stdin
```

This writes `spawns/<id>/report.md` via the `report.create` manifest operation. The report is written as stdin to the command.

**Note**: The CLI surface is `meridian spawn report create --stdin` (nested under spawn), not `meridian report create --stdin`. The prompt instruction says `meridian report create --stdin` — this works because the system treats it as falling back to the auto-extraction path if the command fails.

## Extraction Fallback Chain

`extract_or_fallback_report(artifacts, spawn_id, adapter)` in `launch/report.py`:

```
1. Check artifacts for "report.md" content
   → if non-empty: return with source="report_md"

2. Try adapter.extract_report(artifacts, spawn_id)
   → harness-specific extraction from output.jsonl
   → if non-empty: return with source="assistant_message"

3. Parse output.jsonl lines looking for assistant-role messages
   → _extract_last_assistant_message(): scans JSONL for assistant content
   → falls back to last non-empty line if no structured assistant message found
   → if non-empty: return with source="assistant_message"

4. Return ExtractedReport(content=None, source=None)
```

The `adapter` parameter is optional. If `None`, steps 2 is skipped.

## Report Persistence

`_persist_report()` in `extract.py` (called by `enrich_finalize()`):

- Redacts secrets via `redact_secrets()`
- For `source="assistant_message"`: wraps with `# Auto-extracted Report\n\n` header so readers can identify fallback content
- For `source="report_md"`: persists as-is
- Writes atomically to `.meridian/spawns/<id>/report.md` via `atomic_write_text()`
- Also stores in the `ArtifactStore` under key `<spawn_id>/report.md`

The dual-write (filesystem + artifact store) ensures both `spawn show --report` and artifact-store lookups see the same content.

## enrich_finalize()

`enrich_finalize(artifacts, adapter, spawn_id, log_dir, secrets)` in `extract.py` runs the full post-execution extraction pipeline:

```python
FinalizeExtraction:
    usage: TokenUsage                    # from adapter.extract_usage()
    harness_session_id: str | None       # from adapter.extract_session_id()
    report_path: Path | None             # filesystem path of written report.md
    report: ExtractedReport              # content + source
    output_is_empty: bool                # True if no output AND no report
```

Called after subprocess exit in both `process.py` (primary) and `runner.py` (subagent).

## Report Operations (ops layer)

`src/meridian/lib/ops/report.py` exposes the manifest-level report operations:

- `report.create` — writes `spawns/<id>/report.md`; determines spawn_id from env `MERIDIAN_SPAWN_ID`
- `report.show` — reads and returns report content
- `report.search` — scans reports across all spawns or the current runtime context

CLI surface: `meridian spawn report create/show/search` (nested under `spawn`).  
MCP surface: `report_create`, `report_show`, `report_search` (flat, top-level tools).

The manifest exposes report at the top level for MCP but nests it under `spawn` for CLI. This inconsistency is intentional: CLI users think of reports as spawn artifacts, while MCP consumers interact with reports as first-class objects.

## Auto-extracted Report Marker

Auto-extracted reports are wrapped with `# Auto-extracted Report` header. This lets downstream readers distinguish:
- Agent-authored report (ran `meridian report create`) → no header
- Fallback extraction (last assistant message) → `# Auto-extracted Report` header

The `spawn show` command surfaces this distinction. Agents reading prior-spawn reports via `--from` can note whether the prior report was authoritative.

## Reset on Retry

`reset_finalize_attempt_artifacts()` in `extract.py` clears attempt-scoped artifacts (`output.jsonl`, `stderr.log`, `tokens.json`, `report.md`) before a retry attempt. This prevents a partially-written report from the failed attempt from polluting the next attempt's extraction.
