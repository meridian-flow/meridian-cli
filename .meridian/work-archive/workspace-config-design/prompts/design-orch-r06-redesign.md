# R06 Redesign — Design Orchestrator Cycle

## Context

R06 ("Consolidate launch composition into a hexagonal core") is the lynchpin refactor in `workspace-config-design` — it blocks R05 and is the structural foundation that R01/R02 downstream will depend on. The existing R06 design shipped a skeleton: the factory + LaunchContext sum type + three-driver rewire + bypass handling landed in commits `3f8ad4c..efad4c0` plus post-ship fixes `adea3ff` (bypass scope) and `45d18d7` (dry-run bypass preview).

A recent review cycle (reports attached) confirmed that the skeleton is structurally incomplete — composition still lives in the driving adapters because the factory's input DTO (`PreparedSpawnPlan.ExecutionPolicy`) carries the already-resolved outputs of `resolve_policies` + `resolve_permission_pipeline`. The rest of R06's Fix list (fork-ordering, `observe_session_id` wiring, CI invariants completeness) is similarly reshaped by that central DTO issue.

Your job is a **redesign cycle** that produces an honest, buildable R06 — not a patch.

## Convergence from the Reviewer Cycle

Four reviewers agreed on the shape of the redesign at different resolutions:

- **DTO reshape is the core**. Factory input should be raw request + overrides (sandbox, approval, profile, safety inputs), not pre-resolved `PermissionConfig`/`PermissionResolver`. Named variations: `UnresolvedPreparedPlan` + `ResolvedPreparedPlan` split, or `LaunchInputs` → `LaunchAttempt` pipeline shape — same prescription under different labels.
- **Pipeline staged functions as the inner shape**. Whether the outer label is "hexagonal" or "3 drivers + harness port + 2 executors," the load-bearing inside structure is a typed pipeline of stages (resolve policy → build permissions → build env → build command/spec → materialize fork → attach session observer) with one clear input type before composition and one clear attempt type after.
- **Kill the placeholder modules**. `launch/permissions.py`, `launch/policies.py`, `launch/runner.py` are currently re-export-only shells. Either give each real stage ownership with logic + tests, or delete and let adjacent modules own the concern.
- **Collapse the type ladder**. One run currently has `LaunchRequest` + `SpawnRequest` (dead) + `SpawnParams` + `PreparedSpawnPlan` + `ResolvedPrimaryLaunchPlan` + `LaunchContext` — six partial-truth DTOs. The redesign should name and justify exactly two or three types covering input / attempt / result.
- **Driven port cleanup**. Move concrete permission-flag projection out of `src/meridian/lib/harness/adapter.py` (the port contract module) into the driven adapters themselves. A port describes the contract; mechanism belongs in the adapters.
- **Single-owner constraints**. Bypass dispatch lives in exactly one place (currently split between `launch/__init__.py` and `launch/context.py`). Fork materialization has exactly one owner. `observe_session_id` has concrete implementations per driven adapter and one observation path from the executor.
- **Fork-ordering blocker (D4)**. `src/meridian/lib/ops/spawn/prepare.py:296` forks before spawn/session rows exist — orphan-fork window on any later failure. The redesign must specify the launch transaction: fork materialization happens only after rows exist, inside the factory, with atomic rollback or provenance marker on failure. Related ordering concerns D5-D7, D10.

## Verification Approach Change

R06's original exit criteria were written as `rg X → N matches` counts enforced by `scripts/check-launch-invariants.sh`. That verification shape was heuristic by design and declared explicitly in the prior refactors.md. The redesign replaces it with:

- **`@reviewer` as architectural drift gate** — CI-spawned reviewer reads the diff against a declared-invariant prompt living at `.meridian/invariants/launch-composition-invariant.md` (or similar), pass/fail verdict with file:line violations, blocks merge on fail. See `agent-staffing` skill → "@reviewer as Architectural Drift Gate".
- **Deterministic behavioral factory tests as backstop** — constructors for the redesigned factory input DTO should be usable directly in tests: `ctx = build_launch_context(...)`, assert output reflects the input. The tests pin down the specific invariants that must not drift; the reviewer catches novel violations of the declared intent.
- **pyright + ruff + pytest remain the correctness gate.**
- **Delete `scripts/check-launch-invariants.sh`** as part of R06.

The design should specify which invariants become behavioral tests (priority list), what the declared-invariant prompt asserts, and how the CI workflow spawns the reviewer.

## What Not to Rewrite

Do not second-guess these — the prior cycle's convergence is strong:

- The 3 driving adapters + 1 driven port + 2 executors top-level framing stays.
- The `LaunchContext` sum type (`NormalLaunchContext | BypassLaunchContext`) stays; it's the right executor seam.
- Fork is a real side-effect stage, not a pure-pipeline idealization — treat it as such in the new design, with explicit ordering and one owner.
- `SpawnRequest` as the user-facing DTO stays as a concept; currently dead because flow never adopted it — redesign must make it load-bearing.

## Outputs Expected

A full design package at `.meridian/work/workspace-config-design/design/` with:

1. **`design/refactors.md`** — rewrite the R06 section (preserve R01-R05, R07+ sections unchanged). New R06 covers: DTO reshape, pipeline stages with explicit names and signatures, placeholder-module decisions (delete/keep+own each), type-ladder collapse (name the 2-3 types that survive), driven-port cleanup, single-owner constraints, fork-transaction ordering, verification approach.
2. **`design/architecture/launch.md`** (or similar) — the architecture tree for launch, updated to match the new R06 direction. Describe the technical realization observationally. Each driving adapter's composition call becomes a thin factory invocation. Each driven adapter's contract narrowed to pure translation (no mechanism leak).
3. **`design/spec/`** — if the user-facing behavior contract changes, update the EARS leaves. Most of R06 is structural, so spec may be unchanged — verify.
4. **`design/feasibility.md`** — re-run probes for anything the redesign changes. At minimum: confirm the DTO reshape is viable (the reviewer convergence says yes, but validate with a concrete probe or targeted code read).
5. **`decisions.md`** — append entries for each major redesign choice with reasoning, alternatives considered, and why this option won. See `decision-log` skill.

## Staffing Expectations

Design-orch normally spawns architects + reviewers. Use default profile models and `meridian models list` to inform model choice. One design-alignment reviewer is mandatory in the final convergence round; bring in a second reviewer on a different model for the high-risk DTO-shape call specifically.

## Work Item

Continue on `workspace-config-design` (active, has all prior context, reviews, decisions). Do not create a new work item.

## Termination

Terminal report should summarize the redesign direction, key decisions, and point at the updated design artifacts. Dev-orch will review with the user before routing to impl-orch for the (now Explore-gated) implementation cycle.
