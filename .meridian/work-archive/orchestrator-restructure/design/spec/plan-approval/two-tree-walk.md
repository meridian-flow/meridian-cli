# S03.1: Two-tree approval walk

## Context

When design-orch converges and returns a design package, dev-orch walks the user through it before approving. The walk is built around three root-level artifacts, not leaf-by-leaf, because asking the user to approve a 10k-token design package sentence by sentence makes the review slow and low-quality. Three artifacts at the right altitude (spec root overview, architecture root overview, refactors agenda) is fast and lands user attention where it matters. Drill-down on specific concerns stays available; default is the overview level. The walk shape is the user-facing counterpart of the spec-first ordering rule encoded in S02.1 — the user sees behavior first, structure second, structural cost third.

**Realized by:** `../../architecture/orchestrator-topology/design-phase.md` (A04.4).

## EARS requirements

### S03.1.u1 — Walk artifacts are the two root overviews plus refactors.md

`The dev-orch design-approval walk shall present exactly three root-level artifacts to the user in order: design/spec/overview.md, design/architecture/overview.md, and design/refactors.md.`

### S03.1.u2 — feasibility.md is on-demand, not default

`The dev-orch design-approval walk shall not include design/feasibility.md in the default traversal and shall reference it only when the user asks "how do you know X?" or raises a feasibility concern during the walk.`

**Reasoning.** Probe evidence is the answer to feasibility concerns, not a default walk artifact. Including it in the default walk would move the user's attention from behavior/structure/cost (the load-bearing decisions) to evidence triage (a second-order concern).

### S03.1.e1 — Walk sequence is behavior then structure then cost

`When dev-orch begins the design-approval walk, dev-orch shall read design/spec/overview.md first (behavior the design commits to), design/architecture/overview.md second (how code must look to realize those behaviors), and design/refactors.md third (structural changes that must land to unlock parallel feature work), and shall not reorder the sequence.`

**Reasoning.** Behavior-first keeps the user anchored to their own intent. Structure-second shows the realization. Cost-last is where the user usually has opinions, because refactors have cost they pay for. Swapping the order shifts the conversation toward implementation details before the user has agreed to the target behavior.

### S03.1.s1 — Drill-down is on demand, not exhaustive

`While dev-orch is walking the user through the design package, the user shall be able to drill into any subsystem overview or specific leaf on demand, and dev-orch shall not require per-leaf EARS-by-EARS approval — approving a root overview is approving the shape, and leaf-specific pushback routes back through a scoped design-orch revision cycle.`

### S03.1.c2 — Pushback on a leaf routes through design-orch, not inline edit

`While dev-orch is walking the design package, when the user raises a pushback on a specific spec leaf or architecture leaf, dev-orch shall not edit the leaf directly, and shall instead route the pushback through a scoped design-orch revision cycle that consumes the current design package plus the pushback as context.`

**Reasoning.** Inline leaf edits by dev-orch collapse the author/reviewer boundary — dev-orch becomes a silent co-author of the design and bypasses every convergence check the design-orch flow runs (spec reviewer, alignment reviewer, structural reviewer, dev-principles lens). Routing through design-orch preserves the convergence contract.

### S03.1.s3 — Small work item collapses walk to single-file shape

`While dev-orch is walking a design package whose spec tree is the degenerate root-only shape per S01.2.s2, the walk shall collapse to design/spec/overview.md + design/architecture/overview.md (each a single file) + design/refactors.md only if non-empty, and the altitude-based approval shape shall stay intact — there is simply less to traverse.`

### S03.1.w1 — Approval is a dev-orch → execution handoff

`Where the user approves the design package during the walk, dev-orch shall spawn a planning impl-orch (per S04.1) with the full design package attached via -f, and shall not spawn @planner directly.`

**Reasoning.** @planner needs runtime context only impl-orch can gather. Having dev-orch spawn @planner would force dev-orch to relay information it does not own. See planner.md's five LLM-specific reasons for the separate agent boundary.

## Non-requirement edge cases

- **Exhaustive leaf-by-leaf walk.** An alternative walk shape would traverse every spec leaf and every architecture leaf with the user. Rejected because it collapses into unreadability for medium or heavy spec trees and because the altitude-based contract already routes attention where it matters. Flagged non-requirement to document the rejection.
- **Walk order by priority instead of behavior → structure → cost.** An alternative shape would walk the most controversial artifact first to front-load the decision. Rejected because "most controversial" is a runtime judgment dev-orch cannot reliably make in advance, and the behavior-first anchor is the invariant that keeps the conversation grounded in user intent. Flagged non-requirement because freezing a different order would undo the spec-first anchor.
