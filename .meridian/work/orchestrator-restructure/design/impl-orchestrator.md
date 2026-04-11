# Impl Orchestrator: Target Shape

This doc describes the impl-orchestrator's behavior after the v3 restructure. It is still the largest behavioral change in the package — impl-orch gains a pre-planning step, a planner-spawn handoff, a pre-execution structural gate, a planning cycle cap, and an escape hatch that fires both at execution time and at planning time. Under v3, verification is keyed to **spec leaves** — the EARS-format acceptance criteria design-orch wrote — not to a separate scenarios convention. Everything else in the orchestrator topology exists to support these capabilities.

Read [overview.md](overview.md) first for the surrounding context. The design package impl-orch consumes is the two-tree structure described in [design-orchestrator.md](design-orchestrator.md): `design/spec/` (hierarchical spec tree with EARS leaves), `design/architecture/` (hierarchical architecture tree), `design/refactors.md` (refactor agenda), and `design/feasibility.md` (gap-finding record). The planner agent impl-orch now spawns is described in [planner.md](planner.md), the structural analysis workflow that produced refactors.md and feasibility.md is specified in [terrain-contract.md](terrain-contract.md), and on a redesign cycle impl-orch also consumes the [preservation-hint.md](preservation-hint.md) artifact dev-orch produces. Skills loaded alongside the body are listed at the end.

## What impl-orch does now

Consumes a design package from dev-orchestrator — the spec tree, the architecture tree, `refactors.md`, `feasibility.md`, and the decision log — plus a preservation hint when one exists from a previous redesign cycle. Runs a pre-planning step against runtime context scoped to the work the current cycle still has to do, spawns @planner with the design plus the pre-planning notes, evaluates the resulting plan's Parallelism Posture against the structural gate, and either reports the plan back to dev-orch as a terminal report for the review checkpoint or escalates a structural-blocking signal. After dev-orch approves the plan, a *fresh* impl-orch spawn picks up the plan and runs the per-phase execution loop. The execution-loop impl-orch produces working code committed per phase, a decision log of execution-time judgment calls, and — when needed — a redesign brief that bails out of execution rather than silently patching past a falsified spec leaf.

The pre-planning + planner-spawn replaces the old "dev-orch spawns @planner before impl-orch starts" handoff. The pre-execution structural gate, the planning cycle cap, the planning-time arm of the escape hatch, the terminated-spawn plan review contract, and spec-drift enforcement are behaviors that did not exist in the previous topology.

## Pre-planning as the first action

When impl-orch starts, the first action is reading the design package and any preservation hint from a previous redesign cycle. Specifically:

1. **Read `design/spec/overview.md`** — the root TOC of the spec tree, with every leaf summarized. Impl-orch treats spec leaves as the verification contract and reads them on-demand during pre-planning (cheap to load — each leaf is small) or lazily during execution as phases come up.
2. **Read `design/architecture/overview.md`** — the root topology with current + target posture for the whole system, plus the TOC of architecture subtrees. This tells impl-orch where the runtime probes are worth running.
3. **Read `design/refactors.md`** — the refactor agenda. Every entry names target nodes, parallelism it unblocks, and affected files. Impl-orch does not re-decide whether refactors are needed — design-orch already decided — but it reads them so its pre-planning notes account for the state transitions they imply.
4. **Read `design/feasibility.md`** — the record of what design-orch already probed. Any entry tagged `impl-orch must resolve during pre-planning` is a known unknown impl-orch now has to answer with runtime evidence.
5. **Read any preservation hint from a prior redesign cycle** (only on redesign cycles) per [preservation-hint.md](preservation-hint.md).
6. **Apply the four feasibility questions** (from the `feasibility-questions` skill) against runtime context — probes against real binaries or libraries, dependency walks across the actual codebase, file scans, env-var collisions, test-suite shape inspection. This is where the runtime knowledge the design-orch could not have gets gathered. Impl-orch does not re-run probes design-orch already recorded in feasibility.md — it covers the known unknowns feasibility.md flagged plus any runtime constraints impl-orch notices that design could not anticipate.

