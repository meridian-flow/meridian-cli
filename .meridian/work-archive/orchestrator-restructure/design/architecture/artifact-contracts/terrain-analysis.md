# A02.1: Terrain analysis outputs

## Summary

Terrain analysis is produced by design-orch as three named outputs, two of which are first-class sibling files in the design package: `design/refactors.md` (rearrangement agenda) and `design/feasibility.md` (probe evidence, verdicts, assumption validations, open questions, optional foundational prep, optional parallel-cluster hypothesis). The third output is the architecture tree itself (structural posture), which already has its own subtree (A01). This leaf defines the per-entry shapes of the two sibling files so that @planner, @reviewer, and impl-orch can consume them without reading any other doc.

## Realizes

- `../../spec/design-production/refactors-and-feasibility.md` — S02.3.u1 (two sibling artifacts always produced), S02.3.u2 (rearrangement-vs-scaffolding split), S02.3.e1 (nine-field refactor entry), S02.3.e2 (architecture-anchor must resolve to leaf), S02.3.e3 (per-section feasibility shape), S02.3.s1 (gap-finding during design), S02.3.s2 (known-unknown tagging), S02.3.c1 (design-orch exclusive authorship), S02.3.w1 (parallel-cluster hypothesis threshold).
- `../../spec/design-production/architecture-tree.md` — S02.2.u2 (architecture is observational, refactors+feasibility carry phase-ordering signal).

## Current state

- v2 terrain content lives inside a single `design/overview.md` Terrain section as inline narrative. Refactors, probe evidence, foundational prep, and parallel-cluster hypothesis are all mixed into one section, and consumers have to section-search the overview to find each one.
- `design/terrain-contract.md` in the v2 flat package documents the intended shape of `design/refactors.md` and `design/feasibility.md` as descriptive prose, but the files themselves do not exist on disk — consumers read the contract describing the artifact instead of the artifact itself (the R02 symptom).

## Target state

**Anchor target for R02.** `design/refactors.md` entry R02 (materialize the Terrain split as real sibling artifacts) names this section as its `Architecture anchor`. The R02 migration is done when `design/refactors.md` and `design/feasibility.md` both exist on disk with the shapes described below, the Terrain section is removed from every `overview.md` in both trees, and `terrain-contract.md` either survives as a cross-link stub pointing into this leaf or is absorbed outright per the R01 cleanup.

### Three-output terrain workflow

Terrain analysis has three named outputs, authored by design-orch during the design cycle:

| Output | Location | Role |
|---|---|---|
| **Structural posture** | `design/architecture/` tree | Observational target state: what the code should look like, subsystem by subsystem. Realized as architecture leaves with `Current state` / `Target state` sections. |
| **Refactor agenda** | `design/refactors.md` | Rearrangement of existing code to reach the target architecture. One numbered entry per refactor, nine required fields. |
| **Feasibility evidence** | `design/feasibility.md` | Probe results, fix-or-preserve verdicts, assumption validations, open questions, optional Foundational prep, optional Parallel-cluster hypothesis. |

The three outputs are related but distinct: the architecture tree says *what the target should be*, `refactors.md` says *what rearrangement gets existing code there*, and `feasibility.md` says *what evidence and scaffolding that rearrangement depends on*. Conflating them (as v2 did in a single Terrain section) creates the coupling that R02 unwinds.

### `design/refactors.md` — nine-field per-entry shape

Each entry is a titled subsection (`## R01: <title>`) with the following nine required fields, authored in this order:

1. **ID** — `R01`, `R02`, ... Assigned sequentially as design-orch identifies rearrangement candidates. IDs are stable once written (renumbering is forbidden) because refactor agendas in this repo get cross-referenced from decisions.md, architecture anchors, and plan blueprints.
2. **Title** — a short active-voice description of the rearrangement (`Split auth/handler.py into parser and persistence`). No trailing punctuation.
3. **Target** — exact files, modules, or symbols being restructured. Show the before→after shape where it fits in one line (`auth/handler.py → auth/parser.py + auth/persistence.py`).
4. **Affected callers** — every downstream module, caller, or test file that touches the restructured surface and may need updating during or after the refactor. Explicit file paths, not "the API layer".
5. **Coupling removed** — the concrete coupling this refactor eliminates, with witness evidence (grep result, measured hit count, file size, responsibility count). "Removes coupling" without a witness is a convergence blocker for the structural reviewer.
6. **Must land before** — the spec leaves (by ID) or other refactor entries that depend on this refactor having landed first. This is the phase-ordering signal @planner reads.
7. **Architecture anchor** — a link into `design/architecture/` naming the specific leaf (never an overview.md) whose `Target state` section describes the posture this refactor realizes. If the leaf does not yet exist, design-orch creates it before writing the refactor entry (S02.3.e2 edge case).
8. **Preserves behavior** — `yes` (pure rearrangement, no observable behavior change), `no` (observable behavior changes — spec leaves also change), or `yes after feature X lands, no before` for temporal cases (refactors that delete a legacy path after a feature replaces it).
9. **Evidence** — the files, decisions, reviews, or probe results that justify the entry. Same discipline as feasibility.md probe records: named references, not hand-wavy claims.

