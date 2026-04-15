# S02.1: Spec tree production

## Context

Design-orch authors the spec tree first, directly from `requirements.md`. Every other design artifact — the architecture tree, `refactors.md`, `feasibility.md` — is downstream of this tree. A design whose architecture tree was walked to decide what the system would do and then backfilled into spec leaves has collapsed to spec-kit's constitution-first flow and fails convergence. Spec-first ordering is the load-bearing Kiro rule that keeps the design anchored to user intent rather than to what the codebase currently happens to support (D16, D21).

**Realized by:** `../../architecture/design-package/two-tree-shape.md` (A01.1).

## EARS requirements

### S02.1.u1 — Spec tree is the authoritative behavior contract

`The design-orch authoring flow shall treat design/spec/ as the only authoritative source of behavioral acceptance criteria for the work item.`

### S02.1.u2 — Every leaf file is markdown with ID, summary, context, EARS set, edge cases, cross-links

`Every spec leaf file under design/spec/ shall contain exactly the following sections: leaf ID and title, one-line summary (matching its entry in the parent overview TOC), context, EARS requirements with stable IDs, edge cases enumerated either as additional EARS statements or as explicit non-requirement flags with reasoning, and Realized-by cross-links to architecture leaves.`

### S02.1.e1 — Spec-first ordering

`When design-orch begins the design phase for a work item, design-orch shall author or update design/spec/ before authoring or updating design/architecture/, with the single exception that parallel drafting is permitted only when a spec gap surfaces during architecture work and is immediately closed on the spec side before architecture authoring resumes.`

**Edge cases.**

- **Spec gap discovered mid-architecture.** Design-orch pauses architecture authoring, revises the spec leaf, and only then resumes architecture authoring. The revision is a re-entry into the spec-first step, not a violation of it.
- **Architecture-first authoring is a convergence failure.** A spec tree that was written after the architecture tree (in order to describe what the architecture already encoded) fails convergence via the spec-reviewer's shape check. The failure mode is detectable because architecture-first leaves cite architecture module names in their requirements prose instead of user-observable behavior.

### S02.1.s1 — Overview is a strict TOC, not prose

`While design-orch is authoring a spec tree, every overview.md file in the tree (root and subtree) shall contain only Purpose, TOC, and Reading order sections, and shall not carry substantive authoritative content that would have to drift-track the leaves it points at.`

**Edge case.** A design-orch pass that grows a "Root-level content" section carrying authoritative prose in `design/spec/overview.md` is drifting toward the v2 single-overview shape and must be refactored: move the content into a root-scope leaf under `S00.*` and update the TOC to point at it. This is how the `root-invariants.md` file exists in v3 in the first place — root-level invariants live in a leaf, not in prose.

### S02.1.s2 — Root-level invariants live in reserved-namespace leaves

`While design-orch is authoring a spec tree, root-level ubiquitous requirements that apply across every subsystem shall live in design/spec/root-invariants.md (or a similarly named root-scope leaf) with stable IDs in the reserved S00.* namespace, and shall not live as inline prose in any overview.md.`

**Edge cases.**

- **Reserved namespace enforcement.** No non-root leaf file may claim an ID in the `S00.*` range. The reservation is enforced by the spec reviewer during convergence.
- **Refactor of v2 overview content.** When migrating a v2 design that has inline root-level content in `overview.md`, design-orch moves the content into `root-invariants.md` and replaces the overview section with a TOC entry pointing at the new leaf. This is the mechanical pattern; not an exception.

### S02.1.e2 — Every EARS statement gets a stable ID

`When design-orch writes an EARS statement inside a spec leaf, the statement shall be labeled with an ID in the S<subsystem>.<section>.<letter><number> namespace where the letter encodes the EARS pattern (u=Ubiquitous, s=State-driven, e=Event-driven, w=Where/Optional-feature, c=Complex) and the number is stable across in-place leaf revisions.`

**Edge cases.**

- **Stability across revision.** If a cycle revises an EARS statement in place (same trigger/response concept, refined language), the ID stays. If a cycle introduces a genuinely new requirement alongside an existing one, it gets a new number. Stability lets `plan/leaf-ownership.md` survive redesigns per D26.
- **Pattern-encoded letter.** The letter is not decoration — it carries the parsing-rule selector for the tester. `u`-IDs tell the tester to apply the Ubiquitous row of `../../architecture/verification/ears-parsing.md`; `c`-IDs select the Complex row; etc.

### S02.1.s3 — Hand-wavy acceptance is a convergence blocker

`While design-orch is finalizing a spec leaf, any acceptance criterion that cannot be expressed as one of the five EARS patterns — because the trigger is unknown, the precondition is implicit, or the response is observably vague — shall block convergence until the gap is either closed (EARS statement refined) or the criterion is flagged as a non-requirement with explicit reasoning.`

### S02.1.w1 — Verification notes are optional and must not be load-bearing

`Where a spec leaf carries verification notes (one to three lines describing how a smoke test would exercise the behavior), the notes shall be optional context and shall not be load-bearing for test derivation — a leaf whose tester depends on verification notes to know what to test has an under-specified EARS statement and is a convergence signal per the spec-reviewer rubric.`

### S02.1.c1 — Problem-size scaling degenerates the tree

`While dev-orch has classified the work item as small (per S01.2), when design-orch is producing the spec tree, design-orch shall produce design/spec/overview.md and design/spec/root-invariants.md only (no subtrees) as the full spec artifact set for that cycle.`

**Edge cases.**

- **Degenerate root-only tree is still a tree.** Even the smallest spec tree has both `overview.md` and `root-invariants.md`, and the overview is still a strict TOC. A single-file spec (inline EARS in `overview.md`) is not legal because it violates S02.1.s1.
- **Promotion mid-cycle.** If design-orch determines mid-run that a small-tier spec is under-capturing the work, it terminates with a promotion signal per S01.2.w1 and dev-orch restarts design-orch on the medium or large path.

## Non-requirement edge cases

- **TDD is not part of the spec contract.** The spec tree mandates EARS notation but does not mandate that testers write tests before the coder implements. Kiro and v3 both follow spec-anchored SDD without TDD; spec-kit's test-first flow is rejected. Flagged non-requirement because adding "coder must produce test skeletons before implementation" would undo D21 (no-TDD) and collapse the existing smoke-test discipline.
- **Spec-leaf granularity is not universal.** The specific `S02.<subsystem>.<section>.<letter><number>` depth works at four levels because this work item has four natural levels. Other work items may use two or three levels. The granularity rule is "as deep as the work needs," enforced by the TOC-completeness check at every level, not by a fixed depth. Flagged non-requirement because freezing depth would make scaling-down impossible.
