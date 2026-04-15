# Task: Plan the Spawn Control Plane Redesign

You are planning the implementation of a spawn control plane redesign for meridian-cli. The design package is complete and approved. Your job is to decompose it into executable phases with proper parallelism.

## Design Package Location

All design artifacts are at `$MERIDIAN_WORK_DIR/design/`:
- `spec/` — EARS behavioral contract (cancel, interrupt, inject, liveness, http_surface, authorization)
- `architecture/` — technical realization (cancel_pipeline, interrupt_pipeline, inject_serialization, liveness_contract, http_endpoints, authorization_guard)
- `refactors.md` — R-01..R-11 structural agenda with phase hints
- `feasibility.md` — all probes verified

Also read:
- `$MERIDIAN_WORK_DIR/requirements.md` — problem statement and success criteria
- `$MERIDIAN_WORK_DIR/decisions.md` — D-01..D-24 design decisions
- `$MERIDIAN_WORK_DIR/plan/pre-planning-notes.md` — impl-orch runtime observations

## Hard Constraints

1. **R-08 (AuthorizationGuard) lands BEFORE R-05 and R-09** — no lifecycle surface exposed ungated.
2. **R-10 (AF_UNIX) lands BEFORE R-08** — auth's HTTP path needs AF_UNIX for SO_PEERCRED.
3. **R-09 (HTTP cancel dispatch) BEFORE R-03** — two-lane cancel needs the cross-process HTTP path.
4. **No SIGKILL (D-13)** — removed from pipeline entirely.
5. **Peercred fail-closed (D-19)** — DENY on extraction failure, not operator.
6. **Two-lane cancel (D-03)** — SIGTERM for CLI spawns, in-process for app spawns.
7. **AF_UNIX transport (D-18)** — app server on Unix socket.

## Parallelism Requirements

The design's refactors.md already has phase hints. Key insight:
- Phase A (R-01, R-02, R-11) is pure foundation — new files, no behavioral risk.
- Phase D (R-04, classifier) is independent of B/C.
- Phase F (R-07, liveness) depends on A + R-11 only, not on B/C.
- B, D, F can run in parallel after A completes.
- C requires B (auth before lifecycle surfaces).
- E requires B + C (HTTP surface needs auth + cancel pipeline).

This naturally decomposes into 4 rounds with 3 parallel phases in round 2. The plan MUST exploit this parallelism — sequential execution of independent phases would be rejected.

## Integration Phase Smoke Testing

Every phase that touches an integration boundary (AF_UNIX socket, SIGTERM signals, control-socket protocol change) MUST have @smoke-tester assigned. Specifically:
- Phase B (AF_UNIX transport) — smoke test the socket binding
- Phase C (cancel pipeline) — smoke test SIGTERM handling
- Phase E (HTTP surface) — smoke test HTTP endpoints via AF_UNIX

## What to Produce

Write all plan artifacts per the dev-artifacts contract:
- `plan/overview.md` — parallelism posture, rounds, refactor mapping, mermaid fanout, staffing
- `plan/phase-N-<slug>.md` — one per phase with scope, EARS claims, exit criteria
- `plan/leaf-ownership.md` — one row per spec EARS statement ID with exclusive phase ownership
- `plan/status.md` — initial phase lifecycle state

Ensure every EARS statement ID from the spec tree is assigned to exactly one phase in leaf-ownership.md. No gaps, no overlaps.
