---
name: agent-staffing
description: Team composition for design and implementation phases — which agents to spawn, how many, what can run in parallel, and how to scale effort to complexity. Use when composing a team for a phase, choosing review focus areas, or calibrating effort.
---

# Agent Staffing

Compose the right team for each phase. The goal is coverage across perspectives, not redundant passes from the same angle.

## Model Selection

Profile defaults are correct for most roles — don't override with `-m` unless you have a specific reason. The primary use of `-m` is **review fan-out**: spawning the same reviewer role multiple times with different model families so their blind spots don't overlap. Run `meridian models list` to see available families and strengths.

## General Principles

**Delegation is mandatory for orchestrators.** An orchestrator's value is coordination and judgment across phases, not solo execution. Orchestrators never write code or edit source files directly — not even for trivial changes. Implementing your own phases bypasses the review, structural review, and smoke-test lanes that catch what the implementer can't see in their own work. If no team composition was provided by your caller, compose one yourself before starting — use the catalogs in the resources below.

**Default model primarily, specialists for their blind spots.** Most reviewers should run on the default model — it's the baseline and usually the best cost/quality tradeoff. But every model has blind spots shaped by its training, and using only the default means every reviewer shares the same ones. Bring in a different model when its strengths match the focus area — it's not there for prestige, it's there because it sees things the default model consistently misses on that dimension. Check `meridian models list` for current model strengths. For high-risk focus areas, duplicate coverage with both the default model and the specialist to get convergence across independent perspectives.

**Decision review.** Significant decisions — staffing composition, phase parallelization, design trade-off calls, interface choices — should get a review from a different model before committing. Not just code review; any judgment call that downstream work depends on. A second perspective on a different model catches blind spots cheaply, before they compound into implementation.

**Review convergence.** Review loops run until convergence (no new substantive findings), not a fixed number of passes. The orchestrator can override and stop early, but must log the reasoning in the decision log so future agents understand what was decided and why. The default is to keep iterating — when reviewers come back clean, the work is ready.

**Design alignment as default focus.** Always include one reviewer with design alignment focus, passing the design docs. Every implementation phase should verify the code matches the spec, because drift from the design is invisible until downstream phases build on wrong assumptions. This doesn't need a dedicated agent — spec-vs-code comparison is natural for the model when given both artifacts.

## Effort Scaling

Effort scaling applies mainly to reviewers — the role that fans out within a phase. Coders don't scale within a phase (one coder per phase; split the plan if it's too big). Testers are matched to what changed, not scaled by risk.

For reviewers, scale to the risk and reversibility of the change:
- Fast, low-risk changes: ~2 reviewers on the default model with different focus areas
- Medium risk: 3-5 reviewers with split focus areas, bringing in specialist models where their strengths match the focus area
- High risk or critical paths: 5+ reviewers; for the most critical focus areas, duplicate coverage with both the default model and a specialist reviewing the same concern — convergence across independent perspectives is what gives confidence

## Parallelism

Think about what depends on what:

- Reviewers and testers both need finished code — they wait for the coder
- Reviewers and testers examine different dimensions — they can run simultaneously
- Within each category (all reviewers, all testers) there are no dependencies — fan them out
- Coders parallelize across non-overlapping phases (determined at plan time), not within a single phase
- Documenters and investigators need the full picture — they run after review synthesis

## Agent Catalogs

See resources for detailed catalogs of available agents and when to use each:

- Read `resources/reviewers.md` when composing review teams — covers reviewer, refactor-reviewer, verifier, and investigator. These apply to both design and implementation review.
- Read `resources/testers.md` when deciding what testing a phase needs — covers smoke-tester, browser-tester, and unit-tester.
- Read `resources/builders.md` when staffing implementation and design exploration — covers coders, architects, researchers, explorers, and documenters.
