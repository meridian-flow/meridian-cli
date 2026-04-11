# Orchestrator Restructure: Decisions

Decisions made while drafting the design package. Each entry captures what was chosen, what alternatives were rejected, and the reasoning.

## Executive summary

The restructure has two generations of decisions. The **v2 generation (D1–D15)** built the orchestrator topology and autonomous redesign loop. The **v3 generation (D16–D23)** reframes the design package around spec-driven development (SDD), which reshapes several v2 decisions in place.

**v2 topology and redesign loop (D1–D15):**

- **Topology** — D1 keeps @planner as a separate agent and rehomes the caller from dev-orch to impl-orch. D2 reframes design-orch as observations-only (revised by D18/D19/D20 — see below). D3 adds an impl-orch pre-planning step that bridges design intent and runtime context. D6 makes dev-orch the autonomous router for redesign cycles.
- **Shared frames** — D4 makes the four feasibility questions a skill loaded by design-orch, impl-orch, and @planner so all three layers ask the same questions at different altitudes.
- **Escape hatches** — D5 keys bail-out on falsified assumptions rather than failure severity, and explicitly covers both execution-time and planning-time arms. D7 caps autonomous redesign cycles at K=2 with a new-evidence requirement. D8 makes preserved phases the default. D9 materializes the redesign brief.
- **Parallelism and structure** — D10 makes parallelism-first decomposition the planner's central frame. D11 makes structure and modularity first-class design-phase concerns with required structural review.
- **Contract decisions** — D12 caps the planner cycle within a single impl-orch run at K=3 with a `planning-blocked` escalation signal, distinct from D7's outer redesign cap. D13 extracts the Terrain section into a standalone shared artifact contract (revised by D19/D20 — the single Terrain section splits into three named outputs). D14 defines the preservation-hint as a data contract dev-orch produces between cycles (the "verified scenarios" field is replaced by "spec leaves satisfied" per D22). D15 picks the terminated-spawn model for plan review pause/resume, matching meridian's crash-only design philosophy.

**v3 SDD reframe (D16–D23):**

- **SDD shape** — D16 adopts a spec-driven development shape anchored to Fowler's spec-anchored level and Kiro's requirements → design → tasks flow. D17 mandates EARS notation for every spec leaf. D18 replaces the v2 single-document design overview with two hierarchical trees (`design/spec/`, `design/architecture/`) plus root-level TOC indexes.
- **First-class named artifacts** — D19 extracts the refactor agenda into `design/refactors.md` as a first-class input to @planner, retiring the v2 `structural-prep-candidate: yes|no` tag. D20 extracts feasibility analysis into `design/feasibility.md` with `backs constraint` traceability. Together, D19 and D20 revise D13 — the "one shared contract" intent survives, but the single flat Terrain section becomes three outputs governed by `terrain-contract.md`.
- **Verification** — D21 makes smoke tests the default verification vehicle and parses EARS leaves directly into test triples. D22 retires the v2 `scenarios/` convention entirely — spec leaves subsume scenarios at higher fidelity, and `plan/leaf-ownership.md` replaces `plan/scenario-ownership.md`.
- **Scaling** — D23 preserves a light path for small work items so the two-tree shape does not crush one-line CLI flag changes under design-process weight.

Themes:
- **Topology** — D1, D2, D3, D6
- **Runtime/planning boundary** — D3, D4, D12, D15
- **Redesign loop** — D5, D6, D7, D8, D9, D14
- **Parallelism & structure** — D10, D11, D13
- **SDD shape (v3)** — D16, D17, D18, D19, D20, D21, D22, D23

Reversals and revisions at a glance:
- **D2** ("Terrain section in the design overview") — revised by D18/D19/D20. The Terrain section no longer exists as a section of overview.md; the three outputs that v2 packed into Terrain (architecture target state, refactors agenda, feasibility/gap-finding) are now named artifacts under `design/architecture/`, `design/refactors.md`, and `design/feasibility.md`.
- **D13** ("Terrain section is extracted into a standalone shared artifact contract") — revised by D19/D20. The contract doc (`terrain-contract.md`) survives, but it now describes the shape of three outputs rather than a single flat section. The `structural-prep-candidate: yes|no` tag is retired.
- **D14** ("Preservation hint is a data contract dev-orch produces between cycles") — partially revised by D22. The hint's "verified scenarios" column is replaced by "spec leaves satisfied," and "new scenarios from the redesign cycle" becomes "new or revised spec leaves."
- **v2 `scenarios/` convention** (never formalized as a numbered decision; lived in the `dev-artifacts` skill body and dev-workflow agent bodies) — explicitly reversed by D22. Coordinated skill edit follow-up at the end of this document tracks the downstream removal.


## D1: Keep @planner as a separate agent, rehome the caller from dev-orch to impl-orch

**Decision.** The @planner profile survives. Its caller changes — dev-orch no longer spawns @planner directly. Instead, impl-orch runs a pre-planning step against runtime context, then spawns @planner with the design package + Terrain observations + pre-planning notes attached, waits for plan artifacts to materialize on disk, and reports the plan back to dev-orch for the review checkpoint before executing. Everything downstream of "the plan exists on disk" is unchanged from how the previous topology described the plan review checkpoint and execution loop.

**Reversal note.** A first draft of this restructure deleted @planner entirely and folded planning into impl-orch's own context. The user reversed that call mid-draft. The reasoning for the reversal is captured in the "Reasoning" section below — both the rejected v1 approach and the alternatives that preceded it are kept here so future readers see the full evolution.

**Alternatives rejected.**
- *(v1 draft, now rejected)* **Delete @planner and fold planning into impl-orch's own context.** Initially adopted on the reasoning that the planner's unique contribution was a commitment to phase ordering before execution, and that commitment was the thing going stale. Reversed because folding decomposition and execution into one context blurs two distinct cognitive modes — exactly the blurring problem the restructure was solving on the design-orch side by separating observations from prescriptions. Decomposition is real craft worth a dedicated agent with its own context window. The runtime-context objection (planners do not have runtime knowledge) has a better answer than collapsing the agent: have impl-orch run a pre-planning step first and pass the runtime observations to the planner as input. The planner then has the runtime context the v1 planner lacked, without sharing impl-orch's execution context.
- *Keep the planner but make it optional.* Leaves two paths into impl-orch (with plan, without plan), doubling the surface area and creating inconsistent expectations about what artifacts exist. Also leaves the door open to skipping decomposition entirely on "small" work, which is exactly the framing where planning judgment is hardest to apply correctly.
- *Keep the planner under dev-orch's caller (the original topology).* This is the v0 status quo. Rejected for the original reason: planners running before any agent has runtime context produce plans that go stale on contact with reality. Streaming-parity-fixes phase 2 was the working evidence. The fix is to move when the planner runs, not whether it runs.
- *Keep the planner and give it probe capability so it can gather runtime context itself.* Planners spawning probe agents to gather runtime context duplicates impl-orch's existing capability — impl-orch is already the agent with codebase access and the ability to run probes. Cleaner to have impl-orch do the probing once and feed the results to the planner via `-f` than to have the planner re-do the probing in its own context.

