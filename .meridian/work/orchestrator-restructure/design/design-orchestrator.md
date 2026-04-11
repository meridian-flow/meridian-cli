# Design Orchestrator: Target Shape

This doc describes the design-orchestrator's behavior after the v3 restructure. The core activity — turning requirements into a reviewed design that downstream agents can execute against — stays, but the design output shape changes fundamentally. Design-orch now produces a **two-tree design package**: a hierarchical spec tree (business intent in EARS notation) and a hierarchical architecture tree (technical realization), plus two sibling artifacts (`refactors.md` for the refactor agenda and `feasibility.md` for gap-finding results). Verification under v3 runs against spec leaves, not scenarios. There is no TDD mandate.

Read [overview.md](overview.md) first for context on why the shape changed. The spec and architecture trees are the primary design output; the Terrain analysis workflow (now feeding refactors.md and feasibility.md) lives in [terrain-contract.md](terrain-contract.md).

## What design-orch does

Still turns requirements into a reviewed design specification. What changes under v3:

- The design output is **four artifacts**, not one: `design/spec/` (hierarchical spec tree), `design/architecture/` (hierarchical architecture tree), `design/refactors.md` (refactor agenda), `design/feasibility.md` (gap-finding record).
- Every acceptance criterion and observable behavior in a spec leaf is written in **EARS notation** (Easy Approach to Requirements Syntax). Hand-wavy requirements are a convergence blocker.
- Each tree has a **root-level TOC overview** listing every leaf with a one-line summary, so downstream agents can navigate without loading the whole package.
- Gap-finding is an **active design-phase activity**: design-orch probes real systems (binaries, APIs, libraries, schemas) during design and records probe results in `feasibility.md`. Designing against training-data assumptions is rejected.
- Refactor planning is a **design output**, not a planner invention: `design/refactors.md` is produced during design from the architecture tree's structural delta.
- `dev-principles` is loaded as a **hard convergence gate**. "Does this design violate any project-wide structural principles?" blocks convergence when answered yes.
- The reviewer fan-out includes **spec reviewers, architecture reviewers, alignment reviewers, and a refactor/structural reviewer**, each with its own focus area. Convergence requires the structural reviewer PASS or a documented override.
- Scenarios as a separate concept go away. Spec leaves subsume them; the `scenarios/` folder is no longer produced or consumed anywhere in the design package.
- Problem-size scaling is explicit: the full hierarchical ceremony is warranted for non-trivial work; small work uses a degenerate tree (root-only) or skips design entirely.

## The two-tree structure

```
design/
  spec/                        # hierarchical specification tree (business intent)
    overview.md                # TOC index + root system-level invariants
    <subsystem-A>/
      overview.md              # TOC + subsystem-level contracts
      <capability-1>.md        # EARS acceptance criteria
      <capability-2>.md
    <subsystem-B>/
      ...
  architecture/                # hierarchical technical design tree
    overview.md                # TOC index + root system topology (current + target posture)
    <subsystem-A>/
      overview.md              # TOC + subsystem internal topology
      <module-1>.md            # interface contracts, types, dependency directions, module layout
      <module-2>.md
    <subsystem-B>/
      ...
  refactors.md                 # refactor agenda (parallelism-first prep for planner)
  feasibility.md               # gap-finding / probe results
```

The two trees **mirror** each other but do not interleave. The spec tree describes what the system shall do, in observable terms. The architecture tree describes how the code realizes those behaviors. Cross-links between the trees are explicit: every architecture leaf names the spec leaves it realizes, and every spec leaf names the architecture leaves that realize it.

The depth of each tree matches the complexity of the work. A small work item may have a single spec doc + a single architecture doc (a degenerate root-only tree). A large work item may have three or four levels of subtrees. The structure is proportional, not fixed.

### Spec tree content

Each spec leaf is a markdown file containing:

1. **Leaf ID and title.** A stable identifier (`S03.1`, `S03.2`, ...) so downstream consumers can reference leaves without ambiguity. The ID is path-scoped within the subsystem.
2. **One-line summary.** The same line that appears in `spec/overview.md` under this subsystem.
3. **Context.** What this capability is, why it exists, what part of user intent it realizes.
4. **EARS requirements.** The acceptance criteria in EARS notation. Every observable behavior is one EARS statement.
5. **Edge cases and boundary conditions.** Named explicitly, each either expressed as an additional EARS statement or flagged as a non-requirement with reasoning.
6. **Cross-links.** "Realized by: architecture/<subsystem>/<module>" references.
7. **Verification notes.** One to three lines describing how a smoke test would exercise the behavior — what the trigger looks like, what the precondition setup looks like, what the response assertion looks like.

