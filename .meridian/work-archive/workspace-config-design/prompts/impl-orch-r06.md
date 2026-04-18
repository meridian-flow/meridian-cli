# R06 Implementation — Impl-Orchestrator Cycle

## Context

You are implementing **R06** (Consolidate launch composition into a hexagonal core) for the `workspace-config-design` work item. R06 is the lynchpin refactor — R05, R03, and downstream R01/R02 all depend on it landing correctly.

This is not a fresh cycle. A prior R06 attempt landed a skeleton (commits `3f8ad4c..efad4c0` + post-ship fixes `adea3ff` + `45d18d7`) but composition stayed in the driving adapters because the factory's input DTO shape blocked it. A four-reviewer retry cycle (reports at `reviews/r06-retry-*.md`) plus a full design-orchestrator redesign cycle (p1936 → convergence-2 → convergence-3 at p1939 + architect closure at p1940) produced the current design.

The design is implementation-ready per convergence-3 verdict `ready-with-minor-followups` plus the architect's closure of all 3 followups.

## Design Package (read in this order)

1. **`.meridian/work/workspace-config-design/requirements.md`** — user intent and constraints
2. **`decisions.md`** — reasoning history; **D17, D19, and D20** are the R06-relevant entries. D20 explains why the DTO reshape happened and what load-bearing constraints are enforced.
3. **`design/refactors.md` R06 section** — the refactor agenda, phased scope, exit criteria, verification specification
4. **`design/architecture/launch-core.md`** (A06) — target shape: factory signature, pipeline stages, single-owner constraints, type ladder, driving/driven-adapter responsibilities, fork transaction ordering, verification triad
5. **`design/architecture/harness-integration.md`** (A04) — harness projection composition contract; updated in convergence-3 to align observe-session-id wording
6. **`design/architecture/overview.md`** — where A06 sits in the broader architecture tree
7. **`design/launch-composition-invariant.md`** — the CI drift-gate reviewer prompt, 10 numbered invariants. **Copied verbatim to `.meridian/invariants/launch-composition-invariant.md` during implementation.**
8. **`design/feasibility.md`** — probe evidence and validated assumptions. FV-11 is R06-relevant (worker prepare→execute re-resolution semantics). FV-12 is R06-relevant (the reviewer-as-drift-gate verification pattern).
9. **Reviewer reports** — `reviews/r06-redesign-convergence-3.md` (latest + has 3 top Explore-phase checks), `reviews/r06-redesign-alignment.md`, `reviews/r06-redesign-dto-shape.md` (prior convergence-2), `reviews/r06-retry-*.md` (original retry cycle that diagnosed the DTO barrier)

## Scope

**R06 only**. R01, R02, R03, R05, R07+ are preserved — do not touch them.

Out-of-scope but structurally unblocked by R06 (track separately as follow-up work items, do not fold in):
- Background-worker `disallowed_tools` correctness (now first-class on `SpawnRequest`)
- Issue #34 Popen-fallback session-ID observation (the `observe_session_id()` seam is in place; mechanism swap is separate)

## Explore Phase — Required Before Planning

Your profile's Explore phase is a gate, not a preamble. Produce `plan/pre-planning-notes.md` with the required fields before any planner spawn. The convergence-3 reviewer pre-identified the top 3 Explore-phase checks:

1. **Verify the driving-adapter prohibition list against real call sites.** Run the invariant-prompt I-2 grep list against HEAD — every one of `resolve_policies`, `resolve_permission_pipeline`, `TieredPermissionResolver`, `UnsafeNoOpPermissionResolver`, `adapter.resolve_launch_spec`, `adapter.project_workspace`, `adapter.build_command`, `adapter.fork_session`, `adapter.seed_session`, `adapter.filter_launch_content`, `build_harness_child_env`, `extract_latest_session_id` — in `launch/plan.py`, `launch/process.py`, `ops/spawn/prepare.py`, `ops/spawn/execute.py`, `app/server.py`, `cli/streaming_serve.py`. Confirm no missed callsites invalidate the prohibition list before implementation begins.

2. **Verify fork-after-row preconditions at existing call sites.** Read current `launch/process.py:~306` (spawn-row creation) and `:~328` (factory call) to confirm the ordering already holds on the primary path. Inspect `launch/streaming_runner.py` fallback (`execute_with_streaming`) for the current create-row-mid-flight path D7 flagged — that becomes a precondition-error path, not pass-through. Catch shape surprises before phase 1 starts.

