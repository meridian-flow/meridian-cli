# Task: Update User-Facing docs/ for Spawn-Lifecycle / Reaper Refactor

Update user-facing documentation under `docs/` to reflect commits f6d9f20..27d5237 on main (issue #14 PR1+PR2 + final-review).

## Scope — files to audit and update

- `docs/commands.md` — any `spawn show`, `spawn list`, `work` output descriptions that enumerate spawn statuses
- `docs/troubleshooting.md` — orphan detection guidance, status meanings, recovery behavior
- `docs/mcp-tools.md` — any tool responses / status enums exposed to MCP consumers
- `docs/_internal/ARCHITECTURE.md` — lifecycle / reconciler descriptions

Do NOT touch `$MERIDIAN_FS_DIR` — a separate @code-documenter spawn handles that. Do NOT touch CHANGELOG.

## What to add everywhere the old status set appears

The status enum `{queued, running, succeeded, failed, cancelled}` is now `{queued, running, finalizing, succeeded, failed, cancelled}`. `finalizing` means harness has exited and the spawn is draining output / emitting its report — not yet terminal but no new work will happen. Spawns can be reaped from `finalizing` as `orphan_finalization` (distinct from the older `orphan_run`) if heartbeat goes stale during that window.

## What to add to troubleshooting / architecture

1. **`finalizing` is an active state.** It shows up in `spawn list` / `work` dashboards and counts as in-flight. Users may briefly see it between harness exit and final report.
2. **New orphan classification.** `orphan_finalization` (reaped during drain/report emission) vs `orphan_run` (reaped mid-execution). Both indicate the harness process is gone; `orphan_finalization` specifically means it crashed after exit but before the runner finished post-processing. Troubleshooting path is the same — inspect `stderr.log` / `report.md` if partial.
3. **Authority rule / late runner correction.** If the reaper stamps a spawn as orphaned and the runner *then* completes (e.g. harness was slow, not dead), the runner's authoritative terminal state overwrites the orphan stamp. So a spawn briefly listed as orphaned that later shows `succeeded` is not a bug — it's the projection-authority rule working. Runner/launcher/cancel reports are authoritative; reconciler reports are not.
4. **Heartbeat window 120s.** Reaper waits for 120s of missed heartbeat before classifying a spawn as orphaned. Startup grace 15s. PID-reuse margin 30s (protects against a PID being reassigned to another process and misread as still-alive).

## Context & reference files

- `src/meridian/lib/core/spawn_lifecycle.py` — canonical state enum
- `src/meridian/lib/state/reaper.py` — classifications, gates, authority
- `src/meridian/lib/state/spawn_store.py` — finalize/authority mechanics
- `src/meridian/lib/launch/runner.py` — heartbeat, mark_finalizing
- `.meridian/work-archive/orphan-run-reaper-fix/decisions.md` — rationale

## Output requirements

- Keep user-facing tone. No implementation jargon (e.g. avoid talking about `SpawnOrigin` enum members directly — describe the behavior as "runner reports beat reconciler reports"). `AUTHORITATIVE_ORIGINS` is internal; the user-visible story is "the process that actually ran the work has final say".
- Preserve existing structure. Revise in place — don't add whole new sections unless the existing structure has no home for the new material.
- Update status enumerations consistently across all four files.
- Do not touch CHANGELOG. Do not run git — orchestrator handles commits.