**Reasoning.** The unique value of @planner is decomposition craft — figuring out where the seams cut so phases can run in parallel. That value is real and worth a dedicated agent context. The unique value of *spawning the planner from impl-orch* is that impl-orch can do the runtime work first and pass it to the planner as input, fixing the v1 problem (planner runs before runtime context exists) without recreating the v1.draft problem (decomposition mashed into execution context). Net: separate agent, new caller, runtime context as a structured input rather than an absent gap.

The handoff boundary is the value, not the cost. Impl-orch's pre-planning notes have to be written down legibly because they will be passed to another agent via `-f`. That legibility is itself the artifact — an inspectable record of what runtime context shaped the plan, which a future redesign cycle or audit can read.

## D2: Design-orchestrator produces observations, not implementation recommendations

**Revised by D18, D19, D20.** The observations-not-prescriptions intent survives into v3 — design-orch still produces facts and risks rather than phase ordering, and impl-orch/the planner still convert observations into execution decisions. What changes is *where* the observations land. The v2 "Terrain section in `design/overview.md`" is replaced by three v3 outputs: architecture target-state sections inside the `design/architecture/` tree (D18), the refactor agenda in `design/refactors.md` (D19), and the feasibility/gap-finding record in `design/feasibility.md` (D20). Read this decision for the original reasoning and D18–D20 for the v3 placement.

**Decision.** The design-orchestrator body is changed to require a "Terrain" section in the design overview that captures structural observations: what is coupled, what is independent, what is a leaf, what is a shared interface with ripple risk, what integration boundaries need protocol probing. Observations are framed as facts and risks, not as phase prescriptions.

**Alternatives rejected.**
- *Keep recommendations but call them "guidance"*: rename without behavior change — the impl-orch would still feel pressure to comply with guidance it shouldn't always follow.
- *Drop design-orch's structural framing entirely*: throws away genuine architectural insight that impl-orch cannot reproduce without re-exploring the codebase.

**Reasoning.** Design-orch sees architecture; impl-orch sees runtime. Prescriptions from a model without runtime knowledge force impl-orch to choose between compliance and truth. Observations preserve the insight without locking in decisions.

## D3: Impl-orchestrator runs a pre-planning step in its own context, then spawns @planner

**Decision.** Impl-orch's first action, after reading design and Terrain, is a pre-planning step in its own context: answer the four feasibility questions against runtime data (probes, dependency walks, file scans, env-var collisions, test-suite shape), materialize the answers to `plan/pre-planning-notes.md`, then spawn @planner with the design package + Terrain + pre-planning notes attached. Impl-orch waits for the planner spawn to terminate, reads the materialized plan, and reports back to dev-orch for the review checkpoint. Only after dev-orch approves does impl-orch begin spawning phase coders.

**Reversal note.** A first draft of this restructure had impl-orch perform self-planning entirely in its own context, with no separate planner spawn. The user reversed that call along with the deletion of @planner — see D1 for the topology-level reasoning. This decision tracks the impl-orch-side consequence of D1's reversal.

**Alternatives rejected.**
- *(v1 draft, now rejected)* **Self-plan in-context with no planner spawn.** Initially adopted because the planner's value seemed to be a commitment to phase ordering and that commitment was the thing going stale. Reversed for the same reason as D1 — decomposition and execution are different cognitive modes and folding them blurs both. The pre-planning step is what survives from this approach: the runtime context gathering still happens in impl-orch's own context because impl-orch is the only agent with codebase access plus the design package, but the decomposition itself moves to a focused planner spawn that consumes the pre-planning notes.
- *Plan lazily as phases begin.* Loses the ability for dev-orch or the user to review the plan before execution starts. The whole design package becomes opaque until it is too late to redirect.
- *Skip materialization and hold the plan in conversation context.* Makes the plan invisible to any agent or human checking in, breaks traceability when the session compacts or restarts. Also makes the planner spawn impossible (no `-f` input to attach), so this alternative dies on D1's mechanics alone.
- *Have dev-orch do the pre-planning and spawn the planner directly.* Forces dev-orch to gather runtime context, which it does not have codebase access to do in any structured way. Inserts dev-orch into the loop as a relay between impl-orch's data and the planner's input, with no value added at the relay step.

**Reasoning.** Pre-planning in impl-orch's own context plus a separate planner spawn gives the planner runtime context (the original objection to a separate planner) without giving up the focused decomposition mode (the objection to in-context planning). The pre-planning artifact is the bridge — it forces impl-orch to write the runtime observations down legibly, which is the precondition for the planner to consume them via `-f`. Materializing the plan to disk preserves the review checkpoint and the rehydration story for compaction or restart.

The four feasibility questions frame both the pre-planning step and the planner's decomposition pass so both layers stay structured and consistent with the design-phase feasibility answers.

## D4: The feasibility questions are a shared skill, loaded by every layer that asks them

**Decision.** A new `feasibility-questions` skill carries the four questions every orchestrator and the planner ask. Design-orchestrator, impl-orchestrator, and @planner all load it. The skill is the same body in all three loadouts; the answers each layer produces differ because the data each layer has access to differs.

**Reversal note.** The original draft of this decision named only design-orch and impl-orch as loaders. After D1 reverted to keeping @planner as a separate spawn, the planner was added to the loader list — the same shared frame that keeps design-orch and impl-orch aligned should also align the planner so its decomposition uses the same lens as the upstream answers it consumes.

**Alternatives rejected.**
- *Inline in each body*: duplicates content, drifts over time, and any improvement to the questions requires editing three places now (was two in the original).
- *Put the questions in `/planning`*: `/planning` is about decomposition and blueprint shaping, which is broader than the feasibility check. Bundling them loses the shared-across-layers lens that keeps design-orch, impl-orch, and the planner aligned.
- *Have the planner skip the skill and rely on impl-orch's pre-planning notes alone*: would let the planner answer differently from its inputs, and the divergence would be invisible. The shared skill makes the divergence detectable.