### Architecture tree content

Each architecture leaf is a markdown file containing:

1. **Leaf ID and title.** A stable identifier (`A03.1`, `A03.2`, ...).
2. **One-line summary.** Same line as in `architecture/overview.md`.
3. **Realizes.** Cross-links back to the spec leaves this component satisfies.
4. **Current state.** What exists in the codebase today, cited by file path and symbol.
5. **Target state.** What the component looks like after the design lands — module layout, interfaces, types, dependency directions.
6. **Interfaces.** Any public API or contract this component exposes, with type signatures or data shapes.
7. **Dependencies.** Which other architecture leaves this depends on, and which depend on it. This is the local import DAG slice.
8. **Open questions.** Structural questions design-orch could not answer with architectural reasoning alone — these escalate to feasibility.md probes or to impl-orch's pre-planning step.

### Root overview structure (both trees)

Each tree has a root `overview.md` that serves as an extended table of contents:

- **Purpose.** One paragraph on what this tree covers and what the design scope is.
- **TOC.** Every leaf in the tree, organized by subsystem, each with its stable ID and one-line summary. The TOC is structurally flat — readers see every leaf without having to open subtree overviews.
- **Root-level content.** System-wide invariants (for spec) or system-wide topology (for architecture). The spec root overview carries ubiquitous EARS requirements that apply across all subsystems; the architecture root overview carries the current + target structural posture for the whole system, including the import DAG slice, integration boundaries, and the structural delta that feeds refactors.md.
- **Reading order.** A short section suggesting which subtrees a given consumer should read first (e.g. "planner reads the root topology first, then refactors.md, then the subtree TOCs").

## EARS notation

Every acceptance criterion in a spec leaf uses one of five EARS patterns:

| Pattern | Template | Example |
|---|---|---|
| **Ubiquitous** | `The <system> shall <response>` | `The spawn runner shall emit one heartbeat every 30s while the spawn is live.` |
| **State-driven** | `While <precondition>, the <system> shall <response>` | `While a redesign cycle is active, dev-orch shall not initiate a new design session without a completed brief.` |
| **Event-driven** | `When <trigger>, the <system> shall <response>` | `When impl-orch emits a structural-blocking terminal report, dev-orch shall load the referenced redesign brief.` |
| **Optional feature** | `Where <feature>, the <system> shall <response>` | `Where a preservation hint exists, impl-orch shall scope pre-planning runtime probes to the invalidated phase range.` |
| **Complex** | `While <precondition>, when <trigger>, the <system> shall <response>` | `While the planner cycle cap is not yet exhausted, when a planner spawn returns with a probe-request report, impl-orch shall run the additional probes and re-spawn the planner.` |

EARS is not a stylistic preference. It is a **convergence requirement**. A spec leaf with prose requirements and no EARS statements is not converged on the spec axis. A spec leaf with EARS statements that reviewers cannot parse into trigger/precondition/response is not converged. The structure of the template surfaces gaps: an author trying to write "when <trigger>, the <system> shall <response>" who cannot name the trigger has discovered that the design doesn't know when the response fires.

Every EARS statement maps directly to a smoke test target:

- **Trigger** → test setup (the action that exercises the behavior)
- **Precondition** → test fixture (the state that must hold before the trigger)
- **Response** → test assertion (the observable outcome)

Smoke testers under v3 generate test cases by reading spec leaves and turning each EARS statement into an executable test. This is why the template is not optional — ambiguity in the spec produces ambiguity in the test.

### EARS does not imply TDD

EARS is the notation for requirements, not a test-first methodology. Coders do not write tests before implementing. Testers run smoke tests against committed behavior after the phase lands. Kiro uses EARS without TDD; v3 follows Kiro. This is a deliberate call against spec-kit's test-first approach, which the project's "prefer smoke tests over unit tests" rule would undermine anyway.

### EARS statements have IDs

