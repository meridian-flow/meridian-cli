# Planner: Target Shape

This doc describes the @planner agent after the restructure. The agent profile survives — what changes is the caller (impl-orch instead of dev-orch), the central frame (parallelism-first decomposition), and the explicit wiring between the design's structural delta and the planner's cross-cutting prep phases.

Read [overview.md](overview.md) first for the surrounding topology. The Terrain section the planner consumes is specified in [terrain-contract.md](terrain-contract.md). When a redesign cycle is in progress, the planner also consumes a preservation hint as defined in [preservation-hint.md](preservation-hint.md). Skills loaded are listed at the end.

## What @planner is for

Decomposing a converged design into phases that an impl-orch can execute, *with parallelism as the central frame*. The unit of value is a written plan — `plan/overview.md`, per-phase blueprints, scenario ownership, status seed — materialized to disk before any phase coder is spawned. The plan must include a Parallelism Posture (described below) so that downstream consumers can detect when the design is structurally non-decomposable.

What is changing from the v0 planner: who calls it, what frame the decomposition is built around, and what enforcement infrastructure surrounds the central frame.

## The new caller relationship

Currently @planner is spawned by @dev-orchestrator after design-orch converges and before impl-orch starts. The plan lands, dev-orch reviews it with the user, and impl-orch is handed the plan as input. That ordering means the plan is committed before any agent has runtime context — which is what made plans go stale in the v1 streaming-parity-fixes case.

After the restructure, @planner is spawned by @impl-orchestrator. Sequence:

1. dev-orch spawns impl-orch with the design package.
2. impl-orch reads `design/` (including the Terrain section), reads any preservation-hint from a prior redesign cycle, answers the four feasibility questions against runtime context (probes, file scans, dependency walks), and writes its observations to `plan/pre-planning-notes.md`.
3. impl-orch spawns @planner via `meridian spawn -a planner -f ...` with the design package, the pre-planning notes, the preservation hint (if present), and any decision-log context attached.
4. @planner reads the inputs, decomposes the work, and writes the plan artifacts to disk.
5. impl-orch reads the plan, evaluates its structural posture (see "Parallelism Posture as a structural gate" below), and either reports back to dev-orch with the plan materialized or escalates a structural-blocking signal.
6. After dev-orch approves, dev-orch spawns a fresh impl-orch with the plan attached and the explicit "execute existing plan" semantics, and execution begins. (See [dev-orchestrator.md](dev-orchestrator.md) for the plan-review pause/resume contract.)

The planner does not see a coder spawn or a tester report. It does not run during execution. Its job ends when the plan artifacts land on disk.

## Why a separate agent and not in-context impl-orch work

The first draft of this restructure folded planning into impl-orch's own context. The user reversed that call. The reasoning, with the LLM-specific arguments leading and the framing arguments supporting:

- **Fresh context isolates planning from accumulated execution state.** Once impl-orch starts spawning coders and reading test reports, its conversation context fills with phase-level noise — fix attempts, smoke output, decision deltas. A re-plan late in execution under v1 would have happened in that polluted context. Under v2, planning runs in a fresh window with only the design, the pre-planning notes, and the preservation hint loaded. This is the killer feature, and it is unique to the spawn boundary.
- **Materialized handoffs survive compaction.** Pre-planning notes and the plan itself are files on disk. A planner spawn that crashes or compacts can be re-run from the same `-f` inputs and produce a comparable plan. In-context planning would lose state on every compaction.
- **Different skill loadouts focus the planner on decomposition craft.** The planner loads `planning`, `architecture`, and `feasibility-questions` with the parallelism question taking lead. Impl-orch's loadout is wider (coordination, staffing, fix-loop tooling). Bundling both in one body bloats both and dilutes each.
- **Different model selection enables routing to a planning-optimized model.** The planner runs on a model picked for decomposition reasoning; impl-orch can run on a model picked for execution coordination. Forcing one model for both is a tradeoff that hurts at least one axis.
- **The runtime-context objection has a better answer than collapsing the agent.** The original v1 critique was that planners do not have runtime knowledge. The fix is to give the planner runtime knowledge by having impl-orch run a pre-planning step first and pass the runtime observations to the planner via `-f`. The planner then has the runtime context the v1 planner lacked, without sharing impl-orch's execution context.
- **A separate spawn forces legibility.** Impl-orch's pre-planning notes are written down because they will be passed to another agent via `-f`. That legibility is itself the value — an inspectable record of what runtime context shaped the plan, which a future redesign cycle or audit can read.

