# Terrain Section: Artifact Contract

This doc defines the Terrain section as a shared artifact contract — what it contains, how it is written, and what its consumers expect from it. Producer: design-orchestrator. Consumers: impl-orchestrator (pre-planning), @planner (decomposition), and reviewers (structural review pass).

The Terrain section lives at the end of `design/overview.md`. It is one section, not a separate file, but its contract is shared across multiple agents and so lives here, separately from any single agent body.

Read [overview.md](overview.md) for why structure and modularity are first-class design concerns. Read [design-orchestrator.md](design-orchestrator.md) for how design-orch produces this section. Read [planner.md](planner.md) for how the planner consumes the structural delta.

## Why a contract, not just a section

The Terrain section is consumed by three distinct agents — design-orch (writes), impl-orch (reads as pre-planning input), planner (reads as decomposition input) — plus by the structural reviewer in design-phase fan-out. Without a contract, each consumer interprets the section differently and the producer drifts. With a contract, the producer has a checklist for completeness and the consumers can reason about what they are guaranteed to find.

The contract is the source of truth for Terrain content. The design-orchestrator body references this doc for required content. The planner body references it for what to consume. Both should match.

## Required fields

Every Terrain section must contain these fields, in this order. Missing fields are a convergence blocker, not a stylistic choice.

### 1. Current structural posture

What the codebase looks like today. Concrete content:

- The relevant slice of the import DAG (not the whole repo — only the modules the design touches and their first-degree neighbors).
- Shared interfaces consumed by multiple modules.
- Where coupling lives — modules that import from each other, modules that share global state, modules that touch the same files.
- SOLID violations in the affected surface, named specifically (e.g. "Class X violates SRP because it owns both parsing and persistence").

Evidence requirement: each statement in this section should be backed by a file path or import-graph observation. "Module X is coupled to module Y" without saying which import or which shared file is not concrete enough — name the line, the file, or the symbol.

### 2. Target structural posture

What the codebase should look like after the design lands. Same shape as the current posture but described as the post-implementation state:

- The new import DAG (or the diff against the current one).
- New or narrowed interfaces.
- Where coupling has been removed or replaced.
- SOLID-style improvements named specifically (e.g. "Class X is split into a parser and a persistence adapter; persistence depends on parser, not the reverse").

Evidence requirement: each target statement must be derivable from the design docs. If the target says "module X becomes a leaf" but no design doc describes how, the target is aspirational and should be downgraded or backed by a design change.

### 3. Structural delta

The difference between current and target, framed as discrete cuts and consolidations. This is the section the planner reads to identify cross-cutting refactors that need to land first.

Format: each delta item is a single bullet with three required parts:

```
- [structural-prep-candidate: yes|no] <change description> | <affected modules/interfaces> | <reason>
```

Examples:

```
- [structural-prep-candidate: yes] Split module `auth/handler.py` into `auth/parser.py` and `auth/persistence.py` | auth/, callers in api/ | parser and persistence are unrelated concerns currently mashed together; splitting unblocks parallel work on each side
- [structural-prep-candidate: yes] Extract interface `TokenStore` from class `RedisTokenStore` | tokens/, callers in middleware/ | callers depend on the implementation; extracting the interface lets multiple test doubles substitute in independently
- [structural-prep-candidate: no] Add new field `expires_at` to `Token` schema | tokens/schema.py | feature-scoped change, not a structural refactor
```

The `structural-prep-candidate: yes` tag is the explicit signal to the planner that this item should land as cross-cutting prep before any feature phase that depends on the affected surface. The `no` tag is for feature-scoped changes that happen to live in the structural delta because they were noticed during structural analysis. Both are recorded so the planner has a complete picture.

Items tagged `yes` are the planner's structural-prep candidate set. The planner is required to map each `yes` item to a phase or to an explicit skip decision with reasoning (see [planner.md](planner.md) §"Structural prep candidate handling").

### 4. Fix-or-preserve answer

A required answer with this exact shape:

```
fix_or_preserve: fixes | preserves | unknown
reasoning: <one paragraph>
```

- **fixes** — the target posture eliminates the coupling problems the current posture has. The design has done the structural work the user is depending on. Backing evidence: the structural delta has at least one `structural-prep-candidate: yes` item that addresses each named coupling problem in the current posture.
- **preserves** — the design adds features without resolving the underlying structural coupling. Convergence blocker. Design-orch must either revise the design to fix the structure or document why preservation is acceptable for this work item (and the structural reviewer must concur).
- **unknown** — design-orch could not determine whether the target fixes or preserves, usually because runtime data is needed to confirm. Convergence blocker until resolved. The structural reviewer should treat `unknown` the same as `preserves` — push back until the answer is concrete.

The reasoning paragraph is required for every value. A `fixes` answer with no reasoning is not a real answer; it is design-orch declaring victory without making the case.

### 5. Parallel-cluster hypothesis

