# Orchestrator Restructure: Overview

## What this is

A redesign of the dev-workflow orchestration topology that solves four structural problems: design phases that produce ambiguous or under-specified intent, plans going stale the moment impl-orch hits reality, no mechanism for bailing out when the design is wrong, and designs converging on shapes that block downstream parallelism.

The v2 package of this restructure addressed the last three. v3 extends it with a fourth axis: **spec-driven development** (SDD). Design-orch now produces hard concrete specs alongside a technical architecture, both hierarchical, both user-facing, both load-bearing. The shape is spec-anchored SDD in the Kiro mold — specs persist and stay authoritative through maintenance, verification runs against spec leaves, and there is no TDD mandate. See [design-orchestrator.md](design-orchestrator.md) for how design-orch produces the two trees and [planner.md](planner.md) for how they feed decomposition.

Read this first for orientation. The individual component designs live alongside:

- [dev-orchestrator.md](dev-orchestrator.md) — dev-orch body with autonomous redesign loop, terminated-spawn plan review contract, two-tree approval walk, and preservation-hint production
- [design-orchestrator.md](design-orchestrator.md) — design-orch producing a spec tree, an architecture tree, a refactor agenda, and gap-finding results, with EARS notation mandated in spec leaves
- [impl-orchestrator.md](impl-orchestrator.md) — impl-orch with a pre-planning step, a planner spawn, a pre-execution structural gate, a planning cycle cap, and an escape hatch keyed on runtime evidence falsifying spec leaves
- [planner.md](planner.md) — @planner rehomed under impl-orch with parallelism-first decomposition as the central frame, consuming the architecture tree + refactors.md + spec leaves as input
- [terrain-contract.md](terrain-contract.md) — shared artifact contract for refactors.md and feasibility.md; defines the structural analysis work that produces them
- [preservation-hint.md](preservation-hint.md) — data contract for the redesign-cycle preservation artifact dev-orch produces between cycles
- [feasibility-questions.md](feasibility-questions.md) — shared skill design-orch, impl-orch, and @planner all load
- [redesign-brief.md](redesign-brief.md) — artifact format for impl-orch bail-out (covers both execution-time and planning-time arms)

## The four problems

**Requirements dissolve into hand-wavy design prose.** When design docs describe intent in paragraphs, agents reading the design have to reconstruct the acceptance criteria from context. Two agents reading the same paragraph reach different conclusions about what "correct" means. Testers default to happy-path coverage because the edge cases never made it out of the designer's head. Plans miss scenarios because the plan author did not see them as testable units. The v2 package addressed this partially with a `scenarios/` folder, but scenarios lived in a separate convention from the design and had to be cross-walked manually. v3 folds the contract into the design itself by making EARS-format spec leaves the acceptance criteria.

**Plans go stale the moment impl-orch hits reality.** The pre-v2 flow was design-orch → planner → impl-orch, with the planner committing to phase ordering, staffing, and scenario ownership before any agent had runtime context. Then impl-orch started executing and discovered what the plan couldn't know — collateral damage in unexpected test fixtures, shared state that prevents parallelism, environmental assumptions that don't hold. The plan was wrong in the most expensive way: after another agent had already started consuming it.

**There is no escape hatch when the design is wrong.** Impl-orch could fix phases, adapt scope, and spawn reviewers, but could not say "this foundational assumption is falsified and continuing will compound the error." Multi-model post-impl review caught HIGH findings that were predictable from the design enumeration, but by then it was too late to redirect.

**Design converges on shapes that block downstream parallelism.** A design can be functionally correct, internally consistent, and review-converged — and still land a target system state that is too coupled to decompose into phases that run in parallel. The planner inherits whatever structure the design hands it; if the structure is tangled, the plan is sequential no matter how skilled the decomposition. The restructure treats structure and modularity as design-time concerns paired with active structural review, not as implementation craft to be sorted out later.

## The shape

Three orchestrators, one rehomed planner agent, one shared skill, three artifact contracts, and — new in v3 — a two-tree design output.

### Design output: two hierarchical trees plus two sibling artifacts

Design-orch produces four artifacts, not one:

