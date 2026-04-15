# Feasibility Evidence Base

This file is the evidence record for the v3 design package. It answers three questions per entry: what was checked, what the evidence showed, and what design constraint that evidence backs. Downstream consumers should treat this as the authoritative grounding for why v3 made the shape changes recorded in [decisions.md](../decisions.md), not as a second design narrative.

## Probe records

### P01: Separate `scenarios/` drifted away from the design contract

- **Checked:** [reviews/synthesis.md](../reviews/synthesis.md), especially the v2 synthesis of p1528/p1529/p1530/p1531; [r1-report.md](../reviews/v3-round1/r1-report.md); [r5-opus-convergence.md](../reviews/v3-round2/r5-opus-convergence.md).
- **Observed:** The v2 package depended on a separate `scenarios/` convention to carry verification intent. The design docs describe the failure mode directly: edge cases documented in design prose evaporated before reaching testers, and round-1 review still had to sweep lingering scenario-era wording out of active decision text. The contract was real only if authors remembered to maintain it.
- **Constraint:** Back [decisions.md](../decisions.md) D16, D17, D21, and D22: the verification contract must live in the spec itself, in EARS-shaped leaves, with ownership tracked in `plan/leaf-ownership.md` rather than a sibling `scenarios/` record. See [architecture/verification/orchestrator-verification-contract.md](architecture/verification/orchestrator-verification-contract.md) and [architecture/verification/leaf-ownership-and-tester-flow.md](architecture/verification/leaf-ownership-and-tester-flow.md).

### P02: Flat docs plus a buried Terrain section overloaded the package

- **Checked:** [reviews/synthesis.md](../reviews/synthesis.md) theme T4; [r3-report.md](../reviews/v3-round1/r3-report.md); the current flat design set measured with `wc -c` and `wc -l` on `design/*.md`.
- **Observed:** The current flat package is 9 markdown files totaling 254,924 bytes and 1,892 lines before `feasibility.md` existed. Reviewers flagged that the Terrain material was both overloaded and hard to consume because architecture posture, refactor agenda, and feasibility evidence were mixed into one surface. The entry-point docs were already drifting from the canonical contract by restating retired details.
- **Constraint:** Back [decisions.md](../decisions.md) D18, D19, and D20: split the package into two hierarchical trees plus first-class `refactors.md` and `feasibility.md`, and keep root overviews as TOCs rather than as prose dumps. See [architecture/design-package/two-tree-shape.md](architecture/design-package/two-tree-shape.md) and [terrain-contract.md](terrain-contract.md).

### P03: Structural review has to happen during design, not after implementation starts

- **Checked:** [reviews/extracted/r2-structure.md](../reviews/extracted/r2-structure.md); [reviews/synthesis.md](../reviews/synthesis.md) themes T1 and T2; [decisions.md](../decisions.md) D11.
- **Observed:** The same pattern surfaced twice: the planner could see structural non-decomposability, but without an earlier structural review pass the problem would only become actionable after implementation had already started. Reviewer language was explicit that a functionally coherent design can still be structurally wrong for parallel execution.
- **Constraint:** Back [decisions.md](../decisions.md) D11 and the structural-review contract in [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md): structure is a design-phase convergence criterion, the structural reviewer is required inside normal fan-out, and the planner's `Parallelism Posture` can escalate `structural-blocking` if design preserved coupling. See [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md).

### P04: Artifact ownership drift was real, not hypothetical

- **Checked:** [r1-report.md](../reviews/v3-round1/r1-report.md); [r0-p1548-tranche3-convergence.md](../reviews/v3-round2/r0-p1548-tranche3-convergence.md); [r7-gpt54-convergence.md](../reviews/v3-round2/r7-gpt54-convergence.md).
- **Observed:** Round-1 review found that `terrain-contract.md`, `design-orchestrator.md`, `planner.md`, and `feasibility-questions.md` disagreed on where the parallel-cluster hypothesis and foundational prep lived. The convergence pass had to normalize the three-location split explicitly because producer and consumer docs had drifted apart.
- **Constraint:** Back [decisions.md](../decisions.md) D19 and D20: `terrain-contract.md` is the canonical ownership contract, `refactors.md` carries rearrangement, `feasibility.md` carries probe evidence plus foundational prep, and other docs reference that split instead of restating it. See [terrain-contract.md](terrain-contract.md) and [feasibility-questions.md](feasibility-questions.md).

