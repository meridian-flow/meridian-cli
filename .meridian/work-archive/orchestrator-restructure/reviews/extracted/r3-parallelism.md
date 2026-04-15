Now I have enough context. Let me also check the existing planner profile to see what the v2 design is updating:
I have enough context. Now producing the review.

---

# Review: orchestrator-restructure v2 — parallelism-first decomposition frame

## Overall assessment

The v2 reversal is directionally defensible: the v1 draft collapsed a real cognitive separation that matters, and v2's core insight — that impl-orch can do runtime probing and hand the results to a separate planner — is the right decoupling. The parallelism-first reframing of @planner captures a real user pain (sequential plans starving throughput) and ties the planner's purpose to something concrete the user actually cares about.

**But the v2 design package has a systematic weakness: the parallelism-first frame is asserted in prose and never wired into the machinery that would make it stick.** The `/planning` skill is not updated, the planner profile body is not updated, the blueprint format has no required parallelism justification section, the plan-overview format has no template for parallelism justification per ordering decision, dev-orch's plan review checkpoint has no parallelism criteria, and the re-spawn triggers don't include "parallelism is insufficient." Every piece of downstream infrastructure a planner actually executes against is unchanged from v0. The claim lives in `planner.md` §"Parallelism-first decomposition is the central frame" and `decisions.md` §D10 — and nowhere else that a spawned agent will read.

The result is a design that *says* "central frame" and *delivers* "one sentence in a body that doesn't change anything else." This is the #9 anti-pattern the review prompt called out, and v2 has it.

A second systemic weakness: the v2 reversal recovers the cognitive-mode separation v1 collapsed, but the *specific* v1 insight — that handoff boundaries leak context without adding value — is not actually answered by v2's "legibility-forcing" counter-argument. Legibility can be forced without a spawn boundary. v2's justification is partially post-hoc.

Neither of these is fatal. Both are fixable in this design pass, and should be.

---

## CRITICAL — none

No finding rises to critical. The design is coherent enough to be executable; the findings below are about whether it delivers on what it claims, not whether it works at all.

---

## HIGH

### H1 — The parallelism-first frame has no enforcement infrastructure

**Where:** `planner.md` §"Parallelism-first decomposition is the central frame"; `overview.md` §"The shape"; `decisions.md` §D10. Cross-reference against the `planning` skill body (`meridian-dev-workflow/skills/planning/SKILL.md`) and the current planner profile (`meridian-dev-workflow/agents/planner.md`), which are **not touched by this design package**.

**What:** The design asserts that decomposition decisions should be "evaluated through the parallelism lens" and that "every part of the plan should be justified by what it unlocks downstream." But nothing in the supporting infrastructure requires or even verifies this:

- The `/planning` skill's body still leads with "break design into phases" and mentions parallelism as a secondary concern. It has no "structural refactors land first" pattern, no runtime-constraint-for-parallelism checklist, no required "parallelism justification" blueprint section.
- The current planner profile body (`planner.md` in the source repo) says "Think about what can run in parallel vs what must be sequential" as one line among many. The v2 design package does not specify a replacement body — it describes the planner's role in prose but does not mandate what the profile body must say.
- Blueprint format is unchanged. There is no required "Parallelism justification" section in the blueprint. The design says plan/overview.md should include "an explicit parallelism justification per ordering decision," but gives no template and no example of what that looks like.
- Dev-orch's plan review checkpoint (see `dev-orchestrator.md` §"The delegation chain") does not specify parallelism quality as a review criterion. Dev-orch is told to review "against the design and against the user's stated intent" — parallelism quality isn't in scope.
- The re-spawn triggers in `impl-orchestrator.md` §"Spawning @planner" include "missing required sections," "missing scenario IDs," and "contradicts the pre-planning notes." They do **not** include "parallelism is not justified per ordering decision" or "structural prep not separated from feature work."

**Why it matters:** A planner spawned under the v2 topology loads the old `/planning` skill, reads a profile body that barely mentions parallelism, writes a plan in the old format, and gets reviewed by a dev-orch with no parallelism criteria. The planner will produce whatever plan it would have produced under v0, and the "parallelism-first" frame will exist only in the prose of an architecture doc that the planner never reads. This is the exact anti-pattern the review prompt names as #9.

