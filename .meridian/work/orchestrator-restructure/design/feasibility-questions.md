# feasibility-questions: Skill Content Design

This doc describes the content of a new `feasibility-questions` skill that design-orchestrator, impl-orchestrator, and @planner all load. The skill carries four questions the three agents ask at their respective altitudes — architectural for design-orch, runtime for impl-orch's pre-planning step, and decomposition-time for @planner — so all three passes reinforce each other rather than drifting.

Read [overview.md](overview.md) for why the questions are shared.

## What the skill is for

Giving both orchestrators a shared frame for checking that the work they are about to commit to is sensible. Not a checklist. Not a workflow. A lens the orchestrators look through before locking in decisions that get expensive to reverse.

The four questions are intentionally few and general. More questions would bloat the skill and invite rubber-stamping; fewer would miss categories of discovery that each question is designed to surface.

## The four questions

### Is this feasible?

The most basic question, and the one that is easiest to skip because it feels obvious by the time the team has got this far. Feasibility is not binary — the useful frame is "feasible under what constraints?" The design-orch answers this with architectural data: is there a pattern that supports what we are trying to do, are there interface shapes that would make it simpler, is there prior art that succeeds or fails at this. The impl-orch answers with runtime data: do the libraries behave the way the design assumes, does the environment support the approach, will the test suite tolerate the changes.

Feasibility questions that deserve flagging: a library's advertised behavior disagrees with its observed behavior, a protocol the design assumes does not exist in the real binary, an interface the design assumes is stable has a history of breaking changes upstream, a data shape the design treats as simple has edge cases the design did not enumerate.

A "yes, feasible" answer is less informative than a "yes with these constraints" answer — name what has to hold for the plan to work.

### What can run in parallel?

Parallelism matters because it bounds the critical path. Work that looks sequential but is actually independent wastes time; work that looks parallel but is actually coupled wastes money on concurrent failures.

Design-orch answers at the interface layer: which subsystems share state, which communicate through well-defined contracts, which touch disjoint modules. That is a necessary condition but not sufficient.

Impl-orch answers at the runtime layer: which phases share test suites, which touch the same global registries, which would race on filesystem or environment setup, which depend on unmocked external systems. That is the sufficient side. Two phases can be interface-independent and still fail to parallelize because they share a test harness or stomp on the same env vars.

The two answers together tell impl-orch what it can actually run concurrently.

### Can this be broken down further?

Phase size is a knob with costs on both ends. Phases that are too large accumulate merge debt, make failures harder to localize, and stretch fix loops. Phases that are too small fragment verification and spawn coordination overhead on trivially small coder spawns.

The question to ask: is this phase doing one coherent thing, or is it secretly two concerns that could land independently? Design-orch answers by looking at the logical boundaries in the design — is this phase one refactor, or is it a refactor plus a feature addition? Impl-orch answers by looking at whether the phase's files cluster around one abstraction or span several unrelated surfaces.

A yes answer means splitting, and splitting costs some coordination. But continuing with an oversized phase costs more when it fails. The default bias should be toward splitting when the question surfaces a genuine seam.

### Does something need foundational work first?

Foundational work is anything that exists only to unblock later work and has no standalone value. Type definitions, abstract base classes, shared helpers, interface contracts that do not yet exist. Skipping the foundation means every later phase rebuilds the same scaffolding in slightly different ways, and the cleanup cost lands as a refactor that invalidates work the team already committed.

The question surfaces things the design might treat as part of the first feature phase but are actually prerequisites. Design-orch answers by looking at import dependencies and shared contracts. Impl-orch answers by looking at whether the first phase's coder would need to stub out support modules that every later phase also needs — if yes, the stubs should be a phase of their own, landing before the features. The planner answers by mapping `structural-prep-candidate: yes` items from the design's structural delta into cross-cutting prep phases that land before parallel feature work.

Foundational phases should be short, minimal, and unblock a concrete next phase. If a foundational phase grows, it is probably hiding feature work and should be questioned with "can this be broken down further?"

