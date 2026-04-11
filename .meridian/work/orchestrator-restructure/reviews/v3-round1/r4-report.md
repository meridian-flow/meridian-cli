Spawn: p1544
Status: succeeded (exit 0)
Model: claude-sonnet-4-6 (claude)
Duration: 343.07410052302293s
Parent: p1533
Desc: v3 r4: decomposition sanity (sonnet)
Cost: \$0.7919602499999999
Report: /home/jimyao/gitrepos/meridian-channel/.meridian/spawns/p1544/report.md

# Review Report: v3 Decomposition Sanity

## Status: **needs-revision**

The v3 design package is architecturally sound and the planner can generally do its job from the provided inputs. The two-tree structure, parallelism-first frame, terrain contract, and preservation hint are well-specified and mutually consistent. However, five concrete gaps — two of them blocking for downstream execution — need revision before handing off to the planner.

---

## Input Completeness Verdict

**The planner can write a complete plan from v3 inputs — with one oversight worth noting.**

The input set (spec tree, architecture tree, refactors.md, feasibility.md, pre-planning-notes.md, decisions.md, preservation-hint) is comprehensive. Spec leaves carry EARS IDs, architecture leaves carry cross-links and file paths, refactors.md carries must-land-before edges, and pre-planning-notes carry module-scoped runtime constraints. The planner has enough to decompose work without reaching for anything outside the package.

One minor oversight: `requirements.md` appears in planner.md §"The new caller relationship" as an input impl-orch receives from dev-orch, but `requirements.md` is not listed in the planner's own input set (§"Inputs the planner consumes"). For most work items this doesn't matter — spec leaves subsume user requirements. But if a planner needs to understand *why* a spec leaf was written (e.g., to resolve an ambiguity in EARS phrasing), it has no direct access to the user's original intent. This is a design-time gap, not a planning-time one, but worth noting for edge cases.

---

## Findings by Severity

### BLOCKING: Leaf-ownership granularity is ambiguous

**Where it lives:** planner.md §"Parallelism Posture", planner.md §"Outputs", throughout.

**The problem:** The design uses two different granularities for spec leaf ownership without specifying which applies to `plan/leaf-ownership.md`.

- The ownership rule says "every spec leaf in `design/spec/` claimed by exactly one phase." The natural reading of "spec leaf" is a leaf *file* (e.g., `spec/auth/token-refresh.md`, ID `S03.1`).
- The parallelism justification template shows EARS statement IDs assigned to phases: "P3 claims `S03.1.e1, S03.1.e2`", "P4 claims `S03.2.e1`". This is EARS-statement granularity, not leaf-file granularity.

These two granularities are not equivalent. A single spec leaf file (S03.1) can contain multiple EARS statements (S03.1.e1, S03.1.e2, S03.1.e3). If Phase 3 satisfies S03.1.e1 and S03.1.e2 but Phase 5 satisfies S03.1.e3 (the integration-round statement), is S03.1 double-claimed or not?

Under leaf-file granularity: yes, double-claimed — impl-orch flags a planner bug.
Under EARS-statement granularity: no, each statement is claimed exactly once.

The design needs to pick one and state it explicitly. EARS-statement granularity is the better choice (it reflects the actual verification unit) but requires changing the ownership rule to "every EARS statement in `design/spec/` claimed by exactly one phase" and updating leaf-ownership.md's format accordingly.

**Why it matters:** Without a clear granularity, the planner and impl-orch can disagree on whether a plan has double-claims. The double-claim check is already implicit (impl-orch evaluates completeness), so an ambiguous ownership rule makes a soft check even softer.

---

### BLOCKING: EARS-to-test parsing is not fully mechanical for two patterns

**Where it lives:** overview.md §"EARS notation", design-orchestrator.md §"EARS notation", D21.

**The problem:** D21 and the overview claim that EARS statements map "directly" to smoke-test triples (trigger → setup, precondition → fixture, response → assertion). This is true for Event-driven, State-driven, and Complex patterns. It is false for two of the five canonical patterns:

**Ubiquitous** (`The <system> shall <response>`): No trigger, no precondition. Example: "The spawn runner shall emit one heartbeat every 30s while the spawn is live." A smoke tester reading this has no EARS clause to parse into a test setup action. The test writer must invent a trigger ("create a spawn, wait 60 seconds, check for two heartbeat events") — this is interpretation, not mechanical parsing.

**Optional-feature** (`Where <feature>, the <system> shall <response>`): No trigger. Example: "Where a preservation hint exists, impl-orch shall scope pre-planning runtime probes to the invalidated phase range." A smoke tester needs to know *what action to take* to exercise the scoping behavior — the WHERE clause names the precondition but not the test stimulus. The test setup must be inferred from context.