If a preservation hint exists, impl-orch scopes pre-planning to the invalidated portion. The hint's `replan-from-phase` anchor and the partially-/fully-invalidated phase tables tell impl-orch which surfaces still need probing and which surfaces are immutable starting state. Re-running pre-planning over the entire work item every redesign cycle is the anti-pattern the hint exists to prevent — pre-planning runtime work is proportional to the scope of the change, not to the total work item size.

### Module-scoped constraints, not a tentative decomposition

The chicken-and-egg trap is real: impl-orch could enumerate every possible runtime constraint (huge noise, useless to the planner) or could sketch a tentative decomposition first and then enumerate constraints against it (reproduces the v1 in-context mashing this restructure exists to prevent). Impl-orch does neither. Instead, impl-orch enumerates **module-scoped constraints without imagining phases**. Each constraint is stated as a fact about specific modules: "modules X and Y share fixture Z" or "module W writes to a global registry that any caller of module V will collide with." The planner is the agent that maps constraints onto phases. Impl-orch's job is to make the constraint surface visible, not to pre-bind it.

The test for whether impl-orch is straying into decomposition: if a sentence in the pre-planning notes uses the word "phase," impl-orch is doing the planner's job. Rewrite the sentence as a module-level fact and let the planner read it.

Impl-orch writes those observations to `$MERIDIAN_WORK_DIR/plan/pre-planning-notes.md` as a structured input for the next step. The notes are not a plan — they are the runtime context that the planner will use to *write* the plan. Format:

- **Feasibility answers** for each of the four questions, with runtime evidence for any answer that diverged from the architecture tree's root-posture answer or feasibility.md's evidence.
- **Probe results** for the known unknowns feasibility.md flagged, plus any integration boundaries that needed re-verification before planning.
- **Architecture re-interpretation** flagging anything in the architecture tree that runtime data contradicts or refines (e.g. "architecture/subsystem-A/module-X.md says X is a leaf in the local DAG, but runtime data shows it imports Y transitively").
- **Module-scoped constraints discovered at runtime** that bound the plan's phase ordering — shared test fixtures, global registries, env-var collisions, fixture races. Stated as facts about modules, never as proposed phases.
- **Spec-leaf coverage hypothesis** — impl-orch's runtime-informed reading of which spec leaves cluster together and which can satisfy independently. Stated as clusters of leaf IDs, not as phases.
- **Probe gaps** — questions impl-orch could not answer with the probes it ran, flagged so the planner knows what is missing rather than discovering it during decomposition.

Pre-planning has to land on disk before the planner spawn because the planner consumes it via `-f`. Holding it in impl-orch's conversation context defeats the purpose — the legibility of the runtime observations is the value, and legibility requires materialization.

Pre-planning is not a separate spawn. It is work impl-orch does in its own context, because impl-orch is the only agent in the loop with both the design package and the codebase access needed to gather runtime data. Outsourcing it to another agent would just rebuild the v1 chain of context loss.

Pre-planning notes are a *projection* of runtime context, not equivalent to runtime context. They capture what impl-orch thought to probe; negative results, interaction effects, and tacit codebase knowledge may be absent. The planner reads them as "the runtime data impl-orch chose to write down" and uses the probe-request channel (below) when it needs more.

## Spawning @planner

After the pre-planning notes are written, impl-orch spawns @planner with:

- The spec tree (`design/spec/`) attached via `-f` — the planner needs leaf IDs to map each phase to the spec leaves it satisfies.
- The architecture tree (`design/architecture/`) attached via `-f` — the planner reads the subtree structure and cross-links to identify disjoint surfaces.
- `design/refactors.md` attached via `-f` — the refactor agenda is the planner's Round 1 seed.
- `design/feasibility.md` attached via `-f` — so the planner knows which architectural constraints rest on verified evidence and which on inference.
- The pre-planning notes attached via `-f`.
- The decision log so far attached via `-f`.
- The preservation hint attached via `-f` *(only on redesign cycles)*.
- A short prompt naming the work item and pointing the planner at the inputs.

