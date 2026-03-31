# Design Overview: 3-Orchestrator Model

## The Dev Lifecycle

```
dev-orchestrator
  │ understands user intent
  │ gathers requirements
  │ spawns researchers/explorers
  │
  ├──── --from + -f (whatever context exists) ────►
  │
  │  design-orchestrator (autonomous)
  │    │ explores architecture + tradeoffs
  │    │ reports different approaches
  │    │ light prototyping to test shape
  │    │ review cycles (SOLID, entropy)
  │    │ orchestrates subagents autonomously
  │    │
  │    ├──── design/ + plan/ ────►
  │    │
  │  ◄─┘ design report back to dev-orchestrator
  │
  │ explains design to user
  │ user satisfied? ──no──► another design-orchestrator round
  │              └──yes──►
  │ final approval
  │
  ├──── design/ + plan/ artifacts ────►
  │
  │  impl-orchestrator (autonomous)
  │    │ code → test → review → fix
  │    │ drives to completion
  │    │
  │  ◄─┘ done
  │
  └ reports results to user
```

## Three Orchestrators

### dev-orchestrator — User Relationship Owner

**Identity**: Understands what the user wants and ensures they get it.

Owns:
1. Problem definition — clarifying scope, constraints, what success looks like
2. Requirements gathering — spawning researchers/explorers for context
3. Design review gate — receiving design-orchestrator's output, explaining it to the user, sending it back for iteration if needed
4. Plan approval — final sign-off before implementation
5. Results delivery — reporting impl-orchestrator's output back to the user

Delegates design exploration to design-orchestrator, implementation to impl-orchestrator.

### design-orchestrator — Design Space Explorer

**Identity**: Turns requirements into an executable specification (design + plan).

Owns:
1. Architecture exploration — spawns architects with different approaches
2. Tradeoff analysis — evaluates approaches against requirements
3. Light prototyping — tests the shape of an approach before committing
4. Design review cycles — fans out reviewers, synthesizes, iterates autonomously
5. Entropy reduction — designs for clean boundaries, SOLID, agent navigability
6. Implementation planning — decomposes design into phases, staffs agents
7. Hierarchical design docs — builds a navigable model of the system

**Convergence**: The design is ready when reviewers come back in agreement that it's sound. If reviewers disagree or go in circles, the design-orchestrator has context they don't (full requirements, prior iterations, rejected approaches) and makes the call — but logs the reasoning in the design docs. Convergence is a judgment, not a checklist.

**Escalation**: If reviewers surface something that genuinely requires user input — a scope question, a fundamental tradeoff the requirements don't cover — the design-orchestrator converges on everything else, flags the unresolved decision with clear options, and reports back to dev-orchestrator. Dev-orchestrator resolves with the user, then spawns a scoped follow-up if needed. This avoids full-cycle re-spawns for targeted questions.

**Error case**: If requirements are contradictory or under-specified, the design-orchestrator reports the ambiguity as a finding rather than guessing or blocking. Dev-orchestrator resolves with the user.

### impl-orchestrator — Implementation Executor

**Identity**: Ships working code that matches the specification.

Owns:
1. Codebase exploration — understands current state before changing it
2. Phase execution — code → test → review → fix per phase
3. Agent staffing — composes the right team for each phase
4. Progress tracking — maintains status.md as ground truth
5. Execution-time adaptation — records pivots in decisions.md

**Convergence**: A phase is done when reviewers and QA agents come back in agreement that the implementation is sound. If they disagree or go in circles, the impl-orchestrator makes the call and logs the reasoning in decisions.md. Same judgment pattern as design-orchestrator — the orchestrator has context reviewers don't and owns the final decision.

**Error case**: If implementation hits a blocker that requires design changes (discovered constraint, broken assumption), the impl-orchestrator reports clearly what's blocking and why, so dev-orchestrator can resolve — potentially spawning a scoped design-orchestrator round to amend the design. Delegates design decisions to design-orchestrator, scope decisions to dev-orchestrator.

## Artifact Convention

Each work item produces artifacts in `$MERIDIAN_WORK_DIR/`:

```
requirements.md                        ← optional: dev-orchestrator captures intent if needed
design/
  overview.md                          ← system-level: how everything fits together
  <system>/
    <component>/
      <subcomponent>/
        ...                            ← as deep as the system requires
  tradeoffs.md                         ← approaches considered + rejected, with why
plan/
  phase-1-slug.md                      ← what changes, what files, verification
  phase-2-slug.md
  status.md                            ← impl-orchestrator: execution progress
decisions.md                           ← impl-orchestrator: execution-time pivots
```

### Design Principles for design/

**Single Responsibility**: Each document describes one thing — one component, one interface, one interaction pattern. When a doc starts covering two concerns, split it. Same SRP discipline we apply to code.

**Unbounded depth**: The hierarchy goes as deep as the system requires. `design/overview.md` for a simple change. `design/auth/token-validation/refresh-flow.md` for a complex subsystem. No artificial ceiling — depth matches complexity.

**Linked, not siloed**: Documents link to related docs using relative paths. A component doc links to the components it interacts with, the interfaces it implements, the tradeoffs that shaped it. An agent reading any doc can follow links to build context without reading everything.

```markdown
<!-- Example: design/auth/token-validation.md -->
# Token Validation

Validates JWT tokens on every authenticated request.
See [auth overview](../overview.md) for how this fits into the auth system.
Uses the [key rotation](../key-management/rotation.md) component for public key discovery.

## Interface
...

## Interaction with [rate limiter](../../api/rate-limiter.md)
...
```

**Small, focused files**: An agent should be able to read one doc and understand one concept fully. If understanding requires reading 5 other docs first, the doc is either too abstract or missing context. Include enough inline to be self-contained, link out for depth.

**Describes the target state**: design/ models how the system *should* work after implementation, including existing parts that the new work interacts with. This gives agents complete context — they understand not just what's new but how it fits into what exists.

### Plan as Delta

**plan/** describes what specifically changes to get from the current codebase to the designed state. Each phase references design/ docs for the "what" and "why" but focuses on the concrete changes: which files, what modifications, verification criteria.

### Requirements as Anchor

**requirements.md** captures user intent, constraints, and success criteria. design-orchestrator optimizes toward it. impl-orchestrator verifies against it. If requirements change, the design may need revisiting.

## Scaling Down

Not every task needs all 3 orchestrators:

- **Trivial** (typo fix, one-liner): dev-orchestrator → impl-orchestrator directly, no design phase
- **Simple** (well-understood bug fix): dev-orchestrator → brief design + plan → impl-orchestrator
- **Substantive** (new feature, refactor): full 3-orchestrator flow
- **Complex** (system redesign, cross-cutting): multiple design-orchestrator rounds with deep hierarchical design/

The dev-orchestrator decides which path based on surface area and reversibility.
