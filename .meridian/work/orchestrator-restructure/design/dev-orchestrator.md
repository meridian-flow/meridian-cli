# Dev Orchestrator: Target Shape

This doc describes the dev-orchestrator's behavior after the restructure. The largest change is the autonomous redesign loop — dev-orch can route impl-orch bail-outs back to design-orch without waiting for user input. The delegation chain to @planner shifts: dev-orch no longer spawns @planner directly, impl-orch does. Plan review uses a terminated-spawn contract — impl-orch terminates after the plan materializes and dev-orch spawns a fresh impl-orch for execution. Dev-orch also produces the preservation hint that drives the next impl-orch cycle after a redesign. The interactive role with the user is otherwise unchanged.

Read [overview.md](overview.md) first for surrounding context. The preservation hint dev-orch produces is specified in [preservation-hint.md](preservation-hint.md). The Terrain section dev-orch consumes when reviewing design packages is specified in [terrain-contract.md](terrain-contract.md).

## What dev-orch does

Stays the continuity between the user and the autonomous orchestrators. Its value is still in understanding what the user actually wants, gathering context, forming an opinion, and making sure the right work gets done — not in doing the work itself. None of that changes.

What changes is the delegation chain and the loop it participates in. The direct planner handoff moves down to impl-orch. The autonomous redesign loop is added. Review checkpoints around the materialized plan become part of the normal flow.

## The delegation chain

After the user approves a direction, dev-orch spawns design-orchestrator with scoped context — requirements, relevant files, and any specific tradeoffs to explore. The design-orch run is unchanged on this side of the boundary: dev-orch waits for it to converge, reads the returned design package (docs + decisions + scenarios + Terrain observations), and presents it to the user in plain terms.

Once the user approves the design, dev-orch spawns the **planning** impl-orchestrator with the design package. **It does not spawn @planner directly.** That handoff has moved one layer down — impl-orch is now the caller of @planner, after impl-orch has done its pre-planning step against runtime context. Dev-orch's job at this point is to wait for the planning impl-orch to terminate with a plan-ready terminal report.

The sequence dev-orch sees, in order:

1. Dev-orch spawns the planning impl-orch with the design package (and the preservation hint, on a redesign cycle).
2. Planning impl-orch internally reads design + Terrain + preservation hint, runs pre-planning, spawns @planner, evaluates the plan against the structural gate.
3. Planning impl-orch terminates with one of three terminal report shapes:
   - **plan-ready** — plan converged, all gates passed; report names plan files on disk.
   - **structural-blocking** — planner returned a plan with `Cause: structural coupling preserved by design`; report cites the planning-time redesign brief.
   - **planning-blocked** — planner could not converge after K=3 spawns; report cites the planning-time redesign brief.
4. Dev-orch reads the terminal report and routes accordingly. plan-ready hits the plan review checkpoint below; structural-blocking and planning-blocked enter the redesign loop (see "The autonomous redesign loop").
5. After dev-orch approves a plan, dev-orch spawns a **fresh** impl-orch — the **execution** impl-orch — with the approved plan attached via `-f` and an explicit "execute existing plan" prompt. The execution impl-orch skips pre-planning and the planner spawn entirely and starts directly at the execution loop.

The reason dev-orch is no longer the planner caller is that the planner needs runtime context to write a plan that won't go stale, and only impl-orch can gather runtime context. Inserting dev-orch between impl-orch and the planner would force dev-orch to relay information it does not own. The simpler ordering is to let impl-orch run pre-planning and the planner spawn as one unit and present the result. See [planner.md](planner.md) for the planner-side reasoning and [impl-orchestrator.md](impl-orchestrator.md) for impl-orch's pre-planning step.

The reason the planning impl-orch and the execution impl-orch are separate spawns — rather than one suspended impl-orch that pauses for review and resumes — is that meridian's design is crash-only. State lives on disk, not in conversation context. A suspended impl-orch holding plan state in memory cannot survive a crash, a compaction, or a restart. The terminated-spawn contract puts the plan on disk and lets dev-orch hand it to a fresh process. See `decisions.md` D15 for the rationale and the rejected suspended-spawn alternative.