The design effectively delegates the entire enforcement burden to the single sentence in `planner.md` that calls parallelism "the lens through which decomposition decisions get evaluated." Lenses don't enforce anything.

**Suggested fix:**
1. **Mandate the `/planning` skill update as a prerequisite of this design pass**, not a follow-up. Or, inline the central-frame contract directly into the planner profile body (`meridian-dev-workflow/agents/planner.md`) as part of this package. The planner body should lead with "Your job is to decompose the work so as much as possible can run in parallel" as the first sentence, and the skill body should match.
2. **Require a "Parallelism justification" section in `plan/overview.md`**, with a concrete template: for each execution round, name what enables round N+1 to fan out; for each sequencing constraint, name the specific runtime surface that forces the sequencing; for each structural prep phase, name which downstream parallelism it unlocks.
3. **Add parallelism quality to dev-orch's plan review criteria in `dev-orchestrator.md`.** Specify that dev-orch checks whether the plan has a structural-prep-first shape, whether the parallelism justifications cite real constraints, and whether the dependency graph shows meaningful fanout vs. sequential chains.
4. **Add a re-spawn trigger in `impl-orchestrator.md`**: "The plan's parallelism justifications are hand-wavy or missing, or the plan is sequential when the pre-planning notes indicate disjoint modules are available."

Without at least items 1 and 2, the parallelism-first claim is rhetoric.

---

### H2 — Planner re-spawn loop is unbounded

**Where:** `impl-orchestrator.md` §"Spawning @planner" (para beginning "When the planner spawn returns..."); `dev-orchestrator.md` §"The delegation chain" (para beginning "If dev-orch pushes back..."); `decisions.md` §D7.

**What:** There are two re-spawn paths, and neither has a cycle cap:

- **Internal path:** impl-orch re-spawns the planner when "the plan is missing required sections, references missing scenario IDs, or contradicts the pre-planning notes." Described as "a normal correction, not an escape-hatch trigger."
- **External path:** dev-orch pushes back, impl-orch re-spawns the planner with the feedback. Explicitly marked as not advancing the redesign loop-guard counter.

Both docs are clear that re-spawns are cheap and do not count as redesign cycles. Neither doc says what happens after N re-spawns.

The redesign loop guard in D7 protects the design-orch boundary (two autonomous design cycles before escalation). The planner re-spawn loop has no equivalent. A pathological case:

1. Planner writes plan v1. Impl-orch finds that Phase 3 contradicts runtime constraint X. Re-spawns with feedback.
2. Planner writes plan v2 that fixes Phase 3 but now Phase 5 contradicts runtime constraint Y that wasn't a concern before because the old Phase 3 had different scope. Re-spawns.
3. Plan v3 fixes Phase 5 but reintroduces the v1 problem on Phase 3 because the planner can't hold both constraints simultaneously in its context.
4. ... loops indefinitely.

This isn't hypothetical paranoia: it's exactly the scenario that arises when the design is over-ambitious relative to runtime constraints, or when the pre-planning notes are internally inconsistent, or when the planner's model family has a specific blind spot. The design assumes convergence but provides no upper bound.

**Why it matters:** Pathological planner loops consume spawn budget, burn cache, and produce plans that neither impl-orch nor dev-orch can execute. The system has no mechanism to detect that it's stuck at the planning layer — the escape hatch is described as mid-execution only, so impl-orch has no protocol for bailing out during planning.

**Suggested fix:**
1. **Add a planning-cycle cap in `impl-orchestrator.md`.** After K (suggest K=2 or 3) failed planner spawns on the same work item, impl-orch must either (a) emit a redesign brief citing "planner cannot converge on a plan consistent with the pre-planning notes" as the falsification case and return to dev-orch, or (b) escalate to dev-orch with a different signal ("planning-blocked") that routes differently from the falsification path.
2. **Define what counts as a "failed spawn"** for the cycle counter: a plan that is internally incomplete, a plan that contradicts pre-planning notes, or a plan that dev-orch rejects with concrete revisions. A spawn that produces a complete and consistent plan does not advance the counter.
3. **Specify in `decisions.md`** (new entry, e.g. D12) that the planner re-spawn cap is distinct from the redesign cycle cap and that exhausting the planner cap is itself a signal that escalates to dev-orch.

