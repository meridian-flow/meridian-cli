# v3 Round-2 Convergence Report (final pass)

**Status:** converged

## Round 1 findings × final state

- **Source:** r1-artifact-ownership-drift
  - **Finding:** Producer/consumer docs disagreed on where parallel-cluster hypothesis + foundational prep live.
  - **Final state:** Terrain ownership unified: outputs are three locations (architecture tree + `refactors.md` + `feasibility.md`) in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:5` and `.meridian/work/orchestrator-restructure/design/terrain-contract.md:15`; parallel-cluster hypothesis + foundational prep explicitly live in `feasibility.md` shape in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:121` and `.meridian/work/orchestrator-restructure/design/terrain-contract.md:161`; feasibility-questions doc follows terrain-contract and names those landing spots in `.meridian/work/orchestrator-restructure/design/feasibility-questions.md:70`.
  - **Verdict:** addressed

- **Source:** r1-dev-principles-gate
  - **Finding:** `dev-principles` gate scope inconsistent; overview had inverted yes/no semantics.
  - **Final state:** Scope clarified as design-orch-only gate in `.meridian/work/orchestrator-restructure/decisions.md:344` and design-orch gate spelled out in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:200`; overview gate semantics use “yes blocks” in `.meridian/work/orchestrator-restructure/design/overview.md:179`; impl-orch re-applies as reviewer lens (not a gate) in `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md:206`.
  - **Verdict:** addressed

- **Source:** r1-EARS-enforcement-contract
  - **Finding:** EARS is mandated but reviewer enforcement lane not explicitly operationalized.
  - **Final state:** Spec reviewer explicitly defined as the EARS-enforcement contract in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:271`.
  - **Verdict:** addressed

- **Source:** r1-scenario-reversal-sweep
  - **Finding:** Scenario-era vocabulary lingered in active decisions text after v3 reversal.
  - **Final state:** Active D5 wording updated to spec-leaf vocabulary and two-counter planning-time arm in `.meridian/work/orchestrator-restructure/decisions.md:101`; scenario mentions that remain are explicitly historical / reversal documentation (e.g. D22) in `.meridian/work/orchestrator-restructure/decisions.md:320`.
  - **Verdict:** addressed

- **Source:** r2-dev-orch-inversion
  - **Finding:** dev-orch prose implied architecture-reading shapes acceptance criteria.
  - **Final state:** Requirements-to-spec-first ordering made explicit in `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md:15`.
  - **Verdict:** addressed

- **Source:** r2-spec-first-production-order
  - **Finding:** Spec-first (then architecture) production order not mandated.
  - **Final state:** Spec-first ordering is explicit convergence rule in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:47`.
  - **Verdict:** addressed

- **Source:** r2-EARS-mapping-overreach
  - **Finding:** “Direct” EARS→test triple mapping overreached for Ubiquitous / Optional-feature.
  - **Final state:** Per-pattern parsing guide covers all five patterns (including Ubiquitous + Optional-feature) in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:121`.
  - **Verdict:** addressed

- **Source:** r2-non-orchestrator-EARS-examples
  - **Finding:** EARS examples skewed internal/orchestrator-only; asked for one non-orchestrator-domain example.
  - **Final state:** Domain-agnostic examples added (CLI, filesystem, config, harness adapter, state store) in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:105`.
  - **Verdict:** addressed

- **Source:** r2-verification-notes-field
  - **Finding:** “Verification notes” risked becoming load-bearing prose; should be optional with a reviewer heuristic.
  - **Final state:** Verification notes explicitly optional + non-load-bearing reviewer heuristic in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:61`.
  - **Verdict:** addressed

- **Source:** r2-non-requirement-escape-valve
  - **Finding:** “non-requirement with reasoning” escape valve should be named/audited in spec-reviewer brief.
  - **Final state:** Escape-valve audit added as focus area (6) in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:271`.
  - **Verdict:** addressed

- **Source:** r3-stale-decisions-D11-D13
  - **Finding:** D11/D13 decision text drifted toward v2 Terrain-section mechanics.
  - **Final state:** D11 revised-by notes and live mechanics updated to v3 artifact split in `.meridian/work/orchestrator-restructure/decisions.md:167`; D13 and its v3 three-output shape is explicit in `.meridian/work/orchestrator-restructure/decisions.md:204`.
  - **Verdict:** addressed

- **Source:** r3-overview-contract-drift
  - **Finding:** overview risked restating retired contract details and drifting.
  - **Final state:** Overview points to terrain-contract as canonical and does not mention retired v2 tag mechanics; “Three artifact contracts” section references terrain-contract without `structural-prep-candidate` fields in `.meridian/work/orchestrator-restructure/design/overview.md:102`.
  - **Verdict:** addressed

- **Source:** r3-terrain-contract-paper-cuts
  - **Finding:** Terrain contract wording/fields needed tightening (three locations vs “two outputs”, must-land-before phase-number leak, coupling-removed witness).
  - **Final state:** “Three locations, two first-class artifacts” framing in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:15`; coupling-removed requires a concrete coupling witness in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:55`; must-land-before anchored to spec/architecture/refactor IDs (not phases) in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:56`.
  - **Verdict:** addressed