```
design/
  spec/                        # hierarchical specification tree (business intent)
    overview.md                # TOC index of every spec leaf with one-line summaries, plus root system-level invariants
    <subsystem>/
      overview.md              # TOC for this subtree; subsystem-level contracts
      <capability>.md          # leaves with EARS-format acceptance criteria
  architecture/                # hierarchical technical design tree
    overview.md                # TOC index + root topology (current + target posture, module layout, integration boundaries)
    <subsystem>/
      overview.md              # TOC for this subtree; subsystem internal topology
      <module>.md              # leaves with interface contracts, types, dependency directions
  refactors.md                 # refactor agenda consumed directly by @planner
  feasibility.md               # gap-finding / probe results from design-phase investigation
```

The two trees mirror each other. Every architecture node exists to realize one or more spec nodes, and every spec leaf is covered by one or more architecture leaves. Cross-links are explicit references between the trees, not interleaving within a single doc. The spec tree is business-level (what the system shall do, in observable terms); the architecture tree is technical-level (how the code realizes those behaviors). Thoughtworks' separation of business and technical specs is the anchor for the split.

The root-level `overview.md` in each tree is an extended table of contents. Every leaf gets a one-line summary, organized by subtree, so reviewers and the planner can navigate the trees without loading everything. Context offloading is a first-class design concern — agents reading a design package should read the root overview cheaply and pull leaves on demand. This is the hierarchical summary pattern from the agent-spec writing literature, promoted to a requirement.

### EARS notation in spec leaves

Every acceptance criterion and observable behavior in a spec leaf uses an EARS (Easy Approach to Requirements Syntax) template. The five canonical patterns:

- **Ubiquitous:** `The <system> shall <response>`
- **State-driven:** `While <precondition>, the <system> shall <response>`
- **Event-driven:** `When <trigger>, the <system> shall <response>`
- **Optional feature:** `Where <feature>, the <system> shall <response>`
- **Complex:** `While <precondition>, when <trigger>, the <system> shall <response>`

EARS forces triggers, preconditions, and expected responses to be explicit — hand-wavy requirements don't fit the templates and surface as gaps while the spec leaf is being written. Every EARS requirement maps directly to a smoke-test target: the trigger becomes the test setup, the precondition becomes the fixture, the response becomes the assertion. Verification under v3 is "does the implementation satisfy spec leaves X, Y, Z?" — answered by running smoke tests that exercise the behavior the EARS requirements describe.

### Refactors as a first-class artifact

`design/refactors.md` holds the refactor agenda as a first-class artifact that planner consumes directly as a decomposition input. Each refactor entry names what it does, why the target architecture needs it, what parallelism it unblocks, and what files/modules it touches. Planner sequences cross-cutting refactors first to unlock parallel feature work downstream — this is the central parallelism-first mechanism. Promoting the refactor agenda out of the architecture tree and into its own file means the planner does not have to walk the tree to reconstruct what needs to land first; the plan's Round 1 is derived from reading refactors.md top-to-bottom.

### Feasibility / gap-finding as a first-class artifact

`design/feasibility.md` holds the record of what design-orch actively probed during the design phase — real binary outputs, schema extractions, smoke probes, assumption validations. Each entry names what was checked, what the evidence showed, and what design constraint it produced. Gap-finding is not a sibling activity to design — it's part of design, and its outputs are part of the design package. Designing against training-data assumptions instead of real-system behavior is the failure mode this artifact exists to prevent. Impl-orch reads feasibility.md during pre-planning so it does not re-run the same probes; planner reads it to understand which architectural constraints rest on verified evidence and which on inference.

### Orchestrators

**dev-orchestrator** stays as the continuity with the user but gains an autonomous redesign loop, a two-tree approval walk, and a preservation-hint production responsibility. The approval walk is concrete: dev-orch walks the user through `spec/overview.md` + `architecture/overview.md` + `refactors.md` by default, and the user can drill into any subtree on demand — not leaf-by-leaf approval. When impl-orch bails with a redesign brief — execution-time, structural-blocking, or planning-blocked — dev-orch routes a scoped redesign back to design-orch without waking the user, writes the preservation hint after the design revision converges, and spawns a fresh planning impl-orch with the revised design and the hint attached. Loop guards prevent pathological oscillation. Plan review uses a terminated-spawn contract: planning impl-orch terminates with a plan-ready report, dev-orch reads the plan from disk, dev-orch spawns a fresh execution impl-orch.