## The plan review checkpoint

When the planning impl-orch terminates with a plan-ready report, dev-orch reads the plan from disk and reviews it against the design and the user's stated intent. The judgment of how much review the plan deserves belongs here — not in impl-orch's body, not in a rigid rule. For substantive work, dev-orch reviews thoroughly and either approves or pushes back. For trivial work where the plan is obvious, dev-orch approves without user involvement and immediately spawns the execution impl-orch.

The review criteria dev-orch applies, in priority order:

1. **Parallelism Posture is named and justified.** `plan/overview.md` carries a `Parallelism Posture` field with a value (parallel/limited/sequential) and a cause classification. A plan that omits the field, leaves the cause unnamed, or names a cause that does not match the structure of the plan fails review.
2. **Per-round parallelism justifications cite real constraints.** Each round in the plan has a justification that names what the round unlocks and what prevents earlier execution. Hand-wavy "this depends on the previous phase" justifications without naming the specific dependency or what it unlocks fail review.
3. **Structural-prep candidate handling is complete.** Every `structural-prep-candidate: yes` item from the design's Terrain section is mapped to a phase or to an explicit skip decision. Unaccounted items are a planner bug and dev-orch pushes back.
4. **Scenarios are claimed in `plan/scenario-ownership.md`.** Every scenario file in `scenarios/` is claimed by exactly one phase. Unclaimed or duplicated scenarios are a bug.
5. **Mermaid fanout matches the textual rounds.** The diagram in `plan/overview.md` shows the same parallel structure the round descriptions claim. Drift between diagram and prose is a bug.
6. **Plan does not contradict the user's stated intent.** Phases that re-introduce a constraint the user rejected, or that defer work the user prioritized, are a bug.

If the plan fails any criterion, dev-orch pushes back. Pushback is not in-context iteration with a suspended impl-orch — dev-orch spawns a fresh planning impl-orch with the original design plus the review feedback as additional context. That fresh impl-orch re-runs the planner spawn (subject to the K=3 planning cycle cap in [impl-orchestrator.md](impl-orchestrator.md) §"Planning cycle cap") and emits a new plan-ready report. The pushback loop is between dev-orch and successive planning impl-orch spawns; it does not advance the redesign loop-guard counter because no design change is happening, but it does count toward the planning cycle cap on the impl-orch side.

The reason the judgment lives in dev-orch rather than being a hard rule is that review cost and review value both scale with scope, and the threshold is not knowable in advance. A rigid "always review" rule wastes time on trivia; a rigid "never review" rule misses the catch opportunity. The judgment has to happen at the altitude where scope is visible, which is dev-orch.

## The autonomous redesign loop

The redesign loop is entered when an impl-orch terminal report cites a redesign brief. There are three entry signals, all routed through the same loop:

- **Execution-time falsification** — execution impl-orch hit runtime evidence that contradicts a structural design assumption mid-execution. Brief uses the execution-time sections of [redesign-brief.md](redesign-brief.md).
- **structural-blocking** — planning impl-orch's pre-execution structural gate fired (planner returned `Cause: structural coupling preserved by design`). Brief uses the planning-time sections of [redesign-brief.md](redesign-brief.md), specifically the "Parallelism-blocking structural issues" section.
- **planning-blocked** — planning impl-orch's planner cycle cap (K=3) was exhausted without convergence. Brief cites the planner's last-attempt artifact and the gap reasoning impl-orch provided on each re-spawn.

This is new behavior — the current topology has no mechanism for any of these handoffs.

Dev-orch reads the brief directly. The brief format carries what was completed, what evidence falsified the design (or what prevented planner convergence), what needs to change, and what to preserve. Dev-orch's job is to scope the redesign session correctly and route it.