The "decomposition and execution are different cognitive modes" framing from earlier drafts of this doc is dropped — it imports an anthropomorphic mental model that does not actually hold for LLMs. The real arguments are listed above and they do not depend on cognitive science.

Net: a separate planner agent under a different caller solves the v1 problem (planning before runtime context exists) without recreating the v1.draft problem (decomposition mashed into execution context) and gains four LLM-specific properties (fresh context, compaction tolerance, focused skills, model routing) that an in-context approach cannot match.

## Parallelism-first decomposition is the central frame

The planner's job is not "write a plan." It is "decompose the work so as much as possible can run in parallel." Every part of the plan should be justified by what it unlocks downstream. This is the lens the planner profile body must lead with — not as a section of the body, but as the first sentence.

Concrete shape:

- **Structural refactors land first.** Anything that touches many files — interface renames, module reshuffles, shared-helper extraction — runs as the earliest phases. These are cross-cutting changes that would create merge conflicts if they ran late, after parallel feature phases were already in flight. Getting them out of the way first removes the conflict surface that downstream parallelism depends on. Structural refactors are *rearrangement* of existing code; foundational prep is *creation* of new scaffolding (see [terrain-contract.md](terrain-contract.md) §"Structural refactors vs foundational prep" for the disambiguation). Both can land in cross-cutting prep phases. The planner identifies them by reading the Terrain section's structural delta items tagged `structural-prep-candidate: yes`.
- **Feature phases on disjoint modules then run in parallel.** Once the structural prep has landed, the planner identifies clusters of files that can be touched independently and groups them as parallel-eligible phases. The plan's execution rounds reflect this — Round 1 is structural prep, Round 2 is the parallel feature fanout, later rounds collapse the fanout back together.
- **Phase ordering is justified by parallelism, not just by logical dependency.** Two phases can be logically independent (no import dependency, no shared interface) and still have to be sequenced because they share a test harness, touch a shared registry, race on filesystem fixtures, or stomp the same env vars. The planner surfaces those constraints explicitly in the dependency map and explains why they prevent parallel execution.
- **The default question for any phase ordering is "what does this enable to run in parallel later?"** If the answer is "nothing," the phase is probably not at the right altitude — it should either be merged with a sibling, split into a structural prep + a feature, or reordered.

This frame is not a checklist — it is the lens through which decomposition decisions get evaluated. A plan that produces the right phases for the wrong reasons fails the frame, and a plan that produces a few phases with strong parallelism justification beats a plan that produces many phases without it.

## Structural prep candidate handling

The Terrain section in the design carries a structural delta with each item tagged `structural-prep-candidate: yes|no` (see [terrain-contract.md](terrain-contract.md) §"Structural delta"). The planner's required behavior:

- **Read every `yes`-tagged item** from the structural delta.
- **Map each item to a phase or to an explicit skip decision.** Every `yes` item must end up in one of three states in the plan:
  - Landed as part of phase N (named).
  - Bundled with another `yes` item into a single structural-prep phase.
  - Skipped, with a one-sentence reason (e.g. "covered by Phase 2 incidentally," "design revision removed the need," "no longer applies after pre-planning runtime check").
- **Unaccounted items are a planner bug.** A plan that ignores a `structural-prep-candidate: yes` item without a skip decision is incomplete and impl-orch should re-spawn the planner with the gap as feedback.

This is the structural-decision-traceability mechanism that the design is otherwise missing. Without it, the design-orch produces a delta and the planner is trusted to use it; with it, every structural prep item has a visible chain from the design's claim to the plan's response.

The planner may also identify additional structural prep that the design did not flag — for example, if pre-planning notes reveal a runtime constraint that requires a refactor the design did not anticipate. The plan should call this out explicitly as "planner-added structural prep, not in design's structural delta" so the next reviewer (dev-orch or the user) can decide whether to push the addition back to design-orch or accept it as a pre-planning discovery.

## Parallelism justification template

Every ordering decision in `plan/overview.md` must carry a parallelism justification. The required template is:

```markdown
### Round 1: Structural prep
Phases: P1 (auth refactor), P2 (token store interface)

**Parallelism justification:** Both phases are structural refactors tagged in the design's structural delta. P1 and P2 touch disjoint modules (`auth/` and `tokens/` respectively) and share no test fixtures. Running them in parallel removes the cross-cutting refactor surface for Rounds 2+ in one round instead of two.

### Round 2: Parallel feature fanout
Phases: P3 (auth feature A), P4 (auth feature B), P5 (token feature C), P6 (token feature D)

**Parallelism justification:** P3-P4 work on the parser side of `auth/` (depends on P1's split). P5-P6 work on the token store side (depends on P2's interface extraction). Within each cluster, the features touch disjoint files within the post-prep module shape. All four phases share the test runner but have non-overlapping test paths.

### Round 3: Integration
Phases: P7 (auth+token integration smoke)

**Parallelism justification:** Sequenced after Round 2 because it depends on all four feature phases being committed. Cannot be parallelized with anything in Round 2. This is a sequential constraint; the parallelism gain came from Round 2's fanout.
```

The pattern: name the round, name what it unlocks, name the constraint that prevents earlier execution. Justifications that say "this depends on the previous phase" without naming what the dependency is or what it unlocks fail the frame.

## Parallelism Posture as a structural gate

`plan/overview.md` must include a top-level `Parallelism Posture` field with a required value and a cause classification:

```markdown
Parallelism Posture: parallel | limited | sequential
Cause: inherent constraint | structural coupling preserved by design | runtime constraint | feature work too small to fan out
```

- **parallel** — the plan has at least one round with two or more parallel-eligible phases, justified by named clusters from the Terrain section or the planner's runtime-informed analysis.
- **limited** — the plan has some parallelism but is dominated by sequential constraints. Cause must be named.
- **sequential** — the plan is entirely sequential or near-sequential. Cause must be named.

The cause field is the gate. When the cause is `structural coupling preserved by design`, the planner is signaling that the design's target state is structurally non-decomposable for parallelism, and impl-orch must treat this as a pre-execution structural escalation rather than a normal plan to execute. See [impl-orchestrator.md](impl-orchestrator.md) §"Pre-execution structural gate" for what impl-orch does with this signal. Briefly: impl-orch stops before execution and routes a structural escalation to dev-orch via the redesign-brief mechanism (see [redesign-brief.md](redesign-brief.md) §"Parallelism-blocking structural issues discovered post-design").

The other cause values (`inherent constraint`, `runtime constraint`, `feature work too small to fan out`) are informational, not blocking. A sequential plan caused by an inherent constraint is a real plan and impl-orch executes it. A sequential plan caused by structural coupling preserved by design is a design problem and impl-orch escalates it.

## Planning-cycle cap

Impl-orch is allowed to re-spawn the planner when the plan is missing required sections, references missing scenario IDs, or contradicts the pre-planning notes. To prevent pathological loops where the planner cannot converge on a plan consistent with its inputs, the planning cycle is capped at **three planner spawns per work item per impl-orch cycle**. After the third planner spawn fails to produce a converging plan, impl-orch must escalate to dev-orch with a `planning-blocked` signal rather than re-spawning a fourth time. See [impl-orchestrator.md](impl-orchestrator.md) §"Planning cycle cap" for the impl-orch side and `decisions.md` D12 for the rationale.

A "failed" planner spawn is one that produces a plan with: missing required sections, missing scenarios, contradiction with pre-planning notes, or hand-wavy parallelism justifications that do not cite real constraints. A spawn that produces a complete and consistent plan does not advance the cycle counter.

The cap is distinct from the redesign cycle cap (D7). They count separately. Exhausting the planner cap escalates to dev-orch with a different signal than the execution-time falsification escape hatch.

## Probe-request channel

The planner does not run probes itself. But the planner is allowed to identify gaps in the pre-planning notes — runtime data the planner needs that impl-orch did not capture. When this happens, the planner has two options:

1. **Make a best-effort decomposition with the data on hand and flag the gaps explicitly** in `plan/overview.md` under a "Pre-planning gaps" section. Each gap names what data was missing and what assumption the planner made in its absence.
2. **Terminate the spawn with a "needs more probing" report** instead of a plan. The report names the specific runtime questions the planner could not answer. Impl-orch reads the report, runs the additional probes, updates the pre-planning notes, and re-spawns the planner with the expanded notes. This is a probe-request round; it counts toward the planning cycle cap (above) so it cannot loop indefinitely.

