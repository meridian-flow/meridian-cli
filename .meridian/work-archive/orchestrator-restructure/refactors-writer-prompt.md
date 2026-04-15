# Produce `design/refactors.md` for orchestrator-restructure v3

`design/refactors.md` is a first-class artifact defined by D19 in `$MERIDIAN_WORK_DIR/decisions.md` — the refactor agenda consumed directly by @planner as a decomposition input. Each refactor entry is a named unit of work that moves the codebase (or in this case, the workflow/skill/agent package) from its current shape to the target architecture. Planner sequences these first so feature work downstream can parallelize.

Produce the file at `$MERIDIAN_WORK_DIR/design/refactors.md`.

## Source material

Read before writing:
- `$MERIDIAN_WORK_DIR/decisions.md` — D19 for the artifact's purpose and format, D18 for the two-tree restructure, D22 for scenarios retirement, D24 for dev-principles universalization, plus D16 for the broader SDD shape that drives the refactor agenda.
- `$MERIDIAN_WORK_DIR/design/terrain-contract.md` — especially the 9-field schema for refactor entries. This is the canonical format. Follow it.
- `$MERIDIAN_WORK_DIR/design/terrain-contract.md` §"Boundary cases" — the disambiguation table for refactor-vs-foundational-prep edge cases. Use it when you're unsure whether an entry is a refactor or a foundational prep (and if it's prep, it belongs in feasibility.md §"Foundational prep," not here).
- The existing flat design docs under `$MERIDIAN_WORK_DIR/design/` — enough to understand what moves and where.

## Content: the v2→v3 refactor agenda

These are the concrete refactors the restructure introduces. Each gets an entry following the 9-field schema in terrain-contract.md:

1. **Retire the `scenarios/` convention.** Move every v2 scenario into a spec leaf in `design/spec/` at higher fidelity using EARS notation. Remove references in design-orch body, impl-orch body, feasibility-questions, redesign-brief, and the `dev-artifacts` skill. Migrate `plan/scenario-ownership.md` pattern to `plan/leaf-ownership.md`. Grounds: D22.

2. **Flatten orchestrator design docs into two-tree layout.** Migrate the 9 existing flat design docs (`overview.md`, `design-orchestrator.md`, `impl-orchestrator.md`, `dev-orchestrator.md`, `planner.md`, `feasibility-questions.md`, `terrain-contract.md`, `redesign-brief.md`, `preservation-hint.md`) into `design/spec/` + `design/architecture/` with leaf IDs, root TOC indexes, and cross-links. Grounds: D18. Files touched: every flat design doc.

3. **Split Terrain section into three named artifacts.** The v2 Terrain concept packed architecture target-state, refactor agenda, and gap-finding into one section of `design/overview.md`. v3 splits it into `design/architecture/` (target state), `design/refactors.md` (agenda — this artifact itself), and `design/feasibility.md` (evidence + probes). Grounds: D18, D19, D20.

4. **Universalize `dev-principles` skill loading.** Update agent profiles in `meridian-dev-workflow` to load `dev-principles` on every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns (coders, reviewers, architects, planner, design-orch). Remove "gate" framing from design-orch body and impl-orch body. Grounds: D24 (revised per user correction — see narrow revision spawn p???).

5. **Update `dev-artifacts` skill body.** Replace the `scenarios/` section with the two-tree artifact convention (`design/spec/`, `design/architecture/`, `design/refactors.md`, `design/feasibility.md`). Grounds: D22, D18. This is the "Coordinated skill edit follow-up" already flagged in decisions.md.

6. **Migrate scenario-ownership to leaf-ownership.** Phase blueprints claim spec-leaf IDs instead of scenario IDs; `plan/leaf-ownership.md` replaces `plan/scenario-ownership.md`; `@planner`'s ownership table is regenerated. Grounds: D22 sub-refactor.

Check the design package for any refactor I missed — the list above is a starting point, not exhaustive. If the SDD shape introduces other structural moves (e.g., new cross-link conventions between spec and architecture trees), they earn entries too.

## What's not a refactor here

Foundational prep (new type contracts, new skill bodies from scratch, new base classes) lives in `design/feasibility.md` §"Foundational prep" per terrain-contract.md's boundary disambiguation. If an entry is creating something new rather than rearranging existing material, it belongs there, not here.

Likewise, decisions themselves belong in `decisions.md` with their reasoning; refactors.md records the *work* the decisions imply.

## Quality bar

Every entry uses the 9-field schema from terrain-contract.md. Evidence for the "why" field comes from decisions.md or from concrete probe records (not vibes). The "coupling-removed" field cites concrete coupling signals (shared mutable state, import cycles, fixture sharing, env-var collisions) where applicable.

Entries that can't fill the schema cleanly are probably not well-scoped — either split them into smaller refactors, or check if they're actually foundational prep.

## Format

Markdown. Organize by refactor entry, each as a named subsection. Follow the 9-field schema exactly so planner can parse entries mechanically.

## Return

Terminal report naming:
- The refactor entries written
- Any entries you couldn't fill the schema for (flagged as "check if this is foundational prep or scope-split")
- Any refactors you discovered during the pass that weren't in the starting list above (flag for design-orch to verify they belong)
