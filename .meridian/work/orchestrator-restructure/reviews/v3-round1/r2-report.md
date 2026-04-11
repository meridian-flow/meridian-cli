Spawn: p1541
Status: succeeded (exit 0)
Model: claude-opus-4-6 (claude)
Duration: 338.1s
Parent: p1533
Desc: v3 r2: SDD shape check (opus)
Cost: $1.7892
Report: /home/jimyao/gitrepos/meridian-channel/.meridian/spawns/p1541/report.md

# v3 SDD Shape Review — Fowler's Three Levels Test

## Status

**converged with notes** — The v3 package is genuinely at the spec-anchored altitude the user is targeting. Kiro alignment is the dominant flavor, the two-tree split is substantive, and the scenarios→spec-leaves reversal is real. Two ordering gaps and one growth risk warrant tightening before handoff to planner, but none are structural; design-orch does not need a full redesign pass.

## Altitude diagnosis — L2+ (spec-anchored), not L1 wearing EARS clothes

Evidence the package actually sits at Fowler L2→L3 and not L1-in-disguise:

- **EARS mandate is load-bearing, not decorative.** D17 makes EARS a convergence blocker, and design-orchestrator.md §"EARS notation" is explicit that a prose acceptance criterion is "not converged on the spec axis." The spec-alignment reviewer enforces the shape, not reviewer taste.
- **Mechanical test derivation is specified, not implied.** D21 and design-orchestrator.md both state the mapping: trigger→setup, precondition→fixture, response→assertion. impl-orchestrator.md §"Verification framing" restates it from the tester's side. Three independent docs describe the same mechanical path, which means it will survive when agents only load one of them.
- **Stable IDs flow through the workflow.** `S<subsystem>.<section>.<letter><number>` (e.g. `S03.1.e1`) are required per spec leaf and cited in phase blueprints, leaf-ownership, falsification briefs, and preservation hints. A spec-leaf ID is a first-class reference, not a convenience label.
- **Spec drift enforcement prevents silent L1 fallback.** impl-orchestrator.md §"Spec-drift enforcement" mandates that runtime evidence contradicting a spec leaf triggers bail-out, not a silent code-first workaround. This is the exact Fowler critique of spec-anchored SDD that collapses into L1 when people stop updating the spec — and the v3 design closes it.

**Minor altitude caveat.** The spec-leaf content template (design-orchestrator.md §"Spec tree content" field 7) includes a free-prose "Verification notes" section describing how a smoke test would exercise the behavior. If the EARS statement is well-formed the verification notes are redundant (and fine); if the EARS statement is under-specified and the tester has to read the prose notes to know what to do, the L2 property has quietly decayed to L1 with EARS decoration. Not a design flaw but worth a reviewer heuristic: "Verification notes" should be optional and never load-bearing; if a tester cannot derive the test from the EARS alone, the EARS statement is under-specified.

**Test applied.** I took three edge cases from the design prose (pathological redesign oscillation, spec-leaf falsification mid-execution, planner non-convergence at K=3) and each mapped cleanly into a Complex- or Event-driven EARS statement without needing accessory prose. The template is genuinely sufficient.

## Kiro / spec-kit alignment — Kiro-aligned with one inversion to fix

The package is on the Kiro side: lightweight requirements doc, spec→design→tasks flow, no TDD mandate, no separate constitution artifact, one mandatory convergence gate (structural reviewer PASS) rather than spec-kit's three-approval model. D16 explicitly rejects spec-kit's constitution-first flow in its alternatives section, and D21 explicitly follows Kiro's rejection of TDD.

**Finding 1 — inversion signal in dev-orchestrator.md:15.** The sentence *"that happens inside design-orch's spec tree once an **architecture reading has shaped the acceptance criteria**"* reads naturally as "architecture is read before spec is written, and the reading shapes the spec." Under Kiro's requirements→spec→design flow, acceptance criteria come from requirements; architecture is derived from spec, not the other way around. A brownfield-charity reading ("reading the existing codebase as prior art before writing spec") is defensible but not the most natural parse.

