# Plan Status Seed — orphan-run reaper fix (Round 2)

| Phase | Round | PR | State | Depends on | Notes |
|---|---|---|---|---|---|
| `Phase 1 — defensive-reconciler-hardening` | `Round 1` | `PR1` | `pending` |  | Preventive, zero-schema path. |
| `Phase 2 — finalizing-status-foundation` | `Round 2` | `PR2` | `pending` | `Phase 1` | Core lifecycle source of truth for downstream work. |
| `Phase 3 — cli-and-model-surface` | `Round 3` | `PR2` | `pending` | `Phase 2` | Safe parallel lane with user-facing write set only. |
| `Phase 4 — origin-projection-backfill` | `Round 3` | `PR2` | `pending` | `Phase 2` | Safe parallel lane on state / writer surfaces. |
| `Phase 5 — finalizing-cas-and-reconciler` | `Round 4` | `PR2` | `pending` | `Phase 1`, `Phase 2`, `Phase 4` | Concurrency-sensitive closure phase. |

No implementation phase is preserved from Round 1. This redesign cycle starts
with all phases pending.
