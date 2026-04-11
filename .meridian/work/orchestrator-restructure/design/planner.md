# Planner: Target Shape

This doc describes the @planner agent after the v3 restructure. The agent profile survives — what changes is the caller (impl-orch instead of dev-orch), the inputs (the two-tree design package plus `refactors.md` and `feasibility.md`), the central frame (parallelism-first decomposition), and the explicit wiring between the design's refactor agenda and the planner's cross-cutting prep phases.

Read [overview.md](overview.md) first for the surrounding topology. The design artifacts the planner consumes — `design/spec/`, `design/architecture/`, `design/refactors.md`, `design/feasibility.md` — are produced by design-orch per [design-orchestrator.md](design-orchestrator.md). The structural analysis workflow that feeds `refactors.md` and `feasibility.md` is specified in [terrain-contract.md](terrain-contract.md). When a redesign cycle is in progress, the planner also consumes a preservation hint as defined in [preservation-hint.md](preservation-hint.md). Skills loaded are listed at the end.

## What @planner is for

Decomposing a converged design into phases that an impl-orch can execute, *with parallelism as the central frame*. The unit of value is a written plan — `plan/overview.md`, per-phase blueprints, spec-leaf ownership, status seed — materialized to disk before any phase coder is spawned. The plan must include a Parallelism Posture (described below) so that downstream consumers can detect when the design is structurally non-decomposable.

Under v3, the planner's role narrows significantly. Design-orch has already done the structural analysis (landed in the architecture tree), written the refactor agenda (`refactors.md`), and probed real systems (`feasibility.md`). The planner's job is no longer to invent the decomposition from scratch — it is to **sequence the refactor agenda design identified, sequence the architecture subtrees for parallel execution, and map phases to spec leaves**. Parallelism comes from two sources: disjoint architecture subtrees (structural parallelism) and disjoint spec-leaf coverage (verification parallelism). Both must hold for phases to run in parallel; interface-independent phases that share spec leaves still collide at the verification layer.

What is changing from the v0 planner: who calls it, what frame the decomposition is built around, what inputs shape the decomposition, and what enforcement infrastructure surrounds the central frame.

## The new caller relationship

Currently @planner is spawned by @dev-orchestrator after design-orch converges and before impl-orch starts. The plan lands, dev-orch reviews it with the user, and impl-orch is handed the plan as input. That ordering means the plan is committed before any agent has runtime context — which is what made plans go stale in the v1 streaming-parity-fixes case.

After the restructure, @planner is spawned by @impl-orchestrator. Sequence:

1. dev-orch spawns impl-orch with the design package (`design/spec/`, `design/architecture/`, `design/refactors.md`, `design/feasibility.md`, `decisions.md`, and `requirements.md`).
2. impl-orch reads the design package's root overviews, reads `refactors.md` and `feasibility.md` (design-orch's gap-finding output), reads any preservation-hint from a prior redesign cycle, answers the four feasibility questions against runtime context (probes for any `impl-orch must resolve during pre-planning` tagged entries in `feasibility.md`, plus runtime constraints design could not anticipate like test-suite shape and fixture races), and writes its observations to `plan/pre-planning-notes.md`.
3. impl-orch spawns @planner via `meridian spawn -a planner -f ...` with the design package, the pre-planning notes, the preservation hint (if present), and any decision-log context attached.
4. @planner reads the inputs, decomposes the work, and writes the plan artifacts to disk.
5. impl-orch reads the plan, evaluates its structural posture (see "Parallelism Posture as a structural gate" below), and either reports back to dev-orch with the plan materialized or escalates a structural-blocking signal.
6. After dev-orch approves, dev-orch spawns a fresh impl-orch with the plan attached and the explicit "execute existing plan" semantics, and execution begins. (See [dev-orchestrator.md](dev-orchestrator.md) for the plan-review pause/resume contract.)

The planner does not see a coder spawn or a tester report. It does not run during execution. Its job ends when the plan artifacts land on disk.

## Why a separate agent and not in-context impl-orch work

The first draft of this restructure folded planning into impl-orch's own context. The user reversed that call. The reasoning, with the LLM-specific arguments leading and the framing arguments supporting:

- **Fresh context isolates planning from accumulated execution state.** Once impl-orch starts spawning coders and reading test reports, its conversation context fills with phase-level noise — fix attempts, smoke output, decision deltas. A re-plan late in execution under v1 would have happened in that polluted context. Under v3, planning runs in a fresh window with only the design package, the pre-planning notes, and the preservation hint loaded. This is the killer feature, and it is unique to the spawn boundary.
- **Materialized handoffs survive compaction.** Pre-planning notes and the plan itself are files on disk. A planner spawn that crashes or compacts can be re-run from the same `-f` inputs and produce a comparable plan. In-context planning would lose state on every compaction.
- **Different skill loadouts focus the planner on decomposition craft.** The planner loads `planning`, `architecture`, and `feasibility-questions` with the parallelism question taking lead. Impl-orch's loadout is wider (coordination, staffing, fix-loop tooling). Bundling both in one body bloats both and dilutes each.
- **Different model selection enables routing to a planning-optimized model.** The planner runs on a model picked for decomposition reasoning; impl-orch can run on a model picked for execution coordination. Forcing one model for both is a tradeoff that hurts at least one axis.
- **The runtime-context objection has a better answer than collapsing the agent.** The original v1 critique was that planners do not have runtime knowledge. The fix is to give the planner runtime knowledge by having impl-orch run a pre-planning step first and pass the runtime observations to the planner via `-f`. The planner then has the runtime context the v1 planner lacked, without sharing impl-orch's execution context.
- **A separate spawn forces legibility.** Impl-orch's pre-planning notes are written down because they will be passed to another agent via `-f`. That legibility is itself the value — an inspectable record of what runtime context shaped the plan, which a future redesign cycle or audit can read.

The "decomposition and execution are different cognitive modes" framing from earlier drafts of this doc is dropped — it imports an anthropomorphic mental model that does not actually hold for LLMs. The real arguments are listed above and they do not depend on cognitive science.

Net: a separate planner agent under a different caller solves the v1 problem (planning before runtime context exists) without recreating the v1.draft problem (decomposition mashed into execution context) and gains four LLM-specific properties (fresh context, compaction tolerance, focused skills, model routing) that an in-context approach cannot match.

## Parallelism-first decomposition is the central frame

The planner's job is not "write a plan." It is "decompose the work so as much as possible can run in parallel, and map every phase to the spec leaves it satisfies." Every part of the plan should be justified by what it unlocks downstream. This is the lens the planner profile body must lead with — not as a section of the body, but as the first sentence.

Concrete shape:

- **Refactor agenda lands first.** Anything named in `design/refactors.md` — interface renames, module reshuffles, shared-helper extraction, decoupling moves — runs as the earliest phases. These are cross-cutting changes that would create merge conflicts if they ran late, after parallel feature phases were already in flight. Getting them out of the way first removes the conflict surface that downstream parallelism depends on. Refactors are *rearrangement* of existing code; foundational prep is *creation* of new scaffolding. Both can land in cross-cutting prep phases. The planner identifies refactors by reading `design/refactors.md` directly; it identifies foundational prep by reading the architecture tree's target-state sections.
- **Feature phases on disjoint architecture subtrees then run in parallel.** Once the refactor prep has landed, the planner identifies subtrees of `design/architecture/` that can be implemented independently and groups them as parallel-eligible phases. Parallelism comes from two sources in v3: **disjoint architecture subtrees** (structural parallelism) and **disjoint spec-leaf coverage** (verification parallelism). Both must hold for phases to run in parallel — interface-independent phases that claim overlapping spec leaves still collide at the verification layer. The plan's execution rounds reflect this: Round 1 is refactor prep, Round 2 is the parallel feature fanout, later rounds collapse the fanout back together.
- **Phase ordering is justified by parallelism, not just by logical dependency.** Two phases can be logically independent (no import dependency, no shared interface) and still have to be sequenced because they share a test harness, touch a shared registry, race on filesystem fixtures, or stomp the same env vars. The planner surfaces those constraints explicitly in the dependency map and explains why they prevent parallel execution.
- **The default question for any phase ordering is "what does this enable to run in parallel later?"** If the answer is "nothing," the phase is probably not at the right altitude — it should either be merged with a sibling, split into a refactor prep + a feature, or reordered.

