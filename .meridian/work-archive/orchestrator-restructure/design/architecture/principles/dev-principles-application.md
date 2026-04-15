# A05.1: Dev-principles application

## Summary

`dev-principles` is shared behavioral context loaded by every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns — @coder, @reviewer, @refactor-reviewer, @planner, @architect, @design-orchestrator, @impl-orchestrator, @dev-orchestrator. No agent runs it as a separate binary pass/fail gate. At design-orch convergence, the principles are a lens reviewers apply as part of their normal rubric; at the final implementation review loop, the principles apply across every reviewer in the fan-out as part of each reviewer's rubric. Principle violations are reviewer findings routed through the normal loop alongside every other finding. This is the corrected D24 framing.

## Realizes

- `../../spec/root-invariants.md` — S00.w1 (`dev-principles` as universal shared guidance, no binary gate).
- `../../spec/design-production/convergence.md` — S02.4.w1 (`dev-principles` as shared behavioral lens during convergence).
- `../../spec/execution-cycle/phase-loop.md` — S05.1.s4 (`dev-principles` applied across final review fan-out as reviewer rubric, not separate pass-fail gate).
- `../../spec/execution-cycle/spec-leaf-verification.md` — S05.2.w1 (tester-generated edge cases mandatory, a dev-principles-aligned requirement).

## Current state

- v2 splits `dev-principles` loading across agents unevenly. `meridian-dev-workflow/agents/planner.md`, `coder.md`, and `reviewer.md` do not load the skill at all. `meridian-dev-workflow/agents/design-orchestrator.md` and `impl-orchestrator.md` carry body text that describes special gate or lens handling, but the handling is inconsistent between docs.
- An earlier v3 convergence pass (reflected in decisions.md D24 as originally written) described `dev-principles` as a hard convergence gate specifically at design-orch altitude, a review lens at impl-orch altitude, and context for judgment at @planner altitude. The user correction ruled that framing out — the skill is universal shared guidance at every altitude, never a binary gate.
- v2 feasibility records originally reflected the pre-correction framing. `design/feasibility.md §P05` and `§F04` were swept in step B of this work item and now describe `dev-principles` as universal shared guidance with no binary gate at any altitude, matching the revised D24 rule. The sweep source is the in-session user override in parent session `c1135`.

## Target state

**Anchor target for R07.** `design/refactors.md` entry R07 (universalize `dev-principles` loading and remove gate-only framing) names this section as its `Architecture anchor`. The R07 migration is done when every checked-in prompt body that loads or references `dev-principles` describes it as shared operating guidance (not a binary gate), `@planner`, `@coder`, and `@reviewer` all load the skill, and no agent body still carries "run `dev-principles` as a pass/fail check" framing.

### Shared context, no per-agent gate choreography

The four-rule contract every agent shares:

1. **Universal loading.** Every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns loads `dev-principles` at spawn time. This includes @coder, @reviewer, @refactor-reviewer, @planner, @architect, @design-orchestrator, @impl-orchestrator, and @dev-orchestrator. Research agents (@internet-researcher, @explorer) do not load the skill because their work is high-throughput information gathering, not structural judgment.
2. **No binary gate.** No agent runs a `dev-principles` PASS/FAIL checkpoint as a separate convergence criterion. There is no "did you run the principles check" step in any loop. Principle violations surface as reviewer findings or as self-observed concerns that coders raise in their reports.
3. **Lens, not mechanism.** When applied during convergence (design-orch) or final review (impl-orch), the principles are a lens reviewers apply as part of their normal rubric — refactoring discipline, edge-case thinking, abstraction judgment, deletion courage, existing-pattern conformance, structural health signals, integration boundary probing, doc currency. A reviewer flags a principle violation the same way they flag any other finding, and the finding flows through the normal reviewer loop.
4. **Findings route through the normal loop.** A principle violation at design-orch convergence becomes a design-orch iteration item. A principle violation at impl-orch final review becomes an impl-orch fix-and-re-review item. A principle violation at any intermediate phase becomes a scoped coder fix in the active phase. None of these paths require a separate `dev-principles` gate — they are the same feedback path reviewers use for correctness, alignment, or structural findings.

### Application per agent

