# Phase 2: Skills Updates

## Scope

Update meridian-base skills to teach the query-once + literal-path pattern. Remove derive-from-work_id guidance.

## Target Repo

`/home/jimyao/gitrepos/prompts/meridian-base`

## New Pattern to Teach

```bash
# Query once at session start (or after work switch)
$ meridian work current
/home/user/project/.meridian/work/auth-middleware

# Use literal path everywhere
cat /home/user/project/.meridian/work/auth-middleware/design/overview.md
```

## Files to Update

### 1. skills/meridian-cli/SKILL.md

**Lines ~20, 45, 131:** Update context command documentation

- Remove `work_id` field from example JSON output
- Add `work_dir`, `fs_dir`, `context_roots` fields
- Update description text

**New context output example:**
```json
{
  "work_dir": "/home/user/project/.meridian/work/auth-middleware",
  "fs_dir": "/home/user/project/.meridian/fs",
  "repo_root": "/home/user/project",
  "state_root": "/home/user/project/.meridian",
  "depth": 1,
  "context_roots": ["/home/user/sibling-api"]
}
```

**Also update `work current` documentation to show it returns expanded path.**

### 2. skills/meridian-work-coordination/SKILL.md

**Lines ~20, 52:** Update artifact placement section

- Remove `WORK_ID=$(meridian work current)` pattern
- Replace `.meridian/work/<work_id>/` with direct `$MERIDIAN_WORK_DIR` or literal path
- Show query pattern: `meridian work current` returns expanded path directly

### 3. skills/meridian-spawn/SKILL.md

**Lines ~58, 184:** Update prompt examples and shared-files section

- Replace `.meridian/work/<work_id>/` with `$MERIDIAN_WORK_DIR`
- Show paths are projected or queried, not derived

### 4. skills/agent-creator/SKILL.md

**Lines ~296, 307, 312, 319, 325:** Rewrite output guidance

- Change "derive from work_id" to "use work_dir directly"
- Remove claim that `MERIDIAN_WORK_DIR` / `MERIDIAN_FS_DIR` are not projected
- Update path convention section

### 5. skills/agent-creator/resources/example-profiles.md

**Lines ~117, 159:** Update orchestrator example

- Replace work_id lookup + path derivation with direct work_dir usage
- Show query pattern returns expanded paths

### 6. skills/agent-creator/resources/anti-patterns.md

**Lines ~94, 130, 137, 149:** Rewrite env projection examples

- Remove anti-pattern showing `$(meridian work current)` string interpolation
- Update explanation about what is/isn't projected
- Show correct pattern: query returns literal paths

### 7. skills/meridian-cli/resources/debugging.md

**Lines ~40, 67:** Update shared-files example

- Remove `work current` + derive pattern
- Show direct paths from context query

### 8. agents/meridian-default-orchestrator.md

**Lines ~117, 159:** Update profile

- Replace work_id-based path resolution with direct work_dir usage
- Show literal paths in examples

## Key Messages

1. **Query once, use literal paths:** Call `meridian work current` or `meridian context` once, get expanded paths, use them literally
2. **No string interpolation:** Don't do `.meridian/work/$(meridian work current)/` — just use the path directly
3. **Env vars available:** `$MERIDIAN_WORK_DIR` and `$MERIDIAN_FS_DIR` are projected into spawn environments
4. **Permission-friendly:** Literal paths don't require shell variable expansion

## Exit Criteria

- All files updated with new pattern
- No remaining references to derive-from-work_id pattern
- Examples show literal path usage
