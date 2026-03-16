---
name: plan-implementation
description: Break a design into executable implementation phases with focused blueprints, dependency mapping, and agent staffing. Use this after a design doc exists and before spawning coders — whenever you need to decompose a design into phases, write phase specs, or figure out execution order and parallelism. Also activate when entering the planning phase of dev-workflow.
---

# Plan Implementation

You have a design doc. Now you need to turn it into work that agents can execute. This skill teaches you how to decompose a design into phases, write focused blueprints for each, map dependencies, and staff the agents.

The central idea: **blueprint distillation**. Don't hand the coder your full design doc and hope they extract what's relevant. Instead, compress the design into a focused, phase-specific blueprint that contains only what the coder needs for that phase. Research consistently shows that LLMs perform better with focused, relevant context than with a full information dump. A coder working on "Phase 3: auth middleware" doesn't need the database migration plan from Phase 1. It needs the interfaces Phase 1 produced and the specific requirements for Phase 3.

This skill assumes work setup and artifact placement already come from `__meridian-work-coordination`. Keep phase files and other work-scoped planning artifacts under `$MERIDIAN_WORK_DIR`.

## Phase Decomposition

Break the design into phases. Each phase becomes a unit of work assigned to a single coder agent in a single session. The goal is phases that are small enough to be completable but large enough to be meaningful.

A good phase is:

- **Independently testable.** When it's done, you can verify it works without waiting for later phases. This is the most important property — if you can't test it, you can't gate it.
- **Bounded to specific files.** The coder knows exactly what to touch and what not to touch. Vague scope leads to scope creep.
- **Right-sized.** The sweet spot is 2-8 files. More than ~10 files means the phase is probably doing too much — split it. One file usually means it's too small — merge it with the next phase unless that single file is genuinely complex.
- **Completable in one spawn.** If you're not confident a single coder can do it in one session, it's too big.

Break along natural seams: data model first, then the layer that uses it, then the layer that uses that. If the design has clear architectural boundaries, those are your phase boundaries.

### What to do when decomposition is hard

Some designs resist clean decomposition — everything depends on everything. That usually means the design itself has tight coupling. Before forcing it into phases, reconsider whether the design needs a clearer separation of concerns. If the design is sound but inherently interconnected, find the narrowest interface between the parts and cut there.

## Dependency Mapping

Once you have phases, map which ones depend on which. This determines execution order and parallelism.

Three things to capture for each phase:

1. **What it requires** — which phases must complete first, and specifically what artifacts or interfaces it needs from them.
2. **What it produces** — interfaces, schemas, or patterns that later phases depend on.
3. **What it's independent of** — phases that can run in parallel because they don't share inputs or outputs.

From the dependency map, derive execution groups (rounds). Each round contains phases that can run in parallel. Minimize the number of rounds — that's your critical path.

```
Round 1: Phase 1                    (foundation — everything depends on it)
Round 2: Phase 2, Phase 3           (independent — both need Phase 1, neither needs the other)
Round 3: Phase 4                    (needs Phase 2 and Phase 3)
```

### Front-load risk

If a phase might invalidate the whole approach — a speculative performance optimization, an unproven integration, a dependency you haven't tested — make it an early phase. Find out it doesn't work before you've built five phases on top of it.

Similarly, front-load phases that produce interfaces other phases consume. Get the contracts stable early so downstream phases aren't coding against a moving target.

## Blueprint Distillation

This is the key step. For each phase, write a blueprint that gives the coder everything it needs — and nothing it doesn't.

A blueprint is the phase spec file itself. It lives in `$MERIDIAN_WORK_DIR/plan/` and becomes the primary context the coder receives. Write it so the coder has complete, self-contained instructions without needing to search the full design doc.

### What goes into a blueprint

**Scope and intent.** What to build and why. The "why" matters because it helps the coder make good judgment calls on edge cases. "Add token validation" is less useful than "Add token validation so we can reject expired credentials at the middleware layer before they reach route handlers."

**Interface contracts.** If this phase consumes interfaces from a prior phase, include them directly in the blueprint. Don't say "see Phase 1" — paste the relevant type signatures, function contracts, or schema definitions. The coder shouldn't have to cross-reference other phase files.