This frame is not a checklist — it is the lens through which decomposition decisions get evaluated. A plan that produces the right phases for the wrong reasons fails the frame, and a plan that produces a few phases with strong parallelism justification beats a plan that produces many phases without it.

## The planner does not invent refactors

Critical constraint in v3: **the planner sequences the refactor agenda design-orch produced; it does not invent new refactors.** If pre-planning reveals that a refactor the design did not anticipate is necessary for a parallelism-rich plan, the planner does **not** silently add it to the plan. It escalates.

Two paths for a planner-detected missing refactor:

1. **Structural-blocking escalation.** If the missing refactor is a structural coupling that blocks parallel decomposition — the plan cannot be written with a `parallel` or `limited` posture unless the refactor lands first — the planner sets `Parallelism Posture: sequential` with `Cause: structural coupling preserved by design`, names the specific coupling in the cause narrative, and terminates. Impl-orch reads the posture and fires the structural-blocking bail-out to dev-orch, which routes it back to design-orch as a scoped refactor addition.
2. **Probe-request escalation.** If the planner is uncertain whether the missing refactor is real or an artifact of incomplete runtime data, it uses the probe-request channel (below) to ask impl-orch for more probes before deciding between option 1 and a normal plan.

What the planner must **not** do: add a new cross-cutting prep phase called "refactor X" that is not anchored to a `design/refactors.md` entry, and claim the plan is converged. That move launders a design problem into a plan problem and breaks the traceability chain from design intent to executed refactor. If the planner catches itself reaching for this move, that is the signal that a structural-blocking escalation is the correct next action.

The planner **may** identify foundational prep the design did not scaffold out — new files, new interfaces, new test harness plumbing — and add phases for it. That is not a refactor (not rearrangement of existing code) and does not require a design-orch round-trip. Foundational prep additions must still cite a spec leaf or architecture subtree that motivates them.

## Refactor agenda handling

`design/refactors.md` carries the refactor agenda the planner sequences. Each entry names a target, a reason, and (usually) a scope. The planner's required behavior:

- **Read every entry in `refactors.md`.**
- **Map each entry to a phase or to an explicit skip decision.** Every entry must end up in one of three states in the plan:
  - Landed as part of phase N (named).
  - Bundled with another entry into a single refactor-prep phase.
  - Skipped, with a one-sentence reason (e.g. "covered by Phase 2 incidentally," "design revision removed the need," "no longer applies after pre-planning runtime check").
- **Unaccounted entries are a planner bug.** A plan that ignores a `refactors.md` entry without a skip decision is incomplete and impl-orch should re-spawn the planner with the gap as feedback.

This is the structural-decision-traceability mechanism. Without it, design-orch produces a refactor agenda and the planner is trusted to use it; with it, every refactor has a visible chain from the design's claim to the plan's response.

## Parallelism justification template

Every ordering decision in `plan/overview.md` must carry a parallelism justification. The required template is:

```markdown
### Round 1: Refactor prep
Phases: P1 (auth module split), P2 (token store interface extraction)

**Parallelism justification:** Both phases are refactors named in `design/refactors.md` (R01 and R02). P1 and P2 touch disjoint modules (`auth/` and `tokens/` respectively) and share no test fixtures. Running them in parallel removes the cross-cutting refactor surface for Rounds 2+ in one round instead of two.

**Spec leaves satisfied:** none directly (refactors preserve behavior; no spec leaves change).

### Round 2: Parallel feature fanout
Phases: P3 (auth feature A), P4 (auth feature B), P5 (token feature C), P6 (token feature D)

**Parallelism justification:** P3-P4 work on the parser side of `auth/` (depends on P1's split). P5-P6 work on the token store side (depends on P2's interface extraction). Within each cluster, the features touch disjoint files within the post-refactor module shape. All four phases share the test runner but have non-overlapping test paths. The spec leaves claimed by each phase are disjoint — P3 claims `S03.1.e1, S03.1.e2`, P4 claims `S03.2.e1`, P5 claims `S05.1.e1, S05.1.e2`, P6 claims `S05.2.e1`.

**Spec leaves satisfied:** S03.1.e1, S03.1.e2, S03.2.e1, S05.1.e1, S05.1.e2, S05.2.e1.

### Round 3: Integration
Phases: P7 (auth+token integration smoke)

**Parallelism justification:** Sequenced after Round 2 because it depends on all four feature phases being committed. Cannot be parallelized with anything in Round 2. This is a sequential constraint; the parallelism gain came from Round 2's fanout.

**Spec leaves satisfied:** S07.1.e1 (integration invariant).
```