Without this, the v2 design has unbounded loops at the planning layer, right next to a loop-bounded redesign layer. The asymmetry is an oversight.

---

### H3 — The linkage between Terrain's structural delta and parallelism-first decomposition is implicit, not wired

**Where:** `design-orchestrator.md` §"What the Terrain section contains" (the "structural delta" bullet); `planner.md` §"Inputs the planner consumes" and §"Parallelism-first decomposition is the central frame"; `overview.md` §"Why structure and modularity are first-class design concerns."

**What:** The design makes two claims that should be welded together but aren't:

- Design-orch produces a "structural delta" describing cuts and consolidations: "split module X into A and B," "extract interface Y from class Z," "collapse three near-duplicate config loaders."
- Planner identifies "structural refactors that touch many files" and lands them first as cross-cutting prep.

**These should be the same list.** The design-orch's structural delta IS the planner's structural-prep candidate set. But no part of the design explicitly connects them:

- `design-orchestrator.md` describes the delta but doesn't mark items as "structural prep that should land before feature work."
- `planner.md` §"Inputs the planner consumes" lists `design/` as an input but does not say "read the Terrain section's structural delta and use it as your structural-prep candidate list."
- `planner.md` §"Parallelism-first decomposition is the central frame" says structural refactors land first but gives no heuristic for identifying them. The phrase "touches many files" is the only filter, and it's fuzzy — does 3 files qualify? 5? What about touching 2 high-churn shared modules?

This means in practice, a planner reading the design could easily:
- Miss a structural delta item that the design-orch intended as structural prep, because nothing marks it that way.
- Promote a feature-scoped change to structural prep because it touches many files, even though the structural delta doesn't recommend it.
- Invent its own structural prep items that contradict the structural delta.

**Why it matters:** The entire parallelism-first strategy depends on identifying which changes are cross-cutting. If design-orch produces the delta but the planner has no mandate to treat it as the source of truth, the "structural refactors first" pattern is planner-judgment rather than design-orch-structured-handoff. Under the v1 critique (handoff boundaries leak context), this is exactly where leakage happens: design-orch has the information, but the channel to the planner is unstructured prose.

**Suggested fix:**
1. **Require design-orch to mark structural delta items with an explicit "structural prep" tag** in the Terrain section. The Terrain section should carry a bullet list of "candidate structural prep" items that the planner can consume as a starting set.
2. **Require the planner to explicitly map each "candidate structural prep" item to a phase or a decision to skip.** The plan overview should have a section that walks every item: for each, either "landed as phase N" or "skipped because [reason]." Unaccounted items are a planner bug.
3. **Define "cross-cutting" concretely.** Use a threshold the planner can apply: e.g., "touches shared interfaces consumed by ≥2 feature phases" or "touches modules in the same file that multiple planned phases need to modify." Rough heuristics are better than vague judgment.

This is the structural-decision-traceability move the design makes for scenarios-to-phases (every scenario owned by a phase) but doesn't make for structural-delta-to-structural-prep. It should.

---

### H4 — Pre-planning has a chicken-and-egg problem the design doesn't resolve

**Where:** `impl-orchestrator.md` §"Pre-planning as the first action"; `planner.md` §"Inputs the planner consumes"; `decisions.md` §D3.

**What:** Impl-orch's pre-planning step is supposed to produce "Constraints discovered at runtime that bound the plan's phase ordering — shared test fixtures, global registries, env-var collisions, fixture races." The planner then consumes these constraints to shape the decomposition.

But **impl-orch needs to know what phases exist to know which constraints matter.** Shared test fixtures only matter if two phases would run concurrently and touch the same fixture. Env-var collisions only matter if two phases would race on configuration. Global registries only matter if phases would stomp on each other's registrations.

Without a rough decomposition in hand, impl-orch has two options:
- **(a)** Enumerate *every* shared test fixture, *every* env var, *every* global registry in the codebase. This is expensive, duplicates design-orch's terrain work, and floods the planner with signal-to-noise issues.
- **(b)** Guess at a rough decomposition in impl-orch's own context, then enumerate the constraints relevant to that guess. This is **exactly the in-context planning move that v1 proposed and v2 rejected** — impl-orch would be doing planning-lite before spawning the planner, reproducing the cognitive-mode collapse the v2 design set out to avoid.

