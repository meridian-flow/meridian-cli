# Plan Status

Regenerated remaining-phase status for `workspace-config-design`.

Run-level note:

- This regenerated plan supersedes the prior remaining-phase snapshot that
  assumed a clean R02 handoff.
- Remaining execution should start from the new phase sequence below, not from
  the deleted `phase-2-config-bootstrap-rewire` / `phase-4-harness-projection-and-applicability`
  plan files.

| Item | Type | State | Depends on | Notes |
|---|---|---|---|---|
| Regenerated remaining-phase plan (2026-04-16) | planning | `complete` | none | Live-repo refresh after corrected handoff; this is now the planning authority for the remaining scope. |
| [phase-1-config-surface-convergence.md](phase-1-config-surface-convergence.md) | implementation | `complete` | none | Closes residual R02 carryover and establishes the shared config/workspace surface builder. |
| [phase-2-workspace-model-and-inspection.md](phase-2-workspace-model-and-inspection.md) | implementation | `pending` | phase 1 | Adds the workspace file model, `workspace init`, config/doctor surfacing, and invalid-workspace command gating. |
| [phase-3-launch-projection-and-applicability.md](phase-3-launch-projection-and-applicability.md) | implementation | `pending` | phase 2 | Projects ordered roots through the harness seam and lands explicit applicability diagnostics. |
| Final review loop | review | `pending` | phases 1-3 | GPT reviewer fan-out plus `@refactor-reviewer`, then fix and retest to convergence. |