### P05: `dev-principles` is universal shared guidance, never a binary pass/fail gate

- **Checked:** [r1-report.md](../reviews/v3-round1/r1-report.md); [r5-opus-convergence.md](../reviews/v3-round2/r5-opus-convergence.md); [r7-gpt54-convergence.md](../reviews/v3-round2/r7-gpt54-convergence.md); in-session user correction recorded in [decisions.md](../decisions.md) D24 (revised).
- **Observed:** Round-1 review found inconsistent gate semantics: one doc treated `dev-principles` as a hard convergence gate, another only as a skill load, and overview wording even inverted the blocking logic. An interim convergence fix narrowed the gate to design-orch only and moved impl-orch/planner use to "review lens." The user then corrected that interim framing in-session: the skill is universal shared guidance at every altitude, never a binary gate, including design-orch. Principle violations route through the normal reviewer-finding loop like any other finding.
- **Constraint:** Back [decisions.md](../decisions.md) D24 (revised): load `dev-principles` universally for every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns, and apply it as a shared behavioral lens at every altitude. No agent runs a `dev-principles` PASS/FAIL checkpoint. See `design/architecture/principles/dev-principles-application.md` (A05.1, the R07 anchor) and `design/spec/root-invariants.md` §S00.w1.

### P06: EARS needs per-pattern parsing and statement-granularity ownership

- **Checked:** [r4-report.md](../reviews/v3-round1/r4-report.md); [r0-p1548-tranche3-convergence.md](../reviews/v3-round2/r0-p1548-tranche3-convergence.md); [r5-opus-convergence.md](../reviews/v3-round2/r5-opus-convergence.md).
- **Observed:** Reviewer evidence showed two concrete gaps: a single universal parse rule does not cover Ubiquitous and Optional-feature EARS patterns, and leaf ownership becomes ambiguous if the unit is a leaf file rather than an EARS statement. The convergence passes had to add a per-pattern parsing table and propagate statement-level ownership to planner, dev-orch, and impl-orch.
- **Constraint:** Back [decisions.md](../decisions.md) D17, D21, and D25: every spec leaf is EARS-shaped, testers parse via a per-pattern rule, and `plan/leaf-ownership.md` is authoritative at `S<subsystem>.<section>.<letter><number>` granularity. See [architecture/verification/ears-parsing.md](architecture/verification/ears-parsing.md), [architecture/verification/leaf-ownership-and-tester-flow.md](architecture/verification/leaf-ownership-and-tester-flow.md), and [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md).

### P07: Preserved phases can silently drift when a leaf is revised in place

- **Checked:** [r0-p1548-tranche3-convergence.md](../reviews/v3-round2/r0-p1548-tranche3-convergence.md); [r5-opus-convergence.md](../reviews/v3-round2/r5-opus-convergence.md); [preservation-hint.md](preservation-hint.md).
- **Observed:** The redesign-cycle contract originally preserved phases by commit status only. Reviewers caught the hole: a preserved phase can still own a spec leaf whose ID stays stable while its EARS statement changes. Without a dedicated re-verification pass, the code silently remains correct against the old text and wrong against the new one.
- **Constraint:** Back [decisions.md](../decisions.md) D26: preserved phases with revised leaves become `preserved-requires-reverification`, and impl-orch runs a tester-only pass before treating them as safe. See [preservation-hint.md](preservation-hint.md) and [architecture/orchestrator-topology/execution-loop.md](architecture/orchestrator-topology/execution-loop.md).

### P08: Fowler's SDD spectrum sets the target altitude

- **Checked:** v2 flat `design/overview.md` §"Where v3 sits on Fowler's SDD spectrum" (absorbed into the v3 two-tree rewrite; see [spec/overview.md](spec/overview.md) and [architecture/overview.md](architecture/overview.md)); [decisions.md](../decisions.md) D16.
- **Observed:** The design package explicitly distinguishes informational specs, precise-but-advisory specs, and spec-anchored specs. The evidence used by the package is Fowler's point that level 2 still drifts if nothing forces reconciliation between code and spec.
- **Constraint:** Back [decisions.md](../decisions.md) D16 and the spec-drift enforcement in [architecture/orchestrator-topology/execution-loop.md](architecture/orchestrator-topology/execution-loop.md): v3 must be spec-anchored, meaning runtime contradictions trigger either spec revision or code change, never quiet divergence.

