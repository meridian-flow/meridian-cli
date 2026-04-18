# R06 Implementation Plan — Hexagonal Launch Core

## Parallelism Posture: Sequential (by design)

R06 phases have structural coupling — each phase builds on the types and APIs introduced by its predecessor. The design's suggested 8-phase decomposition is the right granularity. Phases 1 and 2 are independent of each other and could be parallelized, but the remaining phases must be sequential.

**However**, phases 1+2 are small enough (~2 files each, DTO-only changes) that parallelizing them saves minimal wall time vs. the coordination overhead. All phases execute sequentially.

## Phase summary

| Phase | Scope | Exit criteria subset |
|-------|-------|---------------------|
| 1 | SpawnRequest/SpawnParams split | `rg "^class SpawnRequest\b" src/` → 1 match; SpawnParams not constructed outside factory |
| 2 | RuntimeContext unification | `rg "^class RuntimeContext\b" src/` → 1 match |
| 3 | Domain core: factory + LaunchContext sum type + pipeline stages + LaunchResult/LaunchOutcome + observe_session_id adapter seam | All pipeline builder checks, sum type checks, adapter boundary checks |
| 4 | Rewire primary launch through factory | Primary launch calls build_launch_context() |
| 5 | Rewire background worker through factory | Worker calls build_launch_context() |
| 6 | Rewire app streaming HTTP through factory | App server calls build_launch_context() |
| 7 | Deletions: run_streaming_spawn + SpawnManager fallback + streaming_serve rewire | `rg "run_streaming_spawn"` → 0; `rg "UnsafeNoOpPermissionResolver" streaming/` → 0 |
| 8 | MERIDIAN_HARNESS_COMMAND bypass into factory + CI invariants script + pyright hardening | All remaining exit criteria |

## Staffing

- **Coder**: gpt-5.3-codex (per CLAUDE.md preference)
- **Verifier**: baseline every phase (pyright + ruff + pytest)
- **Smoke-tester**: phases 4-8 (when actual launch behavior could change)
- **Reviewers**: final review loop only — fan out across gpt-5.4, gpt-5.2, opus with different focus areas

## Commit strategy

One commit per phase. Each phase must leave the tree green (pyright 0 errors, ruff clean, pytest passing).
