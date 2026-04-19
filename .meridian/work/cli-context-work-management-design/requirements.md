# CLI Context Query — Requirements

## Summary

Replace env var projection for work context with a query-based model. Agents call `meridian context` to get their work context and derive paths from convention.

## Changes

### 1. Add `meridian context` command

New command that returns the current context tuple:

```bash
meridian context
# Output: work_id, repo_root, state_root, depth
```

Output format:
- Human-friendly text when stdout is TTY and `MERIDIAN_DEPTH == 0`
- JSON when `--json` flag or `MERIDIAN_DEPTH > 0`

JSON output:
```json
{
  "work_id": "auth-middleware",
  "repo_root": "/home/user/project",
  "state_root": "/home/user/project/.meridian",
  "depth": 1
}
```

`work_id` is nullable — returns `null` if no work is attached to the current session.

Resolution: look up `MERIDIAN_CHAT_ID` in session store to get `active_work_id`.

### 2. Add `meridian work current` alias

Convenience command that returns just the work_id:

```bash
meridian work current
# Output: auth-middleware (or empty if no work attached)
```

Same output format detection as `meridian context`.

### 3. Kill env var projection

In `src/meridian/lib/launch/context.py`, stop projecting:
- `MERIDIAN_WORK_ID`
- `MERIDIAN_WORK_DIR`  
- `MERIDIAN_FS_DIR`

Keep projecting:
- `MERIDIAN_CHAT_ID`
- `MERIDIAN_DEPTH`
- `MERIDIAN_REPO_ROOT`
- `MERIDIAN_STATE_ROOT`

Update `_ALLOWED_MERIDIAN_KEYS` to remove the killed vars.

### 4. Update prompts/skills

In the source repos (`meridian-base`, `meridian-dev-workflow`), update guidance from:
```bash
cat $MERIDIAN_WORK_DIR/plan.md
```

To:
```bash
WORK_ID=$(meridian work current)
cat .meridian/work/$WORK_ID/plan.md
```

Key files to update:
- `skills/meridian-cli/SKILL.md` — env var table, add context command
- `skills/meridian-work-coordination/SKILL.md` — query pattern
- `skills/dev-artifacts/SKILL.md` — path conventions
- `skills/context-handoffs/SKILL.md` — examples
- `skills/meridian-spawn/SKILL.md` — examples
- Agent profiles that reference `$MERIDIAN_WORK_DIR`

## Path Conventions

With env vars killed, paths are derived from convention:
- Work dir: `.meridian/work/<work_id>/`
- FS dir: `.meridian/fs/`

These are relative to repo root. Agents can get repo root from `meridian context`.

## Non-Goals

- No changes to spawn parent tracking (already exists via `parent_id`)
- No changes to work attachment mechanism (`chat_id → work_id`)
- No new env vars (`MERIDIAN_SPAWN_ID`, `MERIDIAN_PARENT_ID`, etc.)

## Acceptance Criteria

1. `meridian context` returns correct work_id, repo_root, state_root, depth
2. `meridian work current` returns work_id or empty
3. Spawns no longer receive `MERIDIAN_WORK_DIR`, `MERIDIAN_WORK_ID`, `MERIDIAN_FS_DIR`
4. Existing tests pass (or are updated for new behavior)
5. Prompts/skills updated to use query pattern