**design-orchestrator** produces the spec tree, the architecture tree, the refactor agenda, and the feasibility record. EARS notation is mandated in spec leaves. Gap-finding is an active design-phase activity — probe real systems during design, not reason about them from training data. Refactor planning is a design output, not left for planner to invent. The design-phase reviewer fan-out includes spec reviewers (concreteness, testability, coverage, ambiguity), architecture reviewers (structural soundness, refactor sufficiency, parallelism-readiness), alignment reviewers (cross-links between the trees), and a refactor/structural reviewer focused on the architecture tree. `dev-principles` is loaded as a hard gate during convergence — "does this design violate any project-wide structural principles?" blocks convergence if answered yes. Convergence requires a PASS from the structural reviewer or a documented override.

**impl-orchestrator** opens with a pre-planning step before spawning any coders, then spawns @planner. Pre-planning reads the design, the architecture tree's root overview, the refactors agenda, feasibility.md, and any preservation hint from a prior cycle, then answers the four feasibility questions against runtime context (probes, dependency walks, file scans), and writes pre-planning notes to disk as module-scoped facts. Verification framing shifts under v3: "does this phase satisfy spec leaves X, Y, Z?" — not "does this phase's code work?" The escape hatch sharpens: bail-out fires when runtime evidence contradicts a spec leaf, and the redesign brief cites the falsified leaves explicitly. Spec drift enforcement: if impl-orch discovers runtime evidence that contradicts a spec leaf, the spec must be revised before code changes land — no silent spec bypass.

**@planner** survives as a separate agent profile but rehomes under impl-orch as its caller. Its central frame stays parallelism-first decomposition. Under v3, planner's inputs are concrete: the architecture tree + refactors.md + spec leaves, with the plan mapping every phase to the spec leaves it satisfies. Parallelism comes from disjoint architecture subtrees plus disjoint spec-leaf coverage. Planner does not invent refactors — if runtime evidence shows a refactor is needed that design missed, that's a planner→design escalation (structural-blocking), not a plan add-lib move.

**feasibility-questions skill** carries the four questions design-orch, impl-orch, and @planner ask: is this feasible, what can run in parallel, can we break it down further, does something need foundational prep first? Shared skill so all passes stay consistent.

**Three artifact contracts** support the topology:
- **[terrain-contract.md](terrain-contract.md)** — structural analysis workflow that feeds `refactors.md` and `feasibility.md`; required fields, evidence requirements, structural-prep tagging, fix_or_preserve enum.
- **[preservation-hint.md](preservation-hint.md)** — preserved/partially-invalidated/fully-invalidated phase tables, replan-from-phase anchor, new spec leaves, replayed constraints.
- **[redesign-brief.md](redesign-brief.md)** — falsification case citing spec leaves for execution-time bail-outs, parallelism-blocking structural issues for planning-time bail-outs.

## Problem-size scaling

Not every task earns a hierarchical spec tree. A one-line fix does not justify a multi-leaf spec with EARS criteria and a companion architecture tree. Design-orch's body (see [design-orchestrator.md](design-orchestrator.md) §"Problem-size scaling") calls out when the full SDD ceremony is warranted and when lighter-weight design is appropriate. The default is: if the work item needs at least two design docs under the old topology, it earns a spec tree and an architecture tree at v3. If the work item is small enough that the old topology would have used a single design doc or a brief notes file, v3 uses a single spec doc + a single architecture doc as a degenerate tree (root-only, no subtrees). Truly trivial work — a one-line fix, a rename, a documentation typo — skips design entirely and goes straight to a coder + verifier from dev-orch, as it did before.

Forcing hierarchical spec overhead on work that doesn't need it is the Fowler critique of one-size-fits-all SDD: spec bloat, review overhead on verbose markdown, control illusion. The v3 package dodges it by making the depth of the tree proportional to the complexity of the work, not a fixed template.

## Why two trees

Under the v2 package and earlier topologies, the design was a single hierarchical set of docs that interleaved intent, invariants, structural posture, module layout, and interface contracts in the same pages. That worked for small designs and failed for anything with more than a few moving parts: reviewers trying to check "is this testable?" had to extract acceptance criteria from paragraphs; reviewers trying to check "is this decomposable?" had to extract module layout from the same paragraphs; the planner trying to extract refactor candidates had to walk the whole thing.