### P09: Kiro is the right process anchor, not constitution-first spec-kit

- **Checked:** [design-orch-v3-prompt.md](../design-orch-v3-prompt.md); [spec/overview.md](spec/overview.md); [decisions.md](../decisions.md) D16 and D21.
- **Observed:** The reframe repeatedly anchors to requirements -> design -> tasks, EARS notation, smoke-test verification, and human approval at key gates, while explicitly rejecting constitution-first heavy process and TDD-first flows.
- **Constraint:** Back [decisions.md](../decisions.md) D16 and D21: dev-orch captures user intent in `requirements.md`, design-orch turns that into spec and architecture, planner turns that into tasks, and verification runs against spec leaves without making TDD mandatory. See [architecture/orchestrator-topology/redesign-loop.md](architecture/orchestrator-topology/redesign-loop.md) and [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md).

### P10: Thoughtworks and Addy Osmani justify the two-tree + TOC shape

- **Checked:** [design-orch-v3-prompt.md](../design-orch-v3-prompt.md); [architecture/design-package/two-tree-shape.md](architecture/design-package/two-tree-shape.md); [decisions.md](../decisions.md) D18.
- **Observed:** The design rationale cites two distinct research pressures: behavior and technical realization need separate review altitudes, and long agent-facing specs need cheap root indexes with drill-down rather than one massive document. The current flat package size demonstrates why the TOC pattern is not decorative.
- **Constraint:** Back [decisions.md](../decisions.md) D18: keep business/behavior in `design/spec/`, technical realization in `design/architecture/`, and require root-level `overview.md` indexes in both trees so reviewers and planners can orient without loading everything.

### P11: A prior session already demonstrated the cost of letting structure slide

- **Checked:** [decisions.md](../decisions.md) D11 reasoning; v2 flat `design/overview.md` §"The four problems" (absorbed into the v3 two-tree rewrite; see [architecture/overview.md](architecture/overview.md)).
- **Observed:** The package records a concrete lesson from prior work: a design can converge functionally, then reveal only during implementation that the target structure is too coupled to decompose. That failure is not hypothetical; it is the explicit reason D11 exists.
- **Constraint:** Back [decisions.md](../decisions.md) D11 and the structural-review machinery in [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md): require structural review during design, require refactors as first-class design output, and let impl-orch/planner escalate structural non-decomposability before execution.

### P12: The env-propagation incident proved coordination assumptions drift unless normalized and tested

- **Checked:** local commit `2ced688` (`Fix child env WORK_DIR fallback and autocompact inheritance (#12)`); [src/meridian/lib/launch/env.py](../../../../src/meridian/lib/launch/env.py); [tests/exec/test_permissions.py](../../../../tests/exec/test_permissions.py).
- **Observed:** Meridian itself shipped a regression where child processes could lose `MERIDIAN_WORK_DIR`. The fix added `_normalize_meridian_work_dir()` to derive the work dir from `MERIDIAN_STATE_ROOT` plus `MERIDIAN_CHAT_ID`, and added regression tests proving inherited child env reconstructs the active work scratch dir. This was a meta-design failure: the workflow depended on inherited work-item context, and the assumption drifted until code and tests caught it.
- **Constraint:** Back the evidence-first discipline in [decisions.md](../decisions.md) D20 and the re-verification discipline in D26: when v3 assumes inherited context, crash-only restarts, or preserved-phase state carryover, those assumptions need either a real probe or a real regression test. "It should inherit" is not enough.

## Fix-or-preserve verdict

### F01: Verification contract as a separate `scenarios/` convention

**Verdict:** fixes