The design doesn't say which path impl-orch takes. The pre-planning notes format lists the constraint category but doesn't explain how impl-orch discovers what to put in it. D3 says "answer the four feasibility questions against runtime data" — but "what can run in parallel?" can only be answered against a proposed decomposition, and the decomposition doesn't exist yet.

**Why it matters:** If impl-orch takes path (a), pre-planning is slow and the planner gets noise. If impl-orch takes path (b), v2 has quietly reintroduced the v1 mashing that was supposedly rejected — impl-orch is holding a tentative decomposition in its head while probing, which is the exact "decomposition and execution mashed into one context" failure mode D1's reversal claims to prevent.

The design is silent on this, and silence means the choice devolves to whatever the impl-orch agent does on a given run, which is the opposite of the legibility-forcing value v2 claims.

**Suggested fix:**
1. **Acknowledge the chicken-and-egg in `impl-orchestrator.md`** and describe the intended resolution. Options:
   - Impl-orch does a shallow decomposition sketch in pre-planning *explicitly*, passes it to the planner as "impl-orch's working hypothesis about how this might decompose," and the planner either refines or replaces it. This is honest about path (b) and makes the working hypothesis an inspectable input.
   - Or: impl-orch enumerates constraints at the module level without reference to phases ("these 4 test fixtures are shared across modules X, Y, Z"), and the planner maps constraints to phases when it decomposes. This is path (a) with scoping.
2. **Pick one, name it in D3, and describe the format** the pre-planning notes should take accordingly.
3. **If the design picks path (b)**, update `planner.md`'s reasoning about cognitive-mode separation — impl-orch IS doing some decomposition work, and the split is weaker than v2 claims. That's fine but should be honest about it.

This gap is what makes the whole "runtime context as -f input" mechanism work or fall apart. Currently it's unspecified.

---

## MEDIUM

### M1 — "Runtime context as -f input" is equivalent to "having runtime context" — the claim is overstated

**Where:** `overview.md` §"Why @planner stays but rehomes under impl-orch" (bullet: "The runtime-context objection has a better answer than collapsing the agent"); `planner.md` §"Why a separate agent and not in-context impl-orch work"; `decisions.md` §D1.

**What:** The v2 pitch rests on: "the planner then has the runtime context the v1 planner lacked." But a markdown notes file captures a **filtered projection** of runtime context, shaped by whatever frame impl-orch used while probing:

- Discrete facts (module X imports Y) capture cleanly.
- Probe outputs (pastable command results) capture cleanly.
- Enumerated constraints capture cleanly, assuming H4 is resolved.

But some kinds of runtime context don't capture cleanly:
- **Negative results.** "I looked for a global registry and didn't find one" — hard to exhaustively enumerate in a notes file. A planner reading the notes may assume "the constraint isn't listed, therefore it doesn't exist" when the real answer is "impl-orch didn't think to check."
- **Shape and feel.** "The test suite is brittle in a particular way that affects how I'd decompose." Can be written down but usually isn't because it requires someone asking "was it brittle?"
- **Interaction effects.** Runtime constraint A matters only if runtime constraint B also holds. Enumerating them separately loses the interaction.
- **Tacit guidance.** "I tried modifying file X last week and it was painful" — institutional knowledge that shaped design-orch's Terrain section may be absent from impl-orch's probes.

**Why it matters:** The legibility argument is weaker than v2 presents it. The planner has *some* runtime context, not equivalent context. A planner producing a plan based on incomplete runtime projection will make decomposition mistakes that the v1-in-context approach might have caught.

This doesn't invalidate v2. But the design should acknowledge the asymmetry and suggest a mitigation, rather than overclaiming equivalence.

