# Review brief — v3 step B two-tree instantiation, design-alignment lane

You are reviewing the design package at `/home/jimyao/gitrepos/meridian-channel/.meridian/work/orchestrator-restructure/design/`. Step B of the orchestrator-restructure work item just finished materializing the two-tree SDD layout dogfood. Your job is **design-alignment + two-tree fit**.

## Context you need

- `decisions.md` at the work-item root — especially D16-D27. D17 is the EARS notation mandate, D18 is the two-tree + sibling shape, D22 retires `scenarios/`, D24 (revised) is the `dev-principles` shared-context framing, D25 is the per-pattern EARS parsing rule, D26 is preserved-leaf re-verification, D27 (new this cycle) is the leaf-ID convention + strict-TOC rule + reserved S00/A00 namespace.
- `design/spec/` — 6 subsystems of behavioral spec leaves in EARS format. Root-scope invariants at `design/spec/root-invariants.md` under `S00.*`.
- `design/architecture/` — 5 subsystems of structural leaves. Root-scope topology at `design/architecture/root-topology.md` under `A00.*`.
- `design/refactors.md` and `design/feasibility.md` — first-class sibling artifacts. R01-R07 are refactor anchor targets pointing at specific architecture leaves.
- Surviving flat docs: `terrain-contract.md`, `feasibility-questions.md`, `redesign-brief.md`, `preservation-hint.md` (legacy artifact contracts kept as-is with cross-link updates).
- `requirements.md` if it exists at the work-item root, otherwise `dev-orch-v3-prompt.md` and `design-orch-v3-prompt.md` carry the user intent.

## What to check

1. **Two-tree fit.** Is every spec leaf an EARS statement (or set of EARS statements) with a per-pattern parse signature that matches its letter-encoded ID (u/s/e/w/c)? Does every architecture leaf's `Realizes` field name at least one spec leaf? Is every spec leaf actually realized by at least one architecture leaf? D18 + D25 + D27.
2. **Strict-TOC rule.** Does every `overview.md` at any altitude in either tree carry only `Purpose` + `TOC` + `Reading order` with no substantive prose? D27.
3. **Reserved namespace.** Are all root-scope invariants in `spec/root-invariants.md` under `S00.*` and all root-scope topology in `architecture/root-topology.md` under `A00.*`, never inline in overviews? D27.
4. **Design alignment.** Does the package still satisfy the user's v3 intent (spec-driven, two orchestrators split design vs impl, autonomous redesign loop, EARS notation, parallelism-first planning, preservation across redesigns, structural review as first-class)? Any requirement not covered by a spec leaf? Any constraint weakened?
5. **Package cohesion.** Do the 6 surviving flat docs still make sense alongside the two-tree structure, or do any of them now duplicate or contradict tree content?
6. **Small-work path.** Does the design explicitly handle the case where a small work item shouldn't materialize the full package? D23.

## What NOT to check in this lane

- Cross-link integrity at the URL level (that's a separate lane).
- `dev-principles` framing specifically (separate lane).
- Deep structural health of the package shape itself (separate refactor-reviewer lane).

## How to report

Produce a findings list. For each finding: location (file + section/line), what is wrong, what the design intent says it should be, severity (`blocker` / `should-fix` / `nice-to-have`), and a suggested fix. If the package converges on your lane, say so explicitly and name the two or three strongest pieces of evidence you used to decide.