**Why it matters:** The phrase "parse EARS leaves directly into test triples" (D21) is what smoke-testers read in their verification guidance. Smoke testers following this instruction for Ubiquitous and Optional-feature leaves will discover the parsing doesn't work mechanically and will either skip those leaves (coverage gap) or invent interpretations that diverge across testers (verification inconsistency). The design should acknowledge that Ubiquitous and Optional-feature require domain context to generate the test setup, and provide a worked example for each.

**Suggested fix:** Add a note to feasibility-questions.md (or design-orchestrator.md §EARS notation) that: Ubiquitous requirements have no trigger and should include a "verification setup note" in the spec leaf (e.g., "to test: create a spawn, observe for N heartbeat intervals"); Optional-feature requirements should name an example action in their verification notes section.

---

### MODERATE: Refactor-before-feature ordering breaks when a refactor depends on a feature-introduced module

**Where it lives:** planner.md §"Refactor agenda landing first", terrain-contract.md §"Refactors vs foundational prep".

**The problem:** The design mandates Round 1 = refactors, Round 2 = feature fanout. But there's a sequencing hazard the design doesn't address: a refactor that depends on a new module the feature introduces.

Concrete case: Feature F introduces a new abstract protocol module M. Refactor R01 splits existing module X into X-parser and X-persistence, with both sides implementing protocol M. R01 cannot land before M exists, and M only exists after Feature F's work lands (because M is the new interface Feature F introduces).

In principle, the terrain contract prevents this by classifying M as "foundational prep" (creation of new scaffolding) → goes in feasibility.md §"Foundational prep", and R01 as a refactor → goes in refactors.md. The planner would then sequence: Round 0 (foundational prep: M), Round 1 (refactor: R01 using M), Round 2 (feature fanout). This should work.

But it requires design-orch to correctly separate the interface-creation step (foundational prep) from the module-split step (structural refactor). If design-orch describes R01 as a single refactor entry in refactors.md that implicitly depends on M's existence — without surfacing M as foundational prep — the planner receives an R01 that can't land in Round 1 without a dependency the design didn't surface.

