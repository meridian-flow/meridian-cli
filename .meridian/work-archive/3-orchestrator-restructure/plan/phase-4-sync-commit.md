# Phase 4: Sync, Verify, Commit

## Dependencies

Phases 1-3 must complete.

## What Changes

### 4a. Push meridian-dev-workflow submodule
- Commit all changes: new skills, new/modified agents, deleted dev-orchestration, updated README
- Push to remote

### 4b. Push meridian-base submodule (if changed)
- Commit __meridian-orchestration update
- Push to remote

### 4c. Sync .agents/ from sources
- `meridian sources update --force`
- This pulls new skills and agents into .agents/

### 4d. Update agents.toml if needed
- New skills (decision-log, dev-artifacts, context-handoffs) may need registration
- New agent (design-orchestrator) may need registration
- Renamed agent (dev-runner → impl-orchestrator) needs old entry removed, new added

### 4e. Verify full system
- `uv run ruff check .` — lint passes
- `uv run pyright` — types pass
- Grep for stale references: "dev-runner", "dev-orchestration" (the skill, not the concept)
- Every agent profile loads only skills that exist
- README is accurate

### 4f. Commit parent repo
- Submodule pointer updates
- .agents/ changes
- Any AGENTS.md updates

## Staffing

This phase is orchestrator-driven (me), not spawned. Mechanical steps with verification.
