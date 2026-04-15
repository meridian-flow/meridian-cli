# Phase 4: Skill Conflict Overwrite Policy

## Round

Round 2, after Phase 2.

## Scope and Boundaries

Implement R4 in the simplified copy-only planner. Skill conflicts must overwrite rather than merge, agents must keep the existing merge path, and skill overwrites triggered by conflict must emit a warning through the normal diagnostic path. This phase does not touch checksum discipline or target divergence behavior; those belong to Phase 5.

## Touched Files and Modules

- `/home/jimyao/gitrepos/mars-agents/src/sync/plan.rs`
- `/home/jimyao/gitrepos/mars-agents/src/sync/mod.rs`

## Claimed EARS Statement IDs

- `SKILL-01`
- `SKILL-02`
- `SKILL-03`
- `SKILL-04`

## Touched Refactor IDs

- None.

## Dependencies

- Phase 2, because the planner must already be on the copy-only path after REF-01.

## Tester Lanes

- `@verifier`: confirm `ItemKind::Skill` conflicts map to overwrite and `ItemKind::Agent` conflicts still map to merge.
- `@smoke-tester`: run `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` from `/home/jimyao/gitrepos/mars-agents/`; exercise agent-vs-skill conflict scenarios.
- `@unit-tester`: add or update targeted tests around planner conflict branching and diagnostic emission.

## Edge Cases and Constraints

- Emit the warning via `DiagnosticCollector`, not by inventing a second warning field on `SyncPlan`.
- Keep `LocalModified` behavior unchanged: local-only skill edits still keep local unless `--force` is used.
- Preserve the existing `--force` agent overwrite path while making skill conflicts overwrite even without `--force`.

## Exit Criteria

- Skill conflicts plan `PlannedAction::Overwrite` and warn explicitly about overwritten local directory contents.
- Agent conflicts still plan `PlannedAction::Merge` unless `--force` is set.
- No directory-to-file corruption path remains for skill conflicts.
- `cargo build`, `cargo test`, `cargo clippy`, and `cargo check --target x86_64-pc-windows-msvc` pass from `/home/jimyao/gitrepos/mars-agents/`.
