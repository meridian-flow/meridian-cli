# Implementation Plan: Context Query Revision

## Summary

Revise `meridian context` and `meridian work current` to return expanded paths. Teach skills the query-once + literal-path pattern.

## Phases

### Phase 1: CLI Changes (meridian-cli)

**Scope:** Core context query revision + CLI alias consistency

1. **context.py schema change:**
   - `ContextOutput`: Replace `work_id` with `work_dir: str | None`, add `fs_dir: str`, add `context_roots: list[str]`
   - `WorkCurrentOutput`: Replace `work_id` with `work_dir: str | None`
   - Update `context_sync()` to compute expanded paths using `resolve_work_scratch_dir()`, `resolve_fs_dir()`, and `get_projectable_roots()`
   - Update `work_current_sync()` to return expanded `work_dir` path

2. **Metadata updates:**
   - `manifest.py`: Update descriptions for `context` and `work.current` operations
   - `main.py`: Update `context_cmd()` docstring

3. **CLI alias consistency:**
   - `work_cmd.py`: Add `--desc` alias to `--description` in `_work_start()`
   - `spawn.py`: Add `--description` alias to `--desc` in `_spawn_create()`
   - Check `work update` for description field

### Phase 2: Skills Updates (meridian-base)

**Scope:** Update skills to teach query-once + literal-path pattern

Files to update (per skills-changes.md):
- `skills/meridian-cli/SKILL.md` — context command documentation
- `skills/meridian-work-coordination/SKILL.md` — artifact placement guidance
- `skills/meridian-spawn/SKILL.md` — prompt examples, shared-files section
- `skills/agent-creator/SKILL.md` — output guidance
- `skills/agent-creator/resources/example-profiles.md` — orchestrator examples
- `skills/agent-creator/resources/anti-patterns.md` — env projection examples
- `skills/meridian-cli/resources/debugging.md` — shared-files examples
- `agents/meridian-default-orchestrator.md` — profile update

## Staffing

- Phase 1: @coder → @verifier
- Phase 2: @coder → @verifier
- Final: @reviewer for cross-phase consistency

## Dependencies

Phase 2 depends on Phase 1 (CLI defines the contract skills teach).