- **Source:** r4-leaf-ownership-granularity
  - **Finding:** Leaf-ownership granularity ambiguous (leaf-file vs EARS-statement).
  - **Final state:** Statement granularity is explicit in planner output contract `.meridian/work/orchestrator-restructure/design/planner.md:197` and validated by impl-orch `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md:64` and dev-orch `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md:63`.
  - **Verdict:** addressed

- **Source:** r4-EARS-parsing-gap
  - **Finding:** Ubiquitous + Optional-feature lacked mechanical parsing guidance.
  - **Final state:** Parsing guide table includes both patterns with synthesis rules in `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:125`.
  - **Verdict:** addressed

- **Source:** r4-refactor-depends-on-feature
  - **Finding:** Needed explicit sequencing rule for refactors that can only land after a feature.
  - **Final state:** `depends on feature` field and guidance are explicit in `.meridian/work/orchestrator-restructure/design/terrain-contract.md:63`.
  - **Verdict:** addressed

- **Source:** r4-two-counter-cap
  - **Finding:** Probe-requests should not burn the same cap as failed plans.
  - **Final state:** Two-counter scheme in decisions `.meridian/work/orchestrator-restructure/decisions.md:186` and planner contract `.meridian/work/orchestrator-restructure/design/planner.md:137`.
  - **Verdict:** addressed

- **Source:** r4-preservation-carry-over
  - **Finding:** Redesign-cycle carry-over of preserved phase claims into new ownership file was implicit.
  - **Final state:** Preservation hint requires copying preserved claims into new `plan/leaf-ownership.md` in `.meridian/work/orchestrator-restructure/design/preservation-hint.md:122`.
  - **Verdict:** addressed

- **Source:** r4-preserved-reverification
  - **Finding:** Preserved phases with revised-in-place leaves needed re-verification mechanism.
  - **Final state:** `preserved-requires-reverification` decision and tester-only re-verification captured in `.meridian/work/orchestrator-restructure/decisions.md:366` and preservation-hint contract in `.meridian/work/orchestrator-restructure/design/preservation-hint.md:32`.
  - **Verdict:** addressed

- **Source:** r4-signal-precedence
  - **Finding:** Precedence between `structural-blocking` and `planning-blocked` undefined when both apply.
  - **Final state:** Structural-blocking short-circuit precedence is explicit in `.meridian/work/orchestrator-restructure/design/planner.md:145` and decisions `.meridian/work/orchestrator-restructure/decisions.md:190`.
  - **Verdict:** addressed

## p1548 findings × tranche 4/5 fix

- **p1548 finding:** Leaf-ownership granularity mismatch remained on consumer side (impl-orch/dev-orch still validating leaf-file).
  - **Tranche 4/5 fix:** Consumer-side checks updated to EARS-statement granularity in `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md:64` and `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md:63` (planner already statement-granularity in `.meridian/work/orchestrator-restructure/design/planner.md:197`).
  - **Verdict:** addressed

- **p1548 finding:** Scenario-vocabulary + `K=3` sweep incomplete (active D5 + several docs still used old wording).
  - **Tranche 4/5 fix:** D5 updated to spec-leaf vocabulary + two-counter planning-time arm in `.meridian/work/orchestrator-restructure/decisions.md:101`; remaining cap summaries updated across dev-orch + redesign brief + impl-orch add-list in `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md:46`, `.meridian/work/orchestrator-restructure/design/redesign-brief.md:90`, and `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md:231`.
  - **Verdict:** addressed

- **p1548 finding:** Preservation hint column header/semantics stale.
  - **Tranche 4/5 fix:** Column header + semantics clarified as EARS statement IDs in `.meridian/work/orchestrator-restructure/design/preservation-hint.md:41`.
  - **Verdict:** addressed

## New findings introduced by tranche 4 or 5

None.

## Convergence verdict

- **converged** — Every round-1 finding is addressed, p1548 propagation gaps are closed, and tranche 4/5 did not introduce new blockers.

## Paper cuts (non-blocking)

- `K=3` remains only as an explicitly historical alternative mention in `.meridian/work/orchestrator-restructure/decisions.md:193`.
- Scenario terminology remains only in explicitly historical/reversal documentation (e.g. D22) and follow-up notes.