3. **Verify `LaunchRuntime` field set is complete against live driver state.** Walk each driving adapter — primary (`launch/plan.py`, `launch/process.py`), worker prepare (`ops/spawn/prepare.py`), worker execute (`ops/spawn/execute.py`), app streaming (`app/server.py`), `cli/streaming_serve.py` — and cross-check every runtime-injected non-user-input field reaching today's `SpawnParams`/`PreparedSpawnPlan` against the 7 fields declared on `LaunchRuntime`. Any leftover field (debug telemetry hooks, depth markers, control-socket handles) not on `LaunchRuntime` and not factory-derivable is a missed schema entry.

Additional Explore-phase verifications worth running:

- **A04/A06 cross-reference integrity** — the workspace-projection seam (A04) must be reachable inside the A06 pipeline ordering. Verify the names match.
- **FV-11 worker re-resolution semantics** — declared behavior-preserving by inspection in D20 but not probe-validated. Consider a scoped probe: compare today's `execute.py:861` resolver-reconstruction output against what `build_launch_context()` would produce from persisted `SpawnRequest` for a representative test case. If they diverge, flag.
- **Incidental inconsistency flagged by convergence-3 architect:** `report_output_path: Path` at `refactors.md:318` vs `str | None` at `launch-core.md:167`. Invariant I-5 forbids `Path` fields on persisted DTOs — verify which spelling is correct against the implementation, note in pre-planning-notes.

Terminate `explore-falsified` and emit a Redesign Brief if any design claim is contradicted by code reality. This is the cheapest redesign trigger — catch it here, not in planning or build.

## Verification Approach

The verification triad replaces `scripts/check-launch-invariants.sh` (which gets deleted as part of R06):

1. **Behavioral factory tests** at `tests/launch/test_launch_factory.py`. Five new tests specified in `refactors.md` R06 verification section: `test_child_cwd_not_created_before_spawn_row`, `test_composition_warnings_propagate_to_launch_context`, `test_workspace_projection_seam_reachable`, `test_unsafe_no_permissions_dispatches_through_factory`, `test_session_request_carries_all_eight_continuation_fields`. Plus whatever R06 originally specified.

2. **CI architectural drift gate** — `meridian spawn -a reviewer` on PRs touching `src/meridian/lib/(launch|harness|ops/spawn|app)/` or `src/meridian/cli/streaming_serve.py`. Reads the declared-invariant prompt at `.meridian/invariants/launch-composition-invariant.md` (copied verbatim from `design/launch-composition-invariant.md` during R06 implementation, kept in sync as architecture legitimately changes). Returns `pass`/`fail` + violations JSON. CI blocks merge on `fail`. Per `agent-staffing` skill guidance, use a cheaper model (mini/flash) for routine drift detection, escalate for PRs that materially restructure the surface.

3. **pyright + ruff + pytest** — correctness gate alongside.

## Deletions Part of R06

- `scripts/check-launch-invariants.sh` and its `meridian-ci.yml` step
- `src/meridian/cli/streaming_serve.py` (driver collapses into app-streaming)
- `src/meridian/lib/launch/session_ids.py` (observation moves to per-adapter `observe_session_id()`)
- Inline session-id extraction paths in `launch/process.py` and `launch/streaming_runner.py`
- `extract_latest_session_id()` function
- Bypass-dispatch duplicates in `launch/__init__.py:65-77` and `launch/command.py:53`
- Stage-module placeholders (`launch/policies.py`, `launch/permissions.py`, `launch/runner.py`) become owned modules with real logic, not re-export shells

## Phases

The design specifies the phased scope in `refactors.md` R06. Hold that as the sequencing authority for planning — you (or the planner) may refine phase boundaries based on Explore findings, but the overall decomposition is in the design.

## Shipping

- Smoke test required before anything ships. Real CLI invocations, real harness launches against Claude / Codex / OpenCode. Not mocks, not fixtures.
- Final review loop before ship: `@reviewer` fan-out across focus areas (design-alignment, correctness, structural via `@refactor-reviewer`). Model diversity through provider mix per `agent-staffing`.
- Update `plan/status.md` as phases close. Record each major judgment call in `decisions.md` (append-only, caveman full).

## Terminal Report

On success: what was built, what passed, what's deferred, judgment calls made during execution.

On Redesign Brief: per profile — status (design-problem / scope-problem), trigger point (explore / plan / build / re-verify), evidence with code pointers, falsification statement, blast radius, constraints discovered.