Separating the spec tree from the architecture tree is the Thoughtworks move: business-level intent (what the system shall do, in observable terms) is its own thing, and technical-level realization (which modules own which responsibilities) is its own thing. Each tree has its own reviewer focus area and its own convergence criteria. The cross-links between them enforce coverage: every spec leaf must be realized by at least one architecture leaf, and every architecture leaf must justify its existence against at least one spec leaf. When the cross-links are missing, either the architecture has code without a purpose or the spec has an intent with no realization — both are design gaps that reviewers catch by looking at the links.

The two-tree structure also composes with parallelism. A planner decomposing work for parallel execution looks at the architecture tree's subtree structure to find disjoint surfaces and at the spec tree's leaf distribution to find disjoint verification coverage. Parallel phases are phases that touch disjoint architecture subtrees *and* satisfy disjoint spec leaves. Both conditions matter — interface-independent phases that share spec leaves still collide at the verification layer.

## Why EARS

Requirements written in prose drift as they get rewritten. Requirements written in EARS patterns either fit the template or they don't. The template forces the author to name the trigger, the precondition, and the expected response — the three things testers need to write the verification. An author who cannot fit a requirement into EARS has discovered a gap: the trigger is unknown, the precondition is implicit, or the response is hand-wavy. That gap surfaces during design, which is where it is cheapest to fix.

EARS is also AI-friendly in a way prose is not. An agent reading an EARS requirement can generate test fixtures mechanically: trigger → setup, precondition → guard, response → assertion. An agent reading a prose requirement has to guess. Smoke testers generating tests from spec leaves under v3 do not guess.

No TDD mandate comes with EARS. Kiro uses EARS without TDD; spec-kit uses EARS with TDD. v3 follows Kiro. Coders do not write tests first. Testers run smoke tests against committed behavior and report which spec leaves are satisfied, which are violated, and which are not yet covered. The project's existing "prefer smoke tests over unit tests" rule from CLAUDE.md remains the verification strategy; EARS gives smoke testers a concrete contract instead of an imagined one.

## Why hierarchical TOC indexes

Design packages get large. v2 packages routinely ran to tens of thousands of tokens across the design folder. Agents reading the design to do downstream work — planner, impl-orch, reviewers — paid the cost of loading the whole folder even when they only needed one subsystem.

A root-level overview that lists every leaf with a one-line summary lets the reader orient cheaply and load the specific leaves they need. The planner reading `spec/overview.md` sees "S03.1: auth token refresh fires when expiry minus 60 seconds" and knows whether that leaf is in scope for the phase they are designing. A reviewer doing a coverage pass reads the overview to find leaves with no cross-link to the architecture tree without having to open every file. The cost of producing the overview is small; the cost of not having it is paid by every consumer downstream.

The pattern generalizes. At the subsystem level, `spec/<subsystem>/overview.md` does the same job for leaves inside that subsystem: a TOC of capability summaries, enabling drill-down without full-tree traversal. The tree can be as deep as the work needs; each node has its own overview.

## Why refactors as a named artifact

Parallelism-first planning hinges on landing cross-cutting refactors first, so feature work on disjoint surfaces can then run in parallel without merge hell. Under v2, refactor candidates lived inside the Terrain section of the design overview, and the planner extracted them by walking the structural delta. That worked but lost prominence — refactors were buried alongside architectural observations and the planner had to re-derive which entries were refactor candidates vs which were informational.

Promoting refactors to their own file (`design/refactors.md`) does three things. First, the planner reads refactors.md top-to-bottom to build Round 1 of the plan; no extraction step, no derivation. Second, design-orch is forced to think about the refactor agenda as a design output, not an implicit by-product — refactors get reasoned about during design, not left as a planner surprise. Third, the refactor agenda is auditable: a reviewer scanning refactors.md can ask "does this cover every structural problem the current architecture has?" and find the answer by reading one file.

## Why feasibility as a first-class artifact

Designing against training-data assumptions is how teams commit to libraries that don't do what they thought, architectures that have well-known failure modes, and protocol shapes that the real binary doesn't expose. The v2 package had impl-orch run probes during pre-planning to catch falsified assumptions late. v3 pushes probing earlier: design-orch probes real systems during the design phase and records the results in feasibility.md. Impl-orch reads feasibility.md during pre-planning and does not re-run the same probes; the runtime context is already in the design package.