**Foundational prep is distinct from structural refactors**, even though both can land in cross-cutting prep phases. Structural refactors are *rearrangement* of existing code (split a module, extract an interface, collapse duplicates). Foundational prep is *creation* of new scaffolding (new type contracts, new base classes, new shared helpers). The starting point distinguishes them — refactors start from existing modules; foundations start from empty. Both unlock parallelism downstream by removing the surface that would force later phases to either duplicate work or run sequentially. The Terrain section's structural delta records both, and [terrain-contract.md](terrain-contract.md) §"Structural refactors vs foundational prep" defines the disambiguation. The planner sequences them independently when needed.

## Why these four and not others

Other possible questions were considered and rejected because they were either covered by one of the four or they were a sub-question of a broader concern that would get asked anyway.

- "What could go wrong?" is the design-phase edge-case enumeration, which happens in the design-orch body and the `scenarios/` seeding. Not a feasibility question.
- "What are the risks?" is either a feasibility risk (covered by "is this feasible?") or a scope risk (covered by "can this be broken down further?"). Asking it separately invites vague hand-wavy answers.
- "Is the design complete?" is a review question, not a feasibility question. Handled by design-orch's review fan-out.
- "Is the team right?" is a staffing question and belongs to `agent-staffing`, not here.

The four questions cover feasibility, parallelism, decomposition, and sequencing — which are the four axes on which a plan can go wrong without any individual piece being wrong. A skill covering more would dilute attention across questions that do not need asking on every pass.

## How the skill is used

The skill is loaded by design-orchestrator, impl-orchestrator, and @planner. All three agents reference the four questions during their convergence phases:

- Design-orch applies the questions during final design convergence and captures answers in the design overview's Terrain section.
- Impl-orch applies the questions during its pre-planning step (the runtime-context pass that runs before the planner spawn) and captures answers in `plan/pre-planning-notes.md`, then again during each phase's scenario review as a quick re-check against runtime discoveries.
- @planner applies the questions during decomposition itself, with the parallelism question taking the lead — the planner's central frame is parallelism-first, so "what can run in parallel?" is the question the decomposition is built around (see [planner.md](planner.md) for that frame). The other three questions stay as supporting lenses: feasibility against the planner's runtime-informed inputs, breakdown against phase shape, foundational prep against structural prep ordering.

The answers are not templated. The skill does not prescribe a format. Each agent captures what the questions surface in whatever form fits the design, notes, or plan it is writing.

## Why the skill is minimal

A big skill body carries tokens into every agent that loads it. The feasibility questions are four prompts; the meat is in the orchestrator applying them with its own data. A 500-line feasibility-questions skill would be dominated by prose that each agent reads once, ignores, and then falls back on its judgment anyway.

The skill should be short enough that each question lives in the reader's mind during the relevant work, long enough that the reasoning behind each question is clear when the reader has not thought about it in a while. Probably under 150 lines when converted from this design doc to an actual SKILL.md body.

## What is NOT in the skill

- Phase ordering prescriptions. That is `/planning`.
- Tester composition or reviewer staffing. That is `agent-staffing`.
- Edge case enumeration craft. That is design-orch's body and the scenarios convention in `dev-artifacts`.
- Decision capture format. That is `decision-log`.
- Specific model or tool recommendations. Those drift.

The skill stays focused on the four questions, the reasoning for each, and a short note on when they are applied.

## Relationship to other skills

The feasibility-questions skill is distinct from `/planning` — `/planning` covers decomposition craft (how to split work into phases, how to write a blueprint, how to map dependencies), while feasibility-questions covers whether to commit to the decomposition at all. Both are loaded by @planner during decomposition: feasibility-questions surfaces what to commit to, `/planning` shapes how to express it. Both are also referenced by impl-orch during pre-planning and by design-orch during convergence. A plan that passes feasibility-questions might still need `/planning` craft to be written well; a plan that is written well according to `/planning` might still fail feasibility-questions.