Impl-orch then waits for the planner spawn to terminate. The planner reads the inputs, decomposes the work with parallelism-first as the central frame, and writes the plan artifacts to disk (`plan/overview.md` with `Parallelism Posture` and per-round parallelism justification, per-phase blueprints with spec-leaf claims, `plan/leaf-ownership.md`, `plan/status.md`). See [planner.md](planner.md) for the full planner contract.

When the planner spawn returns, impl-orch reads the plan from disk and evaluates it on three axes:

1. **Completeness** — required sections present, every refactors.md entry mapped to a phase or a skip decision, every spec leaf in `design/spec/` claimed by exactly one phase, parallelism justification per round.
2. **Consistency with pre-planning notes** — the plan does not contradict module-scoped constraints impl-orch flagged (e.g. it does not propose parallel phases that share a fixture impl-orch flagged as racing).
3. **Probe-request signal** — if the planner terminated with a "needs more probing" report instead of a plan, impl-orch reads the report's question list, runs the additional probes, updates `pre-planning-notes.md`, and re-spawns the planner. This counts toward the planning cycle cap (below).

If the plan fails completeness or consistency, impl-orch re-spawns the planner with the gap as feedback. Re-spawning is a normal correction, not an escape-hatch trigger — but it is bounded by the planning cycle cap.

The reason planning is a separate spawn rather than in-context impl-orch work is in [planner.md](planner.md) §"Why a separate agent". Short version: fresh context isolates planning from execution noise, materialized handoffs survive compaction, the planner can route to a decomposition-optimized model, and a separate spawn forces the runtime observations to be written down instead of held implicitly in conversation state.

## Planning cycle cap

Planner re-spawns are capped at **K=3 per impl-orch cycle**. A "failed" planner spawn for the purpose of the cap is one where the produced plan has any of: missing required sections, missing or duplicated spec-leaf claims, contradictions with pre-planning notes, hand-wavy parallelism justifications that do not cite real constraints, or unaccounted refactors.md entries. A spawn that produces a complete and consistent plan does not advance the counter. A spawn that terminates with a probe-request report consumes one slot of the cap (so the planner cannot probe-request indefinitely).

After the third failed spawn, impl-orch must escalate to dev-orch with a `planning-blocked` signal rather than re-spawning a fourth time. The escalation is a terminal report citing the planner's last-attempt artifact, the gap reasoning impl-orch provided on each re-spawn, and the conclusion that planner convergence is not achievable with the current design + pre-planning notes. Dev-orch decides whether to revise the design (back through design-orch) or to accept the partial plan with explicit known gaps.

The planning cycle cap is **distinct from the redesign cycle cap (D7)**. They count separately — exhausting the planner cap fires the `planning-blocked` signal; exhausting the redesign cycle cap is the absolute outer bound on the autonomous loop. See `decisions.md` D12 for the cap rationale and `decisions.md` D7 for the outer bound.

## Pre-execution structural gate

Once impl-orch reads a converging plan, the next check is the plan's `Parallelism Posture` field (per [planner.md](planner.md) §"Parallelism Posture as a structural gate"). The gate has one trigger: when `Cause: structural coupling preserved by design`, impl-orch must **not** proceed to execution and must **not** route the plan to dev-orch as a normal plan-review checkpoint. Instead, impl-orch writes a planning-time redesign brief naming the structural coupling, citing the planner's reasoning, and naming the design assumption the planner could not decompose around (typically an architecture subtree shape or a refactors.md entry the planner could not route around). Impl-orch then emits a terminal report routing the brief to dev-orch as a `structural-blocking` signal.

