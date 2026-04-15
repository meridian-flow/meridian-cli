# Review — v3 SDD Shape (Fowler's Three Levels Test)

You are reviewing the **v3 orchestrator-restructure design package** against spec-driven development as Martin Fowler, Kiro (Amazon), Thoughtworks, and Addy Osmani describe it. Your focus is **SDD shape correctness**: does the package actually realize the SDD model the user is targeting, or does it adopt the vocabulary without the substance?

## Background on the target shape

**Fowler's three levels of SDD.** Fowler describes three altitudes at which specs can anchor a workflow:
- Level 1 — specs as prose, tests are independent, spec drift is common.
- Level 2 — specs as structured requirements, tests derive from specs but are hand-authored.
- Level 3 — specs are the source of truth, tests are mechanically generated or verifiable against the spec, and the spec itself is version-controlled alongside code.

The user is targeting **spec-anchored** — somewhere between level 2 and level 3: EARS-shaped requirements that testers parse mechanically into test structure, without mandating full test generation. Kiro is a concrete example of this altitude.

**Kiro shape.** Kiro (Amazon's agent IDE) uses a requirements → design → tasks flow. Requirements are EARS statements. Design derives from requirements and describes target architecture. Tasks derive from design and carry phase-level execution shape. Kiro explicitly does not mandate TDD — smoke tests are the default verification vehicle. The user wants the v3 package to follow Kiro's altitude, not spec-kit's constitution-first flow.

**Thoughtworks two-tree pattern.** Thoughtworks published a pattern of separating business spec and technical design into two trees: business-oriented readers review spec without being distracted by implementation; technical reviewers review architecture without re-deriving intent. The v3 package adopts this as `design/spec/` + `design/architecture/`.

**Addy Osmani's agent-spec writeup.** Osmani argues that agent workflows collapse without hierarchical spec trees with root-level TOC indexes. Agents need context offloading (read overview, drill into subsystem) and cannot load 10k-token flat overviews efficiently. The v3 package adopts the root-level TOC index pattern.

## What to review

Read the v3 package with these references in mind:

1. `$MERIDIAN_WORK_DIR/design/overview.md`
2. `$MERIDIAN_WORK_DIR/design/design-orchestrator.md` — the producer of the spec tree and architecture tree
3. `$MERIDIAN_WORK_DIR/design/dev-orchestrator.md` — the user-interface layer that walks the design with the user
4. `$MERIDIAN_WORK_DIR/design/planner.md` — the downstream consumer that sequences phases against spec leaves
5. `$MERIDIAN_WORK_DIR/design/impl-orchestrator.md` — the execution layer that verifies against spec leaves
6. `$MERIDIAN_WORK_DIR/design/terrain-contract.md` — the refactors/feasibility contract
7. `$MERIDIAN_WORK_DIR/decisions.md` — especially D16 (SDD adoption), D17 (EARS), D18 (two-tree), D19 (refactors), D20 (feasibility), D21 (smoke tests), D22 (scenarios reversal)

## Questions to answer

1. **Fowler's altitude check.** Is the v3 package actually at the spec-anchored altitude, or is it level-1 prose with EARS as decoration? Test: can a tester take a random spec leaf and mechanically derive a test structure from it without needing additional context? If the answer is "only with extra prose from the design doc," the altitude is level 1 wearing level 2/3 clothes.
2. **Kiro alignment.** Does the flow match Kiro's requirements → design → tasks shape? Flag any inversions: for example, is the design derived from the spec, or does the spec get backfilled after the design? Check that D17's EARS mandate is upstream of D16's SDD adoption (requirements come first).
3. **TDD avoidance check.** D21 says smoke tests are the default and TDD is not mandated. Check that nothing in the package sneakily mandates TDD (e.g. a "write tests first" step in impl-orch, a "test file must precede implementation commit" rule). Kiro's choice to avoid TDD is load-bearing — reintroducing it would misalign the shape.
4. **Spec-kit vs Kiro check.** Spec-kit uses constitution-first flow with heavy upfront governance gates. Kiro uses a lighter spec-as-source-of-truth flow. The user explicitly chose Kiro. Flag any place in the v3 package that drifts toward spec-kit's heavy-governance style (e.g. a constitution doc, a charter review, mandatory cross-cutting review gates that look like spec-kit's three-approval model).
5. **Two-tree pattern fidelity.** Thoughtworks' two-tree pattern requires clean separation of business spec and technical design. Are there places where spec leaves describe implementation details (wrong tree) or architecture docs describe observable behaviors (wrong tree)? Flag cross-contamination.
6. **Context offloading check.** Addy Osmani's pattern requires a root-level TOC index that summarizes every leaf in one line so agents can orient without loading the full tree. Check that both `design/spec/overview.md` and `design/architecture/overview.md` are described as TOC indexes, not as abbreviated versions of the tree. An "overview with a few paragraphs and then TOC" is wrong shape.
7. **D22 scenarios reversal check.** The v2 package had `scenarios/` as the verification contract; v3 retires it and subsumes it into spec leaves. Does the v3 shape actually replace scenarios with spec leaves at higher fidelity, or does it just rename the folder? Test: pick three edge cases from the design and check that each is captured as an EARS leaf with trigger/precondition/response, not as a prose bullet.

## Output shape

Write a short report with:

- **Status**: converged / needs-revision / needs-redesign
- **Altitude diagnosis**: which Fowler level the package actually sits at, with evidence
- **Kiro / spec-kit alignment**: is the package on the Kiro side or drifting toward spec-kit
- **Two-tree fidelity**: concrete cross-contamination findings if any
- **Scenarios reversal depth**: is the reversal real or cosmetic
- **Questions to escalate**: where the design leaves SDD-shape details ambiguous
- **Recommendation**: what design-orch should revise before handing off to planner

Submit the report as your terminal report. Do not edit any design files.