The choice between options is the planner's judgment. Small gaps with safe defaults take option 1; gaps that would force the planner to guess on a structural question take option 2. The planner should not guess silently — every assumption made because of a missing pre-planning observation must be visible somewhere in the plan or report.

## Why parallelism matters here specifically

The user's framing: parallel work is the throughput knob, and a tangled structure blocks parallelism no matter how careful the planning is. If the design has landed a coupled mess, the planner cannot decompose it into independent phases — every phase reads from and writes to the same surfaces, so parallel coders would race each other. The only outcome is sequential phases or merge hell.

This is why structure and modularity have been promoted to first-class design concerns (see [design-orchestrator.md](design-orchestrator.md) and [terrain-contract.md](terrain-contract.md)). A design that fixes the structure unlocks parallelism downstream; a design that preserves it locks the planner into a sequential plan no matter how well it does its job.

The planner is the agent that consumes the structure the design lands. If the design is structurally sound, the planner produces a parallelism-rich plan. If the design is not, the planner's first move is to surface that — not produce a plan that papers over the coupling. The Parallelism Posture field with `cause: structural coupling preserved by design` is the explicit mechanism for that escalation; without it, the planner's structural concern would dissipate into prose that downstream consumers might not act on.

## Inputs the planner consumes

The planner is spawned with these attached via `-f`:

- **design/** — every doc in the design package, including `overview.md` (which carries the Terrain section) and `terrain-contract.md` (the contract for what Terrain provides). The planner reads the structural delta with `structural-prep-candidate: yes` items as its starting set for cross-cutting prep.
- **scenarios/** — the verification contract seeded by design-orch. The planner reads existing scenarios so it knows which phases own which scenarios, and appends new scenarios for any cross-phase or sequencing hazards it surfaces.
- **decisions.md** — the design-time decision log, so the planner does not propose phasing that contradicts an already-rejected approach.
- **plan/pre-planning-notes.md** — runtime-informed feasibility answers, probe results, terrain re-interpretation against the actual codebase, anything impl-orch observed that the design-orch could not have known. This is the file that turns the planner from a context-blind agent into a runtime-aware one.
- **plan/preservation-hint.md** *(only on redesign cycles)* — the preservation contract from the previous cycle. When present, the planner respects the preservation anchor and replans only from `replan-from-phase` onward.

The planner does not run probes itself. If a probe is needed, that is impl-orch's job in the pre-planning step, before the planner is spawned. The planner consumes results, not raw exploration capability — but it can request additional probes via the probe-request channel above.

### What pre-planning-notes contain — and what they don't

Pre-planning notes capture what impl-orch thought to probe. They are a *projection* of runtime context, not equivalent to runtime context itself. Negative results, interaction effects, tacit codebase knowledge, and "shape and feel" observations may be absent. The planner should read the notes as "the runtime data impl-orch chose to write down" rather than "everything that is true at runtime." When the planner's decomposition requires runtime context the notes don't cover, the planner uses the probe-request channel rather than guessing.

## Outputs the planner produces

The planner writes these to `$MERIDIAN_WORK_DIR/`:

- **plan/overview.md** — the phases, their dependency relationships, the execution rounds (parallel-eligible groupings), the **Parallelism Posture** field with cause classification, an explicit parallelism justification per round, and the structural-prep candidate handling table (every `structural-prep-candidate: yes` Terrain item mapped to a phase or skipped with reason).
- **plan/phase-N-<slug>.md** — per-phase blueprints with scope, files to modify, dependencies, interface contracts, constraints, verification criteria, and scenario IDs from `scenarios/`.
- **plan/scenario-ownership.md** — every scenario file in `scenarios/` claimed by exactly one phase. Unclaimed scenarios are a planner bug.
- **plan/status.md** — phases seeded with appropriate values. On a first-cycle plan, all phases are `not-started`. On a redesign-cycle plan, phases honor the preservation hint's `preserved`, `partially-invalidated`, `replanned`, `new`, and `not-started` values (see [preservation-hint.md](preservation-hint.md) §"Status field representation").
- **scenarios/SNNN-*.md** — any new scenarios the planner surfaces during decomposition (cross-phase interactions, sequencing hazards, phase-boundary edge cases the design did not anticipate).

The plan must include a Mermaid diagram in `plan/overview.md` showing phase dependencies and execution rounds, so a human or downstream agent can see the parallel structure at a glance.

## Skills loaded

The planner profile keeps its existing skills with the parallelism-first frame inlined into the planner profile body itself, not deferred to a skill update:

- **`planning`** — decomposition craft. Stays loaded. The skill body needs a downstream update to make parallelism-first the central frame across all callers (see "Required follow-up: planning skill update" below). Until that update lands, the planner profile body must carry the parallelism-first frame inline so the planner reads it from the profile even if the loaded skill body has not been updated.
- **`agent-staffing`** — team composition. Stays loaded.
- **`architecture`** — structural reasoning. Stays loaded.
- **`mermaid`** — dependency diagrams. Stays loaded.
- **`decision-log`** — capturing planner-time decisions. Stays loaded.
- **`dev-artifacts`** — where artifacts go. Stays loaded.
- **`meridian-cli`** — the CLI surface. Stays loaded.
- **`feasibility-questions`** *(new addition)* — the four shared questions. Loaded so the planner reads impl-orch's pre-planning answers in the same frame design-orch and impl-orch used to write them.

The planner does not load `meridian-spawn` because it does not spawn other agents. It produces artifacts and exits.

## What is unchanged from the current planner profile

- It is a single-shot agent. It runs once per planning pass, produces artifacts, and terminates. It does not loop or supervise execution.
- It writes to disk. The plan is materialized, not held in conversation.
- It uses `agent-staffing` to compose per-phase teams and final review fanout — staffing is part of the plan, not something impl-orch invents on the fly.
- It includes scenario IDs in every blueprint. Phases that have no scenarios are either incomplete or unnecessary; the planner surfaces which.
- It writes a complete plan or a plan that explicitly states what is missing. It does not write a partial plan and call it done.

## Required follow-up: planning skill update

The current `planning` skill body talks about phase decomposition, blueprint shape, dependency mapping, and staffing. It mentions parallelism but does not lead with it. After this restructure lands, the skill needs a revision pass to make parallelism-first the central frame:

- **Lead with the parallelism question.** The first question the skill asks is not "what are the phases?" but "what would have to be true for these phases to run in parallel, and what is preventing that?"
- **Add a structural-prep section.** The skill should explicitly name the pattern of "land cross-cutting refactors first to unlock parallel feature work later" as a default decomposition move, with examples of when it applies and when it does not.
- **Promote runtime-constraint detection.** The current skill mentions integration boundaries; it should also call out shared test harnesses, global registries, filesystem fixtures, env-var collisions, and other things that look parallel at the interface layer but are not at the runtime layer.
- **Reframe execution rounds.** Today the skill describes rounds as "phases that can run in parallel." That framing is correct but passive. A parallelism-first skill describes rounds as the output of a decomposition that was actively shaped to maximize parallel work.
- **Tighten the relationship to feasibility-questions.** The four shared questions already cover parallelism as one axis. The skill should reference them explicitly so a planner using `planning` knows where the parallelism question fits relative to feasibility, decomposition, and foundational prep.
- **Reference the structural-prep candidate tag in the Terrain contract.** The skill should describe the planner's responsibility to map every tagged item to a phase or skip decision, with the candidate-handling table in `plan/overview.md` as the canonical record.

**This follow-up is a hard prerequisite of any plan written under the v2 topology.** The planner profile body inlines the central-frame contract so a planner spawned before the skill update lands still produces a v2-shaped plan. But the skill update is required before the next major work item begins, so the skill body and the profile body do not drift indefinitely. Dev-orch tracks this as an open work item and prioritizes it before the next design pass that depends on parallelism-first decomposition.

If the skill update has not landed and a planner is spawned anyway, the planner profile body's inlined frame is the source of truth and the skill is treated as supplementary. This avoids the failure mode where a v2 planner runs against a v0 skill and produces a v0-shaped plan because the central frame lived only in design prose.

## Open questions

None at this draft. Anything unresolved at review time gets a decision in [../decisions.md](../decisions.md).