Within a spec leaf, each EARS statement carries a stable ID for reference (`S03.1.e1`, `S03.1.e2`, ...). Testers cite these IDs when reporting verification results. Impl-orch's redesign brief cites them when bailing on falsification. The ID format is leaf-scoped so a spec leaf revision that preserves existing statements keeps their IDs stable; new statements get new IDs.

## Hierarchical TOC indexes

The root `overview.md` of each tree — and every subtree `overview.md` — acts as a TOC index:

- Every leaf in the subtree gets a one-line entry: `S03.1 (auth token refresh): when token expiry is under 60 seconds, the system shall refresh proactively before the next API call.`
- Entries are grouped by subsystem (at the root) or by capability/module (at subtree level).
- Entries link to the leaf file for drill-down.
- The TOC is exhaustive within its subtree: reviewers doing coverage passes see every leaf without opening files.

This is the hierarchical summary pattern from the agent-spec writing literature. It is required, not optional. A design package without root TOC indexes cannot converge.

## Refactors agenda

`design/refactors.md` holds the refactor agenda as a first-class artifact. Each entry names:

1. **What the refactor does.** A one-paragraph description of the rearrangement (split a module, extract an interface, collapse duplicated helpers, rename across consumers).
2. **Why the target architecture needs it.** Cross-link to the architecture tree node(s) that depend on this refactor landing first.
3. **What parallelism it unblocks.** Which architecture subtrees can then proceed in parallel.
4. **Files and modules touched.** Specific paths, specific symbols.
5. **Parallelism-prep classification.** `structural refactor` (rearrangement of existing code) or `foundational prep` (net-new scaffolding). Both can land in cross-cutting prep phases; the category distinguishes how the planner should think about them. See [terrain-contract.md](terrain-contract.md) §"Structural refactors vs foundational prep".

The planner consumes refactors.md top-to-bottom to build Round 1 of the plan. Each refactor entry either lands as a phase, bundles with another refactor entry into a single prep phase, or is explicitly skipped with a one-sentence reason. The planner's responsibility is to make every entry accountable; the design's responsibility is to make every entry real (no refactor speculation without a target-architecture justification).

Design-orch is the sole author of refactors.md during design. If impl-orch discovers during pre-planning that an additional refactor is needed (a runtime constraint the design missed), that's a planner→design escalation — impl-orch bails with `structural-blocking` and design-orch revises. The planner is not allowed to invent refactors; refactors that exist in the plan must exist in refactors.md.

## Feasibility.md — gap-finding as active design work

`design/feasibility.md` is the record of every probe design-orch ran during the design phase. Each entry names:

1. **What was checked.** Specific: "Codex app-server binary approval mode flag existence" or "Supabase JS client streaming API availability on version 2.47".
2. **How it was checked.** The command run, the schema extracted, the endpoint hit, the output captured.
3. **What the evidence showed.** The observed behavior, quoted from real outputs where possible.
4. **What design constraint it produced.** The architectural decision that rests on this evidence. Cross-linked to the architecture tree leaves that depend on it.

Probing is done during design, not deferred to impl-orch. Design-orch spawns @internet-researchers and @coder prototype spawns to validate assumptions before committing to architectural shapes. The cost of each probe is trivial compared to the cost of an architecture leaf that rests on an unchecked assumption.

### Known unknowns

Feasibility.md also carries **known unknowns** — questions design-orch identified but could not resolve from design-phase context alone. Each known unknown is tagged `impl-orch must resolve during pre-planning`. Impl-orch reads the tagged entries as its pre-planning probe inputs and answers them with runtime evidence, landing the answers in `plan/pre-planning-notes.md`.

### Why feasibility is a design output, not a sibling activity

Under v2, pre-planning was where runtime assumptions got validated. That worked but was too late — design-orch had already committed to architecture shapes based on unchecked assumptions by the time impl-orch ran probes. If the assumption turned out wrong, the bail-out fired from pre-planning (or worse, from mid-execution), and design had to revise. Pushing probing earlier catches the wrong assumption during design, where revising costs one doc edit instead of a bail-out cycle.

Impl-orch still runs probes during pre-planning, but those probes cover the known unknowns feasibility.md flagged plus any runtime constraints impl-orch notices that design could not anticipate (test suite shape, fixture races, env-var collisions). It does not re-run probes already recorded in feasibility.md.

## Problem-size scaling