The decision dev-orch makes: is this a design problem that needs design-orch re-engagement, or is it a scope problem that the next impl-orch cycle can resolve with a narrower plan? A brief that claims architectural falsification but only cites a single test failure is probably scope, not design. A brief that cites end-to-end smoke evidence against a protocol assumption is probably design. A structural-blocking brief is almost always a design problem — the planner is signaling that the design's target state preserves a coupling that no decomposition can route around. A planning-blocked brief requires reading the gap reasoning to decide whether the design is unclear (design problem) or the pre-planning notes were incomplete (scope problem solved by re-running with better probes). The call lives in dev-orch because dev-orch is the one that has to answer to the user for the decision.

If dev-orch judges it a design problem, it spawns design-orchestrator with:

- The original design package
- The redesign brief as context
- A scoped instruction: which parts of the design need revision, which should stay, what the preservation list means for the revision

Dev-orch then waits for the design-orch convergence as it would for any design session.

### Dev-orch produces the preservation hint

When the revised design is ready, dev-orch produces the **preservation hint** before spawning the next impl-orch. The hint format is in [preservation-hint.md](preservation-hint.md). Production steps:

1. Read the redesign brief's preservation section (what impl-orch claimed could be preserved, what was partially invalidated, what was fully invalidated).
2. Read the revised design docs to confirm or revise that assessment — design-orch may have narrowed or widened the change scope, and dev-orch updates the preservation lists accordingly.
3. Decide the `replan-from-phase` anchor — the first phase number that must be replanned. Everything before it is preserved or partially-invalidated; everything from it onward is replanned.
4. Replay the constraints-that-still-hold from the brief into the hint so impl-orch and the planner have them in direct context without needing to re-read the brief.
5. List any new scenarios added during the redesign cycle that the planner must claim in the new plan.
6. Write `plan/preservation-hint.md`. The hint is overwritten on each redesign cycle, not appended — cycle history lives in the brief and `decisions.md`.

Dev-orch then spawns a fresh planning impl-orch with the revised design package and the preservation hint attached via `-f`. Impl-orch's next pre-planning + planner spawn starts from the first invalidated phase forward rather than re-planning everything — the preservation hint scopes what the planner needs to re-decompose. Without the hint, default-preserve (D8) would degrade into ad-hoc handling and the planner would re-decompose work that is already valid.

If dev-orch updates a preservation status that the brief originally claimed differently (e.g. dev-orch decides a brief-listed "partially invalidated" phase is actually fully preserved after reading the revised design), dev-orch records the rationale in `decisions.md` for audit. The hint is dev-orch's final call.

### When dev-orch judges it scope, not design

If dev-orch judges the brief is a scope problem rather than a design problem, two paths:

- **Push back on the brief.** Dev-orch can reject the brief and ask impl-orch for a narrower bail justification. This typically applies to execution-time briefs where the evidence does not actually falsify a structural assumption.
- **Spawn a fresh impl-orch with scope adjustments and no design-orch cycle.** The path used when the brief evidence is real but localized — for example, a planning-blocked brief where the gap is clearly in pre-planning probe coverage rather than in the design itself. Dev-orch instructs the fresh impl-orch on what additional probes to run before re-spawning the planner.

Both scope-only paths skip the design-orch cycle and skip preservation hint production (no design changed, nothing to preserve differently).

## The loop runs without user input by default

The reason dev-orch handles the redesign loop autonomously is that the user is a bottleneck on response time, not on judgment. Dev-orch has the original requirements, the full design context, and the brief — routing the redesign does not require human-unique information. Waking the user to say "this needs a redesign, should I redesign it?" is asking permission to do the thing that is already the right move.

Autonomy with visibility, though. Every bail-out triggers a user notification. Every redesign cycle is logged to `decisions.md`. The user can intervene at any time — by responding to the notification, by running `meridian work show`, by pausing the orchestrator chain. The point is that autonomy is not opacity; the user can audit after the fact and intervene during the run if they want.

## Loop guards

