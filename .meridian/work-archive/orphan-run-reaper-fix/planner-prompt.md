# Planner — orphan-run reaper fix, Round 2

Approved design package is on disk. Produce the execution plan per the `planning` skill contract: phases, parallelism posture, leaf ownership, mermaid fanout, staffing. Emit plan-ready, probe-request, or structural-blocking.

## What you have

- `requirements.md` — user intent, success criteria
- `decisions.md` — D-1..D-20 including the Round 2 F1–F8 resolutions
- `design/spec/overview.md` — S-LC-*, S-RN-*, S-RP-*, S-PR-*, S-CF-*, S-OB-*, S-BF-* EARS leaves
- `design/architecture/overview.md` — realization details, writer map, CAS protocol, projection code sketch
- `design/refactors.md` — R-01..R-09, including scope fences and sequencing hint
- `design/feasibility.md` — probe evidence P1–P7 and F-finding verdicts
- `plan/preservation-hint.md` — Round 1 → Round 2 carry-over
- `plan/pre-planning-notes.md` — execution impl-orch runtime observations (read carefully — sequencing hypothesis, sandbox discipline, backfill test mandate, concurrency smoke requirements)
- `plan/status.md` does not yet exist — you create it.

## Mandatory deliverables

1. `plan/overview.md` — parallelism posture, rounds with justification, refactor mapping, mermaid fanout, staffing concrete enough to spawn from.
2. `plan/phase-N-<slug>.md` — one per phase. Each must list: claimed EARS statement IDs (from spec), touched refactor IDs, touched files, dependencies, tester lane assignment, exit criteria.
3. `plan/leaf-ownership.md` — one row per EARS statement, exclusive phase ownership. Empty tester/evidence columns (execution fills).
4. `plan/status.md` — initial row per phase with state `pending`.

## Hard constraints

- **Two-PR split is the preferred structure** (per pre-planning-notes and refactors.md §Sequencing). If you can honor it without creating coupling hazards, do. If you can't, explain in `decisions.md` before emitting plan-ready.
- **Concurrency-sensitive phases (R-03 CAS, R-06 heartbeat) must carry @smoke-tester + @unit-tester in staffing** — not just @verifier.
- **Backfill self-repair phase must claim S-BF-001** and include a unit test that asserts current `.meridian/spawns.jsonl` rows `p1711`, `p1712`, `p1731`, `p1732` project to `succeeded` under the new rule.
- **Respect the scope fences** in refactors.md §"What is explicitly not in scope". Phases that try to extend `finalizing` to non-runner terminal writers or rewrite `is_process_alive` constitute structural-blocking.
- **Every R-01..R-09 covered.** R-08 is the only intentionally-deferred refactor; include it in the plan as a deferred item with the removal trigger called out.
- **If you detect that the design is internally inconsistent or a leaf is unverifiable**, emit `structural-blocking` with a Redesign Brief.
- **If you need probes** (you shouldn't — feasibility is fresh), emit `probe-request` with exact commands.

## Parallelism posture

The pre-planning-notes hypothesis: R-01 first (status + consumer audit foundation) → R-02 + R-04-remainder in parallel → R-03 + R-07 sequentially after R-02 lands → R-06 can run in PR1 independently of PR2 schema work → R-09 piggybacks on R-01. Validate or revise this.

## Exit

Emit terminal report with one of `plan-ready | probe-request | structural-blocking`. If plan-ready, list the phase files you created.
