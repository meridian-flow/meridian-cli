---
name: planning
description: Break design docs into executable implementation phases with focused blueprints, dependency mapping, and agent staffing. Use this after design docs exist and before spawning coders — whenever you need to decompose a design into phases, write phase specs, or figure out execution order and parallelism.
---

# Plan Implementation

The plan is a delta, not a restatement of the full system. Design docs describe the target state; the plan describes what changes from current code to reach it.

The central idea is focused blueprints. Don't hand a coder the full design tree and expect it to extract what matters — coders do better with phase-specific context that includes only the interfaces, constraints, and verification criteria needed for that phase.

See `/dev-artifacts` for where blueprints, status tracking, and decision logs go.

## Phase Decomposition

Break the design into phases. Each phase becomes a unit of work — small enough to be completable, large enough to be meaningful. See `/agent-staffing` for how to staff each phase.

A good phase is:

- **Independently testable.** When it's done, you can verify it works without waiting for later phases. This is the most important property — if you can't test it, you can't gate it.
- **Bounded to specific files.** The coder knows exactly what to touch and what not to touch.
- **Right-sized.** If you're not confident a single coder can complete it in one session, split it.
- **Self-contained.** The coder shouldn't need to understand unrelated subsystems.

Break along natural seams: data model first, then the layer that uses it, then the layer that uses that. If a design resists clean decomposition — everything depends on everything — that usually means tight coupling in the design itself. Find the narrowest interface between the parts and cut there.

## Dependencies and Execution Order

Map which phases depend on which. For each phase capture what it requires, what it produces, and what it's independent of. From the dependency map, derive execution rounds — each round contains phases that can run in parallel:

```
Round 1: Phase 1                    (foundation — everything depends on it)
Round 2: Phase 2, Phase 3           (independent — both need Phase 1, neither needs the other)
Round 3: Phase 4                    (needs Phase 2 and Phase 3)
```

**Front-load risk.** If a phase might invalidate the whole approach — an unproven integration, a speculative optimization — make it early. Find out it doesn't work before you've built five phases on top of it. Similarly, front-load phases that produce interfaces downstream phases consume, so later phases aren't coding against a moving target.

## Writing Blueprints

Each blueprint gives the coder everything it needs, and nothing it doesn't. It should be self-contained enough that the coder does not need to mine the full design doc.

**Include:** scope and intent (what to build and why), files to modify (exact files with notes on expected changes), dependencies and interface contracts (paste signatures directly — don't force cross-referencing), patterns to follow (point to one concrete existing file), constraints and boundaries (what's explicitly out of scope), and verification criteria (concrete checks that gate completion, including design conformance).

**Exclude:** design rationale that doesn't change implementation behavior, plans for later phases, broad context that doesn't affect current decisions. The test: if removing a sentence wouldn't change what the coder builds, it doesn't belong.

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
- [ ] Expired tokens return `401`
- [ ] `uv run pyright` passes
```

## Adapting the Plan

Plans rarely survive first contact with implementation unchanged. Update blueprints, status tracking, and design docs as reality diverges — the plan is a coordination tool, not a contract. Record pivots in the decision log so the reasoning survives.