**Reasoning.** The same questions asked at three different altitudes (architectural, runtime, decomposition) produce three different answers, and that is the design intent. A shared skill keeps the questions consistent so all three passes reinforce each other instead of drifting into ad-hoc rephrasings.

## D5: The escape hatch triggers on falsified design assumptions, not on test failures — at execution time *and* at planning time

**Decision.** Impl-orch bails out only when evidence contradicts a design assumption in a way that cannot be resolved by patching forward. The escape hatch has two arms:

- **Execution-time falsification.** Runtime evidence (smoke tests, real-binary probes, cross-phase ripple) contradicts a structural design assumption mid-execution. Test failures, fixture collateral, scenario scope issues, and missing edge cases are handled by normal fix loops — they are not bail-out triggers.
- **Planning-time falsification.** Three triggers: pre-planning notes contradict a design assumption *before* the planner is spawned (impl-orch bails before wasting a planner slot); the planner cannot converge after K=3 spawns (the `planning-blocked` signal, see D12); the planner returns a plan with `Cause: structural coupling preserved by design` (the `structural-blocking` signal from the pre-execution structural gate).

Both arms write `redesign-brief.md` (D9). The brief format includes a planning-time-specific section so dev-orch can distinguish the two arms and route the design revision accordingly.

**Alternatives rejected.**
- *Bail on any repeated failure*: triggers too often on normal friction, making impl-orch paralyzed on routine issues.
- *Never bail; always patch forward*: reproduces the v1 failure mode where flawed designs ship under patch pressure.
- *Let testers decide*: testers can flag a concern but do not have the cross-phase picture. Bail-out is an orchestrator-level decision.
- *Execution-time-only escape hatch (the original v1 draft of this decision).* Reversed because reviewer feedback on the v1 design package surfaced that the planner-side gates (cycle cap exhaustion, structural-blocking) had no escalation path. The planner could surface "this design is structurally non-decomposable" as prose in `plan/overview.md` and the signal would dissipate. Adding the planning-time arm gives those gates a hard mechanical handoff to the same redesign loop.

**Reasoning.** Bail-out is expensive. Triggering on severity makes it too frequent; triggering on evidence type makes it proportional to the actual problem. A smoke test revealing a protocol contradicts the design is execution-time falsification; a unit test failing because a fixture is stale is a bug. A planner that cannot converge after three spawns is planning-time falsification; a planner that needed one re-spawn for a missing scenario is normal planning iteration. Impl-orch must justify in the redesign brief why the evidence is falsification, and a brief that cannot make that case is rejected. The planning-time arm uses the same justification burden — the brief's "Parallelism-blocking structural issues" section is the planning-time analog of the falsification case section.

## D6: Dev-orchestrator handles the redesign loop autonomously with visibility

**Decision.** When impl-orch emits a redesign brief, dev-orch reads it, scopes a redesign session, spawns design-orch with the original design plus the brief, and re-spawns impl-orch with the revised design when design-orch converges. The user is notified of every bail-out and every redesign cycle but not asked for permission.

**Alternatives rejected.**
- *Escalate every bail-out to the user*: makes the user the latency bottleneck on a decision they have no unique information about.
- *Silent autonomy without notification*: hides the fact that the system is oscillating. User cannot intervene when something is going wrong.

**Reasoning.** Dev-orch has the original requirements and full context; routing the redesign is not a judgment that requires human-unique information. The user can still intervene because every cycle is visible — autonomy with transparency rather than autonomy with opacity.

## D7: Two redesign cycles before escalation

**Decision.** Dev-orch escalates to the user after two autonomous redesign cycles on the same work item without converging. Each bail-out must cite new evidence not present in prior briefs for the cycle counter to advance; a bail-out citing the same evidence is rejected as a duplicate.

**Alternatives rejected.**
- *No cap*: leaves pathological oscillation unchecked.
- *One cycle cap*: prevents even the normal mid-course correction, which is the whole point of the escape hatch.
- *Three or more cycles*: by that point the scoping of the redesign itself is probably wrong and a human should look.

**Reasoning.** A single cycle is a normal correction. Two cycles is a scoping problem worth noticing. More than two is a heuristic threshold for when dev-orch should lose confidence in its own routing and escalate. The cap is not a hard rule — it is the point at which the system admits it may be confused and wants human input.

## D8: Partial work preserves by default across redesign cycles

**Decision.** Phases that have committed when impl-orch bails remain committed and are preserved in the next impl cycle unless the redesign brief explicitly names them as invalidated. The brief carries a "preservation" section that lists committed phases and marks each as preserved, partially-invalidated, or fully-invalidated.

**Alternatives rejected.**
- *Default-invalidate everything*: throws away verified work on any bail-out, making redesign costly out of proportion to the actual change.
- *Let design-orch decide during revision*: design-orch does not know which phases are actually committed in the current state; impl-orch has that information.

**Reasoning.** Each committed phase represents work that passed its scenarios. Default-preserve makes the cost of redesign proportional to the scope of the actual change. Impl-orch's second run can skip preserved phases and start from the first invalidated phase forward.

## D9: The redesign brief is a materialized artifact, not a spawn report

**Decision.** Impl-orch writes `$MERIDIAN_WORK_DIR/redesign-brief.md` before terminal report emission. The terminal report cites the brief prominently; dev-orch reads the brief directly.

**Alternatives rejected.**
- *Embed everything in the spawn report*: reports are more ephemeral than artifacts and are harder for design-orch to consume as context.
- *Use decisions.md for the brief*: conflates execution-time decisions with cross-orchestrator handoff content.

**Reasoning.** The brief is consumed by design-orch on the next cycle and by the user for audit. Materializing it to disk makes it inspectable, passable via `-f`, and persistent across compaction. The terminal report is the notification mechanism, not the content.

## D10: @planner's central frame is parallelism-first decomposition

**Decision.** @planner's job is reframed from "produce a plan" to "decompose the work so as much as possible can run in parallel." Concrete shape: structural refactors that touch many files land first as cross-cutting prep; feature phases on disjoint modules then run in parallel; phase ordering is justified by what it unlocks for parallelism, not just by logical dependency. The planner surfaces constraints that prevent parallel execution explicitly — shared test harnesses, global registries, fixture races, env-var collisions — even when interfaces look independent. The `/planning` skill needs a downstream emphasis shift to make this the central frame; the skill update is named as a follow-up in [planner.md](design/planner.md) but not part of this design pass.

