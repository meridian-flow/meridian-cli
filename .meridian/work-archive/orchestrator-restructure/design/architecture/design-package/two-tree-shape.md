# A01.1: Two-tree shape

## Summary

`$MERIDIAN_WORK_DIR/design/` is laid out as a hierarchical two-tree package: a `spec/` subtree carrying behavior contracts as EARS leaves, an `architecture/` subtree carrying structural observations, a sibling `refactors.md` for the refactor agenda, and a sibling `feasibility.md` for probe-based terrain analysis. Root-scope content lives in reserved-namespace leaves (`S00.*` for spec, `A00.*` for architecture), never as inline prose in overview files. Every overview at every level of both trees is a strict TOC with Purpose + TOC + Reading order sections only. The `scenarios/` convention is retired — spec leaves subsume scenario files at EARS-statement granularity.

## Realizes

- `../../spec/design-production/spec-tree.md` — S02.1.u1, S02.1.u2, S02.1.s1, S02.1.s2, S02.1.e1, S02.1.c1 (spec tree production rules).
- `../../spec/design-production/architecture-tree.md` — S02.2.u1, S02.2.u2, S02.2.e1, S02.2.e2, S02.2.s1 (architecture tree production rules).
- `../../spec/root-invariants.md` — S00.u3 (spec leaves as acceptance contract), S00.u4 (scenarios convention retired), S00.u6 (EARS shape mandated with stable IDs).

## Current state

- `$MERIDIAN_WORK_DIR/design/` today is flat: a single `overview.md` carries the design narrative, a `design-orchestrator.md` / `impl-orchestrator.md` / `dev-orchestrator.md` / `planner.md` set of orchestrator-shape docs, and auxiliary flat files (`terrain-contract.md`, `redesign-brief.md`, `preservation-hint.md`, `feasibility-questions.md`).
- `design/overview.md` carries a Terrain section inline as authoritative prose (v2 shape).
- The refactor agenda and feasibility evidence live inside that Terrain section prose rather than as named artifacts.
- `scenarios/` is a parallel convention alongside `design/` with `S001`-style scenario files and a `plan/scenario-ownership.md` counterpart.

## Target state

### Target layout — two-tree package with root TOCs

**Anchor target for R01.** `design/refactors.md` entry R01 (migrate flat design docs into two-tree SDD layout) names this section as its `Architecture anchor`. The R01 migration is done when the on-disk layout matches the layout described here, every referenced spec leaf is cross-linked via `Realized by` from the architecture leaves that realize it, every architecture leaf is cross-linked via `Realizes` back to at least one spec leaf, and the `scenarios/` convention no longer appears in either `$MERIDIAN_WORK_DIR/design/` or `plan/` artifacts.

```
$MERIDIAN_WORK_DIR/
  requirements.md                       # user-facing intent capture, dev-orch authored
  design/
    spec/
      overview.md                       # strict TOC: Purpose + TOC + Reading order
      root-invariants.md                # S00.* reserved namespace — root-level ubiquitous/state-driven/optional-feature invariants as EARS leaves
      <subsystem>/
        overview.md                     # strict TOC for subsystem
        <leaf-name>.md                  # leaf file with EARS statements and stable IDs
        ...
    architecture/
      overview.md                       # strict TOC
      root-topology.md                  # A00.* reserved namespace — root-level topology (DAG slice, integration boundaries, current vs target posture)
      <subsystem>/
        overview.md                     # strict TOC for subsystem
        <leaf-name>.md                  # leaf file with Current state / Target state / Interfaces / Dependencies / Realizes cross-links
        ...
    refactors.md                        # sibling — refactor agenda authored by design-orch, nine-field per-entry shape per A02.1
    feasibility.md                      # sibling — probe records, fix-or-preserve verdicts, assumption validations, open questions per A02.1
  decisions.md                          # decision log, append-only
  plan/
    overview.md                         # Parallelism Posture + rounds + parallelism justifications + refactor-handling table + Mermaid diagram
    phase-N-<slug>.md                   # per-phase blueprints with claimed spec-leaf IDs
    leaf-ownership.md                   # EARS-statement granularity (not leaf-file granularity)
    status.md                           # phase status values seeded by @planner
    pre-planning-notes.md               # impl-orch's runtime observations
    preservation-hint.md                # dev-orch-authored, redesign cycles only
  redesign-brief.md                     # impl-orch-authored, overwritten per cycle
```

- **No `scenarios/` folder.** Every behavioral contract lives in `design/spec/` as an EARS statement with a stable ID. `plan/leaf-ownership.md` claims EARS statement IDs; testers verify EARS statements per A03.2.
- **No Terrain section in any overview.md.** Refactor agenda lives in `design/refactors.md`. Probe evidence, fix-or-preserve verdicts, foundational prep, and parallel-cluster hypotheses live in `design/feasibility.md`. Root-scope topology that used to live in overview prose now lives in `design/architecture/root-topology.md` under the reserved `A00.*` namespace.
- **Overview files carry no authoritative prose.** Every `overview.md` in both trees is a strict TOC (Purpose + TOC + Reading order). Any substantive content in an overview is a drift signal that must be moved into a leaf before convergence.

### Spec-first ordering

Design-orch authors `design/spec/` first, directly from `requirements.md`. `design/architecture/` is authored second, deriving every architecture leaf from at least one spec leaf. `design/refactors.md` and `design/feasibility.md` are authored alongside the architecture tree because they depend on the target architectural shape, but the spec tree commits first. See S02.1.e1 for the load-bearing spec-first rule and its "pause architecture to close a spec gap" exception.

### Cross-link coverage

Every spec leaf must be named in the `Realized by` list of at least one architecture leaf, and every architecture leaf must name at least one spec leaf in its `Realizes` list (S02.2.e2). Orphans on either side are convergence blockers for the alignment reviewer. Root-scope leaves (`S00.*`, `A00.*`) participate in the coverage rule the same as any other leaf.

## Interfaces

- **Spec-leaf ID format** — `S<subsystem>.<section>.<letter><number>` where the letter encodes the EARS pattern (u/s/e/w/c) per S02.1.e2.
- **Architecture-leaf ID format** — `A<subsystem>.<section>.<letter><number>` using the same pattern-letter convention where applicable; architecture leaves that describe observational shapes typically use numeric subsection IDs (A00.1, A00.2, etc.) without EARS pattern letters because they are not EARS statements.
- **Reserved namespaces** — `S00.*` and `A00.*` are exclusive to root-scope leaves (`design/spec/root-invariants.md` and `design/architecture/root-topology.md` respectively). Non-root leaves must not claim IDs in these ranges.

## Dependencies

- `../../spec/design-production/spec-tree.md` — spec tree production rules.
- `../../spec/design-production/architecture-tree.md` — architecture tree production rules.
- `../artifact-contracts/terrain-analysis.md` — refactors.md and feasibility.md per-entry shapes (A02.1).
- `../artifact-contracts/shared-work-artifacts.md` — `plan/` layout and the retired `scenarios/` convention (A02.2).

## Open questions

None at the architecture level. Unresolved convention questions (e.g. whether a specific subsystem should be spec or architecture scoped) are escalated to design-orch during convergence per S02.4.