The other cause values (`inherent constraint`, `runtime constraint`, `feature work too small to fan out`) do not fire the gate. A sequential plan caused by an inherent constraint is a real plan and impl-orch routes it through the normal review checkpoint. The structural gate fires only when the planner is signaling that the design's target state is structurally non-decomposable for parallelism — i.e. that the architecture tree has preserved a coupling problem that the planner cannot route around and refactors.md did not remove.

This gate is what makes the parallelism-first frame load-bearing. Without it, the planner would surface "this design is structurally tangled" as prose in `plan/overview.md` and downstream consumers would either miss it or interpret it as an aesthetic complaint. With it, the architecture tree's structural problems get a hard mechanical signal that impl-orch must act on.

## Review checkpoint after the plan materializes

Once impl-orch reads a complete plan that passes the structural gate, it does not start spawning phase coders. It does not wait in-context either. Impl-orch **terminates** with a terminal report that names the plan files on disk and the recommended action ("plan ready for review"). The spawn is over.

This is the terminated-spawn contract. There is no suspended impl-orch process holding state. If dev-orch approves the plan, dev-orch spawns a *fresh* impl-orch with the plan attached and explicit "execute existing plan" semantics — that fresh spawn skips pre-planning and the planner spawn entirely and starts directly at the execution loop. If dev-orch pushes back with concrete revisions, dev-orch spawns a fresh impl-orch with the feedback as additional context; that fresh impl-orch re-runs the planner spawn (subject to the planning cycle cap above) and re-emits a plan-ready terminal report.

This contract matches meridian's crash-only design philosophy: state lives on disk, agents are stateless processes that read state from disk on startup. A suspended impl-orch holding plan state in conversation context would be a state that cannot survive a crash, a compaction, or a restart — exactly the failure mode the rest of the topology is designed to avoid. See `decisions.md` D15 for the rationale and the rejected alternative (suspended-spawn pause/resume).

The cost-shape argument for this checkpoint is unchanged: the plan is the most expensive artifact to get wrong because it shapes every phase coder spawn that follows. A cheap review pass before execution costs one round-trip with dev-orch; a wrong plan caught mid-execution costs rollbacks. The checkpoint is not a gate for trivial work — for small scoped tasks where the plan is obvious, dev-orch should approve without user involvement and immediately spawn the execution-loop impl-orch. The judgment of how much review the plan deserves belongs to dev-orch, not impl-orch — impl-orch just presents the plan and exits.

## Execution loop

The execution-loop impl-orch is a fresh spawn launched by dev-orch after plan approval. Its inputs include the approved plan attached via `-f` and an explicit "execute existing plan" prompt that instructs it to skip pre-planning and the planner spawn entirely. From there it executes phases using the per-phase loop: read the phase blueprint, spawn a coder for the phase, wait for the coder, spawn testers to verify the spec leaves the phase claims, iterate the fix loop until all claimed leaves are verified, commit, move to the next phase. Per-phase commits still isolate rollback. Testers still run in parallel where independent.

### Verification framing: spec leaves as the contract

Under v3, verification framing changes. A phase's success criterion is not "the code works" or "the tests pass" — it is **"does this phase satisfy the spec leaves it claims?"** Each phase blueprint names specific spec-leaf IDs (e.g. `S03.1.e1, S03.1.e2, S05.2.e1`) pulled from `design/spec/`. Testers read those leaves, parse the EARS statements, and execute smoke tests that exercise each statement's trigger/precondition/response triple. A phase passes when every claimed leaf has at least one verified EARS statement and none are falsified.

This does not mean testers run only one test per leaf — it means the verification contract is rooted in leaves, not in free-floating test cases. A tester may execute additional edge-case tests beyond the EARS statements as long as the leaf's claims are covered. The reverse — covering edge cases but not the claimed leaves — is incomplete verification.

