# Plan Cleanup Notes

Condensed follow-up notes captured while deleting stale plan documents on 2026-03-08.

These are not full implementation plans. They are the remaining actionable threads
that were worth keeping after plan cleanup.

## Open Follow-Ups

### State layout long tail

- Keep tracking `report_path` cleanup: either remove it from spawn output or
  redefine it so it is not a fake write target.
- Stop CLI report lookup from scanning redundant locations when the canonical
  spawn path is already known.
- Make spawn artifact storage collision-free within the flat `.meridian/`
  layout.

### Spawn observability

- Add canonical per-spawn `events.jsonl` owned by Meridian.
- Keep harness-specific parsing inside adapters; downstream features should read
  canonical records instead of raw harness logs.
- Migrate spawn report/status/show fallbacks off raw heuristics and delete the
  duplicate parsing paths in the same slice.
- Add adapter-fixture and persistence tests for the canonical event path.
- Open schema questions still unresolved:
  - curated fields only vs raw metadata references
  - delta-only events vs delta plus completed-message records
  - how stderr-only failures/warnings should be persisted

### Test suite and strict typing cleanup

- Start with an invariant inventory, not file preservation.
- Rebuild the remaining suite by subsystem (`config`, `state`, `spawn`,
  `harness`, `prompt`, `exec`, `ops`).
- Delete slice-era and other low-value historical tests once replacement
  coverage exists.
- Shrink smoke verification to a short operator workflow.
- Finish with a `pyright`-clean tree.

### Remote workspace viewer

- If this work restarts, preserve the requirements baseline:
  - explicit exposure mode
  - asset upload + mention snippets
  - readable file browser
  - first-class markdown + Mermaid rendering
  - distinct desktop/mobile shells
  - CLI-visible launch status and failures
- Open questions to resolve before any implementation plan:
  - runtime choice
  - dedicated command vs sidecar launch
  - minimum mention-snippet set
  - target repo scale for performance

### Harness capability follow-up

- Revalidate Codex/OpenCode capability gaps against current 2026 reality before
  treating any old blocker notes as true.
- Keep Cursor harness capability evaluation as an explicit future task if that
  integration becomes real.
- Either add the missing `.opencode/plugins/meridian.ts` compaction plugin or
  remove/correct docs that still claim it exists.

### Files-as-authority long tail

- Cross-run query/index strategy if JSONL scans ever become a real limit.
- Run-artifact retention/cleanup policy.
- Further harness lifecycle and error-normalization cleanup.
- Multi-harness end-to-end coverage.
- Optional richer state metadata if the current minimal shape proves too small.
- Security hardening beyond the current cooperative local-user model if threat
  assumptions change.
