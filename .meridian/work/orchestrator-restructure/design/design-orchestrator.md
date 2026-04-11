# Design Orchestrator: Target Shape

This doc describes the design-orchestrator's behavior after the restructure. The core activity (producing reviewed design docs) stays the same, but design-orch gains three additions: a Terrain section in the design overview, the `feasibility-questions` skill as a shared lens with impl-orch and @planner, and **explicit emphasis on structural and modularity concerns as design-time work**, paired with a required structural reviewer in the design-phase fan-out.

Read [overview.md](overview.md) first for context. The reasoning behind the structural emphasis lives in the "Why structure and modularity are first-class design concerns" section there. The Terrain section is a shared artifact contract — its required fields, evidence requirements, and consumer expectations live in [terrain-contract.md](terrain-contract.md), not inline in this doc. This body references the contract; it does not re-state it.

## What design-orch does

Still turns requirements into a reviewed design specification. Design docs describing the target system state, edge cases enumerated, scenarios seeded in `scenarios/`, decisions logged. All of that carries over unchanged from the current topology.

What changes:

- The design overview now carries a Terrain section that captures structural observations about the design — including whether the target state fixes the existing structural problems or preserves them.
- Design-orch answers the four feasibility questions from the shared skill as part of its own convergence before handing off.
- Design-orch's body carries explicit emphasis on modularity, cohesion, and interface boundaries as design-time concerns, treated as convergence criteria rather than implementation craft.
- The reviewer fan-out includes a refactor/structural reviewer by default, with explicit instructions to flag when the design is not modular enough to enable parallel work downstream.

## Why the Terrain section exists

The restructure rehomes the @planner under impl-orch and adds a pre-planning step where impl-orch gathers runtime context. But the planner — and impl-orch's pre-planning — both need structural information the design-orch has and they do not yet: what is coupled, what is a leaf in the import DAG, what interfaces are shared and would cause ripple damage if changed late, what integration boundaries need protocol probing before coding, what modules are foundational and should land first.

Without that information written down, impl-orch's pre-planning step would either re-derive it (expensive, duplicated work) or miss it (the planner inherits a structural blind spot that no amount of decomposition skill can fix). The Terrain section gives impl-orch and the planner a starting point they can trust without being prescriptive about how to use it.

## What the Terrain section contains

The Terrain section lives at the end of `design/overview.md`. It holds observations framed as facts, risks, and opportunities — not phase prescriptions. The goal is for impl-orch and the planner reading the section to be able to answer questions like "which modules must land first?", "which changes are going to ripple?", "what has to be probed against a real binary?", and most importantly "is the target state actually decomposable, or does it preserve the coupling that blocks parallel work?" without guessing.

The full required-field list, evidence requirements, format for the structural delta, and `fix_or_preserve` enum are specified in [terrain-contract.md](terrain-contract.md). Design-orch produces every required field in the order the contract specifies. Missing fields are a convergence blocker, not a stylistic choice. In particular:

- The structural delta uses the `[structural-prep-candidate: yes|no]` tagging the contract requires — that tag is the explicit handoff to the planner for cross-cutting refactor identification.
- The `fix_or_preserve` field uses the contract's enum (`fixes` | `preserves` | `unknown`), each with a required reasoning paragraph. `preserves` and `unknown` are convergence blockers on the structural axis.
- The parallel-cluster hypothesis names at least two clusters with specific modules, per the contract's evidence requirement.

The section is written as observations, not recommendations. The difference is that observations describe the terrain; recommendations describe the route. Design-orch is the cartographer, not the navigator. But design-orch *is* responsible for noticing when the cartography itself shows a target state that no navigator can decompose into parallel routes — that responsibility is what the `fix_or_preserve` field and the structural reviewer are for.

## Active structural review during convergence

Design-orch's convergence is not done when the design is functionally correct and reviewers have signed off on alignment. It is done when the design is also *structurally decomposable*. The signal: a planner reading the design and Terrain should be able to identify cross-cutting refactors to land first, then identify clusters of work that can run in parallel afterwards. If no such decomposition is visible, the design has not solved the structural problem.

This is hard to catch from inside design-orch's own context — design-orch is biased toward shipping the design it has converged on, and "is this decomposable?" is a question its own reviewers may not ask if they are focused on functional correctness. The counterweight is a **required** structural reviewer in the design-phase fan-out. Required means: every design-phase fan-out includes a structural reviewer; the reviewer is never skipped; design-orch may not declare convergence without a PASS from the structural reviewer or a documented override recorded in `decisions.md`. The structural reviewer is one of the focus-area reviewers in the standard fan-out (no separate phase, no separate gate), but its inclusion in the fan-out is mandatory and its sign-off is a convergence prerequisite.

The structural reviewer is loaded with this brief:

**Read inputs:**
- The full design package, including `design/overview.md` and the Terrain section per [terrain-contract.md](terrain-contract.md).
- The decisions log to understand what alternatives were rejected and why.

**Verify Terrain contract compliance:**
- Every required field from the contract is present.
- Posture sections cite specific files, imports, and symbols (not generic prose).
- The structural delta has explicit `structural-prep-candidate: yes|no` tags on every item.
- `fix_or_preserve` has a value other than `unknown` and a reasoning paragraph. Treat `unknown` the same as `preserves` — push back until the answer is concrete.
- The parallel-cluster hypothesis names at least two clusters with specific modules.

**Sketch the decomposition:**
- Identify one or two cross-cutting prep cuts the planner would need to land first to unlock parallelism.
- Identify at least two candidate parallel clusters that could run after the prep lands.
- If the sketch fails (no prep cuts visible, fewer than two clusters identifiable), the design is not structurally decomposable. PASS is not allowed in this state; the reviewer pushes back with the gap.