Not every task earns the full hierarchical spec ceremony. Design-orch judges the scope and applies the appropriate depth:

- **Trivial work** — a one-line fix, a rename, a documentation typo. Skip design entirely. Dev-orch spawns a coder + verifier directly. No spec tree, no architecture tree, no design-orch spawn.
- **Small work** — single concept, few files, obvious structure. Design-orch produces a degenerate tree: `spec/overview.md` with ubiquitous EARS requirements and maybe a handful of event-driven ones, `architecture/overview.md` with the current + target posture, `refactors.md` (possibly empty), `feasibility.md` (what was probed). No subtrees. Root-only. The TOC overview is the whole document.
- **Medium work** — multiple subsystems, non-trivial integrations, some refactoring. Design-orch produces root overviews plus one level of subtrees. Each subsystem gets its own overview and a handful of leaves.
- **Large work** — multi-subsystem, protocol work, significant refactoring, many interacting capabilities. Full hierarchical structure with two or three levels of subtrees. Refactors.md and feasibility.md are substantial artifacts in their own right.

The test for which level applies is: can a reviewer hold the whole design package in working memory while reviewing it? If yes, stay at the current level. If no, promote to the next level. Forcing hierarchical overhead on small work is Fowler's critique of one-size-fits-all SDD; the v3 package dodges it by scaling depth to complexity.

If design-orch is uncertain about which level applies, err toward the lighter level and promote during review if the package gets too dense. Demotion is cheap; promotion is annoying but possible. Both are cheaper than producing a rigid over-specified package for work that didn't need it.

## `dev-principles` as convergence gate

During convergence (after reviewer fan-out has returned), design-orch explicitly loads the `dev-principles` skill and walks through the principles against the current design:

- **Refactor discipline.** Does the design require preparatory refactors? Are they in refactors.md?
- **Edge-case thinking.** Does every spec leaf enumerate edge cases, failure modes, and boundary conditions as explicit EARS statements or non-requirement flags?
- **Abstraction judgment.** Does the design introduce abstractions without at least three concrete instances? Does it duplicate cases that should stay duplicated?
- **Deletion courage.** Does the design propose code that has no clear active purpose?
- **Existing patterns.** Does the design match established project patterns where they solve the problem?
- **Structural health signals.** Does any architecture leaf exceed 500 lines or hold more than three responsibilities? Does any module's import list indicate rising coupling?
- **Integration boundary probing.** Has every external system the design touches been probed during feasibility? Are the probes recorded in feasibility.md?
- **Doc currency.** Does the design include updates to project documentation where behavior changes?

A principle violation is a convergence blocker unless design-orch records an explicit override in decisions.md with reasoning. This is the lightweight constitutional gate — the principles are already defined (no new artifact), and the gate is a mechanical check at convergence time. Any agent reading the design later can audit whether the gate was applied by reading decisions.md for override entries.

The gate is distinct from the reviewer fan-out. Reviewers apply their own focus areas and produce findings; the `dev-principles` gate is a design-orch self-check that runs after reviewers return. It catches things reviewers may have missed because they were focused on other axes.

## Active structural review during convergence

Design-orch's convergence is not done when the design is functionally correct and reviewers have signed off on alignment. It is done when the design is also *structurally decomposable*. The signal: a planner reading the architecture tree + refactors.md should be able to identify cross-cutting refactors to land first, then identify clusters of work that can run in parallel afterwards. If no such decomposition is visible, the design has not solved the structural problem.

This is hard to catch from inside design-orch's own context. The counterweight is a **required structural reviewer** in the design-phase fan-out. Required means: every design-phase fan-out includes a structural reviewer; the reviewer is never skipped; design-orch may not declare convergence without a PASS from the structural reviewer or a documented override recorded in decisions.md.

The structural reviewer is focused on the **architecture tree**, not the spec tree. Its brief:

**Read inputs:**
- `design/architecture/overview.md` (root topology, current + target posture)
- Every architecture leaf in scope
- `design/refactors.md` (the refactor agenda)
- `design/feasibility.md` (probe results that justify the target posture)
- `decisions.md` for rejected alternatives

**Verify architecture tree completeness:**
- Every architecture leaf cross-links to at least one spec leaf.
- Every spec leaf (via the spec TOC) is realized by at least one architecture leaf (cross-coverage check).
- Current state is cited by file path and symbol, not prose.
- Target state is derivable from the design; no aspirational targets with no backing.