**Suggested fix:**
1. **In `planner.md` §"Inputs the planner consumes"**, add a note: "Pre-planning notes capture what impl-orch thought to probe. If the planner's decomposition requires runtime context impl-orch did not capture, the planner should flag the gap in its plan overview rather than guess."
2. **Add a re-spawn path from planner back to impl-orch for targeted probes.** Currently the planner cannot request anything — it consumes notes and produces plan. Allow the planner to terminate with a "need more probing" report, which impl-orch reads and re-probes, then re-spawns the planner with expanded notes. This is a new spawn round but preserves legibility.
3. **Or, more minimally: at least document the "no probe request" constraint** so readers know the planner is consuming a fixed projection.

The design should not assert equivalence it doesn't have.

---

### M2 — "Decomposition and execution are different cognitive modes" is an anthropomorphism for LLMs

**Where:** `planner.md` §"Why a separate agent and not in-context impl-orch work"; `planner.md` §"Why the planner stays a real spawn even though impl-orch already has runtime context"; `decisions.md` §D1 "Reasoning" paragraph.

**What:** The central v2 argument for keeping the planner is that decomposition and execution are "different cognitive modes" and "holding both in one context window blurs the lens." This framing is borrowed from human cognition literature where task-switching has real costs.

But LLMs don't have the same mode-switching problem. An LLM given a well-structured prompt can decompose in the same context as it executes, *provided the context isn't polluted by unrelated noise*. The real cost in v1 wasn't "mode blur" — it was that impl-orch's execution context would accumulate phase-level state (coder outputs, test results, fix loops) that would interfere with late-stage re-planning.

That's a real cost. But the v2 design is using the *wrong* argument to justify the split. The right argument is:
- Fresh context isolates planning from accumulated execution state (true for LLMs)
- Different skill loadouts focus the planner on decomposition craft (true, but not unique to v2 — could be swapped dynamically)
- Different model selection allows optimizing planning for the planning task (true, but also swappable)
- A materialized boundary is inspectable and re-runnable after compaction (true, and unique to v2 — this is the real killer feature)

The "cognitive modes" framing hides the actual killer feature (inspectable, re-runnable, compaction-tolerant boundary) behind an anthropomorphic metaphor.

**Why it matters:** A reader who is skeptical of anthropomorphism (correctly) will read the v2 design and think "this argument is weak, the v1 approach was right." The design would be more robust if it led with the real LLM-specific reasons. It would also be more honest about what the v2 boundary actually buys.

**Suggested fix:** Rewrite the "why a separate agent" reasoning in `planner.md` and `overview.md` and `decisions.md` D1 to lead with:
1. Fresh context isolates decomposition from accumulated execution state (not "cognitive mode")
2. Materialized pre-planning notes + materialized plan = an inspectable, re-runnable handoff that survives compaction
3. Separate skill loadouts enable planning-specific craft
4. Separate model selection enables routing to a planning-optimized model

Drop the "cognitive modes" language. It's anthropomorphic, unsupported by evidence in LLM behavior, and distracts from the stronger actual arguments.

---

### M3 — Dev-orch's plan review checkpoint has no criteria

**Where:** `dev-orchestrator.md` §"The delegation chain" (para beginning "When impl-orch reports back..."); `impl-orchestrator.md` §"Review checkpoint after the plan materializes."

**What:** Dev-orch is supposed to review the plan and either approve or push back. The design says "dev-orch reviews the plan against the design and against the user's stated intent" — but does not specify *what* dev-orch checks.

If parallelism-first is the central frame (D10) and if the whole point of the pre-planning step is to make runtime constraints visible before execution commits, then dev-orch's review should check:
- Does the plan have a structural-prep-first shape where the delta demands it?
- Does every ordering decision have a parallelism justification?
- Do the parallelism justifications cite concrete runtime constraints from pre-planning notes?
- Are all scenarios claimed?
- Does the plan contradict the pre-planning notes anywhere?
- Is the dependency graph mermaid diagram showing meaningful fanout, or is it sequential?

None of these are in the design. Dev-orch's criteria are left to "dev-orch's judgment," which means in practice dev-orch will rubber-stamp anything that looks complete.

**Why it matters:** If the planner produces a bad plan under the new topology, dev-orch is the last line of defense before execution. A rubber-stamp checkpoint buys no value over "impl-orch executes directly after planner terminates." The whole review checkpoint has to actually *check* something for the two-phase plan-then-approve flow to be worth its cost.