The pattern: name the round, name what it unlocks, name the constraint that prevents earlier execution, name the spec leaves each phase satisfies. Justifications that say "this depends on the previous phase" without naming what the dependency is or what it unlocks fail the frame.

## Parallelism Posture as a structural gate

`plan/overview.md` must include a top-level `Parallelism Posture` field with a required value and a cause classification:

```markdown
Parallelism Posture: parallel | limited | sequential
Cause: inherent constraint | structural coupling preserved by design | runtime constraint | feature work too small to fan out
```

- **parallel** — the plan has at least one round with two or more parallel-eligible phases, justified by disjoint architecture subtrees and disjoint spec-leaf coverage.
- **limited** — the plan has some parallelism but is dominated by sequential constraints. Cause must be named.
- **sequential** — the plan is entirely sequential or near-sequential. Cause must be named.

The cause field is the gate. When the cause is `structural coupling preserved by design`, the planner is signaling that the design's target state is structurally non-decomposable for parallelism, and impl-orch must treat this as a pre-execution structural escalation rather than a normal plan to execute. See [impl-orchestrator.md](impl-orchestrator.md) §"Pre-execution structural gate" for what impl-orch does with this signal. Briefly: impl-orch stops before execution and routes a structural escalation to dev-orch via the redesign-brief mechanism (see [redesign-brief.md](redesign-brief.md) §"Parallelism-blocking structural issues discovered post-design").

The other cause values (`inherent constraint`, `runtime constraint`, `feature work too small to fan out`) are informational, not blocking. A sequential plan caused by an inherent constraint is a real plan and impl-orch executes it. A sequential plan caused by structural coupling preserved by design is a design problem and impl-orch escalates it.

## Planning-cycle cap

Impl-orch is allowed to re-spawn the planner when the plan is missing required sections, claims spec leaves that do not exist, leaves `design/refactors.md` entries unmapped, or contradicts the pre-planning notes. To prevent pathological loops where the planner cannot converge on a plan consistent with its inputs, the planning cycle is capped at **three planner spawns per work item per impl-orch cycle**. After the third planner spawn fails to produce a converging plan, impl-orch must escalate to dev-orch with a `planning-blocked` signal rather than re-spawning a fourth time. See [impl-orchestrator.md](impl-orchestrator.md) §"Planning cycle cap" for the impl-orch side and `decisions.md` D12 for the rationale.

A "failed" planner spawn is one that produces a plan with: missing required sections, spec leaves unclaimed or double-claimed, `refactors.md` entries unmapped, contradiction with pre-planning notes, or hand-wavy parallelism justifications that do not cite real constraints. A spawn that produces a complete and consistent plan does not advance the cycle counter.

The cap is distinct from the redesign cycle cap (D7). They count separately. Exhausting the planner cap escalates to dev-orch with a different signal than the execution-time falsification escape hatch.

## Probe-request channel

The planner does not run probes itself. But the planner is allowed to identify gaps in the pre-planning notes and `feasibility.md` combined — runtime data the planner needs that neither design-orch nor impl-orch captured. When this happens, the planner has two options:

1. **Make a best-effort decomposition with the data on hand and flag the gaps explicitly** in `plan/overview.md` under a "Pre-planning gaps" section. Each gap names what data was missing and what assumption the planner made in its absence.
2. **Terminate the spawn with a "needs more probing" report** instead of a plan. The report names the specific runtime questions the planner could not answer. Impl-orch reads the report, runs the additional probes, updates the pre-planning notes, and re-spawns the planner with the expanded notes. This is a probe-request round; it counts toward the planning cycle cap (above) so it cannot loop indefinitely.