**Verify refactors.md completeness:**
- Every structural problem in the current posture has a corresponding refactor entry or an explicit "preserve" reasoning.
- Each entry names the target architecture node that depends on it.
- Each entry names the parallelism it unblocks.
- Each entry names specific files and modules (no vibes).

**Sketch the decomposition:**
- Identify one or two cross-cutting prep cuts from refactors.md that the planner would land first.
- Identify at least two candidate parallel clusters from the architecture tree that could run after the prep lands.
- If the sketch fails (no prep cuts visible, fewer than two clusters identifiable), the design is not structurally decomposable. PASS is not allowed in this state; the reviewer pushes back with the gap.

**Apply SOLID-as-signals:**
- **SRP:** flag architecture leaves that own multiple unrelated concerns and would resist being decomposed by the planner.
- **ISP:** flag fat interfaces that force consumers to depend on methods they do not use.
- **DIP:** flag concrete-class dependencies that prevent the planner from substituting implementations across phases.

**Apply `dev-principles` structural signals:**
- Flag any architecture leaf that would exceed 500 lines or hold more than three responsibilities once implemented.
- Flag import list growth indicating rising coupling.
- Flag "adding one variant requires edits in N files" patterns.
- Flag abstractions accumulating conditionals across added variants.

**Output:**
- PASS / REQUEST CHANGES verdict.
- For PASS: explicit confirmation that the decomposition sketch worked and refactors.md is complete.
- For REQUEST CHANGES: the specific gap and the change that would close it.

The structural reviewer's findings feed back into the design like any other reviewer's findings — design-orch responds with revisions or pushes back with reasoning, and the loop iterates until convergence. Convergence is now functional + spec-testability + structural + `dev-principles`-compliant, not just functional.

## Reviewer fan-out

The reviewer fan-out runs across diverse strong models. Each reviewer has a focus area matched to a tree or artifact:

- **Spec reviewer.** Reads the spec tree. Focus areas: concreteness (every EARS statement is specific, not hand-wavy), testability (the response in each EARS statement is observable), coverage (edge cases and failure modes are enumerated), ambiguity (no prose slipping past EARS format). Spec reviewers generally run on strong models because ambiguity detection benefits from careful reading. Two spec reviewers on different model families is typical.
- **Architecture reviewer.** Reads the architecture tree + refactors.md. Focus areas: structural soundness (does the target topology realize the spec), refactor sufficiency (does refactors.md cover every structural problem the current posture has), parallelism readiness (can the architecture be decomposed into parallel subtrees). This is in addition to, not instead of, the required structural reviewer below.
- **Alignment reviewer.** Reads both trees and the cross-links. Focus areas: every spec leaf is realized (no orphans in spec), every architecture leaf justifies its existence against at least one spec leaf (no orphans in architecture), cross-links are mutual and consistent.
- **Refactor/structural reviewer (required).** Reads the architecture tree + refactors.md with the brief in "Active structural review during convergence" above. PASS required for convergence.
- **Feasibility reviewer (optional).** Reads `feasibility.md`. Focus areas: probe evidence is concrete (not "we assumed X works"), probes cover every external system the design touches, known unknowns are tagged for impl-orch pickup.

Cross-model diversity matters. Each model has different blind spots; the fan-out has to avoid overlapping them. Run `meridian models list` to see current options and staff accordingly. For high-risk designs, duplicate coverage on critical axes with both the default model and a specialist.

## Feasibility-questions skill

Design-orch loads the `feasibility-questions` skill and applies the four questions during final convergence. Answers land partly in feasibility.md (probe evidence) and partly in the architecture tree root overview (architectural posture). The four questions:

1. Is this feasible?
2. What can run in parallel?
3. Can this be broken down further?
4. Does something need foundational work first?

See [feasibility-questions.md](feasibility-questions.md) for the skill body. The key v3 change from v2: the answers now land in concrete artifacts (feasibility.md for question 1 probe evidence, architecture tree topology for question 2 cluster hypothesis, refactors.md for question 4 refactor agenda), not as a single Terrain section.

## Observations vs prescriptions (architecture tree)