**Suggested fix:** Add a "Plan review criteria" subsection in `dev-orchestrator.md` that enumerates the specific checks dev-orch performs. Tie the checks to the parallelism-first frame (H1) and the re-spawn triggers (H2). Dev-orch can still exercise judgment about *how much* review the plan deserves (trivial vs. substantive), but the criteria for what "review" means should be specified.

---

### M4 — Terminology collision between "structural refactors" and "foundational work"

**Where:** `planner.md` §"Parallelism-first decomposition is the central frame" ("Structural refactors land first"); `feasibility-questions.md` §"Does something need foundational work first?"

**What:** The design uses two different phrases for similar-but-distinct concepts:

- **Structural refactors** (planner.md): "cross-cutting changes that would create merge conflicts if they ran late" — examples given are "interface renames, module reshuffles, shared-helper extraction."
- **Foundational work** (feasibility-questions.md): "anything that exists only to unblock later work and has no standalone value" — examples given are "type definitions, abstract base classes, shared helpers, interface contracts."

These overlap (shared helpers, interfaces) but are not the same category. Structural refactors *rearrange* existing structure to make future parallel work possible. Foundational work *creates* new scaffolding that later phases depend on. A planner applying both frames to the same design would find them colliding — is extracting a helper a structural refactor or foundational work? Both? Neither?

The feasibility-questions skill is loaded by the planner, so the planner will read both framings and either:
- Treat them as synonyms (losing the distinction design-orch cared about)
- Treat them as separate categories (wasting effort deciding which bucket something goes in)
- Use one and ignore the other (undermining one of the two framings)

**Why it matters:** This is a small cognitive burden on the planner that accumulates across every decomposition decision. It's also a sign that the design evolved in two separate docs without a reconciliation pass. Small now; compounds as the frame gets applied to real designs.

**Suggested fix:** Reconcile the terminology. Recommended: keep "structural refactors" as the rearrangement category (planner.md's usage) and "foundational scaffolding" as the new-scaffolding category (feasibility-questions.md's usage), and explicitly name both in both docs with cross-references. Alternatively, fold them into a single "structural prep" umbrella with two sub-categories.

---

### M5 — No mechanism for impl-orch to bail out during planning

**Where:** `impl-orchestrator.md` §"The escape hatch" (scope-bounded to execution); `decisions.md` §D5.

**What:** The escape hatch is described as mid-execution: impl-orch bails when "runtime evidence falsifies a structural assumption the design rests on." The concrete examples all assume code has been written and tested (smoke tests, fix attempts, contract changes).

But the same epistemic failure can occur during planning, before any code is written:
- Pre-planning reveals that the design's assumption X is runtime-false. The planner cannot produce a valid plan because the design is unplannable.
- Planner re-spawns exhaust the cycle cap (H2) with no convergent plan.
- Impl-orch detects the plan cannot be made consistent with pre-planning notes.

In all three cases, the right move is the same as the execution-time escape hatch: emit a redesign brief, return to dev-orch, trigger the autonomous redesign loop. But the design specifies the escape hatch as execution-time only.

**Why it matters:** An edge case the design doesn't handle: planning-time falsification. Without a protocol for it, impl-orch has two options: keep re-spawning the planner indefinitely (H2), or silently proceed with a bad plan because "the escape hatch isn't for this." Both are wrong.

**Suggested fix:**
1. **Extend `impl-orchestrator.md` §"The escape hatch"** to explicitly include planning-time falsification as a trigger. Specify the evidence shape: pre-planning notes contradict a design assumption, or the planner cannot converge after N attempts.
2. **Add a brief example** to `redesign-brief.md` showing a planning-time bail-out (status section would show "no phases committed," evidence section would show the pre-planning observation that falsified the design).
3. **Update `decisions.md` §D5** to explicitly include this case.

---

## LOW

### L1 — "Parallelism justification" is mentioned but not templated

**Where:** `planner.md` §"Parallelism-first decomposition is the central frame" ("Phase ordering is justified by parallelism, not just by logical dependency"); §"Outputs the planner produces" ("explicit parallelism justification per ordering decision").

**What:** The design requires parallelism justification per ordering decision but gives no example or template. A planner writing this will produce whatever feels justified without a concrete shape to aim for. Justifications will range from "Phase 3 runs first because it unlocks parallel work in Phase 4 and 5" (good) to "Phase 3 is first because the dependency graph says so" (bad).