**Alternatives rejected.**
- *Leave the planner's frame as "produce a plan" without a sharper goal.* Generic planning produces decompositions that satisfy the dependency graph but miss the parallelism opportunity. The user's experience is that this is the most expensive recurring failure mode of plans — sequential phasing of work that could have run concurrently, leaving throughput on the table.
- *Make parallelism a section in the plan rather than the central frame.* A section is something a planner can fill in after the fact with whatever parallelism the existing decomposition happens to allow. A frame is something that shapes the decomposition itself. The user explicitly wanted the latter.
- *Rewrite the `/planning` skill in this design pass.* Out of scope for this restructure — the skill rewrite is execution work that needs its own focused pass once this design lands. Naming it as a follow-up here is sufficient.

**Reasoning.** Parallel work is the throughput knob. Sequential plans starve the system of throughput even when the underlying work is independent. A planner that optimizes for parallelism by default produces plans that execute faster, fail more locally (a single phase failing does not block parallel siblings), and surface the structural seams that need to land first. The "structural prep first, then parallel feature fanout" pattern is the canonical shape this frame produces; it is the same shape the design-side structural emphasis (D11) is trying to enable.

The frame is not a checklist — it is the lens through which decomposition decisions get evaluated. A plan that produces the right phases for the wrong reasons fails the frame, and a plan that produces a few phases with strong parallelism justification beats a plan that produces many phases without it.

## D11: Structure and modularity are first-class design-phase concerns with mandatory structural review

**Revised by D18, D19, D20.** The core intent — structure and modularity as design-time convergence criteria with mandatory structural review and functional-plus-structural convergence — is unchanged. What changes is where the structural claims land: "current/target structural posture" now lives in the `design/architecture/` tree's target-state sections (D18), the structural delta landing as an explicit agenda lives in `design/refactors.md` (D19), and the "fix or preserve" verdict lives in `design/feasibility.md` (D20). The structural reviewer still runs against the same axis; they just read three named files instead of one overview section.

**Decision.** Design-orch treats structure, modularity, and SOLID-style decomposability as design-time convergence criteria, not implementation craft to be sorted out later. Three concrete changes:

1. The Terrain section in `design/overview.md` includes the current structural posture, the target structural posture, the structural delta, and an explicit answer to "does the target state fix or preserve the existing structural problems?" — used by reviewers and by impl-orch/the planner to evaluate decomposability.
2. The reviewer fan-out in the design phase requires a refactor/structural reviewer by default, loaded with explicit instructions to flag when the design is not modular enough to enable parallel work downstream.
3. Convergence criteria expand from functional-only to functional + structural. A design that converges with reviewers but leaves the system as coupled as it found it is treated as not-yet-converged on the structural axis.

**Alternatives rejected.**
- *Leave structural concerns to refactor reviewers in the implementation final review loop.* This is the v0 status quo. The user's lesson from a prior session: structural wrongness only surfaced during implementation, after the design had already shipped. By that point, the design has committed to a shape that determines what is decomposable. Catching it later costs more than catching it during design, and the asymmetry compounds — every phase of implementation built on the wrong structure has to be revisited.
- *Add the structural emphasis to design-orch's body but keep the structural reviewer optional.* Design-orch has a built-in bias toward shipping the design it has converged on. Reviewers focused on functional correctness do not naturally ask "is this decomposable?" The active counterweight has to be a reviewer with explicit instructions, not a passive emphasis in the body. Optional means it gets skipped on small designs and small designs are exactly where the structural seams are most determined by early choices.
- *Run a structural reviewer post-design but pre-impl as a separate gate.* Adds a gate. Convergence loops are already iterative; folding the structural reviewer into the existing fan-out keeps the iteration tight without an extra phase boundary.

**Reasoning.** Structure and modularity are the enabler that makes parallelism-first planning (D10) possible at all. If the design lands a tangled structure, the planner cannot decompose it for parallelism no matter how hard it tries. Every phase ends up reading from and writing to the same coupled surfaces, parallel coders race each other, and the plan collapses to sequential execution. The structural review is what catches the tangle before it locks in.

The design-orch and planner sides of this restructure are interlocking: design-orch's job is to land a structurally decomposable target state, and the planner's job is to consume that structure and decompose it for parallelism. If either side fails, the chain produces a sequential plan. Pairing the two decisions (D10 and D11) is what makes the restructure pay off — neither one alone is enough.

## D12: Planning cycle is capped at K=3 planner spawns per impl-orch cycle

**Decision.** Impl-orch may re-spawn @planner up to three times within a single impl-orch cycle to fix gaps in the plan (missing sections, scenario claims, contradictions with pre-planning notes, hand-wavy parallelism justifications). After the third failed planner spawn, impl-orch must escalate to dev-orch with a `planning-blocked` signal rather than re-spawning a fourth time. A "failed" spawn for cap purposes is one that produces a non-converging plan or terminates with a "needs more probing" report; a spawn that produces a complete and consistent plan does not advance the counter.

**Alternatives rejected.**
- *No cap.* Reviewer feedback on the v1 design package flagged unbounded planner re-spawn as a pathological-loop risk. A planner that cannot converge with the inputs it has will not converge with the same inputs on a fourth try; the cap forces escalation.
- *K=1 or K=2.* Too tight. A normal planning iteration (e.g. fixing a missing scenario claim) is a single re-spawn, and a second iteration to address a follow-up gap is normal. K=3 leaves room for two real corrections plus an unsuccessful third before escalating.
- *K=5 or higher.* Too loose. Beyond three failed convergence attempts, the gap is almost always in the inputs (design or pre-planning notes), not in the planner's craft. Dev-orch should be the one to decide whether to revise inputs or accept partial planning.
- *Cap by elapsed wall time instead of spawn count.* Spawn count is the meaningful unit for a non-deterministic agent, and wall time varies by model and load.

**Reasoning.** The planning cycle cap is the planning-time analog of D7's redesign cycle cap. They count separately — D7 caps redesign cycles across the work item, D12 caps planner spawns within a single impl-orch cycle. Exhausting D12 fires the `planning-blocked` signal which routes to dev-orch via the redesign loop and may or may not advance D7's counter depending on how dev-orch routes it. Without D12, the planner could loop indefinitely on a design or pre-planning gap that requires escalation to fix.

The cap is also what makes the probe-request channel safe: planner spawns that terminate with "needs more probing" reports consume one slot of the cap, so the planner cannot probe-request indefinitely.

## D13: Terrain section is extracted into a standalone shared artifact contract

