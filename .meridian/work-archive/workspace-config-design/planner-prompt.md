# Planner — R06 Launch Composition Refactor

## Task

Produce the complete implementation plan for **R06 — Consolidate launch composition into a typed pipeline** in the `workspace-config-design` work item. R06 is the entire scope of this planning cycle; out-of-scope are the background-worker `disallowed_tools` bug and Issue #34 Popen-fallback session-ID (both unblocked by R06 but not part of it).

The design package is approved and convergence-3 reviewed (see `reviews/r06-redesign-convergence-3.md`). Two convergence-3 minor inconsistencies have been resolved in the Explore phase: `LaunchRuntime` uses **frozen pydantic model** (not `@dataclass`), and `CompositionWarning.detail` is `dict[str, str] | None`. See `plan/pre-planning-notes.md` for the full Explore output including verified call-site line numbers, latent risks, and a leaf-distribution hypothesis.

## Inputs you must read

1. `requirements.md` — user intent and constraints for the umbrella work item
2. `decisions.md` — D1–D20 reasoning log (D17 hexagonal core, D19 typed pipeline, D20 convergence-2 DTO completeness)
3. `design/refactors.md` — R06 section is the sequencing authority (phased scope, 15 behavioral tests, pipeline stage ownership, DTO reshape)
4. `design/architecture/launch-core.md` (A06) — target pipeline order, type ladder, single-owner table, driving-adapter prohibition list
5. `design/architecture/harness-integration.md` (A04) — driven-port shape, per-adapter `observe_session_id`, workspace-projection seam
6. `design/architecture/overview.md` — module boundaries
7. `design/launch-composition-invariant.md` — the 10 invariants (I-1..I-10) that the CI drift-gate reviewer enforces
8. `design/feasibility.md` — probe evidence
9. `reviews/r06-redesign-convergence-3.md` — closing reviewer verdict (ready-with-minor-followups, both minors resolved in Explore)
10. `plan/pre-planning-notes.md` — Explore output with verified call-site evidence, latent risks, leaf-distribution hypothesis

## Deliverables

Produce the following artifacts under `plan/`:

### `plan/overview.md`

- **Parallelism posture**: sequential vs parallel rounds, and the cause. R06 is structurally coupled (factory signature change cascades to every driver), so most of it will be sequential. Identify any safely-parallelizable tail (e.g., driven-port cleanup + invariant-file copy + CI drift-gate add).
- **Round definitions** with per-round justification (what must land before the next round is safe).
- **Refactor handling**: map the 10-phase hypothesis from `pre-planning-notes.md` → rounds. Refine phase boundaries if Explore findings justify it; justify any deviation from the hypothesis.
- **Mermaid fanout** diagram matching the textual rounds.
- **Staffing section** concrete enough that the execution impl-orch can spawn workers directly: per-phase @coder + tester lanes (@verifier baseline; @smoke-tester at integration boundaries and at shipping; @unit-tester for specific behavioral guards per the 15 tests in refactors.md).

### `plan/phase-N-<slug>.md` (one per phase)

Each blueprint includes:
- **Scope and boundaries** — what is done, what is explicitly deferred
- **Touched files/modules** (with absolute paths like `src/meridian/lib/launch/context.py`)
- **Claimed behavioral test IDs** — R06 uses behavioral-test ownership rather than EARS statement IDs (spec leaves are umbrella-level for workspace config, not per-R06-phase). Use the 15 tests declared in `refactors.md` R06 §Behavioral tests as ownership anchors. Each phase must claim at least one testable outcome.
- **Touched refactor IDs** (R06 is the only refactor here, but note any prep that unblocks subsequent refactors)
- **Dependencies** — which earlier phases must close first
- **Tester lane assignment** — which tester(s) run after @coder closes
- **Exit criteria** — specific, verifiable: file paths exist/don't exist, imports land, tests pass, invariant prompt applies cleanly
- **Invariant IDs touched** (I-1..I-10) for awareness; CI drift-gate runs in phase 9 but all phases must not regress prior invariants

### `plan/leaf-ownership.md`

One row per behavioral test ID from `refactors.md` R06 §Behavioral tests. Columns: Test ID | Description | Owning phase | Tester lane | Evidence pointer (seeded empty). Use the 15-test → phase mapping from `pre-planning-notes.md` as the starting draft; refine where Explore evidence contradicts.

### `plan/status.md`

Phase lifecycle ground truth. Seed every phase as `pending`. Include a top section for run-level status (planning complete, phase-1 in progress, etc.).

## Hard constraints

- **Do not create new design artifacts.** Planning is downstream of design; if you find a design gap, terminate with `probe-request` or `structural-blocking`, do not patch design docs.
- **R06 phase boundaries must preserve safety** — the factory signature change cascades across drivers. A plan that parallelizes driver rewrites before the factory is stable is unsafe; terminate with `structural-blocking` + Redesign Brief if you find coupling you cannot decouple.
- **Single source of truth for the 15 behavioral tests** — the canonical list is in `refactors.md` R06 §Behavioral tests. Do not invent new test IDs; you may reference supporting unit tests per phase, but the 15 are the verification contract.
- **The convergence-3 minors are resolved** — do not re-raise `LaunchRuntime` type family or `CompositionWarning.detail` nullability. Explore chose pydantic-frozen and `dict[str, str] | None`.
- **Deletions are explicit phases or part of a phase** — `scripts/check-launch-invariants.sh`, `cli/streaming_serve.py`, `launch/session_ids.py`, `PreparedSpawnPlan`, `ExecutionPolicy`, top-level `SessionContinuation`, `ResolvedPrimaryLaunchPlan`, user-facing `SpawnParams` all must land in specific phases with explicit ownership.

## Terminal states

- **plan-ready** — all four artifact groups written and internally consistent. Your terminal report lists the plan files and confirms the sequencing cause.
- **probe-request** — you need runtime evidence the Explore phase did not gather. List specifically which probes and why.
- **structural-blocking** — the design forces an unsafe sequential coupling that prevents any safe plan. Terminate with a Redesign Brief section (status, evidence, falsification, blast radius, constraints discovered, why decomposition cannot safely parallelize).

## Format for terminal report

```
## Terminal state
<plan-ready | probe-request | structural-blocking>

## Plan files written
- plan/overview.md
- plan/phase-1-<slug>.md
- ...

## Sequencing cause
<one-paragraph justification of the parallelism posture — why sequential, where parallel>

## Judgment calls
<any phase-boundary refinements from the 10-hypothesis, with reasoning>

## Handoff notes for execution impl-orch
<specific things the executor must know that are not obvious from the plan files>
```

Work directory is `$MERIDIAN_WORK_DIR` — paths in plan artifacts should use that prefix or repo-relative paths (`src/meridian/...`) as appropriate.