**Suggested fix:** Give one concrete template in `planner.md` showing what a parallelism justification looks like for structural prep, for sequencing constraints, and for parallel-eligible groups. Three examples is enough to anchor the pattern. See H1 fix 2.

---

### L2 — The "parallelism-failure" trigger is not in the redesign brief format

**Where:** `redesign-brief.md` §"Cycle heading" and example shape.

**What:** The redesign brief format has six sections: status, evidence, falsification case, design change scope, preservation, constraints that still hold. None of these natively capture "the plan could not be decomposed for parallelism because the design is structurally tangled" — which is the exact failure mode D11 is trying to prevent by requiring structural review at design time.

If the structural review catches it at design time, great. If it slips through and only surfaces during pre-planning or early execution, the brief needs a way to express it.

**Suggested fix:** Add a seventh optional section to the brief format: "Parallelism-blocking structural issues discovered post-design" — used when the failure is not a specific design assumption being falsified but a whole-design structural problem. Points design-orch at the structural delta rather than at a specific assumption.

---

### L3 — Planner cannot request probes mid-planning

**Where:** `planner.md` §"Inputs the planner consumes" ("The planner does not run probes itself").

**What:** The planner consumes pre-planning notes but has no back-channel to impl-orch. If the planner identifies a gap — "I need to know if module X and module Y share a fixture" — it cannot ask. It must either guess, or flag the gap in the plan and let impl-orch re-probe on a re-spawn.