**Revised by D19, D20.** The "shared contract governing multiple consumers" intent survives — `design/terrain-contract.md` still exists, still binds producer and consumers to one source of truth, and still prevents drift across producer and consumer bodies. What changes is the *shape* of the contract. The v2 single Terrain section of `design/overview.md` becomes three named outputs: the architecture tree's target-state sections (D18), `design/refactors.md` (D19), and `design/feasibility.md` (D20). The `structural-prep-candidate: yes|no` tag is retired — entries in `refactors.md` are candidates by construction. `terrain-contract.md` in v3 describes the shape of the three outputs rather than a single flat section.

**Decision.** The required content of the Terrain section, including required fields, evidence requirements, the structural delta tagging format (`structural-prep-candidate: yes|no`), the `fix_or_preserve: fixes|preserves|unknown` enum with reasoning, and the parallel-cluster hypothesis requirement, lives in `design/terrain-contract.md` as a standalone artifact contract. The producer (design-orchestrator.md) and consumers (impl-orchestrator.md, planner.md, structural reviewer brief) all reference the contract rather than re-stating it.

**Alternatives rejected.**
- *Keep the content inline in design-orchestrator.md (the v1 draft).* Reviewer feedback flagged that this tangles producer responsibility with consumer expectations. A planner reading planner.md would have to also read design-orchestrator.md to know what to expect from Terrain, and a structural reviewer would have to read both to know what to check. Updates to the contract would land in one body and silently drift from the others.
- *Distribute the contract across producer and consumer bodies.* Each body would need a slightly different slice of the contract, and over time the slices would diverge. The shared spec exists to prevent that.
- *Make Terrain an entirely separate file from `design/overview.md`.* Rejected because Terrain is part of the design, and changes to the design that invalidate Terrain claims should be visible in the same review pass. Keeping Terrain as a section of overview.md preserves co-located review; the contract doc specifies what the section contains, not where it lives.

**Reasoning.** Shared concerns get their own doc; agents reference shared docs from their own bodies. This is the same pattern the rest of the design package follows. The Terrain section has three distinct consumers and one producer; without a contract, drift is inevitable. With a contract, the structural reviewer can be briefed against one source of truth, the planner can be told exactly what to expect under `structural-prep-candidate: yes`, and impl-orch can scope its pre-planning notes to fields that are guaranteed to exist.

The structural reviewer's job becomes mechanical on the contract-compliance axis — every required field is either present and evidenced or it isn't. The decomposability sketch is the part that requires judgment; everything else is a checklist.

## D14: Preservation hint is a data contract dev-orch produces between cycles

**Partially revised by D22.** The data-contract intent, the producer/consumer roles, the `replan-from-phase` anchor, and the append-versus-overwrite choice all survive into v3. What changes are the column names in the preservation tables and the redesign-delta section: "verified scenarios" becomes "spec leaves satisfied," "new scenarios from the redesign cycle" becomes "new or revised spec leaves from the redesign cycle," and revised-in-place spec leaves keep their IDs with a `revised: <reason>` annotation (the anti-pattern D14 did not anticipate in v2). `preservation-hint.md` has been updated in place; read this decision alongside D22 for the full story.

**Decision.** After every successful design-orch revision cycle, dev-orch writes `plan/preservation-hint.md` per the format in `design/preservation-hint.md`. The hint carries the preserved-phase list (with commit SHAs and verified scenarios), the partially-invalidated list (with what is invalid and what is salvaged), the fully-invalidated list, the `replan-from-phase` anchor, the new scenarios from the redesign cycle, and the constraints-that-still-hold from the brief. The hint is overwritten each redesign cycle, not appended — cycle history lives in the brief and decisions.md. The next planning impl-orch consumes the hint as the first thing it reads in pre-planning, scopes runtime probing to the invalidated portion, and passes the hint to the planner via `-f`.

**Alternatives rejected.**
- *Implicit preservation via decisions.md and the brief alone.* Reviewer feedback on the v1 design package flagged that "default-preserve" (D8) was a verbal claim with no mechanism — without a structured artifact, impl-orch's next cycle had no way to know which phases to skip. Without the hint, default-preserve degrades into ad-hoc handling.
- *Append-only hint per cycle.* The hint is current-state instructions for the next cycle, not a history. History lives in the brief (which is append-only) and decisions.md. Mixing the two would force the next impl-orch to figure out which entries are current.
- *Have impl-orch produce its own preservation summary in the next cycle.* Impl-orch does not yet know what design-orch revised; only dev-orch sees both the brief and the revised design and can make the final preservation call. Putting the decision in dev-orch means the audit trail of what was preserved (and why) lives at the same level as the routing decision.
- *Encode preservation in plan/status.md alone.* Status tracking is the execution loop's runtime state, not the planning input. Mixing them would require the planner to read execution-state files; the contract is cleaner if the hint is the input and status.md reflects the output.

**Reasoning.** Default-preserve is the central claim of the autonomous redesign loop. Without a concrete data contract, the next impl-orch cycle has no structured way to know which phases to skip, which scopes a re-plan to which surface, and which scenarios are still claimed. The hint makes the claim auditable and gives every consumer a single source of truth for the preservation state.

The hint also carries `replan-from-phase`, which is what makes redesign cheap: pre-planning runtime work is proportional to the scope of the change, not to the total work item size. Without the anchor, impl-orch would re-run pre-planning over the entire work item every cycle.

## D15: Plan review uses a terminated-spawn contract, not a suspended impl-orch

**Decision.** The planning impl-orch terminates with a plan-ready terminal report after the plan materializes on disk. There is no suspended impl-orch process holding state across the dev-orch plan review checkpoint. If dev-orch approves the plan, dev-orch spawns a *fresh* impl-orch with the approved plan attached via `-f` and an explicit "execute existing plan" prompt; the fresh impl-orch skips pre-planning and the planner spawn entirely. If dev-orch pushes back with revisions, dev-orch spawns a fresh planning impl-orch with the original design plus the review feedback as additional context.

**Alternatives rejected.**
- *Suspended impl-orch holding plan state across the checkpoint.* The v1 draft of dev-orchestrator.md left the model ambiguous ("the same spawn or a fresh one — dev-orch's choice"). Reviewer feedback flagged this as internally inconsistent with impl-orchestrator.md, which separately implied a waiting impl-orch. Picked a single model: terminated spawn. The reasoning is that meridian's design is crash-only — state lives on disk, agents are stateless processes. A suspended impl-orch would be holding plan state in conversation context that cannot survive a crash, a compaction, or a restart. The exact failure mode the rest of the topology is designed to avoid.
- *Have dev-orch read plan state from impl-orch's spawn report and resume in-context.* Same problem — the in-context state is not crash-tolerant.
- *Background the impl-orch process and re-attach.* Meridian's spawn model does not support process reattachment in this way. Even if it did, the conversation context held in the suspended process is not durable.

