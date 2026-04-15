# Review brief — v3 step B two-tree instantiation, cross-link integrity lane

You are reviewing the design package at `/home/jimyao/gitrepos/meridian-channel/.meridian/work/orchestrator-restructure/design/`. Step B just finished migrating 9 flat design docs into a two-tree spec + architecture layout. Your job is **cross-link integrity + bi-directional coverage**, not semantic review.

## Context you need

- `decisions.md` D18 (two-tree shape), D19 (refactors.md first-class), D20 (feasibility.md first-class), D27 (leaf-ID convention + reserved namespace + strict-TOC rule).
- `design/spec/` and `design/architecture/` trees in full.
- `design/refactors.md` — R01-R07 refactor entries with `Architecture anchor` fields pointing at specific architecture leaves.
- `design/feasibility.md` — P01-P12 probe records and F01-F05 fix-or-preserve entries with `Checked` / `Constraint` cross-links.
- 5 flat docs were absorbed into the tree and deleted: `overview.md`, `design-orchestrator.md`, `impl-orchestrator.md`, `dev-orchestrator.md`, `planner.md`. Any remaining markdown link to `](overview.md)`, `](design-orchestrator.md)`, `](impl-orchestrator.md)`, `](dev-orchestrator.md)`, or `](planner.md)` from anywhere inside `design/` is a broken link.

## What to check

1. **Every `Realizes` field resolves.** Walk every leaf file in `design/architecture/`. For each line in a leaf's `Realizes` section, verify the spec leaf it names actually exists at the stated path and contains the EARS statement ID cited. Flag every broken reference.
2. **Bi-directional coverage.** Every spec leaf must be realized by at least one architecture leaf. Walk every leaf in `design/spec/` and check that at least one architecture leaf's `Realizes` field names it. Flag any spec leaf with no realizer — that's an uncovered behavioral claim.
3. **R01-R07 anchor resolution.** Open `design/refactors.md`. For each refactor entry R01 through R07, verify the `Architecture anchor` field points at a real file and a real §-named section inside that file. Flag any anchor that resolves to a missing file or missing section.
4. **Broken flat-doc links.** Grep the entire `design/` tree for any markdown link `](overview.md)`, `](design-orchestrator.md)`, `](impl-orchestrator.md)`, `](dev-orchestrator.md)`, `](planner.md)` — and also for absolute-relative variants like `](../overview.md)` or `[text](overview.md)`. Every match is a broken link.
5. **`design/feasibility.md` P01-P12 and F01-F05 cross-links.** Walk every `Checked` and `Constraint` field. Every markdown link must resolve to a real path under `design/`, `../decisions.md`, `../reviews/*`, or an upstream project file. Flag dead links.
6. **Subtree overview TOC entries.** Every `overview.md` in a subtree lists its children in the `TOC` section. Verify every listed child file exists. Flag TOC entries that point at missing files.
7. **Reserved-namespace IDs.** Verify no `S00.*` statement appears outside `design/spec/root-invariants.md` and no `A00.*` appears outside `design/architecture/root-topology.md`. These IDs are reserved for root scope per D27.

## What NOT to check in this lane

- Whether the EARS statements parse correctly (that's the alignment lane).
- Whether `dev-principles` is framed correctly (separate lane).
- Subjective design quality — stay on integrity checks.

## How to report

For each broken link or missing coverage: filename, line number (or grep context), exact broken reference, and which check caught it (Realizes / bi-directional / R0N anchor / flat-doc link / feasibility link / TOC entry / reserved namespace). If integrity is clean on a check, say so explicitly. End with a summary table: `Check | Passed | Findings count`.