**Conditional fields:** `Depends on feature` is required when a refactor depends on a spec leaf landing first (e.g. deleting a legacy path after its replacement is built). Omit when not applicable.

**Forbidden in refactors.md:** feature work (additive spec-leaf work belongs in plan blueprints), foundational prep (net-new scaffolding belongs in `feasibility.md §Foundational prep`), probe records (belong in `feasibility.md §Probe records`), and parallel-cluster hypothesis (belongs in `feasibility.md §Parallel-cluster hypothesis`).

### `design/feasibility.md` — per-section shape

Each feasibility.md file contains the following sections, in this order. Some sections are conditional; all that appear must follow the per-entry template below the section header.

1. **Probe records** — numbered `P01`, `P02`, ... Each record has five fields: `Why asked` (the assumption probed), `How probed` (the concrete command, script, test, or document inspection), `Result` (what the probe returned), `Backs constraint` (the spec leaves, architecture sections, or refactor entries that depend on this probe's outcome), `Stale-if` (the conditions under which the probe result is no longer reliable).
2. **Fix-or-preserve verdict** — numbered `F01`, `F02`, ... Each verdict has `Verdict` (`fixes` / `preserves` / `fixes <X>, preserves <Y>`), `Checked` (the evidence surfaces the verdict draws from), `Observed` (what the evidence showed), `Constraint` (the design constraint or decision the verdict backs).
3. **Assumption validations** — numbered `A01`, `A02`, ... Each has `Checked`, `Observed`, `Constraint`, same shape as fix-or-preserve verdicts but for design-time assumptions that are validated rather than fix-or-preserve classified.
4. **Open questions** — numbered `O01`, `O02`, ... Each has `Checked`, `Observed`, `Constraint`. Questions that design-orch could not resolve within the design cycle must be tagged `impl-orch must resolve during pre-planning` per S02.3.s2.
5. **Foundational prep** *(conditional — present only if the work item has net-new scaffolding, types, abstract base classes, or interface contracts that do not yet exist)* — numbered entries. Each has a short description, the refactor or spec leaves it unblocks, and the "greenfield" marker (no current file).
6. **Parallel-cluster hypothesis** *(conditional — mandatory when the spec tree contains more than ten spec leaves per S02.3.w1, optional otherwise)* — one subsection per cluster. Each cluster names the architecture subtree it lives under, the specific modules or files it touches, and the spec leaves it unblocks. "Frontend cluster" is not concrete; "architecture/ui/auth/ + components/SignIn.tsx + tests/components/auth/" is.

**Gap-finding during design, not deferred.** Design-orch must run feasibility probes during the design cycle, not punt them to impl-orch's pre-planning step. The only exception is a specifically tagged `impl-orch must resolve during pre-planning` open question, which must cite a reason design-orch could not resolve it at design time (e.g. requires a dev-machine version check design-orch cannot perform remotely).

**Design-orch-exclusive authorship.** @planner cannot append to either file. If @planner discovers that a missing refactor or missing foundational-prep entry blocks decomposition, @planner escalates via the probe-request channel or structural-blocking signal per S04.2, and design-orch appends to the file as part of the next design-revision cycle.

## Interfaces

- **`-f $MERIDIAN_WORK_DIR/design/refactors.md`** — attached by @planner during `plan-and-review` loop (S04.2.e1), by the structural reviewer during design convergence, and by impl-orch's pre-planning step.
- **`-f $MERIDIAN_WORK_DIR/design/feasibility.md`** — attached by @planner, structural reviewer, and impl-orch pre-planning. Also attached by the tester during spec-leaf verification when a leaf's acceptance contract cites a probe record.
- **Cross-link back into `design/architecture/`** — every `Architecture anchor` field on a refactor entry is a working link into a specific architecture leaf.

## Dependencies

- `../design-package/two-tree-shape.md` — the two-tree layout that hosts these siblings.
- `../../spec/design-production/refactors-and-feasibility.md` — the spec-side contract these shapes realize.
- `../../terrain-contract.md` *(flat doc, absorbed under R01)* — v2 source of the nine-field shape description; this leaf is the v3 replacement.

## Open questions

None at the architecture level.