- **Why it matters.** If design-orch interprets this as "walk the target architecture tree, then backfill spec to describe what that system does," the spec becomes a description of a decided system — the spec-kit pattern the package otherwise rejects. The cross-link enforcement ("every architecture leaf realizes a spec leaf") compensates after the fact but only detects structural holes, not backfilled provenance.
- **Recommended revision.** Replace with "once design-orch has read the existing codebase as context" or delete the sub-clause entirely. The default Kiro framing is: requirements → spec leaves → architecture tree derived from spec, with existing-code reading used only as structural context, not as a shape-driver for spec content.

**Finding 2 — missing production-order mandate.** design-orchestrator.md describes the spec tree and the architecture tree as mirrors with cross-links, but never says "produce the spec tree first, then derive architecture leaves in response." A reader could reasonably interpret the two trees as produced in parallel. That's a structural weak spot: Kiro's altitude depends on spec being authoritative upstream, and "authoritative upstream" requires production ordering, not just reference mirroring.

- **Recommended revision.** Add an explicit statement in design-orchestrator.md §"The two-tree structure": *"The spec tree is produced first. Architecture leaves are derived from spec leaves — every architecture leaf exists because some spec leaf motivates it. Parallel drafting is permitted only when iteration reveals a spec gap; the gap closes on the spec side first, then the architecture side follows."*

**Finding 3 — cumulative gate count is creeping.** The package has: (a) required structural reviewer PASS, (b) `dev-principles` convergence gate, (c) required EARS shape check, (d) required cross-link coverage check, (e) required refactors.md completeness check. Each is individually light; collectively they are approaching spec-kit's governance surface. Not a current problem, but worth calling out as a watch-list item: every additional mandatory convergence gate increases drift risk toward spec-kit's heavy-upfront-governance flow. The `dev-principles` gate is explicitly framed as "lightweight constitutional gate" — honest and acceptable — but adding a third mandatory gate in a future revision would cross the Kiro/spec-kit line.

## TDD avoidance check — clean

Three independent passes (overview.md §"Why no TDD", design-orchestrator.md §"EARS does not imply TDD", impl-orchestrator.md §"Verification framing", and D21) all state coders do not write tests before implementing. No "test file must precede implementation commit" rule. No "write tests first" step in impl-orch's execution loop. The closest thing to TDD is the tester-reads-EARS-and-writes-smoke-test flow in D21, which is explicitly post-implementation verification. No sneak-ins found.

## Two-tree fidelity — clean, with a pedagogical note

Architecture leaves do not describe observable behavior — their template (current state, target state, interfaces, dependencies, open questions) is strictly structural, with a `Realizes:` cross-link back to spec rather than a copy of the behavior. No cross-contamination in the architecture→spec direction.

**Pedagogical note on the EARS example set.** Every EARS example in design-orchestrator.md and overview.md describes internal orchestrator protocol (e.g. "While a redesign cycle is active, dev-orch shall not initiate a new design session..."). This is not strictly a two-tree violation — when the design scope IS internal tooling, "the system" boundary is the internal tool and "observable behavior" is developer-observable behavior. But a new author reading these examples might generalize "EARS statements name internal agents" to work items whose scope is user-facing behavior, and then mis-scope real spec leaves. Low-cost fix: add one non-orchestrator-domain EARS example (e.g. a CLI subcommand, a filesystem contract) so the example set does not implicitly teach internal-protocol framing as the default.

## Scenarios reversal depth — substantive, not cosmetic

D22 is real. Evidence:

- **Format upgrade, not rename.** Scenarios in v2 were prose bullets; spec leaves in v3 are EARS triples with stable IDs and verification-note mappings. The format change is the reversal's load-bearing piece.
- **Spec leaf template explicitly subsumes edge cases.** design-orchestrator.md §"Spec tree content" field 5: "Edge cases and boundary conditions. Named explicitly, each either expressed as an additional EARS statement or flagged as a non-requirement with reasoning." Edge cases are mandated into the spec structure, not deferred to a separate convention.
- **Ownership file renamed to match.** `plan/scenario-ownership.md` → `plan/leaf-ownership.md` with spec-leaf IDs. Not a cosmetic rename: the IDs are structurally different and flow to different consumers.
- **Test applied.** Three edge cases from the design prose — pathological oscillation, mid-execution falsification, planner non-convergence — each map cleanly to a Complex or Event-driven EARS statement with explicit trigger/precondition/response. The test passes.