Smoke tests remain the default per the project's existing "prefer smoke tests over unit tests" rule. There is no TDD mandate — coders do not write tests before implementing. Testers run smoke tests after the phase lands and report which spec leaves are verified, which are falsified, and which are not yet covered.

### Spec-drift enforcement

If impl-orch discovers during execution that runtime evidence contradicts a spec leaf — not just that the code does not yet satisfy it, but that the spec itself describes behavior the system cannot or should not have — **the spec must be revised before code changes land**. Quiet workarounds that leave the code satisfying unstated behavior while the spec says something else are exactly the drift Fowler warns about under spec-anchored SDD.

The enforcement mechanism is the escape hatch. A falsified spec leaf fires execution-time bail-out; impl-orch stops spawning fix coders, writes the redesign brief naming the falsified leaf IDs, and routes to dev-orch. Design-orch revises the affected leaves (and any architecture-tree nodes that realize them), dev-orch writes a preservation hint, and a fresh impl-orch resumes against the revised spec. There is no path where code lands satisfying behavior the spec does not describe.

This is the central v3 discipline. Under v2, discovered edge cases got appended to the scenarios folder and testing continued. Under v3, discovered edge cases that the spec already covered get tested normally; discovered edge cases that the spec did not cover either get added to spec leaves (a small design revision routed through dev-orch) or trigger a bail-out if they reveal a structural falsification. The spec is authoritative; the code follows it.

### Decision log, status, and context handoffs

The decision log, status tracking, and context-handoff patterns carry over unchanged. On a redesign cycle, the execution-loop impl-orch reads the preservation hint and skips phases marked `preserved`, treats `partially-invalidated` phases as needing revision (re-spawns the coder with the partial-invalidation scope), and runs the `replanned` and `new` phases as fresh work. Leaf ownership survives the redesign cycle via the hint's preservation section — leaves claimed by preserved phases remain claimed; leaves affected by the revision get reclaimed by the replanned phases.

## The escape hatch

The escape hatch fires when runtime evidence falsifies a **spec leaf** the design rests on. There are two arms — execution-time and planning-time — and they share the same brief format ([redesign-brief.md](redesign-brief.md)) but different sections.

### Execution-time falsification

During execution, impl-orch watches for evidence that contradicts a spec leaf. Not test failures — those are normal friction. Not fixture collateral or scope creep — those are fix-loop concerns. The specific signal is runtime evidence that falsifies a spec leaf the design wrote as contract.

Concrete examples of what qualifies:

- A smoke test against a real binary reveals the behavior an EARS statement requires cannot be achieved (e.g. spec leaf `S07.3.e1` says "when a confirm-mode approval is requested, the spawn runner shall route the request to the user via a dedicated approval channel" — but the Codex app-server binary has no approval channel, confirmed by running `codex app-server --help`).
- Fixing a failure would require a contract change that invalidates one or more already-verified spec leaves in earlier phases (the change ripples backwards, not just forward).
- The same spec leaf fails across multiple fix attempts, each fix exposing the next symptom of the same underlying wrong contract shape.
- External tool behavior discovered at runtime contradicts the precondition or trigger of an EARS statement in a way that cannot be hidden by a local projection or guard.

The reason the trigger is epistemic rather than severity-based: triggering on severity makes bail-out fire on normal friction and paralyzes impl-orch. Triggering on spec-leaf falsification makes bail-out fire only when continuing would compound a contract error. The distinction is what the failure reveals about the spec, not how painful it was to hit.

When the trigger fires, impl-orch stops spawning fix coders for that concern. It writes `$MERIDIAN_WORK_DIR/redesign-brief.md` following the format in [redesign-brief.md](redesign-brief.md), citing the specific leaf IDs (e.g. "falsified: `S07.3.e1`, `S07.3.e2`; the confirm-mode contract cannot be expressed on the current app-server channel"), emits a terminal report citing the brief, and returns control to dev-orchestrator.

### Planning-time falsification

