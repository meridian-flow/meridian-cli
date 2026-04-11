# Review request: orchestrator-restructure design v2 — parallelism-first frame and decomposition sanity

You are reviewing the **second draft** of a design package that restructures the dev-workflow orchestration topology. Your specific focus is the **parallelism-first decomposition frame** for @planner that v2 introduced, and whether the new design actually delivers what it claims about decomposition quality.

You should also act as the adversarial check on the v1 → v2 reversal: did v2 lose any value v1 had? Are there blind spots in the new topology that the v1 deletion-of-planner approach would have caught?

## Context: what v2 says about @planner

The v1 draft deleted @planner entirely and folded planning into impl-orch's own context. The user reversed that call. The v2 keeps @planner as a separate agent and rehomes its caller (now impl-orch, was dev-orch). The user also explicitly sharpened @planner's central frame from "produce a plan" to **"decompose the work so as much as possible can run in parallel."**

The concrete shape:

- Structural refactors that touch many files land first as cross-cutting prep — these would create merge conflicts if they ran late, so getting them out of the way unlocks downstream parallelism.
- After structural prep lands, feature phases on disjoint modules run in parallel.
- Phase ordering is justified by what it unlocks for parallelism, not just by logical dependency. Two phases can be logically independent and still have to be sequenced because they share a test harness, registry, env vars, etc.

The `/planning` skill needs an emphasis shift downstream to make this the central frame. The design package names that shift as a follow-up but does not implement it.

## What to read

Read everything in `$MERIDIAN_WORK_DIR/design/` and `$MERIDIAN_WORK_DIR/decisions.md`, paying particular attention to:

- `design/planner.md` — **new in v2** — the rehomed planner agent doc
- `design/impl-orchestrator.md` — especially "Pre-planning as the first action" and "Spawning @planner" sections
- `design/overview.md` — especially "Why @planner stays but rehomes under impl-orch"
- `decisions.md` — D1 (the reversal), D3 (impl-orch pre-planning + planner spawn), D10 (parallelism-first central frame)

## What to check

1. **Is the parallelism-first frame actionable, or is it rhetoric?** The doc says decomposition decisions should be evaluated through the parallelism lens. What does that mean concretely for a planner running on a real design? Walk through a hypothetical scenario: a design with 8 features touching overlapping modules. What does parallelism-first decomposition produce? Is the answer obvious from `planner.md`, or would the planner just default to whatever decomposition it would have produced anyway?

2. **The "structural refactors land first" pattern.** This is the canonical move under the parallelism-first frame. But how does the planner actually identify which refactors are cross-cutting versus which are feature work? Does the design give the planner a heuristic, or is this just trusted to the planner's judgment? If trusted to judgment, is that strong enough?

3. **Does the planner have what it needs from impl-orch's pre-planning notes?** Trace the data flow from impl-orch's runtime probes through the pre-planning notes to the planner's decomposition output. Is there missing data the planner would need that the pre-planning step doesn't capture? Conversely, is the pre-planning step over-specified in ways that waste impl-orch effort on data the planner won't use?

4. **The two-cycle context split.** v2 has impl-orch do pre-planning in its own context, then spawn the planner in a fresh context. The argument is that decomposition and execution are different cognitive modes. Is this argument sound? What does the planner *gain* from a fresh context that justifies the spawn boundary, and what does it *lose* by not being co-located with impl-orch's runtime data? Be skeptical — the v1 draft explicitly argued the other direction.

5. **Re-spawning the planner.** The design says impl-orch can re-spawn the planner if the first plan is missing sections, references missing scenarios, or contradicts the pre-planning notes. The design also says dev-orch pushing back triggers a planner re-spawn. Is the re-spawn loop bounded? What prevents a pathological loop of impl-orch and the planner ping-ponging on a plan neither can write correctly?

6. **The runtime-context fix.** The whole point of the v2 reversal is that the planner now gets runtime context via impl-orch's pre-planning notes, where the v1-original-topology planner did not. Is the "runtime context as -f input" mechanism actually equivalent to "the agent has runtime context"? What kinds of runtime context are easily captured in a markdown notes file, and what kinds aren't? If something can't be captured, does it matter?

7. **What v1 (delete the planner) had that v2 doesn't.** The v1 draft argued that the handoff boundary was where context leaks without adding value. v2 reintroduces that boundary. Is the legibility-forcing argument (that materializing pre-planning notes is the value, not just a cost) actually compelling, or is it post-hoc justification for keeping the planner? Take a position.

8. **The follow-up `/planning` skill update.** The design names this as a follow-up but does not implement it. Is the follow-up well-scoped? Is there a risk that a planner spawn under the v2 topology runs against the old `/planning` skill body and produces a plan that doesn't match the parallelism-first frame? Should the design package mandate the skill update before any plan written under the new topology depends on it?

9. **Anti-pattern: claims of central framing without supporting infrastructure.** "Parallelism-first" is a claim. Does the rest of the design infrastructure (skill loadouts, agent staffing, blueprint format, scenario ownership) actually support that claim, or is it a single sentence in a body that doesn't change anything else?

## How to report

Severity-tagged findings (CRITICAL / HIGH / MEDIUM / LOW). For each finding:

- **Where**: file and section
- **What**: the specific issue
- **Why it matters**: the consequence if shipped as-is
- **Suggested fix**: concrete change

Be adversarial. The v1 → v2 reversal is a real direction change and the user explicitly wants cross-model scrutiny on whether v2 actually delivers what v1 was reaching for in a different way. A review that just says "the parallelism frame is good" without probing at how it would actually shape decomposition is not useful.

Return your findings as a single report. No file edits — read-only review.