**Apply SOLID-as-signals:**
- **SRP (Single Responsibility):** flag classes or modules that own multiple unrelated concerns and would resist being decomposed by the planner.
- **ISP (Interface Segregation):** flag fat interfaces that force consumers to depend on methods they do not use, blocking interface-narrowing refactors.
- **DIP (Dependency Inversion):** flag concrete-class dependencies that prevent the planner from substituting implementations across phases or test doubles in parallel test paths.

These are signals the reviewer reports on, not laws to enforce mechanically. The point is that "the design preserves the coupling" should land as a concrete SOLID-shaped finding, not as vibes-based prose.

**Identify anti-patterns:**
- 3-5 specific anti-pattern signals from the affected surface (e.g. "parser and persistence concerns mashed in `auth/handler.py`", "global registry write in `tokens/init.py` couples every caller", "duplicated config loaders in three modules").
- Each finding names the file, the symbol, and the structural problem.

**Output:**
- PASS / REQUEST CHANGES verdict.
- For PASS: explicit confirmation that the decomposition sketch worked and the contract fields all check.
- For REQUEST CHANGES: the specific gap and the cut that would close it.

The structural reviewer's findings feed back into the design like any other reviewer's findings — design-orch responds with revisions or pushes back with reasoning, and the loop iterates until convergence. Convergence is now functional + structural, not just functional. A design that converges with reviewers but leaves the structural posture as it found it must be treated as not-yet-converged on the structural axis even if no functional issue is flagged.

## Why observations and not recommendations

Design-orch sees architecture. Impl-orch sees architecture plus runtime. When design-orch prescribes "do phase 1 first, then 2, then 3/4/5 in parallel," impl-orch either follows blindly or deviates silently. Blind following wastes runtime knowledge (the phases might share a test suite and parallelism would cause cross-talk). Silent deviation loses the traceability link back to the design.

Observations preserve design-orch's structural insight without locking in decisions that runtime data might contradict. Impl-orch reads observations and uses them as inputs when answering the same feasibility questions with its own runtime context.

If design-orch finds itself wanting to prescribe a specific phase ordering, the right move is to capture the structural fact that implies that ordering ("module X is a leaf with zero reverse dependencies"), not the ordering itself. Impl-orch will arrive at the same conclusion if the fact is sound and will have better information if it is not.

## Why design-orch loads the feasibility-questions skill

The feasibility questions are asked twice — once at design time, once at execution time — and the answers matter at both altitudes. Design-orch loading the skill makes the first pass structured and consistent with what impl-orch will ask later, which means the two passes reinforce each other.

Without the shared skill, design-orch might ask the questions in its own ad-hoc way and impl-orch would ask them in a different ad-hoc way, and the answers would drift over time as both agents' bodies were edited independently. A shared skill keeps the frame fixed.

The skill body is in [feasibility-questions.md](feasibility-questions.md). Design-orch applies it during its final convergence pass, before presenting the design package to dev-orch, and captures the answers in the Terrain section.

## Edge case enumeration and scenarios stay the same

The current design-orch behavior of enumerating edge cases and seeding `scenarios/` with concrete testable scenarios is unchanged. The restructure does not alter the scenarios-as-verification-contract pattern — if anything it depends on it, because impl-orch's phase convergence gates on scenario verification.

Every edge case the design enumerates still gets a corresponding scenario file. Every gap flagged in an audit or investigation report still gets a scenario. The lifecycle in `dev-artifacts` stays as-is.

## Decision log stays the same

Design-orch's decision log captures approaches considered, tradeoffs evaluated, what was rejected and why. The restructure does not change this — if anything, Terrain observations and decision-log entries are complements: observations state the facts, decisions state what was chosen in response.

## Reviewer fan-out

The current pattern of spawning diverse-model reviewers with focus areas (design alignment, type contract, permission pipeline, refactor) carries over with two adjustments:

- **Refactor/structural reviewer is required in every design-phase fan-out** — not optional, not "default-on with override," not skippable for trivial work. The reviewer is loaded with the brief in "Active structural review during convergence" above. Its job is to evaluate decomposability for parallel work, not just to flag code-quality concerns. Design-orch may not declare convergence without a PASS from the structural reviewer or a documented override in `decisions.md`.
- **Terrain contract and feasibility questions are explicit review targets.** Reviewers should flag when Terrain fields are missing or under-evidenced, when `structural-prep-candidate` tags are missing from delta items, when the `fix_or_preserve` answer is wrong, absent, or `unknown`, when fewer than two parallel clusters are named, when integration boundaries are glossed over, when the four feasibility questions have not been answered or have been answered with hand-waving.

The fan-out runs across diverse strong models so blind spots do not overlap. Convergence requires the structural axis to be addressed, not just the functional axis.

## What is deleted

Nothing from design-orch's current behavior is removed. The restructure is purely additive on this side — Terrain section requirement, feasibility-questions skill load, structural review mandate, "fix or preserve" framing, stronger emphasis on observations-not-prescriptions.

## What is added

- Terrain section requirement in `design/overview.md`, with required fields and evidence requirements specified by [terrain-contract.md](terrain-contract.md). The contract is the source of truth for what Terrain contains; this body references it.
- `feasibility-questions` skill loaded and applied during final convergence.
- Explicit framing in the agent body that design-orch produces observations, not phase prescriptions, for impl-orch and the planner to consume during pre-planning and decomposition.
- Structural/refactor reviewer required in every design-phase reviewer fan-out, with the explicit brief covering Terrain contract verification, decomposition sketch, and SOLID-as-signals.
- Convergence criteria expand from functional-only to functional + structural; structural reviewer PASS or documented override is a convergence prerequisite.