Each feasibility entry names what was checked, what the evidence showed, and what design constraint it produced. "We probed the Codex app-server binary — it has no `--approval-mode` flag, confirmed by running `codex app-server --help` on version 0.25.0. Design constraint: the permission pipeline must express approval modes through a different channel." Without this record, the constraint would be implicit in the design author's head and would dissolve during review. With it, the constraint is citable, re-verifiable, and directly consumable by downstream agents.

Gap-finding is distributed across the design-orch body, not confined to a single phase. Every probe result lands here; every assumption validated lands here; every known unknown impl-orch inherits lands here with an explicit "impl-orch must resolve this during pre-planning" tag.

## Why no TDD, smoke tests against spec leaves

SDD does not require test-first development. Kiro explicitly does not mandate TDD; spec-kit does. The v3 package follows Kiro — coders implement phases and testers verify behavior against the spec leaves the phase claims to satisfy. Verification is "did the implementation achieve spec leaves X, Y, Z?" — answered by smoke tests that exercise the EARS-described behavior. Unit tests stay surgical per the project's existing rule: only for logic that is hard to smoke test (concurrency, parsing edge cases, signal handling, sync engine algorithms).

The reason TDD does not earn its cost here is that the project's testing culture already prefers smoke tests over unit tests for correctness, and the cost of writing tests before the code exists is duplicated work when the design is still converging. A coder who writes tests against a spec leaf that later gets revised does the work twice. A coder who implements first and runs smoke tests against the converged spec does the work once.

Scenarios as a separate concept go away. The v2 package had a `scenarios/` folder that duplicated edge-case enumeration alongside the design. Spec leaves subsume scenarios at higher fidelity — an EARS requirement is a scenario with a template applied. Every mention of scenarios in the v2 package is replaced with spec-leaf references in v3.

## Why observations, not recommendations (architecture tree)

Design-orch sees architecture and impl-orch sees runtime. When design-orch prescribes phase ordering, impl-orch either follows blindly (wasting its runtime knowledge) or deviates silently (losing traceability against the design). Observations preserve design-orch's insight without locking in decisions made without runtime context. "Module X is a leaf in the import DAG" is a fact impl-orch can use. "Do X first" is a prescription that may or may not survive impl-orch's discoveries.

Under v3, the observations live in the architecture tree (and feasibility.md for probe-backed facts). The spec tree, by contrast, is declarative and authoritative — spec leaves are not observations, they are contracts. Impl-orch cannot override a spec leaf; if runtime evidence contradicts one, impl-orch bails and the spec is revised. The architecture tree is observation-space (how the current code is and how it will be), the spec tree is contract-space (what the system shall do). Different agents have different authority over the two trees.

## Why every layer asks the same questions

Feasibility, parallelism, breakdown, and foundational prep are questions with different answers at different altitudes. Design-orch answers them with architectural data and probe evidence, landing the answers in feasibility.md and refactors.md. Impl-orch re-answers them in its pre-planning step with runtime data — probes, dependency walks, file scans, env-var collisions — and writes the runtime-informed answers to its pre-planning notes. The planner then consumes both passes and uses the same four questions to guide the decomposition itself. A shared skill keeps every pass aligned so the answers reinforce each other.

## Why the escape hatch triggers on spec falsification, not failure

Bail-out is expensive — it invalidates in-flight work and restarts a design cycle. Triggering on every test failure or every tester finding makes impl-orch paralyzed. Not triggering at all reproduces the v1 problem where flawed designs ship under patch pressure.

Under v3 the trigger is: runtime evidence contradicts a spec leaf. A test failure against code that is still being implemented is a bug, fixable in-place. Collateral damage is mechanical, fixable with a cleanup coder. But a smoke test revealing that the behavior the spec leaf requires is not achievable — that's falsification, and patching past it means the next phase builds on broken contract. The redesign brief cites the specific spec leaf IDs the evidence contradicts, so design-orch on revision knows exactly which leaves to revise.

Spec drift enforcement is the other half. If impl-orch discovers during execution that the spec is wrong — not just that the code does not yet satisfy it, but that the spec itself describes behavior the system cannot or should not have — the spec must be revised before code changes land. Quiet workarounds that leave the code satisfying unstated behavior while the spec says something else are exactly the drift Fowler warns about. The redesign brief is the mechanism: bail out, revise the spec, resume.

## Why dev-principles as a convergence gate