The planner, seeing a Round 1 refactor that depends on Round 2's output, faces a paradox: violate the refactor-first rule, or escalate structural-blocking. Neither escalation path is explicitly described for this case. The design should state what the planner should do when a refactors.md entry has an undisclosed dependency on architecture target-state that doesn't yet exist (as opposed to a dependency on another refactor entry, which refactors.md's ordering handles).

**Sequencing hazard verdict:** Concrete and real for work items that add features to modules they also refactor. Design-orch must correctly separate M (foundational prep → feasibility.md) from R01 (structural refactor → refactors.md). If design-orch gets this wrong, the planner has no described path out.

---

### MODERATE: K=3 cap can be exhausted by probe-request iterations before any plan is attempted

**Where it lives:** planner.md §"Planning-cycle cap", impl-orchestrator.md §"Planning cycle cap", D12.

**The problem:** Probe-request rounds — where the planner terminates with "needs more probing" instead of a plan — count toward the K=3 cap. For a planner working through a large spec tree (20+ leaves) with multiple runtime data gaps, the probe-request channel can exhaust the cap without the planner ever producing a bad plan:

- Spawn 1: planner finds gap A, terminates with "needs more probing for A." Count: 1.
- Impl-orch runs probes for A, re-spawns.
- Spawn 2: planner finds gap B (different gap), terminates with "needs more probing for B." Count: 2.
- Impl-orch runs probes for B, re-spawns.
- Spawn 3: planner produces a real plan but it's missing spec leaf S15.2. Count: 3 (failure).
- → `planning-blocked` escalation, redesign loop fires.

The redesign loop fires not because the design was wrong, but because impl-orch's pre-planning notes were incomplete (gaps A and B should have been caught in pre-planning). This is a false positive for the redesign signal — it triggers a design-orch revisit for a problem that was a pre-planning gap.

D12 addresses this obliquely: "beyond three failed convergence attempts, the gap is almost always in the inputs (design or pre-planning notes), not in the planner's craft." True — but the fix for a pre-planning gap is improving the pre-planning notes, not a design revision. The planning-blocked signal routes to dev-orch, who "decides whether to revise the design (back through design-orch) or to accept the partial plan with explicit known gaps." The "or" path (accept partial plan) is available, but it's a judgment call that requires dev-orch to diagnose whether the planning-blocked was a pre-planning gap or a true design gap.

**Risk level:** K=3 is realistic for most cases (D12's reasoning holds for well-formed pre-planning notes). The false-positive risk is real for work items where pre-planning notes are thin. Mitigation: impl-orch's "spec-leaf coverage hypothesis" section in pre-planning-notes should be required (not optional) for work items with more than 10 spec leaves, to front-load the cluster analysis the planner would otherwise do via probe requests.

---

### MINOR: Preservation-cycle leaf carry-over into new leaf-ownership.md is implicit

**Where it lives:** preservation-hint.md §"How impl-orch consumes the hint", planner.md §"Outputs".

**The problem:** On a redesign cycle, the planner must write a new `plan/leaf-ownership.md`. This file must include leaf claims for preserved phases (e.g., "Phase 1: S01.1.e1, S01.1.e2") as well as new claims for replanned phases. The preservation hint carries a "Spec leaves satisfied" column per preserved phase — this is the source the planner should use.

But the design never explicitly says "the planner writes preserved phases' leaf claims from the hint into the new leaf-ownership.md." The planner is told to "honor the preservation anchor and replans only from replan-from-phase onward." Whether "honoring the anchor" includes copying preserved phases' leaf claims into the new leaf-ownership.md is implicit.

If the planner omits preserved phases from the new leaf-ownership.md, impl-orch's completeness check ("every spec leaf in `design/spec/` claimed by exactly one phase") would flag preserved phases' leaves as unclaimed — a false planner bug that consumes a re-spawn slot.

If the planner includes preserved phases in leaf-ownership.md by reading the hint, it might assign the old leaf IDs but miss revised-in-place leaves (which have the same ID but a new EARS statement). The `revised: <reason>` annotation in the hint partially addresses this, but the planner has to notice it.

**Suggested fix:** Add one sentence to planner.md §"Outputs": "When a preservation hint is present, leaf-ownership.md must include entries for preserved phases populated from the hint's 'Spec leaves satisfied' column, with `revised: <reason>` entries flagged for re-verification."

---

### MINOR: Structural-blocking vs planning-blocked precedence undefined when K=3 fires with a structural-blocking plan

**Where it lives:** impl-orchestrator.md §"Planning cycle cap", §"Pre-execution structural gate", D5, D12.

**The problem:** If the third (K=3 exhausted) planner spawn returns a plan with `Cause: structural coupling preserved by design`, two signals would logically trigger simultaneously:
- K=3 exhausted → `planning-blocked` signal
- Cause field → `structural-blocking` signal

The two signals route differently: planning-blocked routes dev-orch to "revise design or accept partial plan"; structural-blocking routes dev-orch to "send back to design-orch for structural revision." If both fire simultaneously, the design is silent on which takes precedence.

**Suggested fix:** One line in impl-orchestrator.md: "If K=3 is exhausted and the terminal spawn also returned `Cause: structural coupling preserved by design`, emit `structural-blocking` — it is the more actionable signal and subsumes `planning-blocked` for this case."

---

## Double-Claim Protection Verdict

**The check exists but is soft.** `plan/leaf-ownership.md` makes double-claims visible, and impl-orch's completeness check is the catch mechanism. There is no dedicated reviewer step or mechanical verification pass; impl-orch catches double-claims in its own judgment during plan evaluation. During redesign cycles, the carry-over gap (Finding 5 above) creates a secondary path for false unclaimed-leaf flags that consume re-spawn capacity. The check works in the happy path; it frays slightly under redesign conditions.

---

## Signal Clarity Verdict

**Clean distinction in the common case.** `structural-blocking` fires from the Cause field in the Parallelism Posture, `planning-blocked` fires from the spawn counter. Impl-orch can tell them apart without interpretation. Dev-orch can route them differently based on the brief's "Bail-out trigger" field. The one edge case (K=3 fires with structural-blocking plan) needs the one-line precedence rule described above.

---

## Recommendations for Design-Orch

Before handing off to the planner, design-orch should revise:

1. **Leaf-ownership granularity (blocking):** Decide: leaf-file granularity or EARS-statement granularity. Update the ownership rule, leaf-ownership.md format spec, and the parallelism justification template to be consistent. EARS-statement granularity is recommended.

2. **EARS-to-test note for Ubiquitous and Optional-feature (blocking):** Add guidance (in design-orchestrator.md §EARS notation) that Ubiquitous and Optional-feature patterns require a "verification setup note" written by the spec author, naming the action that exercises the behavior. The spec leaf template should include this as a required field for these two patterns.

3. **Refactor-depends-on-feature sequencing (moderate):** Add a note to terrain-contract.md §"Refactors vs foundational prep" that if a refactor entry in refactors.md has an implicit dependency on target-state code that doesn't yet exist, that code must be extracted as a foundational-prep entry in feasibility.md. The planner's escalation path (structural-blocking) should be named explicitly for the case where a refactors.md entry has an undisclosed dependency that the terrain contract should have caught.

4. **Preservation-cycle leaf carry-over (minor):** Add one explicit sentence to planner.md §"Outputs" about how the planner handles preserved phases' leaf claims in redesign-cycle leaf-ownership.md.

5. **Structural-blocking/planning-blocked precedence (minor):** One line in impl-orchestrator.md defining which signal wins when K=3 fires with a structural-blocking plan.

---

## Files Read

- `design/overview.md`
- `design/planner.md`
- `design/impl-orchestrator.md`
- `design/design-orchestrator.md`
- `design/feasibility-questions.md`
- `design/terrain-contract.md`
- `design/preservation-hint.md`
- `design/redesign-brief.md`
- `decisions.md` (all D1–D23)