The architecture tree describes the target system state as an observation about how the code *should be* after the design lands — not as a prescription for how to get there. Design-orch sees architecture; impl-orch sees architecture plus runtime. When design-orch prescribes "do phase 1 first, then 2, then 3/4/5 in parallel," impl-orch either follows blindly or deviates silently. Observations preserve design-orch's insight without locking in decisions that runtime data might contradict.

The spec tree is different. Spec leaves are **contracts**, not observations. Impl-orch cannot override a spec leaf; if runtime evidence contradicts one, impl-orch bails and the spec is revised. Different trees have different authority:

- **Spec tree** — authoritative. Impl-orch must satisfy it. Drift triggers bail-out, not workaround.
- **Architecture tree** — observational. Impl-orch may deviate if runtime evidence supports it, logging the deviation in decisions.md. The architecture tree describes intent; the decision log captures deviations.
- **refactors.md** — the refactor agenda is the planner's input. Planner may skip entries with reasoning, but cannot invent new refactors without escalating to design-orch.
- **feasibility.md** — the evidence record. Impl-orch trusts it as the design's probe output and only re-runs probes for items it specifically needs to re-verify.

## Decision log

Design-orch's decision log captures approaches considered, tradeoffs evaluated, what was rejected and why. Use the `decision-log` skill. Decisions are recorded as they are made, not retroactively. The decision log lives at `$MERIDIAN_WORK_DIR/decisions.md`, the same location as under v2.

The `dev-principles` gate can produce decision entries when a principle is overridden — the override and its reasoning land in decisions.md so downstream agents know why a principle was not applied.

## Skills loaded

- `meridian-spawn`, `meridian-cli`, `meridian-work-coordination` — coordination fundamentals.
- `architecture` — methodology for exploring structural approaches and making tradeoffs explicit.
- `agent-staffing` — composing review teams.
- `feasibility-questions` — the four shared questions. Same skill impl-orch and @planner load.
- `decision-log` — capturing design-time decisions.
- `dev-artifacts` — artifact placement conventions. The skill needs a coordinated update to match the v3 layout (spec tree + architecture tree + refactors.md + feasibility.md, scenarios removed). See "Required follow-up" below.
- `tech-docs` — technical writing methodology; applies to every design doc.
- `dev-principles` — loaded as the convergence gate. Applied after reviewer fan-out returns, before declaring convergence.
- `context-handoffs` — scoping what reviewers and architects receive.
- `caveman` — communication mode.

## What is deleted

- The scenarios convention. Spec leaves subsume scenarios at higher fidelity. No `scenarios/` folder is produced; no mentions of scenarios live in design-orch's body.
- The single-doc design overview with an inline Terrain section. Replaced by the two-tree structure plus refactors.md and feasibility.md.
- Phase prescriptions in the architecture tree. Architecture is observations; phase ordering belongs to the planner.

## What is added

- The two-tree structure: `design/spec/` (hierarchical spec tree with EARS leaves) and `design/architecture/` (hierarchical architecture tree).
- EARS notation mandate in every spec leaf. Non-EARS acceptance criteria are a convergence blocker.
- Root-level TOC overview in each tree, with every leaf summarized.
- `design/refactors.md` as a first-class design output, consumed directly by the planner.
- `design/feasibility.md` as a first-class gap-finding artifact, with known-unknowns flagged for impl-orch pickup.
- Problem-size scaling guidance — light path for small work, full ceremony for large work.
- `dev-principles` as a convergence gate, applied after reviewer fan-out.
- Reviewer fan-out split by tree (spec, architecture, alignment, structural, feasibility).
- Probe-driven design: gap-finding happens during design, not deferred.

## Required follow-up

The `dev-artifacts` skill in `meridian-dev-workflow` currently defines `design/`, `plan/`, `scenarios/`, and related artifacts. After v3 lands, the skill needs a coordinated edit to replace the scenarios section entirely and introduce the spec tree, architecture tree, refactors.md, and feasibility.md as the canonical design artifacts. This is a **required follow-up**, flagged in the v3 package for the user to pick up after approval. Design-orch should not edit the skill itself during this pass — the coordinated edit happens after the user approves v3.

The `planning` skill similarly needs a downstream edit to consume refactors.md directly and map phases to spec leaves. That edit is tracked in [planner.md](planner.md) §"Required follow-up".

## Open questions

None at this draft. Anything unresolved at review time gets a decision in [../decisions.md](../decisions.md).