A hypothesis about which clusters of work should be parallelizable after the structural prep lands. Required even if the planner later corrects it with runtime data.

Format: a list of named clusters with the modules they touch.

```
- Cluster A (auth refactor): auth/parser.py, auth/persistence.py, tests/auth/
- Cluster B (token store interface): tokens/, middleware/, tests/tokens/
- Cluster C (telemetry hooks): telemetry/, hooks/
```

The point is forcing design-orch to actually imagine the decomposition. If design-orch cannot name two or more clusters, the design is probably not decomposable for parallelism — that is the structural reviewer's signal to push back.

Evidence requirement: each cluster must name specific modules, not abstract concepts. "Frontend cluster" is not concrete; "components/SignIn.tsx + components/SignUp.tsx + tests/components/auth/" is concrete.

### 6. Leaves and dependencies

Which modules in the target state have no internal dependencies and can land first. Which modules import from which. Used by the planner for ordering decisions and by impl-orch for understanding the dependency graph at runtime.

### 7. Coupling and ripple risk

Which interfaces are shared across multiple consumers. Which changes would invalidate work in other phases. Where a contract change late in execution would be hardest to reverse.

### 8. Foundational prep

Anything that exists only to unblock later work and has no standalone value. Distinct from structural refactors — see "Structural refactors vs foundational prep" below for the disambiguation. Design-orch does not commit to an ordering, but it names what later work will depend on.

### 9. Integration boundaries

Which protocols, binaries, or APIs need real probing before coding against them. Design-orch surfaces the risk; impl-orch decides how to cover it during pre-planning.

### 10. Known unknowns

Anything design-orch judged it could not resolve without runtime data. Flags for impl-orch to address during the pre-planning step. Not a place to dump everything — only the structural questions design-orch could not answer with architectural reasoning alone.

## Structural refactors vs foundational prep

The Terrain section uses two related but distinct categories. The distinction matters because the planner treats them differently.

- **Structural refactors (rearrangement).** Change to existing structure: split a module, extract an interface, collapse duplicates, rename across consumers. The starting point exists; the change moves things around. Tagged in the structural delta with `structural-prep-candidate: yes` when they need to land before feature work to unlock parallelism.
- **Foundational prep (new scaffolding).** Net-new code that exists only to unblock later work and has no standalone value: type definitions, abstract base classes, shared helpers, interface contracts that don't yet exist. The starting point is empty; the change adds something later phases depend on.

Both can land in cross-cutting prep phases. Both can unlock parallelism. The difference is whether the change is rearrangement (refactor) or creation (foundation). A planner reading the Terrain section should be able to identify which category each delta item is in by looking at whether the affected modules already exist.

If a single delta item is both ("split module X into A and B *and* add a new shared helper Z"), record it as two items so the planner can sequence them independently if needed.

## Evidence and convergence

The structural reviewer in the design-phase fan-out checks every required field for evidence:

- Posture sections have file/import citations, not vibes.
- Delta items have named modules and reasoning, not generic descriptions.
- `fix_or_preserve` has a value other than `unknown` and a reasoning paragraph.
- Parallel-cluster hypothesis has at least two named clusters with specific modules.

A Terrain section that fails any of these checks is not converged on the structural axis, even if functional review has passed. The structural reviewer is required in the design-phase fan-out for exactly this purpose; see [design-orchestrator.md](design-orchestrator.md) §"Active structural review during convergence".

## Anti-patterns the contract is designed to prevent

- **Vibes-based "fixes coupling" prose.** The fix_or_preserve field plus the evidence requirements force a real answer.
- **Structural delta without a planner-usable signal.** The `structural-prep-candidate` tag is the explicit handoff to the planner; without it, the planner has to guess which deltas are cross-cutting prep.
- **Aspirational target posture with no design-doc backing.** The evidence requirement on the target posture prevents design-orch from describing a cleaner architecture it has not actually designed.
- **No parallel-cluster hypothesis at all.** A design that cannot name two clusters is a design that is probably not decomposable for parallelism, and the structural reviewer should catch that before convergence.
- **Drift between the Terrain section and the rest of the design.** The Terrain section is part of `design/overview.md`, not a separate file, so changes to design docs that invalidate Terrain claims are visible in the same review pass.

## Why the contract lives in its own doc

Earlier drafts of this restructure had the Terrain section content described inline in `design-orchestrator.md`. That tangles producer responsibility with consumer expectations: a planner reading `planner.md` would have to also read `design-orchestrator.md` to understand what it could expect from Terrain, and a structural reviewer would have to read both to know what to check.

Extracting the contract into its own doc means:

- The producer (design-orchestrator.md) references this doc for required content rather than re-stating it.
- The planner consumer (planner.md) references this doc for what to expect.
- The structural reviewer is briefed against this doc directly.
- Updates to the contract land in one place and propagate by reference to all consumers.

This is the same pattern the rest of the design package follows: shared concerns get their own doc; agents reference shared docs from their own bodies.
