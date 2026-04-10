---
name: planning
description: Break design docs into executable implementation phases with focused blueprints, dependency mapping, and agent staffing. Use this after design docs exist and before spawning coders — whenever you need to decompose a design into phases, write phase specs, or figure out execution order and parallelism.
---

# Plan Implementation

The plan is a delta, not a restatement of the full system. Design docs describe the target state; the plan describes what changes from current code to reach it.

The central idea is focused blueprints. Don't hand a @coder the full design tree and expect it to extract what matters — @coders do better with phase-specific context that includes only the interfaces, constraints, and verification criteria needed for that phase.

See `/dev-artifacts` for where blueprints, status tracking, and decision logs go.

## Thoroughness is Mandatory

A shallow plan produces shallow implementation, and shallow implementation ships bugs that the design already warned about. Before you declare the plan done, you must have walked through every design doc, every entry in the decision log, and every audit or investigation report in your context. Each of these sources contains information that must end up in a phase — either as a file to modify, an interface to respect, a scenario to verify, or a constraint to honor. Nothing in the input gets to evaporate between your reading of it and the @coder receiving the blueprint.

The test of thoroughness: for every numbered decision in the decision log, you should be able to point at the exact phase that implements it. For every edge case the design enumerates, you should be able to point at the exact scenario a tester will verify. For every gap an audit report flagged, you should be able to point at the phase that closes it and the scenario that proves it. If any of these produce "none," the plan is incomplete.

Thorough planning is expensive. Do it anyway — the cost of a thorough plan is always smaller than the cost of re-implementing a phase because the original plan missed a constraint.

## Phase Decomposition

Break the design into phases. Each phase becomes a unit of work — small enough to be completable, large enough to be meaningful.

### Staffing is mandatory output

Every plan must include a staffing section that the @impl-orchestrator can execute without guessing. Without explicit staffing, the orchestrator runs @coders only — no review loops, no model diversity, no quality gates beyond tests. The staffing section must specify:

1. **Per-phase teams**: which `@coder` model, which testers (`@verifier`, `@smoke-tester`, `@unit-tester`, `@browser-tester`), and whether the phase needs a scoped `@reviewer` (escalation only for intermediate phases).
2. **Final review loop**: which `@reviewer` models, which focus areas, and which `@refactor-reviewer` assignments. Fan out across diverse model families so blind spots don't overlap. Pass design docs to the design-alignment reviewer.
3. **Escalation policy**: when intermediate-phase testers should trigger a `@reviewer` instead of just fixing and retesting.

See `/agent-staffing` for the full framework — reviewer catalogs, model selection, effort scaling, and parallelism rules.

A good phase is:

- **Independently testable.** When it's done, you can verify it works without waiting for later phases. This is the most important property — if you can't test it, you can't gate it.
- **Bounded to specific files.** The @coder knows exactly what to touch and what not to touch.
- **Right-sized.** If you're not confident a single @coder can complete it in one session, split it.
- **Self-contained.** The @coder shouldn't need to understand unrelated subsystems.

Break along natural seams: data model first, then the layer that uses it, then the layer that uses that. If a design resists clean decomposition — everything depends on everything — that usually means tight coupling in the design itself. Find the narrowest interface between the parts and cut there.

## Dependencies and Execution Order

Map which phases depend on which. For each phase capture what it requires, what it produces, and what it's independent of. From the dependency map, derive execution rounds — each round contains phases that can run in parallel:

```
Round 1: Phase 1                    (foundation — everything depends on it)
Round 2: Phase 2, Phase 3           (independent — both need Phase 1, neither needs the other)
Round 3: Phase 4                    (needs Phase 2 and Phase 3)
```

**Front-load risk.** If a phase might invalidate the whole approach — an unproven integration, a speculative optimization — make it early. Find out it doesn't work before you've built five phases on top of it. Similarly, front-load phases that produce interfaces downstream phases consume, so later phases aren't coding against a moving target.

**Identify integration boundaries.** When a phase involves talking to an external binary, API, or wire protocol, mark it explicitly. Integration phases need different treatment than self-contained code:

- **Protocol validation first.** Before coding an adapter, the @coder must probe the real system — run the binary, hit the endpoints, generate the schema. This is a prerequisite step in the blueprint, not an afterthought. Reference the actual protocol spec or observed behavior in the blueprint.
- **Test against the real thing.** Phase-level verification for integration phases must include running against the real external system, not just unit tests and type checks. Staff a @smoke-tester that exercises each integration target.
- **Observability before correctness.** If the integration layer lacks debug/trace capability, build it first. You can't verify protocol correctness without seeing the wire traffic. A phase that adds an adapter without wire-level observability is incomplete.
- **One adapter per phase.** Don't bundle multiple integration targets (e.g., "adapters for Codex, Claude, and OpenCode") into a single phase. Each external system has its own protocol, its own failure modes, and its own verification requirements. Bundling them hides which ones were actually tested.

## Writing Blueprints

Each blueprint gives the @coder everything it needs, and nothing it doesn't. It should be self-contained enough that the @coder does not need to mine the full design doc.

**Include:** scope and intent (what to build and why), files to modify (exact files with notes on expected changes), dependencies and interface contracts (paste signatures directly — don't force cross-referencing), patterns to follow (point to one concrete existing file), constraints and boundaries (what's explicitly out of scope), verification criteria (concrete checks that gate completion, including design conformance), and a **Scenarios to Verify** section (see below).

**Exclude:** design rationale that doesn't change implementation behavior, plans for later phases, broad context that doesn't affect current decisions. The test: if removing a sentence wouldn't change what the @coder builds, it doesn't belong.

## Scenarios to Verify

Verification contracts live in `scenarios/`, not embedded in blueprints. See `/dev-artifacts` for the scenarios folder convention — format, IDs, lifecycle, and who appends when. As planner, your job is two-fold:

1. **Append new scenarios** that planning surfaces. When decomposition reveals a cross-phase interaction, sequencing hazard, or phase-boundary edge case that the design did not anticipate, add it to `scenarios/` with the phase ID it belongs to. Tag with the appropriate tester role.
2. **Reference scenarios in every blueprint.** Each phase blueprint must include a "Scenarios" section that lists the scenario IDs this phase must verify before it can be considered complete. Pull them from `scenarios/overview.md` and filter to the ones tagged for this phase.

The blueprint does not re-describe the scenario — it references it by ID. The tester reads the scenario file directly from `scenarios/`. This keeps the blueprint focused on "what to build" and prevents drift between the blueprint's scenario copy and the canonical scenario file.

If `scenarios/` does not exist or is empty when you start planning, the design is incomplete — design was supposed to seed it with every edge case. Send it back to @design-orchestrator rather than plowing ahead with a thin plan. Implementation built on absent scenarios ships absent tests.

Every gap an audit or investigation report flagged must already be a scenario in `scenarios/`. If an audit is in your context and you find a gap with no matching scenario, add it before continuing with the plan. No gap gets dropped between investigation and implementation.

### Example

```markdown
# Phase: Auth middleware token validation

## Scope
Add middleware-level token expiration checks so expired credentials are rejected before route handlers.

## Files to Modify
- `src/auth/middleware.py` -- implement validation path
- `tests/auth/test_middleware.py` -- add expiration coverage

## Dependencies
- Requires: Token claims interface from prior phase
- Independent of: UI error copy phase

## Interface Contract
`TokenClaims(expires_at: datetime, subject: str, scopes: list[str])`

## Verification Criteria
- [ ] `uv run pytest tests/auth/test_middleware.py` passes
- [ ] `uv run pyright` passes

## Scenarios

This phase must verify the following scenarios from `scenarios/`:

- **S012** — Expired token rejection (@unit-tester)
- **S013** — Clock-skew tolerance (@unit-tester)
- **S014** — Missing expires_at claim (@unit-tester)
- **S015** — End-to-end expired token flow (@smoke-tester)
- **S016** — Refresh flow during expiration (@smoke-tester)

Phase cannot close until every scenario above is marked verified in its scenario file.
```

## Adapting the Plan

Plans rarely survive first contact with implementation unchanged. Update blueprints, status tracking, and design docs as reality diverges — the plan is a coordination tool, not a contract. Record pivots in the decision log so the reasoning survives.
