# Orchestrator Restructure: Overview

## What this is

A redesign of the dev-workflow orchestration topology to fix three structural problems with the current shape: planning as a stale commitment, no mechanism for bailing out when the design is wrong, and design-time blindness to the structural seams that downstream parallelism depends on.

Read this first for orientation. The individual component designs live alongside:

- [dev-orchestrator.md](dev-orchestrator.md) — new dev-orch body with autonomous redesign loop, terminated-spawn plan review contract, and preservation-hint production
- [design-orchestrator.md](design-orchestrator.md) — design-orch with observations instead of recommendations and a required structural reviewer in every fan-out
- [impl-orchestrator.md](impl-orchestrator.md) — impl-orch with a pre-planning step, a planner spawn, a pre-execution structural gate, a planning cycle cap, and an escape hatch with both execution-time and planning-time arms
- [planner.md](planner.md) — @planner rehomed under impl-orch with parallelism-first decomposition as the central frame, the structural gate, the planning cycle cap, and the probe-request channel
- [terrain-contract.md](terrain-contract.md) — shared artifact contract for the Terrain section: required fields, evidence requirements, structural-prep tagging, fix_or_preserve enum, parallel-cluster hypothesis
- [preservation-hint.md](preservation-hint.md) — data contract for the redesign-cycle preservation artifact dev-orch produces between cycles
- [feasibility-questions.md](feasibility-questions.md) — shared skill design-orch, impl-orch, and @planner all load
- [redesign-brief.md](redesign-brief.md) — artifact format for impl-orch bail-out (covers both execution-time and planning-time arms)

## The three problems

**Plans go stale the moment impl-orch hits reality.** The current flow is design-orch → planner → impl-orch, with the planner committing to phase ordering, staffing, and scenario ownership before any agent has runtime context. Then impl-orch starts executing and discovers what the plan couldn't know — collateral damage in unexpected test fixtures, shared state that prevents parallelism, environmental assumptions that don't hold. The plan is wrong in the most expensive way: after another agent has already started consuming it. Streaming-parity-fixes phase 2 is the current evidence — 18 test failures, a ripgrep dependency, and scenario scope creep that the planner had no way to anticipate.

**There is no escape hatch when the design is wrong.** Impl-orch can fix phases, adapt scope, and spawn reviewers, but it cannot say "this foundational assumption is falsified and continuing will compound the error." Streaming-parity-fixes v1 shipped with bugs the design already warned about because once the plan committed to an approach, the orchestrator's only option was to patch forward. Multi-model post-impl review caught four HIGH findings that were predictable from the design enumeration, but by then it was too late to redirect.

**Design converges on shapes that block downstream parallelism.** A design can be functionally correct, internally consistent, and review-converged — and still land a target system state that is too coupled to decompose into phases that run in parallel. The planner inherits whatever structure the design hands it; if the structure is tangled, the plan is sequential no matter how skilled the decomposition. A prior session produced exactly this failure: the structural wrongness only surfaced during implementation, after design had already shipped. That was a design-phase miss masquerading as an implementation problem. The restructure treats structure and modularity as design-time concerns paired with active structural review, not as implementation craft to be sorted out later.

## The shape

Three orchestrators, one rehomed planner agent, one shared skill, three artifact contracts.

**dev-orchestrator** stays as the continuity with the user but gains an autonomous redesign loop and a preservation-hint production responsibility. When impl-orch bails with a redesign brief — execution-time, structural-blocking, or planning-blocked — dev-orch routes a scoped redesign back to design-orch without waking the user, writes the preservation hint after the design revision converges, and spawns a fresh planning impl-orch with the revised design and the hint attached. Loop guards prevent pathological oscillation. Dev-orch no longer spawns @planner directly — that handoff moves down to impl-orch. Plan review uses a terminated-spawn contract: planning impl-orch terminates with a plan-ready report, dev-orch reads the plan from disk, dev-orch spawns a fresh execution impl-orch.

