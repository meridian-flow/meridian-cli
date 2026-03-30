---
name: planning
description: Break a design into executable implementation phases with focused blueprints, dependency mapping, and agent staffing. Use this after a design doc exists and before spawning coders — whenever you need to decompose a design into phases, write phase specs, or figure out execution order and parallelism. Also activate when entering the planning phase of dev-orchestration.
---

# Plan Implementation

You have a design doc. Now you need to turn it into work that agents can execute. This skill teaches you how to decompose a design into phases, write focused blueprints for each, map dependencies, and staff the agents.

The central idea is focused blueprints. Don't hand a coder the full design doc and expect it to extract what matters. Coders do better with phase-specific context that includes only the interfaces, constraints, and verification criteria needed for that phase.

This skill assumes work setup and artifact placement already come from `/__meridian-work-coordination`. Keep phase files and other work-scoped planning artifacts under `$MERIDIAN_WORK_DIR`.

## Phase Decomposition

Break the design into phases. Each phase becomes a unit of work assigned to a single coder agent in a single session. The goal is phases that are small enough to be completable but large enough to be meaningful.

A good phase is:

- **Independently testable.** When it's done, you can verify it works without waiting for later phases. This is the most important property — if you can't test it, you can't gate it.
- **Bounded to specific files.** The coder knows exactly what to touch and what not to touch. Vague scope leads to scope creep.
- **Right-sized.** If you're not confident a single coder can complete it in one session and produce a testable result, it's too big — split it.
- **Self-contained.** The coder shouldn't need to understand unrelated subsystems to do the work.

Break along natural seams: data model first, then the layer that uses it, then the layer that uses that. If the design has clear architectural boundaries, those are your phase boundaries.

### Signs a phase is too big

- It requires understanding multiple unrelated subsystems.
- It has internal sequencing ("do A, then B, then C") that should really be separate checkpoints.
- You can't write concrete verification criteria because the scope is too diffuse.
- The scope keeps accumulating "and also..." tasks.

When this happens, split at the internal dependency boundary you already see.

### Signs a phase is too small

- It is a one-file mechanical tweak with trivial verification.
- It exists only because every file change was treated as its own phase.
- Reviewing it separately adds overhead without reducing risk.

When this happens, merge it into an adjacent phase that touches related code.

### What to do when decomposition is hard

Some designs resist clean decomposition — everything depends on everything. That usually means the design or architecture itself has tight coupling. Before forcing it into phases, reconsider whether the design or code architecture needs a clearer separation of concerns or deeper refactor. If the design is sound but inherently interconnected, find the narrowest interface between the parts and cut there.

## Dependencies and Execution Order

Once you have phases, map which ones depend on which. This determines execution order and parallelism.

Three things to capture for each phase:

1. **What it requires** — which phases must complete first, and specifically what artifacts or interfaces it needs from them.
2. **What it produces** — interfaces, schemas, or patterns that later phases depend on.
3. **What it's independent of** — phases that can run in parallel because they don't share inputs or outputs.

From the dependency map, derive execution rounds. Each round contains phases that can run in parallel. Minimize the number of rounds — that's your critical path.

```
Round 1: Phase 1                    (foundation — everything depends on it)
Round 2: Phase 2, Phase 3           (independent — both need Phase 1, neither needs the other)
Round 3: Phase 4                    (needs Phase 2 and Phase 3)
```

### Front-load risk

If a phase might invalidate the whole approach — a speculative performance optimization, an unproven integration, a dependency you haven't tested — make it an early phase. Find out it doesn't work before you've built five phases on top of it.

Similarly, front-load phases that produce interfaces downstream phases consume. Get the contracts stable early so later phases aren't coding against a moving target.

## Writing Blueprints

For each phase, write a blueprint that gives the coder everything it needs, and nothing it doesn't. The blueprint is the phase spec file in `$MERIDIAN_WORK_DIR/plan/`, and it should be self-contained enough that the coder does not need to mine the full design doc.

### Include

- **Scope and intent.** What to build and why, so judgment calls on edge cases stay aligned.
- **Files to modify.** Exact files in scope, with short notes on expected changes.
- **Dependencies and interface contracts.** Paste relevant signatures and schema contracts directly; don't force cross-referencing.
- **Patterns to follow.** Point to one concrete existing file when conventions matter.
- **Constraints and boundaries.** State what is explicitly out of scope.
- **Verification criteria.** Define concrete checks that can gate completion.

### Exclude

- Design rationale that doesn't change implementation behavior.
- Plans for later phases.
- Broad context that does not affect current code decisions.

The test: if removing a sentence from the blueprint wouldn't change what the coder builds, that sentence doesn't belong there.

### Lightweight blueprint example

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
- [ ] Expired tokens return `401`
- [ ] `uv run pyright` passes
```

Use any filename convention that keeps ordering and intent obvious to the team. The quality of the blueprint matters more than the exact naming pattern.

## Context File Selection

Pick `-f` context files deliberately when spawning coders. Too little context forces guessing; too much context drowns signal.

Always include:

- The phase blueprint itself.
- Source files the coder will edit.

Include when relevant:

- Interface definitions produced by upstream phases.
- One existing file that demonstrates the pattern to follow.
- The design overview, if the phase needs broader architectural constraints.

Leave out:

- Unrelated phase blueprints.
- Tests and docs for code untouched by this phase.
- Rationale documents that do not affect implementation decisions.

## Agent Staffing

For each phase, match staffing to risk and ambiguity.

Implementer:
Usually `coder`. Use a stronger reasoning model for phases with architectural ambiguity or complex tradeoffs.

Reviewers:
Choose review lenses based on likely failure modes that tests may miss (security, concurrency, architecture fit, design alignment). Increase reviewer depth as risk increases.

Testing:
Default to `verifier` for behavior-changing phases so tests, typing, and lint are cleared before review. Add `unit-tester`, `smoke-tester`, or `browser-tester` based on what could fail in practice.

`investigator` is reactive, not pre-staffed. Spawn only when implementation or review surfaces off-scope uncertainty.

## Practical Tips

- Avoid cleanup-only phases. Integrate cleanup into each phase's done criteria.
- Write verification criteria that can be objectively checked.
- Plan for review and rework loops on higher-risk phases.
- Define and propagate interface contracts early so downstream phases code against stable shapes.
- Number phases by execution order so parallel rounds stay obvious.

## When Planning Is Done

You're ready to move to `implementing` when each phase file gives the coder clear scope and intent, the files to touch are explicit, dependencies include the actual interface contracts, and you can write concrete verification criteria. The dependency map should make execution order obvious — including what can run in parallel.

## Adapting the Plan

Plans rarely survive first contact with implementation unchanged. When a phase reveals that the plan needs adjustment:

- Update the affected phase files in `plan/`
- Record the change and reasoning in your design doc
- If the change affects dependencies, re-evaluate downstream phases

Don't treat the plan as sacred. It's a tool for coordination, not a contract. If reality diverges from the plan, update the plan to match reality — then continue with accurate information.
