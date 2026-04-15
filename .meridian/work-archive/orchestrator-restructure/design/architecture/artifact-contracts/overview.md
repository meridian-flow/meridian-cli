# A02: Artifact Contracts — Subsystem Overview

## Purpose

This subsystem describes the on-disk shapes of the artifacts design-orch emits and every other agent consumes. The artifacts covered here are `design/refactors.md`, `design/feasibility.md`, `plan/*` layout, `preservation-hint.md`, and `redesign-brief.md`. This overview is a strict TOC; substantive content lives in the leaves.

## TOC

- **A02.1** — Terrain analysis outputs ([terrain-analysis.md](terrain-analysis.md)): per-entry shapes of `design/refactors.md` and `design/feasibility.md`, including the nine-field refactor-entry shape and the feasibility.md section inventory. Contains the R02 anchor target.
- **A02.2** — Shared work artifacts ([shared-work-artifacts.md](shared-work-artifacts.md)): canonical `$MERIDIAN_WORK_DIR/plan/` layout after the `scenarios/` retirement, including `leaf-ownership.md`, `pre-planning-notes.md`, `status.md`, and the root `plan/overview.md`. Contains the R03 anchor target.
- **A02.3** — Preservation hint and redesign brief ([preservation-and-brief.md](preservation-and-brief.md)): on-disk shape of `preservation-hint.md` (dev-orch-authored, overwrite per cycle) and `redesign-brief.md` (impl-orch-authored, overwritten per cycle), including the status vocabulary and the revised-annotation rule.

## Reading order

Read A02.1 first to anchor refactors.md and feasibility.md — every other artifact contract depends on these two sibling files. Then A02.2 for the `plan/` layout each planner and tester consumes. Then A02.3 for the redesign-cycle handoff artifacts. Cross-references in each leaf point back at the spec leaves they realize.