**design-orchestrator** produces design docs plus observations about the terrain — what is coupled, what is independent, what needs foundational work, what the integration boundaries are, *and whether the designed target state fixes the existing structural problems or preserves them*. Observations are structural facts, not prescriptions. The Terrain section follows the shared contract in [terrain-contract.md](terrain-contract.md). The design phase reviewer fan-out includes a required refactor/structural reviewer in every run, briefed against the contract, with the brief covering Terrain compliance verification, decomposition sketch, and SOLID-as-signals. Convergence requires structural reviewer PASS or a documented override.

**impl-orchestrator** opens with a pre-planning step before spawning any coders, then spawns @planner. The pre-planning step reads the design, the Terrain section, and any preservation hint from a prior cycle, answers the four feasibility questions against runtime context (probes, dependency walks, file scans), and writes pre-planning notes to disk as module-scoped facts (not as a tentative decomposition). Impl-orch then spawns @planner with the design + Terrain + pre-planning notes + (on redesign cycles) the preservation hint attached. After the planner returns, impl-orch evaluates the plan against the pre-execution structural gate — if `Cause: structural coupling preserved by design`, it escalates a `structural-blocking` signal; if the planner cycle cap (K=3) is exhausted, it escalates `planning-blocked`. Otherwise it terminates with a plan-ready report and exits. A separate execution impl-orch is spawned later by dev-orch to run the per-phase loop. The escape hatch fires both at execution time (runtime evidence falsifies a design assumption) and at planning time (pre-planning contradicts the design, or planner cannot converge, or planner returns structural-blocking).

**@planner** survives as a separate agent profile but rehomes under impl-orch as its caller. Its central frame shifts from "produce a plan" to "decompose the work so as much as possible can run in parallel." Structural refactors that touch many files land first as cross-cutting prep; feature phases on disjoint modules then run in parallel; phase ordering is justified by what it unlocks for parallelism, not just by logical dependency. The plan carries a `Parallelism Posture` field with a cause classification — `structural coupling preserved by design` is the trigger for the structural gate. The planner maps every `structural-prep-candidate: yes` Terrain item to a phase or skip decision. The planner consumes impl-orch's pre-planning notes so the runtime context is in its input, not absent from it, and uses a probe-request channel when the notes have gaps. See [planner.md](planner.md).

**feasibility-questions skill** carries the four questions design-orch, impl-orch, and @planner ask: is this feasible, what can run in parallel, can we break it down further, does something need foundational prep first? Shared skill so all passes stay consistent.

**Three artifact contracts** support the topology:
- **[terrain-contract.md](terrain-contract.md)** — Terrain section required fields, evidence requirements, structural-prep tagging, fix_or_preserve enum.
- **[preservation-hint.md](preservation-hint.md)** — preserved/partially-invalidated/fully-invalidated phase tables, replan-from-phase anchor, new scenarios, replayed constraints.
- **[redesign-brief.md](redesign-brief.md)** — falsification case for execution-time bail-outs and parallelism-blocking structural issues for planning-time bail-outs.

## Why @planner stays but rehomes under impl-orch

A first draft of this restructure deleted @planner entirely and folded planning into impl-orch's own context. The user reversed that call. The reasoning behind keeping @planner as a real agent — with the LLM-specific arguments leading and the framing arguments supporting:

- **Fresh context isolates planning from accumulated execution state.** Once impl-orch starts spawning coders and reading test reports, its conversation context fills with phase-level noise. A re-plan late in execution under v1 would have happened in that polluted context. Under v2, planning runs in a fresh window with only the design, the pre-planning notes, and the preservation hint loaded.
- **Materialized handoffs survive compaction.** Pre-planning notes and the plan itself are files on disk. A planner spawn that crashes or compacts can be re-run from the same `-f` inputs and produce a comparable plan. In-context planning would lose state on every compaction.
- **Different skill loadouts focus the planner on decomposition craft.** The planner loads `planning`, `architecture`, and `feasibility-questions` with the parallelism question taking lead. Bundling that loadout with impl-orch's execution-coordination loadout would bloat both and dilute each.
- **Different model selection enables routing to a planning-optimized model.** The planner runs on a model picked for decomposition reasoning; impl-orch can run on a model picked for execution coordination.
- **The runtime-context objection has a better answer than collapsing the agent.** The original objection to a separate planner was that planners do not have runtime knowledge, so the plan goes stale. The fix is not to delete the planner — it is to give the planner runtime knowledge by having impl-orch do a pre-planning step first and pass the runtime observations to the planner as input. The planner then has the runtime context the v1 planner lacked, without sharing impl-orch's execution context.
- **A separate spawn forces legibility.** Impl-orch's pre-planning notes have to be written down because they will be passed to another agent via `-f`. That legibility is itself the value — it produces an inspectable record of what runtime context shaped the plan, which a future redesign cycle or audit can read.

Net effect on the topology: dev-orch no longer spawns @planner. Impl-orch does. Everything downstream of "the plan exists on disk" is unchanged from how the previous topology described the plan review checkpoint and execution loop, except the checkpoint itself uses a terminated-spawn contract (D15) rather than a suspended impl-orch.

The `/planning` skill stays loaded on @planner. It needs a downstream emphasis shift to make parallelism-first decomposition the central frame, but the planner profile body inlines the central frame so a planner spawned before the skill update lands still produces a v2-shaped plan. See [planner.md](planner.md) for the follow-up scope.

## Why observations, not recommendations

Design-orch sees architecture and impl-orch sees runtime. When design-orch prescribes phase ordering, impl-orch either follows blindly (wasting its runtime knowledge) or deviates silently (losing traceability against the design). Observations preserve design-orch's insight without locking in decisions made without runtime context. "Module X is a leaf in the import DAG" is a fact impl-orch can use. "Do X first" is a prescription that may or may not survive impl-orch's discoveries.

## Why every layer asks the same questions

Feasibility, parallelism, breakdown, and foundational prep are questions with different answers at different altitudes. Design-orch answers them with architectural data, capturing the answers in the Terrain section. Impl-orch re-answers them in its pre-planning step with runtime data — probes, dependency walks, file scans, env-var collisions — and writes the runtime-informed answers to its pre-planning notes. The planner then consumes both passes (Terrain + pre-planning notes) and uses the same four questions to guide the decomposition itself.

The two passes plus the planner reading is the value: architectural feasibility and runtime feasibility are not the same thing. "These phases are independent at the interface layer" and "these phases share a test suite and can't actually parallelize" are both true answers to the same question, and the expensive failure mode is discovering the runtime constraint after the plan has committed. A shared skill keeps every pass aligned so the answers reinforce each other instead of drifting into ad-hoc rephrasings.

## Why the escape hatch triggers on falsification, not failure

Bail-out is expensive — it invalidates in-flight work and restarts a design cycle. Triggering on every test failure or every tester finding makes impl-orch paralyzed. Not triggering at all reproduces the v1 problem where flawed designs ship under patch pressure.

The trigger is epistemic: runtime evidence falsifies a design assumption. A test failure is a bug, fixable in-place. Collateral damage is mechanical, fixable with a cleanup coder. A scenario scope issue is scoping, narrowable with a scenario update. But a smoke test against a real binary revealing the protocol doesn't work the way the design assumed — that's falsification, and patching past it means the next phase builds on broken ground.

The distinction is about what kind of evidence the failure produced, not how severe the failure was. Impl-orch must justify in the redesign brief why it's falsification and not a fixable bug; a brief that cannot make that case should not bail.

## Why dev-orch handles redesign autonomously

The user is a bottleneck on response time, not on judgment. Dev-orch has the original requirements, the design context, and the redesign brief — it has everything it needs to scope a redesign session and route it back to design-orch without waking the user. Asking for permission is asking for permission to do the thing that is already the right move.

