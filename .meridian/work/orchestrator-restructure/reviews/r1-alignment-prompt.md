# Review request: orchestrator-restructure design v2 — alignment and reversal coherence

You are reviewing the **second draft** of a design package that restructures the dev-workflow orchestration topology in this repo. The first draft (v1) made one decision the user has now reversed, and the rest of the package has been updated to reflect the reversal. Your job is to verify the v2 draft is internally consistent end-to-end and that the reversal hangs together coherently.

## Context: what changed v1 → v2

**v1 deleted @planner entirely** and folded planning into impl-orchestrator's own context as a "self-planning first phase." The planning skill was rehomed onto impl-orch.

**v2 keeps @planner as a separate agent** but rehomes its caller — dev-orch no longer spawns @planner directly. Impl-orch is now the caller. Impl-orch runs a pre-planning step in its own context (gathering runtime data via probes, dependency walks, file scans), writes the runtime observations to `plan/pre-planning-notes.md`, then spawns @planner with the design + Terrain + pre-planning notes attached. Impl-orch waits for the plan to materialize, then reports back to dev-orch for the plan review checkpoint.

**Two new emphases were also added in v2:**
- **Parallelism-first decomposition** is now @planner's central frame. Structural refactors land first, feature phases on disjoint modules then run in parallel.
- **Structure and modularity** are now first-class design-phase concerns, with a structural/refactor reviewer mandatory in design-phase fan-out.

## What to read

Read every file in `$MERIDIAN_WORK_DIR/design/` plus `$MERIDIAN_WORK_DIR/decisions.md`:

- `design/overview.md` — topology orientation
- `design/dev-orchestrator.md` — dev-orch body
- `design/design-orchestrator.md` — design-orch body with Terrain section requirements
- `design/impl-orchestrator.md` — impl-orch body with pre-planning + planner spawn + escape hatch
- `design/planner.md` — **new in v2** — the rehomed planner agent
- `design/feasibility-questions.md` — shared skill design
- `design/redesign-brief.md` — escape hatch artifact format
- `decisions.md` — D1 and D3 are revised, D10 and D11 are new

## What to check

This is a design-alignment review with a focus on the reversal hanging together. Specifically:

1. **End-to-end topology coherence.** Trace the lifecycle from "user approves a direction" through design → pre-planning → planner spawn → plan review → execution → (optional bail-out) → autonomous redesign cycle. Does the chain of spawns and handoffs make sense at every link? Are there any places where an agent receives or produces something that doesn't match what its caller or callee expects?

2. **Cross-doc consistency.** Pay attention to whether every doc tells the same story. For example: does dev-orchestrator.md correctly say "dev-orch does NOT spawn @planner" while impl-orchestrator.md says "impl-orch spawns @planner" while planner.md says "the caller is impl-orch"? Did anything in the v1 wording survive that contradicts the v2 direction (e.g. references to "self-planning in-context", "deleted planner", etc.)?

3. **Decision log coverage.** D1 in decisions.md is the reversed decision. Does it capture the full reasoning for the reversal, the v1 alternative as rejected, and the rationale for why the new shape solves the original v1 motivation without creating a new problem? D3 was also revised — does it match D1's reversal? D10 and D11 are new — are they grounded in the design docs or just floating decisions?

4. **The "what is deleted" / "what is added" lists.** Each component doc has these sections. Are they accurate to v2, or do they still carry v1 wording (e.g. "@planner agent profile is deleted")?

5. **The pre-planning step is the key new piece.** Does impl-orchestrator.md describe it well enough that an impl-orch could actually run it? Is the artifact format for `plan/pre-planning-notes.md` clear enough? Does planner.md describe what the planner consumes from those notes?

6. **The runtime-context argument.** The v1 motivation was "planners can't have runtime knowledge so plans go stale." The v2 fix is "impl-orch gathers runtime data first, then passes it to @planner via -f." Does the v2 design actually solve the original problem, or does it just push it around? Be skeptical here.

7. **Anything missed.** Anything you think a reasonable reader would expect to find in this design package and doesn't, or anything you think shouldn't be there.

## How to report

Severity-tagged findings (CRITICAL / HIGH / MEDIUM / LOW). For each finding:

- **Where**: file and section
- **What**: the specific issue
- **Why it matters**: the consequence if shipped as-is
- **Suggested fix**: concrete change

Be adversarial. The user has explicitly flagged that the reversal needs cross-model scrutiny. Findings that say "this is fine" with no caveats are less useful than findings that probe at the seams.

Return your findings as a single report. No file edits — read-only review.