- **Checked:** [reviews/synthesis.md](../reviews/synthesis.md); [architecture/verification/orchestrator-verification-contract.md](architecture/verification/orchestrator-verification-contract.md); [decisions.md](../decisions.md) D22.
- **Observed:** The v2 authors had to remember to maintain `scenarios/` separately from the design. The package itself records that this is where the edge-case contract evaporated.
- **Constraint:** v3 fixes this by retiring `scenarios/`, moving the authoritative contract into EARS-shaped spec leaves, and tracking ownership at statement granularity in `plan/leaf-ownership.md`. See [architecture/verification/leaf-ownership-and-tester-flow.md](architecture/verification/leaf-ownership-and-tester-flow.md) and [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md).

### F02: Flat design doc set with no navigation index

**Verdict:** fixes

- **Checked:** byte and line counts for the 9 flat docs; [design-orch-v3-prompt.md](../design-orch-v3-prompt.md); [decisions.md](../decisions.md) D18.
- **Observed:** The current package already exceeds 250 KB of prose across flat docs, and root navigation depends on human memory rather than a mechanical index.
- **Constraint:** v3 fixes this with hierarchical `design/spec/` and `design/architecture/` trees plus root TOCs that summarize every leaf. See [architecture/design-package/two-tree-shape.md](architecture/design-package/two-tree-shape.md) and [architecture/orchestrator-topology/design-phase.md](architecture/orchestrator-topology/design-phase.md).

### F03: Terrain as one overloaded concept

**Verdict:** fixes

- **Checked:** [terrain-contract.md](terrain-contract.md); [r3-report.md](../reviews/v3-round1/r3-report.md); [decisions.md](../decisions.md) D19 and D20.
- **Observed:** Reviewers explicitly called out that architecture posture, refactor agenda, and feasibility evidence were hard to distinguish when treated as one Terrain surface. Cross-doc drift appeared immediately once multiple docs tried to summarize the same mixed contract.
- **Constraint:** v3 fixes this by splitting Terrain into three named outputs: structure in the architecture tree, rearrangement in `refactors.md`, and evidence/gap-finding in `feasibility.md`. The canonical contract lives in [terrain-contract.md](terrain-contract.md).

### F04: `dev-principles` framed as any binary gate at any altitude

**Verdict:** fixes the gate framing everywhere, preserves and extends universal skill loading

- **Checked:** [r1-report.md](../reviews/v3-round1/r1-report.md); [r5-opus-convergence.md](../reviews/v3-round2/r5-opus-convergence.md); [decisions.md](../decisions.md) D24 (revised); in-session user correction recorded in the same D24 entry.
- **Observed:** The original v2 framing described a hard pass/fail gate at impl-orch altitude. An interim v3 fix moved the gate to design-orch only. The user then overruled the design-orch-gate framing too: no altitude runs a binary gate. Every agent loads `dev-principles` as shared behavioral guidance, and principle violations surface as reviewer findings flowing through the normal loop alongside correctness and alignment findings.
- **Constraint:** v3 loads `dev-principles` for every structural/correctness-shaping agent (@coder, @reviewer, @refactor-reviewer, @planner, @architect, @design-orchestrator, @impl-orchestrator, @dev-orchestrator) and applies it as a shared lens at every altitude. No binary gate anywhere. See `design/architecture/principles/dev-principles-application.md` (A05.1, the R07 anchor) for the per-agent application table, `design/spec/root-invariants.md` §S00.w1 for the universal-loading rule, and `design/spec/design-production/convergence.md` §S02.4.w1 for the design-orch-specific lens application.

### F05: Scenario-ownership tracking as the execution-level truth

**Verdict:** fixes

- **Checked:** [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md); [preservation-hint.md](preservation-hint.md); [decisions.md](../decisions.md) D22, D25, and D26.
- **Observed:** Once spec leaves become the authoritative behavior contract, ownership also has to move from scenario IDs to the specific EARS statements phases satisfy and preserve across redesigns.
- **Constraint:** v3 fixes this by replacing `plan/scenario-ownership.md` with `plan/leaf-ownership.md`, propagating preserved claims through the hint, and re-verifying revised-in-place statements rather than treating preservation as file-level ownership. See [architecture/verification/leaf-ownership-and-tester-flow.md](architecture/verification/leaf-ownership-and-tester-flow.md), [preservation-hint.md](preservation-hint.md), and [architecture/orchestrator-topology/execution-loop.md](architecture/orchestrator-topology/execution-loop.md).