**Minor risk.** The "flagged as a non-requirement with reasoning" escape valve in the spec leaf template is a drift lane: an author who cannot write the EARS statement can label the edge case "non-requirement" and move on with prose. The reviewer fan-out should treat "non-requirement" labels as a review signal and verify the reasoning is honest. Not a design change, just a reviewer heuristic worth naming in the spec-reviewer brief.

## Context offloading / TOC fidelity — works small, risks ballooning large

The TOC index is present and mandatory (design-orchestrator.md §"Hierarchical TOC indexes": "A design package without root TOC indexes cannot converge"). But the root `overview.md` carries more than a pure TOC: Purpose, TOC, root-level content (ubiquitous EARS / system topology / structural delta / import DAG slice), Reading order.

- **On small work**, the root content is small and the overview is still cheap to load. Fine.
- **On large work**, the "structural delta" and "import DAG slice" at the root could grow to tens of thousands of tokens, defeating Osmani's cheap-orientation promise. There is no size cap, and nothing prevents the root overview from becoming a second overview doc.

Not structurally broken — the TOC is still there and consumers that only need the TOC can scroll past the root content. But strict Osmani shape would keep the root overview as a pure index and promote the root structural content to its own file (e.g. `architecture/root-topology.md` linked from the root TOC). Worth a future tightening; not a current blocker.

## Questions to escalate

1. **Is dev-orchestrator.md:15's "architecture reading has shaped the acceptance criteria" line describing (a) existing codebase reading for brownfield context, or (b) target-architecture-tree reading that spec is derived from?** If (b), the flow is backwards from Kiro and needs reshaping. If (a), the sentence should be rewritten to say so unambiguously.

2. **Is the spec tree mandated to be produced before the architecture tree, or are they produced in parallel?** The design does not say. For strict Kiro alignment, spec-first production should be explicit.

3. **Is there a size cap on the root `overview.md`, or a promotion rule that pushes root structural content into a sub-doc when the root grows past some threshold?** Currently nothing enforces the root staying cheap to load.

4. **Should the spec leaf template's "Verification notes" field be optional rather than part of the default shape?** Making it optional would prevent prose from quietly becoming load-bearing for test derivation.

5. **Should the "flagged as a non-requirement with reasoning" escape valve in spec leaves be reviewer-checked with a specific brief?** Without that check, it's a drift lane back to prose.

## Recommendation

Hand off to planner after the following scoped revisions — none require a redesign pass, all are text edits in design-orchestrator.md (and one in dev-orchestrator.md):

**Must-fix before planner (blocking):**
1. Rewrite dev-orchestrator.md:15 to remove the "architecture reading has shaped the acceptance criteria" ambiguity. Either delete the sub-clause or explicitly anchor it to existing-codebase context.
2. Add an explicit production-order statement in design-orchestrator.md §"The two-tree structure": spec tree is authored first, architecture leaves derive from spec leaves, parallel drafting is permitted only for iterative gap-closing with spec as the authoritative direction.

**Should-fix (non-blocking, file as follow-ups if planner is time-boxed):**
3. Add one non-orchestrator-domain EARS example (CLI subcommand, filesystem contract, or similar) to the example set so internal-protocol framing does not become the implicit default.
4. Downgrade the spec leaf template's "Verification notes" field from "required" to "optional — included only when the EARS statement alone is insufficient context for a tester" and surface the weakening as a reviewer signal.
5. Name the "non-requirement with reasoning" escape valve explicitly in the spec-reviewer brief as a flag worth double-checking.
6. Consider (future design pass, not this one) adding a root-overview size cap or promotion rule to keep strict Osmani-shape context offloading on large designs.

The altitude the user targeted is real in this package. The two load-bearing fixes above are about making the Kiro direction unambiguous in the prose, not about moving the package to a different altitude.