**Reasoning.** Crash-only design is a load-bearing principle of meridian, not an aesthetic preference. Every other artifact in the topology (plan, spec leaves, decisions, brief, hint) is materialized to disk for the same reason: ephemeral state breaks compaction-tolerance and audit. The plan review checkpoint should follow the same principle. The terminated-spawn contract is slightly more verbose (one extra spawn boundary per work item) but eliminates a class of failure modes that would otherwise have to be handled with custom resume logic.

The consequence is that planning impl-orch and execution impl-orch are separate spawns with different prompts. The planning impl-orch reads the two-tree design package + preservation hint and runs pre-planning + planner spawn. The execution impl-orch reads the approved plan and runs the per-phase loop. This separation also makes the planning-time escape hatch (D5 second arm) cheaper: if the planning impl-orch fires `structural-blocking` or `planning-blocked`, the execution impl-orch is never spawned, and there is no rollback to do.

## D16: Adopt a spec-driven development (SDD) shape for the design package

**Decision.** The design package is reframed around spec-driven development. Design-orch produces a **spec** that describes observable behaviors the system must exhibit, and a separate **architecture** that describes the technical target state that realizes the spec. Requirements (user intent) and spec (behaviors) are separated, and spec drives the rest of the workflow: phase blueprints claim spec leaves, testers verify against spec leaves, bail-out briefs cite falsified spec leaves, and convergence is measured against spec coverage. The shape is anchored to Fowler's three levels of SDD and Kiro's requirements → design → tasks flow.

**Alternatives rejected.**
- *Keep the v2 single-document design overview with inline terrain section.* Leaves the verification contract implicit in prose. Reviewers and testers default to happy-path coverage because there is no enumerated list of behaviors to verify against. The v2 shape worked for the top-down overview walk but left verification artifacts scattered across reviewer notes and ad-hoc scenarios files.
- *Adopt spec-kit's constitution-first flow instead of Kiro's requirements-first flow.* Spec-kit's constitution is a heavy upfront commitment that does not match the orchestrator-restructure's actual scope — we are redesigning a system that already has a codebase, not building a greenfield system. Kiro's requirements → spec → tasks flow maps cleanly to the dev-orch/design-orch/impl-orch chain we already have.
- *Adopt TDD-style test-as-spec where the tests themselves are the behavioral contract.* Tests are the verification output, not the intent. Treating them as the contract collapses the distinction between "what should the system do" and "how do we check." Kiro explicitly does not mandate TDD for the same reason; v3 follows Kiro on this.
- *Describe behaviors informally inside the architecture doc.* Leaves verification coverage ambiguous — testers cannot tell which paragraph in an architecture doc is a commitment to behavior versus a description of current state.

**Reasoning.** The central v2 failure mode was that edge cases documented in design docs evaporated before reaching testers. Scenarios were supposed to patch this but required a separate convention agents had to remember to maintain. Spec leaves fix it at the source: the design itself enumerates observable behaviors, in a format (EARS, D17) that maps directly to test structure. Every downstream consumer reads the same canonical list. This is what Kiro's Amazon team learned after replacing informal specs with EARS-shaped requirements, and it is what Addy Osmani's agent-spec writeup identifies as the single highest-leverage change for agent-driven dev workflows. The decision reshapes every doc in the package and a number of downstream flows; D17-D23 carry the specific mechanics.

## D17: Spec leaves use EARS notation