The escape hatch also fires *before* execution, while the planner is being spawned or just after the planner returns. Three planning-time triggers:

1. **Pre-planning notes contradict a spec leaf or an architecture leaf the design rests on.** If the runtime probes impl-orch ran during pre-planning falsify a spec-leaf contract or reveal that the architecture tree's assumed structure is wrong (e.g. the architecture tree says module X is a leaf but runtime data shows X is a hub), impl-orch writes a planning-time redesign brief naming the contradiction and routes to dev-orch *before* spawning the planner. Spawning the planner against a falsified design wastes a planner slot and produces a plan that has to be thrown away.
2. **Planner cannot converge after K=3 spawns.** Exhausting the planning cycle cap fires the `planning-blocked` signal and emits a redesign brief naming the gap reasoning that prevented convergence. See "Planning cycle cap" above for the cap mechanics.
3. **Planner returns a plan with `Cause: structural coupling preserved by design`.** The pre-execution structural gate fires the `structural-blocking` signal and emits a redesign brief naming the structural coupling the planner could not decompose around — typically an architecture subtree that refactors.md did not break apart. See "Pre-execution structural gate" above.

Planning-time briefs use the "Parallelism-blocking structural issues" section of [redesign-brief.md](redesign-brief.md). The brief format includes a section for planning-time evidence specifically, so dev-orch can distinguish a planning-time bail-out from an execution-time bail-out and route the design revision accordingly.

The justification burden is the same for both arms: the brief must articulate why the evidence is falsification rather than fixable friction, and dev-orch will reject a weak brief and push back. The escape hatch is cheap to invoke but expensive to defend, which is the counterweight that prevents it from becoming a shortcut past hard work.

## Justification burden on the brief

A redesign brief that cannot name specific falsified spec leaves (execution-time) or cannot show the planner's structure-resistance case (planning-time) is not a valid bail-out. Dev-orch reading a weak brief should reject it and push back on impl-orch to either patch forward or produce a stronger case. This is the counterweight to the escape hatch — the mechanism is cheap to invoke but requires real evidence to justify, which prevents it from becoming a shortcut past hard work.

The brief format includes a section explicitly for this justification. For execution-time bail-outs, impl-orch names the spec-leaf IDs (e.g. `S07.3.e1`), quotes the EARS statement, and names the runtime evidence that contradicts it. For planning-time bail-outs, impl-orch names the architecture subtree and the refactors.md entries the planner could not route around. The shape of that section is in [redesign-brief.md](redesign-brief.md).

## What does not warrant bail-out

- First-time test failures: fix and retry.
- Fixture collateral damage: cleanup coder sweep.
- Missing edge cases that the spec already covered via an EARS statement the tester did not exercise: generate the missing test from the EARS trigger/precondition/response and run it.
- Missing edge cases the spec did *not* cover at all: route a scoped spec revision through dev-orch (a small design-cycle update adds the new leaves; not every missing edge case is structural falsification).
- Coder mistakes that a re-spawn would catch.
- Tester disagreements on how strictly to read an EARS statement — push back to dev-orch with a specific reading question rather than bailing.

All of those are normal fix-loop territory (or small scoped revisions). Promoting them to bail-out triggers would reproduce the streaming-parity-fixes phase 2 friction in reverse — the orchestrator would stop every time it hit a bump.

## Adaptation stays allowed

The restructure does not remove impl-orch's authority to adapt execution order, split phases, or adjust scope in response to runtime findings. That authority is a separate behavior from the escape hatch. Adaptation happens inside the execution loop and stays scoped to what impl-orch can resolve. Bail-out happens when adaptation cannot resolve the issue because the problem is higher than the plan.

Impl-orch may also deviate from the architecture tree's observational shape when runtime evidence supports it — the architecture tree is observation, not contract. Every deviation gets logged to `decisions.md` with rationale. The spec tree is different: impl-orch may not deviate from a spec leaf; spec-leaf disagreements route through the escape hatch or through a scoped design revision.

