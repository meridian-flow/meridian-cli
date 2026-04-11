---
name: agent-staffing
description: Team composition for design and implementation phases — which agents to spawn, how many, what can run in parallel, and how to scale effort to complexity. Use when composing a team for a phase, choosing review focus areas, or calibrating effort.
---

# Agent Staffing

Compose the right team for each phase. The goal is coverage across perspectives, not redundant passes from the same angle.

## Model Selection

Profile defaults are correct for most roles — don't override with `-m` unless you have a specific reason. The primary use of `-m` is **review fan-out**: spawning the same @reviewer role multiple times with different model families so their blind spots don't overlap. Run `meridian models list` to see available families and strengths.

## General Principles

**Delegation is mandatory for orchestrators.** An orchestrator's value is coordination and judgment across phases, not solo execution. Orchestrators never write code or edit source files directly — not even for trivial changes. Implementing your own phases bypasses the review, structural review, and smoke-test lanes that catch what the implementer can't see in their own work. If no team composition was provided by your caller, compose one yourself before starting — use the catalogs in the resources below.

**Default model primarily, specialists for their blind spots.** Most @reviewers should run on the default model — it's the baseline and usually the best cost/quality tradeoff. But every model has blind spots shaped by its training, and using only the default means every @reviewer shares the same ones. Bring in a different model when its strengths match the focus area — it's not there for prestige, it's there because it sees things the default model consistently misses on that dimension. Check `meridian models list` for current model strengths. For high-risk focus areas, duplicate coverage with both the default model and the specialist to get convergence across independent perspectives.

**Decision review.** Significant decisions — staffing composition, phase parallelization, design trade-off calls, interface choices — should get a review from a different model before committing. Not just code review; any judgment call that downstream work depends on. A second perspective on a different model catches blind spots cheaply, before they compound into implementation.

**Review convergence.** Review loops run until convergence (no new substantive findings), not a fixed number of passes. The orchestrator can override and stop early, but must log the reasoning in the decision log so future agents understand what was decided and why. The default is to keep iterating — when @reviewers come back clean, the work is ready.

**Design alignment as default focus.** Always include one @reviewer with design alignment focus and pass the design docs. Apply this explicitly in design review and again in the final end-to-end review loop after implementation phases are complete. Intermediate phases stay tester-driven unless a specific @reviewer escalation is needed.

## Effort Scaling

Scale @reviewer and tester effort to the risk and reversibility of the change. Two questions to ask: how expensive is it to be wrong here, and how much harder is it to fix this later than now?

**@reviewer effort by stage:**

- **Design phase:** this is where @reviewer fan-out pays off most. Structural flaws caught here save rework cycles across every implementation phase that builds on them. Lean toward more @reviewers with wider focus area coverage and more model diversity for higher-risk designs; lean toward two @reviewers on the default model with different focus areas when the design is small and obvious.
- **Intermediate implementation phases:** scale testers, not reviewers. One @coder per phase, with @verifier as a baseline and smoke/unit/browser lanes added when risk concentrates in things they specifically catch (smoke = end-to-end behavior, unit = tricky logic, browser = UI). @reviewer involvement here is escalation-only.
- **Final review loop:** after all phases pass phase-level testing, run one full-change @reviewer fan-out across diverse model families. Use the same risk-and-reversibility scaling as design review — cross-phase drift and structural debt are most visible here.

For high-risk focus areas anywhere, duplicate coverage across independent perspectives — the default model and a specialist reviewing the same concern give convergence that single-reviewer coverage can't.

## Parallelism

Think about what depends on what:

- **Intermediate implementation phase:** @coder runs first, then testers fan out in parallel. @reviewers are not part of the default per-phase lane.
- **Escalation path:** if testers surface a real behavioral issue the @coder cannot resolve, spawn a scoped @reviewer for that specific concern while continuing with the smallest useful loop.
- **Final review loop:** @reviewers fan out in parallel only after all implementation phases are complete and passing phase-level tests. Then @coder fixes, testers re-check, and @reviewers re-run until convergence.
- @coders parallelize across non-overlapping phases (determined at plan time), not within a single phase.
- Documenters and @investigators need the full picture — they run after review synthesis.

## When Reviewers Apply

@reviewers are high-leverage and should be used deliberately:

- **Design phase (default):** heavy @reviewer fan-out across diverse model families; include @refactor-reviewer.
- **Final implementation loop (default):** one end-to-end @reviewer fan-out over the complete change set; include @refactor-reviewer.
- **Intermediate implementation phases (exception only):** @reviewer engagement is escalation-driven, triggered by specific unresolved behavioral concerns from testing.

## Integration Boundaries

When a phase talks to an external system (CLI tool, API, wire protocol), the staffing changes:

- **@coder prerequisite:** the blueprint must include a protocol validation step — probe the real binary/API, extract or reference the actual schema, then implement against observed behavior. Don't let @coders write adapters against assumed protocols.
- **@smoke-tester is mandatory, not optional:** integration code can only be verified by running against the real external system. Staff a @smoke-tester for every integration phase, with explicit instructions to test against each external target. Unit tests and type checks verify internal correctness; only smoke tests verify protocol correctness.
- **Per-target coverage:** if the phase touches N integration targets, the @smoke-tester must exercise all N and explicitly report which were tested. Testing one target out of three is incomplete coverage, not a passing result.

## Edge Case Coverage

Edge-case coverage is mandatory at every layer:

- **Design:** enumerate failure modes, boundary conditions, and edge cases explicitly in design artifacts.
- **Implementation planning:** before coding each phase, identify additional edge cases that the design may have missed and pass them to testers.
- **Testing:** testers must generate and execute their own edge cases, not only the @coder's described happy path.

## Agent Catalogs

See resources for detailed catalogs of available agents and when to use each:

- Read `resources/reviewers.md` when composing review teams — covers @reviewer and refactor-reviewer. @reviewers apply by default in design and final review loops, and by exception for intermediate-phase escalations.
- Read `resources/testers.md` when deciding what testing a phase needs — covers @verifier, @smoke-tester, @browser-tester, and unit-tester.
- Read `resources/builders.md` when staffing implementation and design exploration — covers @coders, @architects, @internet-researchers, and @explorers.
- Read `resources/maintainers.md` when a phase needs documentation updates, decision mining, or issue triage — covers @code-documenter, @tech-writer, and investigator.