The re-spawn path exists (H2's external correction loop) but isn't explicitly documented as a probe request channel. This works, but the framing is "planner has everything it needs" rather than "planner can request more."

**Suggested fix:** In `planner.md`, note that if the planner identifies missing runtime data, it should flag the gap as an output (specific questions impl-orch should answer on re-spawn) rather than guessing. This formalizes the probe-request channel.

---

## On the v1 → v2 reversal: what v2 lost

The review prompt asks me to take a position on whether the legibility-forcing argument is compelling or post-hoc justification. **Mostly post-hoc, partially real.** Breakdown:

**What v1 had that v2 doesn't:**
- **No unbounded re-spawn loop.** v1's in-context planning couldn't ping-pong between impl-orch and a separate planner because the planning was in the same agent. v2 has the pathological planner loop (H2).
- **No chicken-and-egg problem.** v1's impl-orch could interleave probing and sketching a decomposition naturally, discovering which constraints mattered as it went. v2's pre-planning step has to enumerate constraints before knowing what decomposition they serve (H4).
- **No terminology collision.** v1 had one agent doing both framings so reconciliation was automatic. v2 has the planner reading `feasibility-questions` and `planning` and the planner.md body, potentially with three different framings for structural prep (M4).
- **No "equivalent runtime context" overclaim.** v1 genuinely had runtime context because impl-orch WAS doing the probing. v2 has a projection of runtime context that the design treats as equivalent when it isn't (M1).

**What v2 has that v1 doesn't:**
- **Fresh context isolation from execution state.** This is real. Once impl-orch starts executing, its context fills with fix-loop noise. A re-plan late in execution under v1 would have had to happen in that noise. Under v2, re-planning means a fresh planner spawn with fresh context. This is the strongest v2 argument and the design underweights it.
- **Materialized, compaction-tolerant plan artifacts as a natural consequence.** v1 could have materialized the plan too, but the pressure to do so was weaker. v2's planner spawn requires it.
- **Model routing flexibility.** Planner can run on a planning-optimized model (gpt-5.4 in the current profile) without impl-orch committing to that model for execution. v1 forced one model for both.

**My take:** The reversal is directionally right. The cognitive-mode argument is weak and should be dropped (M2). The legibility argument is partially post-hoc but has a real core — the stronger version is "fresh context isolates planning from accumulated execution state" (M2's preferred framing). The decisive v2 advantage is actually none of the arguments the design currently makes; it's that re-planning mid-execution under v1 would have been a nightmare in a polluted context window. If the design said that plainly, the reversal would be airtight.

**What v2 took from v1 and should not have:** nothing critical — but the design should have taken v1's honest acknowledgment that handoff boundaries leak context without adding value. v2 papers this over with "legibility-forcing" when the honest answer is "yes, there's some leakage, and we accept it in exchange for fresh context and model flexibility." That honesty would also make the design more robust to H1 and H3, which are both leakage instances that the current framing treats as mere implementation details.

---

## Follow-up skill update: well-scoped?

**No, it's under-scoped.** The design names the `/planning` skill update as a follow-up but does not:
- Mandate it lands before the new topology is used for real work
- Specify the scope of changes required (see H1 items 1 and 2 for what the skill needs)
- Address the risk that a v2 planner running against the v0 skill produces v0-shaped plans

The follow-up should be promoted to a **prerequisite** of this design pass, or the central-frame content should be inlined into the planner profile body so it doesn't depend on a future skill revision.

If the follow-up stays a follow-up, the design package should add a gate: "No plan written under the v2 topology ships until the `/planning` skill revision lands, or the planner profile body is updated to carry the parallelism-first frame directly." Without that gate, v2 silently degrades to v0 planning with new prose around it.

---

## Verdict

**Request changes.** Not a rejection of the direction — the reversal is defensible and the cognitive separation is worth preserving. But the v2 design package has three structural problems that should be fixed before implementation:

**Blocking findings (must address in this design pass):**
- **H1** — parallelism-first frame has no enforcement infrastructure. Fix by mandating either the `/planning` skill update or inlining the central frame into the planner profile body, plus adding plan-overview format requirements and dev-orch review criteria.
- **H2** — planner re-spawn loop is unbounded. Fix by adding a planning-cycle cap in impl-orch.
- **H3** — structural delta is not wired to structural-prep. Fix by requiring design-orch to tag candidate items and requiring the planner to map each to a phase or a skip decision.
- **H4** — pre-planning chicken-and-egg is unresolved. Fix by picking an explicit resolution path (working hypothesis vs. module-scoped enumeration) and documenting it.

**Worth addressing but non-blocking:**
- **M1–M5** — overclaiming equivalence, anthropomorphic framing, missing review criteria, terminology collision, missing planning-time bail-out path. Individually small; collectively they're the difference between a design that reads as precise and a design that reads as "we wrote prose around it."

**Pickups for polish:** L1–L3.

If H1 and H2 are addressed, v2 delivers what it claims. If they ship as-is, the parallelism-first frame is rhetoric and the planner loop can pathologically oscillate.

Now writing the run report.
Review delivered above as a single adversarial report, and persisted via `meridian spawn report create --stdin` (spawn p1341, 6919 bytes).

**Verdict: Request changes.** The v1 → v2 reversal is directionally defensible — the fresh-context argument has a real core — but v2 has a systematic weakness: **parallelism-first is asserted in prose and never wired into the machinery that would enforce it.** Four blocking HIGH findings:

1. **H1** — No enforcement infrastructure. `/planning` skill, planner profile body, blueprint format, plan-overview format, dev-orch review criteria, and re-spawn triggers are all unchanged from v0. A v2 planner will produce v0-shaped plans.
2. **H2** — Planner re-spawn loop is unbounded. D7's redesign cap explicitly excludes planner re-spawns; pathological ping-pong is possible.
3. **H3** — Terrain's structural delta and the planner's structural-prep-first pattern should be the same list but nothing welds them. Design-orch doesn't tag items, planner has no mandate to read them.
4. **H4** — Pre-planning chicken-and-egg: impl-orch must enumerate parallelism-blocking constraints without a decomposition in hand. Either exhaustive enumeration (noise) or in-context sketching (reproduces the v1 mashing v2 rejected). Design is silent on which.

Plus 5 MEDIUM (overclaim of runtime-context equivalence, anthropomorphic "cognitive modes" framing, empty dev-orch review criteria, terminology collision between "structural refactors" and "foundational work," no planning-time escape hatch path) and 3 LOW findings (parallelism-justification template, redesign-brief format gap, probe-request channel).

The follow-up `/planning` skill update is under-scoped — should be promoted to a prerequisite of this design pass, or the central frame should be inlined into the planner profile body. Without that gate, v2 silently degrades to v0 planning with new prose around it.