## Assumption validations

### A01: Child processes can reconstruct work-item context from session state

- **Checked:** [src/meridian/lib/launch/env.py](../../../../src/meridian/lib/launch/env.py); [tests/exec/test_permissions.py](../../../../tests/exec/test_permissions.py); commit `2ced688`.
- **Observed:** The current code explicitly normalizes `MERIDIAN_WORK_DIR` from active session state when the variable is absent, and tests lock that behavior in.
- **Constraint:** v3 can safely lean on work-item artifacts under `$MERIDIAN_WORK_DIR`, but any future launch-path edit that touches child env inheritance must be re-probed because this assumption has already failed once.

### A02: The terminated-spawn plan-review model matches Meridian's crash-only posture

- **Checked:** [meridian-cli SKILL.md](../../../../meridian-base/skills/meridian-cli/SKILL.md); [decisions.md](../decisions.md) D15; [architecture/orchestrator-topology/redesign-loop.md](architecture/orchestrator-topology/redesign-loop.md); [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md).
- **Observed:** The design argument is coherent: Meridian treats on-disk state as authoritative, so a suspended impl-orch holding plan state in conversation would violate the crash-only model. This work item did not run an end-to-end spawn/resume smoke probe, but the runtime model and the design choice point in the same direction.
- **Constraint:** Keep D15 as the design contract, and treat implementation as requiring a smoke test before rollout rather than as something already proven here.

### A03: Stable EARS IDs and preserved-phase carry-over are load-bearing runtime assumptions

- **Checked:** [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md); [preservation-hint.md](preservation-hint.md); [decisions.md](../decisions.md) D25 and D26.
- **Observed:** The design now clearly states that IDs remain stable across in-place revisions and that preserved claims copy forward verbatim into the next `plan/leaf-ownership.md`. What is validated here is the design contract, not the implementation machinery that will eventually enforce it.
- **Constraint:** Planner and impl-orch implementation should smoke-test ID stability, carry-over, and tester-only re-verification before downstream agents rely on this contract as if it were already mechanized.

## Open questions

### O01: Exact review-spawn lineage is not fully recoverable from the work tree

- **Checked:** [feasibility-writer-prompt.md](../feasibility-writer-prompt.md); repo-wide grep for `p1535`, `p1536`, `p1537`, `p1538`, and `p1547`.
- **Observed:** The prompt references a `p1535` convergence report and v2 reviewer spawns `p1536/p1537/p1538/p1547`, but those artifacts are not present in the work tree. The accessible evidence set instead points to the v2 synthesis (`p1528`-`p1531`) and the stored v3 review/convergence reports (`p1540`-`p1544`, `p1548`).
- **Constraint:** If downstream consumers need exact spawn-by-spawn traceability, design-orch should either archive the missing reports or update the prompt/reference docs to match the artifacts that actually exist.

### O02: The research anchors are cited in design rationale, not preserved as raw-source bibliography

- **Checked:** [design-orch-v3-prompt.md](../design-orch-v3-prompt.md); [architecture/overview.md](architecture/overview.md); [decisions.md](../decisions.md).
- **Observed:** Fowler, Kiro, Thoughtworks, and Addy Osmani are all named and their conclusions are reflected in the package, but the work item does not preserve raw URLs or excerpt-level citations for those sources.
- **Constraint:** The current evidence base is sufficient for this design artifact, but a future audit or public-facing doc set would be stronger if it added a small bibliography or research appendix instead of forcing later readers to reconstruct the source list from prose.

### O03: Runtime smoke proof still needs to be earned for the new meta-workflow contracts

- **Checked:** [architecture/orchestrator-topology/redesign-loop.md](architecture/orchestrator-topology/redesign-loop.md); [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md); [architecture/orchestrator-topology/execution-loop.md](architecture/orchestrator-topology/execution-loop.md).
- **Observed:** Several important v3 behaviors are designed but not yet runtime-proven in this work item: terminated planning/execution spawn handoff, preserved-leaf carry-over, and tester-only re-verification of revised leaves.
- **Constraint:** Planner and impl-orch should treat these as mandatory smoke-test targets during implementation rather than as assumptions already settled by doc review alone.
