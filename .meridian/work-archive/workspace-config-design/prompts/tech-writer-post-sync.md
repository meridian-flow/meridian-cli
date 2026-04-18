# Small Tech-Writer Pass — Post Dev-Workflow Sync

Scope: small, fast updates related to the recent sync of `meridian-dev-workflow` from v0.0.25 → v0.0.26.

## What just shipped in the sync

- `@impl-orchestrator` gained a mandatory **Explore** phase before Plan. Verifies design against code reality, produces `plan/pre-planning-notes.md` as a gate artifact with required fields, terminates to a Redesign Brief when the design is falsified before any planning burn.
- `agent-staffing` skill: new "Terminology: Fan-Out vs Parallel Lanes" section (same-prompt-different-models vs different-prompts-different-focus-areas) and new "@reviewer as Architectural Drift Gate" section (CI-spawned reviewer against a declared-invariant prompt enforces structural invariants semantically).

## Tasks (all in meridian-cli repo)

### 1. CHANGELOG.md — add entry for the sync bump

Add an entry to the `[Unreleased]` section in `/home/jimyao/gitrepos/meridian-cli/CHANGELOG.md`. Caveman-full style, terse, following the project's existing CHANGELOG voice. Short — 2-3 bullets max. Mention:

- dev-workflow bumped 0.0.25 → 0.0.26 via `meridian mars sync`
- what downstream readers will notice: `@impl-orchestrator` now has an Explore phase; `agent-staffing` has new fan-out/drift-gate guidance
- AGENTS.md model-routing block removed (delegated to profile defaults + `meridian models list`)

### 2. Sweep for stale references

Quick grep pass across `AGENTS.md`, `CLAUDE.md` (symlink), `README.md`, and `docs/` for references to:
- `gpt-5.2` (no longer in active catalog)
- "fan out" used to mean parallel-lanes (the mixed-up usage we just clarified upstream)
- references to an rg-based CI invariants script (not replaced in meridian-cli but the concept is deprecated upstream)

For each finding, either fix it or report back with file:line — your call on which is cheaper per instance. Don't rewrite; just keep the surface consistent.

### 3. Do NOT touch

- The skill files at `~/gitrepos/prompts/meridian-dev-workflow/` — those are upstream source, not this repo's concern for this pass.
- `.agents/` under meridian-cli — generated output, overwritten by `meridian mars sync`.
- Anything in `.meridian/work/` — work-scoped artifacts, not documentation surface.
- README.md — it has an uncommitted edit by someone else. Leave it alone.

## Termination

Terminal report should list:
- CHANGELOG entry written (path + summary)
- Stale-reference findings (fixed or reported)
- Anything you noticed that's out of scope but worth flagging

Style: caveman full. Keep the tech-docs skill in mind for consistency.
