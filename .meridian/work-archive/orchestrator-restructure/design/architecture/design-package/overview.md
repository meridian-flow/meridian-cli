# A01: Design Package — Subsystem Overview

## Purpose

This subsystem describes how the design package shape is laid out on disk: the two-tree structure (`design/spec/` + `design/architecture/`), the sibling `design/refactors.md` and `design/feasibility.md` artifacts, the overview-TOC discipline, and the reserved-namespace placement of root-scope content. The subsystem realizes the spec-side design-production rules in S02. This overview is a strict TOC; substantive content lives in leaves.

## TOC

- **A01.1** — Two-tree shape ([two-tree-shape.md](two-tree-shape.md)): the `design/spec/` + `design/architecture/` + `design/refactors.md` + `design/feasibility.md` layout, strict-TOC overview discipline at every level, spec-first ordering, root-scope leaves in `S00.*`/`A00.*` reserved namespaces, and the `scenarios/` convention retirement. Anchor target for refactor entry R01 per `design/refactors.md`.

## Reading order

Read A01.1 directly; this subtree has one leaf because the package shape is a single concept. The corresponding spec content lives in `../../spec/design-production/spec-tree.md` (S02.1) and `../../spec/design-production/architecture-tree.md` (S02.2).