**Decision.** Every leaf in `design/spec/` is written as an EARS statement — one of the five EARS patterns (Ubiquitous, State-driven, Event-driven, Optional-feature, Complex) — with an assigned ID. EARS is not a suggestion; it is the mandated shape, enforced by the spec-alignment reviewer during design convergence. An EARS leaf looks like `WHEN <trigger> WHILE <state> THE <system> SHALL <response>` or one of the other patterns; the ID format is `S<subsystem>.<section>.<letter><number>` (e.g. `S03.1.e1` for section 3.1's first event-driven leaf).

**Alternatives rejected.**
- *Free-form prose with a "should" style convention.* Reverts to the v2 failure mode where testers cannot parse behavior commitments out of narrative. EARS mandates trigger-precondition-response triples that map mechanically to test setup-fixture-assertion triples.
- *User stories ("As a user, I want...").* User stories express intent, not behavior commitments. They belong in `requirements.md`, not `design/spec/`. Mixing altitudes blurs what is user intent versus what is system commitment.
- *Gherkin (Given/When/Then) throughout.* Gherkin is close to EARS event-driven but does not cover ubiquitous or state-driven statements cleanly, and it invites a test-case mindset ("the Given is my fixture") that collapses the spec-vs-test distinction D16 explicitly preserves. EARS is the strict superset here.
- *Let reviewers flag ambiguity ad-hoc instead of mandating a shape.* Makes the convergence gate non-deterministic — two reviewers would disagree on "is this clear enough" and the spec-alignment reviewer's judgment would be the only check. An enforced shape is a deterministic gate.

**Reasoning.** EARS was designed by Mavin et al. for exactly this problem: making natural-language requirements unambiguous without introducing a formal language that writers reject. Each EARS pattern decomposes into trigger (test setup), precondition (fixture), and response (assertion), which is the triple testers need. The mandatory shape also forces design-orch to commit to a specific behavior rather than leaving it implicit — "THE system SHALL return a 4xx response WHEN the token is expired" is harder to write vaguely than "the system should handle expired tokens properly." The downstream smoke-test contract in D21 depends on EARS being parseable mechanically from each leaf, so the mandate is load-bearing, not stylistic.

## D18: Spec and architecture are hierarchical two-tree structures with root-level TOC indexes

**Decision.** Replace the v2 single-document design overview with two separate hierarchical trees under `design/`: `design/spec/` (the business spec) and `design/architecture/` (the technical design). Each tree has a root-level `overview.md` that functions as a TOC index — every leaf gets one line summarizing the behavior (spec) or the subtree (architecture) it represents. Downstream agents read the root overview first to orient and drill into specific subtrees on demand. For small work items a tree may degenerate to a single `overview.md` with embedded content; the tree structure is mandated for any work item with more than three spec subsystems or more than three architecture subtrees.

**Alternatives rejected.**
- *Keep v2's single flat `design/overview.md` with section headings.* Forces every downstream agent to load the whole overview (10k+ tokens) to read any part of it. Context offloading is poor, and drill-down requires text search rather than file navigation.
- *Interleave spec and architecture in a single tree (per-subsystem docs containing both).* Collapses the behavior-versus-technical-design distinction D16 sets up. Changing architecture without touching spec becomes harder; reviewers lose the ability to review one axis without re-reading the other.
- *Use a flat directory with no tree structure (`design/spec/s01.md`, `design/spec/s02.md`, ...).* Scales poorly past ten subsystems; no grouping means the root overview becomes a long flat list instead of a navigable index.

**Reasoning.** Context offloading is the primary win. An agent needing only the permission-pipeline spec reads `spec/overview.md` (small) plus `spec/permission-pipeline/*.md` (scoped), not the entire design. This is the pattern Addy Osmani identifies in the agent-spec writeup and that Kiro's IDE affordances assume: hierarchical specs with overview entry points are how you keep agent context small without losing the ability to drill down. The two-tree separation (business spec, technical spec) is the Thoughtworks pattern — it lets business-oriented review focus on spec without being distracted by implementation detail, and technical review focus on architecture without re-deriving the behavior contract. The root TOC index is the contract between the tree and its consumers: every consumer is guaranteed a one-line summary of every leaf at the root level.

## D19: `design/refactors.md` is a first-class artifact consumed directly by the planner

**Decision.** The refactor agenda moves out of the Terrain section (D13) into a named artifact at `design/refactors.md`, with a required per-entry shape (ID, target, affected callers, coupling removed, must-land-before, architecture anchor, behavior-preservation flag, evidence). The planner is required to map every entry to a phase or an explicit skip decision; unaccounted entries are a planner bug. The `structural-prep-candidate: yes|no` tag from v2 is retired — entries in `refactors.md` are refactor candidates by construction.

**This revises D13.** D13 extracted terrain analysis into a standalone shared artifact contract. D19 keeps that intent (shared contract, producer/consumer separation) but splits the single Terrain section into three outputs: `refactors.md` (this decision), `feasibility.md` (D20), and the architecture tree's target-state sections (D18). D13's "one shared contract doc" remains — `terrain-contract.md` — but it now describes the shape of the three outputs rather than a single flat section.

**Alternatives rejected.**
- *Keep the Terrain section as a subsection of `design/overview.md`.* Forces the planner to load the entire overview to consume the refactor agenda. The whole point of context offloading (D18) is lost for the artifact the planner consumes most directly.
- *Split into named artifacts but keep the `structural-prep-candidate: yes|no` tag.* The tag was a hack to let refactors and non-refactors share a section. With a dedicated file, every entry is a refactor by definition and the tag is dead weight.
- *Let @planner identify refactors itself by reading the architecture tree.* Puts the decision in the wrong agent. Design-orch has the time and the review fan-out to get structural reasoning right; the planner runs in a narrower window focused on decomposition. D19 reinforces this with an explicit rule: the planner does not invent refactors (see planner.md §"The planner does not invent refactors"), it sequences design-orch's agenda.

**Reasoning.** Refactors are the single highest-leverage input to a parallelism-rich plan (D10). Making them a named file with a required shape does three things: (1) gives the planner a direct `-f`-able input that does not require traversing the overview, (2) gives reviewers an isolated surface to audit structural intent, (3) gives the traceability chain from design claim to executed refactor a concrete artifact it can pass through. The per-entry fields are chosen to be the minimum the planner needs to sequence an entry without re-deriving analysis design-orch already did.

## D20: `design/feasibility.md` is a first-class artifact for gap-finding and probe evidence

**Decision.** Feasibility analysis — fix-or-preserve verdict, parallel-cluster hypothesis, probe evidence with stale-if conditions, foundational prep catalog, integration-boundary risks, and known unknowns tagged `impl-orch must resolve during pre-planning` — moves out of the Terrain section into a named artifact at `design/feasibility.md`. Design-orch produces it, impl-orch reads it during pre-planning, and @planner reads it as a decomposition input. Probe evidence entries include a `backs constraint` field pointing at the spec leaves or architecture sections that depend on the probe's outcome, establishing grounded-claim traceability.

**This revises D13** alongside D19. D13's single Terrain section is now three outputs — refactors.md, feasibility.md, architecture target-state sections. The shared artifact contract still exists (`terrain-contract.md`) but now governs the shape of feasibility.md and refactors.md rather than a single flat section.

**Alternatives rejected.**
- *Fold feasibility into `refactors.md`.* Conflates two different consumers. @planner reads `refactors.md` for sequencing and `feasibility.md` for runtime-known constraints; a merged file would force every consumer to read everything.
- *Let impl-orch do all feasibility work during pre-planning instead of having design-orch produce a `feasibility.md`.* Delays probe work to a stage where the whole design package has already been committed. If a probe reveals a structural problem, the whole design has to be redone; earlier probing catches the issue while the design is still malleable.
- *Put probe evidence inline in the spec or architecture docs that depend on it.* Breaks the separation between intent (spec) and evidence (feasibility). A reader of `spec/permission-pipeline/codex.md` should see the behavior commitment; the reader who wants to know "is this grounded" follows the `backs constraint` link to `feasibility.md`.

**Reasoning.** Feasibility is design's answer to "are the things we just committed to actually achievable." Giving it a named file with a `backs constraint` traceability line means every spec leaf and architecture section can be audited for groundedness — a reviewer can ask "is this leaf grounded?" and follow the link to a probe. Without this, grounded claims and unprobed assumptions read the same in the design package and reviewers cannot tell the difference. `impl-orch must resolve during pre-planning` tags give impl-orch a checklist of what to re-probe under runtime conditions rather than requiring impl-orch to re-read the whole design hunting for assumptions.

## D21: Smoke tests are the default verification vehicle and parse EARS leaves directly

**Decision.** Per-phase verification is performed by smoke tests rather than a mandated TDD flow. Each phase blueprint lists the spec-leaf IDs the phase claims, and the smoke-tester reads each leaf's EARS statement and parses it into a trigger/precondition/response triple to drive test setup/fixture/assertion. Unit tests and integration tests are additive (used when smoke tests cannot cover a constraint cheaply) but not mandated.

**Alternatives rejected.**
- *Mandate TDD — write tests before implementation.* Kiro explicitly rejects this, and the v3 shape follows Kiro. TDD's cost-benefit is poor in agent workflows where tests are regenerated from the spec on each phase; the test artifact's value is verification, not design. Mandating TDD would invert the producer-consumer relationship without adding signal.
- *Rely on unit tests as the primary verification.* Unit tests can pass without exercising real integration boundaries. Meridian's dev-principles skill already warns about this for integration code; smoke tests against real binaries catch protocol mismatches that unit tests cannot.
- *Let each phase decide its own verification style ad-hoc.* Loses the spec-leaf-to-test traceability — a phase that verifies leaves via browser tests and a phase that verifies via unit tests would report results in incomparable formats. Smoke tests with EARS-driven setup give a consistent shape.

**Reasoning.** EARS leaves decompose mechanically into the three parts a smoke test needs: WHEN clause → test setup, WHILE clause → fixture, SHALL clause → assertion. This is the operational payoff of D17 — the spec shape drives the test shape. Smoke tests are the default because they exercise real boundaries (see dev-principles §"Probe Before You Build at Integration Boundaries") and because the meridian project explicitly prefers smoke over unit (see CLAUDE.md §"Testing"). The combination means per-phase verification has a standard recipe: enumerate claimed leaves, parse each into a triple, write a smoke test from the triple, run it. The tester's judgment lives in how to set up the trigger and fixture, not in whether to test at all.

## D22: Spec leaves subsume the v2 `scenarios/` convention

**Decision.** The v2 `scenarios/` folder convention is retired. Every v2 scenario is subsumed by a spec leaf in `design/spec/` at higher fidelity — an EARS statement is a scenario with a template applied. Phase blueprints claim spec-leaf IDs instead of scenario IDs; `plan/leaf-ownership.md` replaces `plan/scenario-ownership.md`; design-orch does not produce a `scenarios/` folder, and @planner does not append to one.

**This explicitly reverses the v2 scenarios-as-verification-contract convention** (introduced in the v2 `dev-artifacts` skill body). Scenarios are not a parallel convention to spec leaves; they are the same concept at lower fidelity. Running both would give two overlapping records of the same commitments and invite drift.

**Alternatives rejected.**
- *Keep `scenarios/` as a lower-fidelity supplementary record.* Every spec leaf would already carry the information a scenario would, so `scenarios/` would be a redundant record whose only job is catching what the spec missed. If the spec misses something, the fix is writing the missing leaf, not maintaining a parallel folder.
- *Keep `scenarios/` for items that are too informal to become spec leaves.* "Too informal" is the failure mode — the whole point of EARS is forcing informal observations into a shape testers can parse. Allowing a `scenarios/` escape valve reintroduces the v2 problem.
- *Keep `scenarios/` in `plan/` to track phase-level verification state.* `plan/leaf-ownership.md` plus per-phase blueprints already carry this. A separate scenarios folder in `plan/` would fragment verification state across two files.

**Reasoning.** This is the specific failure mode D16 and D17 fix: the v2 design had `scenarios/` as the verification contract, and the contract evaporated because authors forgot to maintain it. The v3 design puts the verification contract in `design/spec/` where reviewers already look, in a format (EARS) that forces completeness, with ownership tracking in `plan/leaf-ownership.md`. Consolidating into one place eliminates the drift surface. The reversal is explicit because it changes the dev-artifacts skill body downstream — see the "Coordinated skill edit follow-up" note at the end of this decision log.

## D23: Design effort scales with problem size, including a light path for small work

**Decision.** Design-orch runs a light path for small work items: the two trees may degenerate to a single `spec/overview.md` and a single `architecture/overview.md` with embedded content, `refactors.md` may be empty (written as "no refactors required" with one sentence of reasoning), and `feasibility.md` may cover only the fix-or-preserve verdict and one probe entry if one was needed. The heavy path (hierarchical trees, full refactor agenda, full feasibility with multiple probes and cluster hypothesis) is mandated for work items that touch more than three subsystems, introduce cross-cutting refactors, or involve external integration boundaries.

**Alternatives rejected.**
- *Mandate the heavy path for every work item.* Makes small edits cost-prohibitive in design effort. A one-line CLI flag addition would require the full two-tree spec package, multiple reviewer lanes, and a refactor agenda that is always empty. Agents would route around the process or produce shallow artifacts to satisfy the shape.
- *Let dev-orch choose the path case-by-case without a rule.* Leaves the decision to judgment without a concrete threshold. Agents resuming mid-session cannot tell whether a missing artifact is "light path, intentional" or "heavy path, missing."
- *Two explicit profiles (design-orch-light and design-orch-heavy).* Multiplies the agent profile count and splits the decision logic across two bodies. One profile with a scaling rule keeps the design logic in one place.

**Reasoning.** Problem-size scaling is how every real workflow stays honest: the same shape that works for a CLI flag addition and a cross-cutting refactor is too heavy for one and too light for the other. The threshold is deliberately concrete (three subsystems, cross-cutting refactors, external integrations) so a resuming agent can read the design package and tell which path was followed by checking which artifacts exist. Light-path runs still produce every artifact class (spec, architecture, refactors, feasibility) — they just collapse the hierarchy when the work is small enough that there is nothing to hierarchize. Dev-orch sets the path during the requirements-gathering pass based on the user's framing and the scope implied by `requirements.md`.

---

## Coordinated skill edit follow-up

The v3 decisions above reshape the `dev-artifacts` skill in `meridian-dev-workflow`. The skill body currently describes `scenarios/` as a first-class artifact and is loaded by every orchestrator. After these decisions land and the user approves the v3 design package, the `dev-artifacts` skill needs a coordinated edit to:

- Remove the `scenarios/` folder convention entirely (D22 reversal).
- Add the two-tree spec/architecture shape (D18) with root-level TOC index expectations.
- Add `design/refactors.md` (D19) and `design/feasibility.md` (D20) as named artifacts with producer/consumer responsibilities.
- Add `plan/leaf-ownership.md` as the ownership artifact (D22) replacing `plan/scenario-ownership.md`.
- Add the problem-size scaling guidance (D23) so orchestrators loading the skill can see the light-path convention without having to load the design-orchestrator profile body.
- Reference EARS (D17) as the mandated spec-leaf shape with a short example.

The follow-up is deliberately not bundled with this decision log. The edit changes every agent that loads `dev-artifacts` (which is every dev-workflow orchestrator), so it should land as a single commit after the design-restructure work is approved rather than being threaded through the restructure itself. Dev-orch tracks this as an open work item and prioritizes it before the next design pass that depends on the v3 convention.
