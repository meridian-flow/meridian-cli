# S02.3: Refactors and feasibility as sibling artifacts

## Context

`design/refactors.md` and `design/feasibility.md` are first-class design outputs, not subsections of the architecture tree or the overview. They are the canonical locations for the terrain-analysis work (refactor agenda, probe results, parallel-cluster hypothesis, foundational prep, known unknowns) that v2 buried inside a single overview's Terrain section. Promoting them to siblings lets @planner consume them directly via `-f` without walking the architecture tree, and gives the structural reviewer a single auditable surface for "does this design cover every structural problem?" (D19, D20). Design-orch is the sole author; @planner may not invent refactors or foundational prep (S04.2).

**Realized by:** `../../architecture/artifact-contracts/terrain-analysis.md` (A02.1) and `../../architecture/artifact-contracts/shared-work-artifacts.md` (A02.2).

## EARS requirements

### S02.3.u1 — Two first-class sibling artifacts, always produced

`The design-orch authoring flow shall produce design/refactors.md and design/feasibility.md as sibling artifacts alongside design/spec/ and design/architecture/, for every work item that runs the design phase (including the small/light path where one or both may be minimal but must still exist on disk).`

### S02.3.u2 — `refactors.md` is rearrangement, `feasibility.md` is probe evidence

`design/refactors.md shall carry only rearrangement of existing code (renames, moves, interface extractions, decoupling), and design/feasibility.md shall carry probe results plus any foundational prep (net-new scaffolding, types, abstract base classes, interface contracts that don't yet exist).`

**Edge case.** The disambiguation rule is the rearrangement/scaffolding split. Borderline cases (e.g. "extract interface that requires defining new base types") default to `refactors.md` if the existing code already has the concept inlined and `feasibility.md §Foundational prep` if the concept is wholly new.

### S02.3.e1 — Per-entry shape in `refactors.md`

`When design-orch writes an entry in design/refactors.md, the entry shall include the nine required fields from terrain-contract.md §"`design/refactors.md` — required shape": ID, Title, Target, Affected callers, Coupling removed, Must land before, Architecture anchor, Preserves behavior, Evidence.`

### S02.3.e2 — Architecture anchor must resolve to a leaf

`When design-orch writes the Architecture anchor field on a refactors.md entry, the anchor shall resolve to a section inside a specific architecture leaf under design/architecture/, not to prose in any overview.md.`

**Edge case.** If no suitable architecture leaf exists yet, design-orch creates one (with ID in the appropriate subsystem) before writing the refactor entry. The refactor-entry-first anti-pattern (writing refactors.md against a sketchy architecture leaf that has not been committed) is a convergence failure detected by the alignment reviewer.

### S02.3.e3 — Per-section shape in `feasibility.md`

`When design-orch writes design/feasibility.md, the file shall contain the sections named in terrain-contract.md §"`design/feasibility.md` — required shape": Probe records (numbered P01, P02, ...), Fix-or-preserve verdict (F01, F02, ...), Assumption validations (A01, A02, ...), Open questions (O01, O02, ...), plus optional Foundational prep entries and optional Parallel-cluster hypothesis when the work item's scope triggers either.`

### S02.3.s1 — Gap-finding during design, not deferred

`While design-orch is authoring the design package, gap-finding — probing real binaries, extracting real schemas, running smoke probes against external systems — shall land in design/feasibility.md and shall not be deferred to impl-orch's pre-planning step except via explicit "impl-orch must resolve during pre-planning" tags on specific known-unknown entries.`

### S02.3.s2 — Known unknowns carry explicit tags

`While design-orch is authoring design/feasibility.md, every question design-orch identified but could not resolve with probes available during design shall be tagged `impl-orch must resolve during pre-planning` in the Open questions section.`

### S02.3.c1 — Refactors/foundational-prep are design-orch-exclusive

`While a design cycle is active, when @planner discovers that a missing refactor or missing foundational-prep entry blocks decomposition, @planner shall escalate via the probe-request channel or structural-blocking signal per S04.2, and design-orch shall be the sole agent that appends to refactors.md or feasibility.md §Foundational prep.`

### S02.3.w1 — Parallel-cluster hypothesis is conditional

`Where a work item's spec tree contains more than ten spec leaves, design-orch shall populate feasibility.md §Parallel-cluster hypothesis with a first-pass clustering of leaves into parallel-eligible groups before termination of the design cycle.`

**Edge case.** For work items with ten or fewer spec leaves, the cluster hypothesis is optional because the planner can derive it in-context without consuming a probe-request slot (see S04.3 cluster-hypothesis front-loading). The ten-leaf threshold is the boundary where front-loading the analysis becomes cheaper than letting the planner re-derive it.

## Non-requirement edge cases

- **Automated rearrangement detection.** A future tool could scan the repo and propose refactor entries mechanically. Flagged non-requirement because refactors in v3 must be design-justified (anchored to target architecture shapes), not just repo-metric-driven. A tool that suggests entries would need to be paired with design-orch judgment, not replace it.
- **`feasibility.md` as a separate per-probe file per entry.** An alternative shape could be `design/feasibility/P01-codex-flags.md` etc. Rejected because feasibility entries are short and the cross-entry relationships (fix-or-preserve verdicts referencing probe IDs) are easier to maintain in one file. Flagged non-requirement to document the rejection.