| Agent | What they load | How they apply it |
|---|---|---|
| **@dev-orchestrator** | `dev-principles` as shared context | Uses the principles as judgment context when routing redesign signals, reviewing plans, and deciding between design-problem and scope-problem classifications. Never runs a principles gate on impl-orch reports. |
| **@design-orchestrator** | `dev-principles` as shared context | Walks each principle against the design during convergence as one of the reviewer lenses. Principle violations become reviewer findings and iterate through the normal convergence loop. No separate principles PASS/FAIL checkpoint (S02.4.w1). |
| **@impl-orchestrator (planning)** | `dev-principles` as shared context | Uses the principles as judgment context when writing `plan/pre-planning-notes.md` and interpreting @planner outputs. Never runs a principles gate on @planner reports. |
| **@impl-orchestrator (execution)** | `dev-principles` as shared context | Uses the principles as judgment context when accepting coder outputs and routing review findings. Attaches the skill to every final-review-loop @reviewer spawn so reviewers apply it as part of their rubric (S05.1.s4). Never runs a principles gate as a separate pass-fail step. |
| **@planner** | `dev-principles` as shared context | Uses the principles as judgment context when decomposing the design into phases — structural health signals inform round boundaries, integration-boundary probing informs tester-lane assignment, abstraction judgment informs whether a refactor should land as its own phase. |
| **@architect** | `dev-principles` as shared context | Uses the principles as judgment context when exploring structural approaches — extract-when-three, integration-boundary probing, delete-aggressively all inform which candidate approach to recommend. |
| **@coder** | `dev-principles` as shared context | Applies the principles during implementation — follows existing patterns, delete aggressively, probe before building at integration boundaries, refactor early. Never runs a principles self-check gate. |
| **@reviewer / @refactor-reviewer** | `dev-principles` as shared context | Applies the principles as part of the review rubric. Principle violations are findings alongside correctness and alignment findings. The refactor-reviewer lane is specifically principles-adjacent (it exists because refactoring discipline is one of the principles), but even that lane is not a gate — findings route through the normal loop. |

### Why not a gate

The framing matters. A binary gate at any altitude creates three failure modes the shared-context model avoids:

1. **Gate gaming.** When a gate exists, agents optimize for passing the gate instead of applying the principles to judgment. A design that passes a `dev-principles: pass` checkbox without anyone actually walking the principles is worse than a design where reviewers surfaced two principle-aligned findings that iterated to resolution.
2. **Altitude mismatch.** The principles are judgment prompts for structural and correctness concerns. At different altitudes they surface different concerns — a refactor-reviewer finds structural debt, a coder finds existing-pattern conformance, a tester finds edge-case coverage. Collapsing all three into one gate at one altitude means the other altitudes lose the signal.
3. **Bureaucratic drift.** Every additional gate costs a handoff and risks the "did we run that yet?" failure mode. A principles-as-shared-context model keeps the cost at skill-load time (free, automatic, survives compaction via skill reload) and folds application into loops that already exist.

The user correction that overruled the earlier gate-at-design-altitude framing came during this work item's review cycle, specifically because the earlier version would have created a second convergence gate at design-orch without actually improving the principle coverage. The correction lives in this leaf as the post-correction D24 framing.

### Retirement surface — where the gate framing must not reappear

- `meridian-dev-workflow/agents/design-orchestrator.md` — body rewritten to describe `dev-principles` as a lens during convergence, not a gate.
- `meridian-dev-workflow/agents/impl-orchestrator.md` — body rewritten to describe `dev-principles` as shared context loaded by every final-review-loop reviewer, not a gate impl-orch runs separately.
- `meridian-dev-workflow/agents/planner.md` — loads `dev-principles` and describes it as shared judgment context for decomposition.
- `meridian-dev-workflow/agents/coder.md` — loads `dev-principles` and describes it as shared implementation guidance.
- `meridian-dev-workflow/agents/reviewer.md` — loads `dev-principles` and describes it as part of the review rubric.
- `design/feasibility.md §P05` and `§F04` — gate framing was swept in step B of this work item; future edits must preserve the post-correction "universal shared guidance, no binary gate at any altitude" framing and must not reintroduce design-time-gate or impl-orch-gate language.

## Interfaces

- **Skill load at spawn time** — every relevant agent loads `dev-principles` via its profile YAML or body-level skill reference. Load is automatic and survives compaction via skill reload (see `agent-creator` and `skill-creator` resources).
- **Reviewer report format** — principle violations appear as findings in the same format as correctness, alignment, and structural findings. No separate "principles section" in reports.
- **Decisions.md** — when a reviewer finding invokes a principle and design-orch or impl-orch decides to override the finding, the override rationale references the principle explicitly so post-hoc readers know the override was deliberate.

## Dependencies

- `../../spec/root-invariants.md` — S00.w1 is the spec-side rule this leaf realizes.
- `../../spec/design-production/convergence.md` — S02.4.w1 is the design-orch convergence rule this leaf realizes.
- `../orchestrator-topology/design-phase.md` — design-orch convergence flow that applies the principles.
- `../orchestrator-topology/execution-loop.md` — final review loop that applies the principles.

## Open questions

None at the architecture level.
