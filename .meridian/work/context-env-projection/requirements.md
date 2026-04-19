# Context Query Revision

## Summary

Revise `meridian context` and `meridian work current` to return expanded paths. No env var projection — agents query and use literal paths.

## Design

**One model:** Query returns expanded paths. Agents remember and use literal path strings in commands. No env vars, no shell variable expansion, no worker/orchestrator split.

### `meridian context` output

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

- `work_dir` — expanded path (null if no work attached)
- `fs_dir` — expanded path (always present)
- `context_roots` — from workspace.local.toml (enabled + existing)
- No `work_id` field — paths are pre-expanded

### `meridian work current` output

Returns expanded `work_dir` path:
```
/home/user/project/.meridian/work/auth-middleware
```
Empty if no work attached.

### No env var projection

Do NOT project `MERIDIAN_WORK_DIR`, `MERIDIAN_FS_DIR`, or `MERIDIAN_WORK_ID`. These stay dead.

Keep projecting:
- `MERIDIAN_REPO_ROOT`
- `MERIDIAN_STATE_ROOT`  
- `MERIDIAN_DEPTH`
- `MERIDIAN_CHAT_ID`

### Agent pattern

```bash
# Query once at session start (or after work switch)
$ meridian work current
/home/user/project/.meridian/work/auth-middleware

# Use literal path everywhere
cat /home/user/project/.meridian/work/auth-middleware/design/overview.md
```

Literal paths are permission-friendly (no variable expansion) and don't go stale.

## CLI Consistency

Both `--desc` and `--description` should work on all commands that accept a description. They're aliases for the same parameter.

Commands to update:
- `spawn` — already has `--desc`, add `--description` alias
- `work start` — already has `--description`, add `--desc` alias
- `work update` — check and add both
- Any others with description fields

## Rationale

- Env var projection can't handle work switching (subprocess can't set parent env)
- Two patterns (env vars for workers, query for orchestrators) creates confusion
- Agents can't introspect whether they're workers or orchestrators
- One model is cleaner: query returns paths, agents use literals
