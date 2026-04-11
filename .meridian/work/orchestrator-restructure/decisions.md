# Orchestrator Restructure: Decisions

Decisions made while drafting the design package. Each entry captures what was chosen, what alternatives were rejected, and the reasoning.

## Executive summary

The restructure has four interlocking topology changes plus four supporting contract decisions:

- **Topology** — D1 keeps @planner as a separate agent and rehomes the caller from dev-orch to impl-orch. D2 reframes design-orch as observations-only. D3 adds an impl-orch pre-planning step that bridges design intent and runtime context. D6 makes dev-orch the autonomous router for redesign cycles.
- **Shared frames** — D4 makes the four feasibility questions a skill loaded by design-orch, impl-orch, and @planner so all three layers ask the same questions at different altitudes.
- **Escape hatches** — D5 keys bail-out on falsified assumptions rather than failure severity, and explicitly covers both execution-time and planning-time arms. D7 caps autonomous redesign cycles at K=2 with new-evidence requirement. D8 makes preserved phases the default. D9 materializes the redesign brief.
- **Parallelism and structure** — D10 makes parallelism-first decomposition the planner's central frame. D11 makes structure and modularity first-class design-phase concerns with required structural review.
- **Contract decisions** — D12 caps the planner cycle within a single impl-orch run at K=3 with a `planning-blocked` escalation signal, distinct from D7's outer redesign cap. D13 extracts the Terrain section into a standalone shared artifact contract so producer and consumers reference one source of truth. D14 defines the preservation-hint as a data contract dev-orch produces between cycles. D15 picks the terminated-spawn model for plan review pause/resume, matching meridian's crash-only design philosophy.

Themes:
- **Topology** — D1, D2, D3, D6
- **Runtime/planning boundary** — D3, D4, D12, D15
- **Redesign loop** — D5, D6, D7, D8, D9, D14
- **Parallelism & structure** — D10, D11, D13


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

**Decision.** The required content of the Terrain section, including required fields, evidence requirements, the structural delta tagging format (`structural-prep-candidate: yes|no`), the `fix_or_preserve: fixes|preserves|unknown` enum with reasoning, and the parallel-cluster hypothesis requirement, lives in `design/terrain-contract.md` as a standalone artifact contract. The producer (design-orchestrator.md) and consumers (impl-orchestrator.md, planner.md, structural reviewer brief) all reference the contract rather than re-stating it.

**Alternatives rejected.**
- *Keep the content inline in design-orchestrator.md (the v1 draft).* Reviewer feedback flagged that this tangles producer responsibility with consumer expectations. A planner reading planner.md would have to also read design-orchestrator.md to know what to expect from Terrain, and a structural reviewer would have to read both to know what to check. Updates to the contract would land in one body and silently drift from the others.
- *Distribute the contract across producer and consumer bodies.* Each body would need a slightly different slice of the contract, and over time the slices would diverge. The shared spec exists to prevent that.
- *Make Terrain an entirely separate file from `design/overview.md`.* Rejected because Terrain is part of the design, and changes to the design that invalidate Terrain claims should be visible in the same review pass. Keeping Terrain as a section of overview.md preserves co-located review; the contract doc specifies what the section contains, not where it lives.

**Reasoning.** Shared concerns get their own doc; agents reference shared docs from their own bodies. This is the same pattern the rest of the design package follows. The Terrain section has three distinct consumers and one producer; without a contract, drift is inevitable. With a contract, the structural reviewer can be briefed against one source of truth, the planner can be told exactly what to expect under `structural-prep-candidate: yes`, and impl-orch can scope its pre-planning notes to fields that are guaranteed to exist.

The structural reviewer's job becomes mechanical on the contract-compliance axis — every required field is either present and evidenced or it isn't. The decomposability sketch is the part that requires judgment; everything else is a checklist.

## D14: Preservation hint is a data contract dev-orch produces between cycles

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

**Reasoning.** Crash-only design is a load-bearing principle of meridian, not an aesthetic preference. Every other artifact in the topology (plan, scenarios, decisions, brief, hint) is materialized to disk for the same reason: ephemeral state breaks compaction-tolerance and audit. The plan review checkpoint should follow the same principle. The terminated-spawn contract is slightly more verbose (one extra spawn boundary per work item) but eliminates a class of failure modes that would otherwise have to be handled with custom resume logic.

The consequence is that planning impl-orch and execution impl-orch are separate spawns with different prompts. The planning impl-orch reads design + Terrain + preservation hint and runs pre-planning + planner spawn. The execution impl-orch reads the approved plan and runs the per-phase loop. This separation also makes the planning-time escape hatch (D5 second arm) cheaper: if the planning impl-orch fires `structural-blocking` or `planning-blocked`, the execution impl-orch is never spawned, and there is no rollback to do.