**Patterns to follow.** If the codebase has established conventions (error handling patterns, naming conventions, module structure), point to a specific existing file as an example. "Follow the pattern in `src/auth/existing_handler.py`" is concrete. "Follow existing patterns" is not.

**Constraints and boundaries.** What the coder should not do is as important as what they should do. If a file is out of scope, say so. If there's a known issue they should avoid fixing in this phase, say so. Boundary clarity prevents scope creep.

**Verification criteria.** Concrete checks the coder (and later the verifier) can run. "Tests pass" is bare minimum. "Token validation rejects expired tokens with a 401, test case exists in `tests/auth/`" is actionable.

### What stays out of a blueprint

- Design rationale that doesn't affect implementation ("we considered three approaches and picked this one")
- Plans for other phases ("in Phase 4 we'll add rate limiting")
- Broad architectural context that doesn't change what the coder does in this phase

The test: if removing a sentence from the blueprint wouldn't change what the coder builds, that sentence doesn't belong there.

## Agent Headcount

For each phase, decide who works on it. The staffing depends on what the phase touches and how risky it is.

### Implementer

Usually `coder`. For phases with significant UI/UX work, complex architectural decisions, or heavy ambiguity, consider `coder -m opus` for a stronger model.

### Reviewers

Pick review lenses based on what the phase actually touches:

| Phase touches | Reviewer lens |
|---------------|---------------|
| Shared state, locks, async | `reviewer-concurrency` |
| Auth, input handling, user data | `reviewer-security` |
| New abstractions, interfaces, module boundaries | `reviewer-solid` |
| Foundational phase that later phases build on | `reviewer-planning` |

Two reviewers is the default. Three for high-risk phases. One for simple/mechanical phases. Zero for trivial changes (config tweaks, renames).

### Other agents

- **Verifier:** Include for any phase that modifies logic. The verifier runs tests and type checks, fixing mechanical issues before reviewers see the code. This avoids wasting reviewer attention on things a type checker catches.
- **Unit tester:** Include when the phase creates behavior that's hard to verify manually — edge cases, error paths, boundary conditions.
- **Smoke tester:** Include when the phase produces user-visible behavior that benefits from end-to-end validation.
- **Investigator:** Not staffed per phase. Spawned reactively when the coder or reviewer flags something outside the current scope.

## Writing Phase Files

Write phase specs in `$MERIDIAN_WORK_DIR/plan/`. Each phase gets a file named `phase-{N}-{slug}.md`.

The phase spec IS the blueprint. Write it with the coder as your audience. It should be complete enough that the coder can work from this file plus the referenced source files, without reading the full design doc.

Each phase file covers:

1. **Scope** — what to build and why
2. **Files to modify** — every file the phase is expected to touch
3. **Dependencies** — which phases must complete first and what interfaces they provide
4. **Verification criteria** — concrete, runnable checks
5. **Agent headcount** — implementer, reviewers, and other agents for this phase
6. **Context files** — what to pass as `-f` references when spawning the coder

Read `resources/planning-reference.md` for detailed conventions on phase file naming, dependency graph formats, right-sizing heuristics, and context file selection.

### Context files for the coder spawn

When spawning the coder, pass:

```bash
meridian spawn -a coder -m codex \
  -p "Phase N: [description]" \
  -f $MERIDIAN_WORK_DIR/plan/phase-N-slug.md \
  -f src/relevant/existing_code.py \
  -f src/relevant/interfaces_from_prior_phase.py
```

The phase spec is always included. Add existing source files that show patterns to follow or interfaces to consume. Don't include everything in the repo — pick what's relevant.

## When Planning Is Done

You have a `plan/` directory with phase files. Each phase has:

- Clear scope with the "why" explained
- Specific file boundaries
- Dependencies on other phases with interface contracts included
- Concrete verification criteria
- Agent staffing decided

The execution order is clear from the dependency map. You know which phases can run in parallel and which must be sequential. The orchestrator can now move to `implementing` and start executing phases.

## Adapting the Plan

Plans rarely survive first contact with implementation unchanged. When a phase reveals that the plan needs adjustment:

- Update the affected phase files in `plan/`
- Record the change and reasoning in `decision-log.md`
- If the change affects dependencies, re-evaluate downstream phases

Don't treat the plan as sacred. It's a tool for coordination, not a contract. If reality diverges from the plan, update the plan to match reality — then continue with accurate information.