Autonomy with visibility matters, though. The user sees every bail-out and every redesign cycle, can intervene at any time, and the final report surfaces how many cycles happened and why. Autonomy earns its keep by being transparent enough to audit after the fact.

## Why loop guards

Pathological oscillation is possible: a redesign that fixes one thing and breaks another, triggering a new bail-out. Loop guards are a heuristic for when dev-orch should notice its own confidence is dropping and escalate to the user. A single cycle is a normal mid-course correction. Two cycles is a scoping problem worth noticing. Three cycles suggests the scoping of the redesign itself is wrong and a human should look. The guard is a threshold for escalation, not a hard cap on progress.

## Why partial work preserves by default

Each committed phase represents verified behavior. Throwing it away because a later phase revealed an issue means throwing away work that still passes its scenarios. The redesign brief names explicitly which phases are invalidated, and anything unnamed stays committed. Default-preserve makes the cost of redesign proportional to the scope of the actual change, not to the position in the plan where the issue was discovered.

## Why structure and modularity are first-class design concerns

The user's framing: "structure and modularity and SOLID are important so we can move fast with parallel work." This is not abstract craftsmanship — it is the enabler that makes parallelism-first planning possible at all. If the design lands a tangled structure, the planner cannot decompose it for parallelism no matter how hard it tries. Every phase ends up reading from and writing to the same coupled surfaces, parallel coders race each other, and the plan collapses to sequential execution.

This means the restructure has to push structural concerns up the lifecycle. They cannot live as implementation craft to be sorted out by coders or refactor reviewers after the fact, because by then the design has already committed to a shape that determines what is decomposable.

How that lands in the design-orch body and the Terrain section:

- **Design-orch carries explicit emphasis on modularity, cohesion, and interface boundaries** as design-time concerns, not just implementation concerns. The four feasibility questions already include "does something need foundational work first?" — but that question can be answered "no" by a design that has missed the structural problem entirely. The answer has to be paired with an active structural review pass during design convergence.
- **The Terrain section calls out not just the current coupling, but whether the designed target state fixes it or preserves it.** A design that lands "same tangled structure, new features bolted on" is a design that cannot be decomposed for parallelism. The Terrain section names the target state's structural posture as well as the current one, and the delta between them.
- **The reviewer fan-out includes a structural/refactor reviewer by default in the design phase.** That reviewer is loaded with explicit instructions to flag when the design is not modular enough to enable parallel work downstream. This is the active counterweight to the "feasibility says no" failure mode — the structural review pass exists to make sure that "no" is actually informed, not assumed.

The signal to design-orch is: a design that converges with reviewers but leaves the system as coupled as it found it should be treated as not-yet-converged, even if no functional issue is flagged. Structural decomposability is part of the convergence criteria, not a nice-to-have.

## Scope of this restructure

Four agent rewrites: dev-orchestrator, design-orchestrator, impl-orchestrator, planner. No agent deletions. The parallelism-first frame is inlined into the planner profile body so a planner spawned under v2 produces a v2-shaped plan even if downstream skills have not been updated yet. Two existing skill updates: `planning` shifts emphasis to parallelism-first decomposition (named as a hard prerequisite of any plan written under v2; the inlined profile frame is the source of truth in the meantime), `dev-artifacts` documents the redesign brief, terrain contract, and preservation hint artifacts. One new skill: `feasibility-questions`. Three new artifact contracts under `design/`: `terrain-contract.md`, `preservation-hint.md`, `redesign-brief.md`. One existing agent profile left alone: `agent-staffing` stays as a shared skill since staffing concerns are identical across the old and new topologies.

No behavioral change to coders, testers, reviewers, or any leaf agent. The restructure is entirely at the orchestrator and planner layer.

## Decision log

Decisions made while drafting this package live in [decisions.md](../decisions.md).