## Final review loop stays end-to-end

After all phases pass phase-level verification, the final review loop runs across the full change set as today — reviewer fan-out across diverse models, one refactor reviewer, design-alignment reviewer, iterate until convergent. Design alignment at this stage checks the full implementation against the spec tree: every spec leaf has been verified by at least one phase, and no committed code introduces behavior the spec does not describe.

The escape hatch does not interact with the final review loop under normal conditions. If the final review surfaces a spec-leaf gap or a drift between code and spec, that is either a patch-forward finding (code does not satisfy an existing leaf) or a scoped design revision (behavior exists that the spec did not anticipate). Bail-out from the final review would be unusual and require strong justification, since by that point every phase has passed its verification contract.

## Skills loaded

- `meridian-spawn`, `meridian-cli`, `meridian-work-coordination` — coordination fundamentals.
- `agent-staffing` — team composition for phase execution. Impl-orch still consumes the staffing the planner authors per-phase, but it loads the skill so it can interpret the staffing decisions and adjust at execution time when runtime data calls for it.
- `feasibility-questions` — the four shared questions. Loaded for the pre-planning step and for mid-execution re-checks against runtime discoveries. Same skill design-orch and the planner load, so all three layers use the same frame.
- `decision-log`, `dev-artifacts`, `context-handoffs`, `dev-principles`, `caveman` — unchanged from the current profile.

The `planning` skill is **not** loaded on impl-orch. It moved off impl-orch when @planner survived as a separate agent — the decomposition craft lives where the decomposition happens. Impl-orch consumes the plan; it does not author it.

## What is deleted

- The dev-orch → @planner direct handoff. @planner is no longer spawned by dev-orch. The planner agent profile itself stays.
- The expectation that the plan exists on disk *before* impl-orch is spawned. The plan now exists on disk *after* impl-orch's pre-planning step and planner spawn complete, before dev-orch's plan review checkpoint.
- The `planning` skill load on impl-orch's profile (it was added on impl-orch in the v1 of this restructure when planning was being folded inline; reverted now that planning is a spawn again).
- The single long-lived impl-orch spawn that was implied by earlier drafts where impl-orch "waits" for plan review. Replaced by the terminated-spawn contract: planning impl-orch and execution impl-orch are separate spawns separated by dev-orch's plan review checkpoint.
- Scenario-based verification framing. Phases now claim spec-leaf IDs and testers verify EARS statements; the `scenarios/` convention is retired entirely.

## What is added

- The pre-planning step and `plan/pre-planning-notes.md` artifact, with module-scoped constraint enumeration that does not pre-bind a decomposition.
- The @planner spawn invocation from impl-orch's body, including probe-request handling.
- The planning cycle cap (K=3) and `planning-blocked` escalation signal.
- The pre-execution structural gate driven by the planner's `Parallelism Posture` field, with the `structural-blocking` escalation signal.
- The terminated-spawn contract for plan review (impl-orch terminates, dev-orch spawns a fresh impl-orch for execution after approval).
- The `feasibility-questions` skill load (carried from v1 of this restructure — still wanted because pre-planning and mid-execution checks both apply the four questions).
- The escape hatch with both execution-time and planning-time arms, keyed on spec-leaf falsification rather than on test failure, and the `redesign-brief.md` emission behavior.
- Preservation hint consumption (on redesign cycles only): impl-orch reads the hint as the first thing in pre-planning, scopes runtime probing to the invalidated portion, and seeds the execution loop with the hint's preserve/replan decisions.
- Spec-leaf verification framing: phases claim leaf IDs, testers verify EARS statements, success = all claimed leaves verified.
- Spec-drift enforcement: runtime evidence contradicting a spec leaf fires the escape hatch; no silent spec bypass.

## Open questions

None at this draft. Anything unresolved at review time gets a decision in [../decisions.md](../decisions.md).