The choice between options is the planner's judgment. Small gaps with safe defaults take option 1; gaps that would force the planner to guess on a structural question take option 2. The planner should not guess silently — every assumption made because of a missing pre-planning observation must be visible somewhere in the plan or report.

The probe-request channel is distinct from the structural-blocking escalation. A gap the planner can probe its way out of is a probe request. A refactor the planner detects is missing from `design/refactors.md` and needs to land before parallelism is possible is a structural-blocking escalation — even if a probe would confirm the refactor is necessary, the decision to add a refactor is a design decision, not a planning decision.

## Why parallelism matters here specifically

The user's framing: parallel work is the throughput knob, and a tangled structure blocks parallelism no matter how careful the planning is. If the design has landed a coupled mess, the planner cannot decompose it into independent phases — every phase reads from and writes to the same surfaces, so parallel coders would race each other. The only outcome is sequential phases or merge hell.

This is why structure and modularity have been promoted to first-class design concerns (see [design-orchestrator.md](design-orchestrator.md) and `design/refactors.md`). A design that fixes the structure via its refactor agenda unlocks parallelism downstream; a design that preserves the coupling locks the planner into a sequential plan no matter how well it does its job.

The planner is the agent that consumes the structure design-orch lands. If the architecture tree plus `refactors.md` describe a structurally sound target, the planner produces a parallelism-rich plan. If the design preserves coupling, the planner's first move is to surface that via the Parallelism Posture gate — not produce a plan that papers over the coupling, and not invent the missing refactor itself. The `Cause: structural coupling preserved by design` value is the explicit mechanism for that escalation; without it, the planner's structural concern would dissipate into prose that downstream consumers might not act on.

## Inputs the planner consumes

The planner is spawned with these attached via `-f`:

- **design/spec/** — the spec tree root (`overview.md`) plus every spec doc. The planner reads the spec leaves (EARS statements) as the verification contract each phase must satisfy. Every phase in the plan names the spec-leaf IDs it claims.
- **design/architecture/** — the architecture tree root (`overview.md`) plus every subtree. The planner reads the architecture to identify disjoint subtrees that can be implemented in parallel and to map the target-state interfaces to phase scopes.
- **design/refactors.md** — the refactor agenda. Every entry must land in a phase or be explicitly skipped.
- **design/feasibility.md** — design-time feasibility answers and known unknowns. The planner reads this so it knows what runtime context design-orch already resolved and does not re-request probes that feasibility.md already answered.
- **decisions.md** — the design-time decision log, so the planner does not propose phasing that contradicts an already-rejected approach.
- **plan/pre-planning-notes.md** — impl-orch's runtime-informed additions to `feasibility.md`: additional probe results, spec-leaf coverage hypothesis, anything impl-orch observed beyond what `feasibility.md` already recorded. This is the file that turns the planner from a context-blind agent into a runtime-aware one.
- **plan/preservation-hint.md** *(only on redesign cycles)* — the preservation contract from the previous cycle. When present, the planner respects the preservation anchor and replans only from `replan-from-phase` onward.

The planner does not run probes itself. If a probe is needed, that is impl-orch's job in the pre-planning step, before the planner is spawned. The planner consumes results, not raw exploration capability — but it can request additional probes via the probe-request channel above.

### What pre-planning-notes contain — and what they don't

Pre-planning notes capture what impl-orch thought to probe on top of what `feasibility.md` already answered. They are a *projection* of runtime context, not equivalent to runtime context itself. Negative results, interaction effects, tacit codebase knowledge, and "shape and feel" observations may be absent. The planner should read the notes as "the runtime data impl-orch chose to write down" rather than "everything that is true at runtime." When the planner's decomposition requires runtime context neither `feasibility.md` nor the notes cover, the planner uses the probe-request channel rather than guessing.

## Outputs the planner produces

The planner writes these to `$MERIDIAN_WORK_DIR/`:

- **plan/overview.md** — the phases, their dependency relationships, the execution rounds (parallel-eligible groupings), the **Parallelism Posture** field with cause classification, an explicit parallelism justification per round, the spec-leaves-satisfied list per round, and the refactor-agenda handling table (every `design/refactors.md` entry mapped to a phase or skipped with reason).
- **plan/phase-N-<slug>.md** — per-phase blueprints with scope, files to modify, dependencies, interface contracts, constraints, verification criteria, and the **spec-leaf IDs** the phase claims (with EARS statements quoted or cited). Verification notes instruct testers to parse each claimed EARS leaf into trigger/precondition/response and smoke-test it.
- **plan/leaf-ownership.md** — every spec leaf in `design/spec/` claimed by exactly one phase. Unclaimed or double-claimed leaves are a planner bug.
- **plan/status.md** — phases seeded with appropriate values. On a first-cycle plan, all phases are `not-started`. On a redesign-cycle plan, phases honor the preservation hint's `preserved`, `partially-invalidated`, `replanned`, `new`, and `not-started` values (see [preservation-hint.md](preservation-hint.md) §"Status field representation").

The plan must include a Mermaid diagram in `plan/overview.md` showing phase dependencies and execution rounds, so a human or downstream agent can see the parallel structure at a glance. The diagram and the textual round descriptions must agree — drift is a plan bug.

## Skills loaded

The planner profile keeps its existing skills with the parallelism-first frame and the spec-leaf verification framing inlined into the planner profile body itself, not deferred to a skill update:

- **`planning`** — decomposition craft. Stays loaded. The skill body needs a downstream update to make parallelism-first the central frame and to replace scenario-ownership references with leaf-ownership (see "Required follow-up: planning skill update" below). Until that update lands, the planner profile body must carry the parallelism-first frame and the spec-leaf verification framing inline.
- **`agent-staffing`** — team composition. Stays loaded.
- **`architecture`** — structural reasoning. Stays loaded.
- **`mermaid`** — dependency diagrams. Stays loaded.
- **`decision-log`** — capturing planner-time decisions. Stays loaded.
- **`dev-artifacts`** — where artifacts go. Stays loaded.
- **`meridian-cli`** — the CLI surface. Stays loaded.
- **`feasibility-questions`** *(new addition)* — the four shared questions. Loaded so the planner reads design-orch's `feasibility.md` and impl-orch's pre-planning answers in the same frame design-orch and impl-orch used to write them.
- **`dev-principles`** *(new addition)* — engineering hygiene. Loaded so the planner applies refactor-early discipline and edge-case scoping when sequencing phases.

The planner does not load `meridian-spawn` because it does not spawn other agents. It produces artifacts and exits.

## What is unchanged from the current planner profile

- It is a single-shot agent. It runs once per planning pass, produces artifacts, and terminates. It does not loop or supervise execution.
- It writes to disk. The plan is materialized, not held in conversation.
- It uses `agent-staffing` to compose per-phase teams and final review fanout — staffing is part of the plan, not something impl-orch invents on the fly.
- It includes verification IDs in every blueprint. Under v3, those IDs are spec-leaf IDs rather than scenario IDs. Phases with no claimed spec leaves are either incomplete or unnecessary; the planner surfaces which.
- It writes a complete plan or a plan that explicitly states what is missing. It does not write a partial plan and call it done.

## What is changed from the v2 planner

- **Inputs reshape.** v2 consumed `design/` as a flat set plus `scenarios/` plus the Terrain section inside `design/overview.md`. v3 consumes the spec tree, the architecture tree, `design/refactors.md`, and `design/feasibility.md` — four distinct artifacts with distinct roles.
- **Verification contract reshape.** v2 phases claimed scenario IDs from `scenarios/`. v3 phases claim spec-leaf IDs from `design/spec/`. The ownership file is `plan/leaf-ownership.md` instead of `plan/scenario-ownership.md`, and `scenarios/` is retired as a convention (see [overview.md](overview.md) §"Scenarios are subsumed by spec leaves").
- **Refactor input shape reshape.** v2 read the Terrain section's structural delta with `structural-prep-candidate: yes|no` tags. v3 reads `design/refactors.md` as a named first-class artifact. Every `refactors.md` entry is required to land in a phase or be explicitly skipped — the same traceability mechanism, pointing at a cleaner input.
- **No refactor invention.** v2 allowed the planner to add "planner-identified structural prep, not in design's structural delta." v3 removes that path — if the planner detects a missing refactor that blocks parallelism, it escalates via the Parallelism Posture gate instead of silently adding a phase.
- **Feasibility input added.** v2 had pre-planning-notes as the planner's only runtime-aware input. v3 adds `design/feasibility.md` as the design-time feasibility record, with pre-planning-notes as the runtime delta impl-orch layers on top. The planner does not re-request probes `feasibility.md` already answered.

## What is deleted

- The `scenarios/` convention at the planner level — scenario files, SNNN IDs, `plan/scenario-ownership.md`, scenario-appending responsibility during planning.
- The `structural-prep-candidate: yes|no` tag reading — replaced by direct reads of `design/refactors.md`.
- The "planner-added structural prep, not in design's structural delta" loophole.

## What is added

- Spec-leaf claim semantics — phases name spec-leaf IDs, the planner writes `plan/leaf-ownership.md`, and tester guidance parses EARS into trigger/precondition/response triples.
- `design/feasibility.md` as a separate input from pre-planning-notes.
- `dev-principles` skill load for refactor-early discipline and edge-case scoping.
- Explicit prohibition on inventing refactors — missing refactors escalate via the Parallelism Posture gate.

## Required follow-up: planning skill update

The current `planning` skill body talks about phase decomposition, blueprint shape, dependency mapping, scenario ownership, and staffing. It mentions parallelism but does not lead with it, and it still uses scenario-ownership vocabulary. After this restructure lands, the skill needs a revision pass to match v3:

- **Lead with the parallelism question.** The first question the skill asks is not "what are the phases?" but "what would have to be true for these phases to run in parallel, and what is preventing that?"
- **Replace scenario-ownership language with spec-leaf-ownership language.** Phases claim leaf IDs; the ownership file is `plan/leaf-ownership.md`.
- **Reference `design/refactors.md` as the canonical refactor input.** The skill should describe the planner's responsibility to map every `refactors.md` entry to a phase or skip decision, with the refactor-handling table in `plan/overview.md` as the canonical record.
- **Reference `design/feasibility.md` as the canonical feasibility input.** The skill should describe the split between design-time feasibility answers (`feasibility.md`) and planning-time runtime deltas (`pre-planning-notes.md`).
- **Add a refactor-prep section.** The skill should explicitly name the pattern of "land cross-cutting refactors first to unlock parallel feature work later" as a default decomposition move, with examples of when it applies and when it does not.
- **Promote runtime-constraint detection.** The current skill mentions integration boundaries; it should also call out shared test harnesses, global registries, filesystem fixtures, env-var collisions, and other things that look parallel at the interface layer but are not at the runtime layer.
- **Reframe execution rounds.** A parallelism-first skill describes rounds as the output of a decomposition that was actively shaped to maximize parallel work.
- **Tighten the relationship to feasibility-questions.** The four shared questions already cover parallelism as one axis. The skill should reference them explicitly so a planner using `planning` knows where the parallelism question fits relative to feasibility, decomposition, and foundational prep.
- **Name the no-invented-refactors rule.** Missing refactors escalate via the Parallelism Posture gate; the planner does not add refactor phases that are not anchored to `refactors.md` entries.

**This follow-up is a hard prerequisite of any plan written under the v3 topology.** The planner profile body inlines the central-frame contract so a planner spawned before the skill update lands still produces a v3-shaped plan. But the skill update is required before the next major work item begins, so the skill body and the profile body do not drift indefinitely. Dev-orch tracks this as an open work item and prioritizes it before the next design pass that depends on parallelism-first decomposition.

If the skill update has not landed and a planner is spawned anyway, the planner profile body's inlined frame is the source of truth and the skill is treated as supplementary. This avoids the failure mode where a v3 planner runs against a v0 skill and produces a v0-shaped plan because the central frame lived only in design prose.

## Open questions

None at this draft. Anything unresolved at review time gets a decision in [../decisions.md](../decisions.md).
