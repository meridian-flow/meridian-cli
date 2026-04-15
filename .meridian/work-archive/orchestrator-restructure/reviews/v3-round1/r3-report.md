Spawn: p1542
Status: succeeded (exit 0)
Model: gpt-5.2 (codex)
Duration: 272.4s
Parent: p1533
Desc: v3 r3: structure/refactor discipline (gpt-5.2)
Report: /home/jimyao/gitrepos/meridian-channel/.meridian/spawns/p1542/report.md

Tried to persist this via `meridian spawn report create --stdin`, but it failed because the filesystem is read-only (`Errno 30` writing under `.meridian/spawns/`). Here’s the same report markdown as the fallback.

# v3 Orchestrator-Restructure Design Package — Structural Review (Modularity / Refactor Discipline)

**Status:** needs-revision

## Top 3 structural findings

1) **Decision log entries still describe the v2 shape (Terrain section + structural-prep tags), which conflicts with the v3 artifacts.**
- Where: `.meridian/work/orchestrator-restructure/decisions.md` §“D11: Structure and modularity…” (Decision bullets) and §“D13: Terrain section is extracted…” (Decision text + reasoning).
- Why it matters: `decisions.md` is supposed to be the durable “why”; right now it re-introduces the old topology (Terrain section in `design/overview.md`, `structural-prep-candidate: yes|no`) even though the v3 package explicitly moved to `design/architecture/` + `design/refactors.md` + `design/feasibility.md`. This is the fastest path to future drift because readers will cargo-cult the obsolete fields back into new docs.
- Recommended move: In each “Revised by …” decision, either (a) rewrite the **Decision** subsection to match v3 and move the v2 content under an explicit “Historical (v2, superseded)” heading, or (b) delete the obsolete v2 mechanics from the entry entirely and keep only the intent + the v3 shape.

2) **Cross-doc drift already exists in the design package index: `overview.md` describes terrain-contract details that the v3 contract explicitly retired.**
- Where: `.meridian/work/orchestrator-restructure/design/overview.md` §“Three artifact contracts” (terrain-contract bullet mentions “structural-prep tagging”).
- Why it matters: the overview is the entry-point doc; any incorrect “one-liner summaries” become the most-repeated lies. This is a concrete example of why duplicating contract-level details outside the contract doc is risky.
- Recommended move: Keep overview bullets at “what/why” altitude only (e.g., “terrain-contract defines refactors+feasibility artifact shapes”), and avoid listing retired fields or tags there. Let `design/terrain-contract.md` be the only place that enumerates required fields.

3) **The terrain contract is close to being mechanically enforceable, but it has a few “paper cuts” that weaken the refactor/feasibility handoff.**
- Where: `.meridian/work/orchestrator-restructure/design/terrain-contract.md` §“The two outputs” (naming/structure mismatch), and §“`design/refactors.md` — required shape” (the `must land before` semantics).
- Why it matters:
  - The contract says “two outputs” but then lists three locations (architecture overview + refactors + feasibility). That’s small, but it’s exactly the kind of ambiguity that downstream agents will interpret differently.
  - `must land before` can drift into “phase-number coupling” (examples like P3/P4) even though phases don’t exist at design time. If this field is filled with plan-specific placeholders, it becomes non-auditable.
- Recommended move:
  - Rename to “Outputs and where they live” (or similar) and consistently treat architecture tree as an input+anchor plus two workflow outputs.
  - Define `must land before` as *architecture/spec anchored* (e.g., “before any phase that touches architecture anchor X / realizes spec leaves S…”) rather than plan-phase labels.

## Refactor-contract integrity (vibes resistance)

Overall: **mostly solid, but not fully vibes-proof yet.**

Strengths (good anti-vibes fields):
- `Affected callers` + `Architecture anchor` + `Evidence` make it hard to claim refactors without touching concrete code and a concrete target topology.
- `Preserves behavior` forces an explicit “refactor vs feature” boundary.
- `fix_or_preserve` + required reasoning makes “we improved structure” falsifiable.

Weak spots (where hand-waving can still slip in):
- `Coupling removed` can still be written as prose without proving the coupling. The contract hints at citing symbols/grep; consider requiring at least one concrete coupling witness (import edge, symbol dependency, shared global, fixture, or call chain reference).
- `Must land before` should not depend on phase numbers that don’t exist yet; anchoring it to spec leaves and architecture nodes makes it auditable pre-plan.

## Cross-doc duplication / drift risks

Concrete drift instances:
- `.meridian/work/orchestrator-restructure/design/overview.md` §“Three artifact contracts” vs `.meridian/work/orchestrator-restructure/design/terrain-contract.md` §“`design/refactors.md` — required shape” (overview implies structural-prep tagging; contract explicitly retires tag semantics).
- `.meridian/work/orchestrator-restructure/decisions.md` §D11 Decision bullet (Terrain section in `design/overview.md`) vs `.meridian/work/orchestrator-restructure/design/terrain-contract.md` §“Terrain section … dropped in v3” and the broader v3 two-tree+named-artifacts posture.
- `.meridian/work/orchestrator-restructure/decisions.md` §D13 Decision (structural-prep tag + “keep Terrain section in overview”) vs `.meridian/work/orchestrator-restructure/decisions.md` §D19/D20 (explicitly split into named artifacts and retire the tag).

## Recommendation (what design-orch should revise before handing off to planner)

- Normalize the “Revised by …” decision entries (D11, D13) so the current v3 mechanics are the only “live” instruction text.
- Trim `design/overview.md` to avoid restating contract-level fields; link to `design/terrain-contract.md` for the field list.
- Tighten `design/terrain-contract.md` language:
  - fix “two outputs” wording,
  - define `must land before` in architecture/spec terms,
  - optionally add a small required template for “structural-blocking escalation payload” so when the planner sets `Cause: structural coupling preserved by design` it must include (a) attempted cluster sketch and (b) the missing refactor entry skeleton with evidence anchors. This directly addresses the “planner gave up vs design is non-decomposable” ambiguity.

## Verification

- Read-only inspection of the v3 design package docs; no edits.
- Commands run: `wc -l`, `rg` for headings, `sed`/`nl` for section reads.

## Files read (primary)

- `.meridian/work/orchestrator-restructure/design/overview.md`
- `.meridian/work/orchestrator-restructure/design/design-orchestrator.md`
- `.meridian/work/orchestrator-restructure/design/terrain-contract.md`
- `.meridian/work/orchestrator-restructure/design/planner.md`
- `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md`
- `.meridian/work/orchestrator-restructure/decisions.md`