SDD research describes "constitutional gates" — a set of project-wide principles that every design must satisfy before being approved. Spec-kit implements this with an explicit constitution file; v3 reuses the project's existing `dev-principles` skill for the same purpose. During convergence, design-orch loads `dev-principles` and asks "does this design violate any project-wide structural principles?" — a no answer blocks convergence. This is the lightweight version of constitutional gates, reusing machinery the project already has without adding a new artifact.

The principles are not discovered at convergence time; they are the fixed set in `dev-principles`. Convergence is the point at which they get applied to the concrete design. A design that violates refactor discipline, edge-case thinking, abstraction judgment, structural health signals, or integration boundary probing fails the gate.

## Why dev-orch handles redesign autonomously

The user is a bottleneck on response time, not on judgment. Dev-orch has the original requirements, the design context, and the redesign brief — it has everything it needs to scope a redesign session and route it back to design-orch without waking the user. Asking for permission is asking for permission to do the thing that is already the right move.

Autonomy with visibility matters, though. The user sees every bail-out and every redesign cycle, can intervene at any time, and the final report surfaces how many cycles happened and why. Autonomy earns its keep by being transparent enough to audit after the fact.

## Why loop guards

Pathological oscillation is possible: a redesign that fixes one thing and breaks another, triggering a new bail-out. Loop guards are a heuristic for when dev-orch should notice its own confidence is dropping and escalate to the user. A single cycle is a normal mid-course correction. Two cycles is a scoping problem worth noticing. Three cycles suggests the scoping of the redesign itself is wrong and a human should look. The guard is a threshold for escalation, not a hard cap on progress.

## Why partial work preserves by default

Each committed phase represents verified behavior against the spec leaves it claimed. Throwing it away because a later phase revealed an issue means throwing away work that still satisfies its spec leaves. The redesign brief names explicitly which phases are invalidated (and which spec leaves they were satisfying that are now falsified), and anything unnamed stays committed. Default-preserve makes the cost of redesign proportional to the scope of the actual change, not to the position in the plan where the issue was discovered.

## Why structure and modularity are first-class design concerns

The framing: "structure and modularity and SOLID are important so we can move fast with parallel work." This is not abstract craftsmanship — it is the enabler that makes parallelism-first planning possible at all. If the design lands a tangled architecture tree, the planner cannot decompose it for parallelism no matter how hard it tries. Every phase ends up reading from and writing to the same coupled surfaces, parallel coders race each other, and the plan collapses to sequential execution.

The restructure pushes structural concerns up the lifecycle. They cannot live as implementation craft to be sorted out by coders or refactor reviewers after the fact, because by then the architecture tree has already committed to a shape that determines what is decomposable. How that lands in v3:

- **Architecture tree carries explicit current + target structural posture** at its root overview, including the import DAG slice, SOLID-shaped observations, coupling risks, and the delta between current and target. The delta becomes the refactor agenda.
- **refactors.md** is a direct design output, not a planner invention. Planner consumes it top-to-bottom.
- **The reviewer fan-out includes a structural/refactor reviewer by default in the design phase**, focused on the architecture tree. That reviewer is loaded with explicit instructions to flag when the architecture is not modular enough to enable parallel work downstream.
- **`dev-principles` loaded as convergence gate** catches refactor discipline violations design-orch may have missed.

The signal to design-orch is: a design that converges with reviewers but leaves the architecture as coupled as it found it should be treated as not-yet-converged, even if no functional issue is flagged. Structural decomposability is part of the convergence criteria, not a nice-to-have.

## Scope of this restructure

Four agent rewrites: dev-orchestrator, design-orchestrator, impl-orchestrator, planner. No agent deletions. The parallelism-first frame stays inlined into the planner profile body. EARS notation is a new expectation that lives in the design-orchestrator body. Two existing skill updates are follow-ups: `dev-artifacts` documents the spec tree + architecture tree + refactors.md + feasibility.md layout (replacing the scenarios section entirely), and `planning` shifts emphasis to parallelism-first decomposition. One new skill exists: `feasibility-questions`. Three artifact contracts under `design/`: `terrain-contract.md`, `preservation-hint.md`, `redesign-brief.md`.

No behavioral change to coders, testers, reviewers, or any leaf agent. The restructure is entirely at the orchestrator and planner layer.

## Decision log

Decisions made while drafting this package live in [decisions.md](../decisions.md). v2's D1-D15 decisions are preserved; v3 adds D16-D23 and marks reversals explicitly where v3 supersedes v2 commitments.