Dev-orch tracks redesign cycles per work item. The counter advances on every autonomous design-orch re-spawn regardless of which signal triggered it (execution-time, structural-blocking, or planning-blocked). If a work item goes through two autonomous redesign cycles without converging, dev-orch escalates to the user on the third bail-out rather than initiating another autonomous cycle. The escalation carries all prior briefs, all prior decisions, the preservation hints from each cycle, and a summary of what each cycle tried to fix — the user is not starting cold, but dev-orch is declining to route again without human input.

The reason two cycles is the threshold: a single cycle is a normal mid-course correction, two cycles is a scoping issue worth noticing, three or more cycles means the framing of the redesign itself is probably wrong and dev-orch should not trust its own routing. The threshold is a heuristic for when dev-orch's confidence should drop, not a hard cap. See `decisions.md` D7 for the rationale.

Each bail-out also has to cite new evidence not present in prior briefs. A brief that repeats the same falsification claim from a previous cycle is rejected as a duplicate — it does not advance the cycle counter and it does not trigger a new design-orch spawn. That guard prevents impl-orch from looping on a failure it cannot describe in new terms.

The redesign cycle counter (this section, K=2) is **distinct from the planning cycle cap** (K=3, in [impl-orchestrator.md](impl-orchestrator.md) §"Planning cycle cap"). The planning cap counts planner re-spawns within a single impl-orch cycle. The redesign cap counts design-orch re-spawns across the whole work item. They count separately — exhausting the planning cap fires `planning-blocked` (which advances the redesign counter only if dev-orch then routes it to a design-orch cycle). See `decisions.md` D12 for the planning cap rationale.

## Final report to the user

At the end of a work item, dev-orch's report covers what was built, what passed, any redesign cycles that happened (with per-cycle briefs and decisions), and what the final shape looks like versus the original design. The user sees the full trajectory, including any autonomous corrections, so the autonomy is auditable.

For work items that went straight through without bail-outs, the report is what it is today: a summary of the implementation against the design.

## Skills loaded

The dev-orchestrator profile keeps its current skills, with `agent-staffing` staying because dev-orch still needs to understand staffing when presenting plans to the user and when scoping redesign sessions. The `planning` skill is removed from dev-orch — decomposition craft lives on @planner, which dev-orch does not call directly.

## What is deleted

- The direct dev-orch → @planner spawn step. Dev-orch no longer spawns @planner. (The planner agent profile itself stays — see [planner.md](planner.md). It is now spawned by impl-orch.)
- The `planning` skill load on dev-orch's profile.
- Any language in dev-orch's body framing the plan as something dev-orch produces by spawning a planner agent of its own.
- The implied "single long-lived impl-orch" model where dev-orch holds a suspended impl-orch process across the plan review checkpoint. Replaced by terminated-spawn contract: planning impl-orch terminates, dev-orch reads the plan from disk, dev-orch spawns a fresh execution impl-orch for the run.

## What is added

- The plan review criteria checklist (Parallelism Posture, per-round justifications, structural-prep handling, scenario claims, mermaid fanout, intent alignment).
- Structural-blocking and planning-blocked terminal report handling (in addition to execution-time bail-outs) as redesign loop entry signals.
- Preservation hint production after every design-orch revision cycle, written by dev-orch to `plan/preservation-hint.md` and attached to the next planning impl-orch via `-f`.
- The fresh execution impl-orch spawn after plan approval, with explicit "execute existing plan" semantics that bypass pre-planning and the planner spawn.

## What stays

- The interactive role with the user: understanding intent, gathering context, forming a view, presenting recommendations.
- The design-orchestrator handoff with conversation context and scoped exploration briefs.
- The plan review checkpoint after impl-orch returns with a materialized plan — the responsibility for judging the plan and either approving or pushing back stays with dev-orch.
- The per-commit lifecycle with git status checks and concurrent-work safety.
- The judgment about matching process to problem: some work goes straight to a coder + verifier, some needs a full design cycle, some needs multiple design rounds.
