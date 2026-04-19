# Decisions

## 2026-04-17: Kill env var projection, query instead

**Decision:** Remove `MERIDIAN_WORK_DIR`, `MERIDIAN_WORK_ID`, and `MERIDIAN_FS_DIR` env var injection. Replace with `meridian work current` query.

**Reasoning:**
- Env vars projected at spawn time don't help the primary harness (it runs `work switch` but doesn't see the vars)
- Shell statelessness means env vars don't persist between Bash calls anyway
- Current model creates confusion — agents assume vars are set when they aren't
- Explicit query is debuggable and works the same everywhere

**Alternatives rejected:**
- `work switch` outputs exports for `eval` — still relies on shell persistence, conflates mutation with projection
- Shell hooks/functions — fragile across shells, against "fresh shell is normal" principle
- Keep env vars but improve docs — doesn't fix the fundamental problem

## 2026-04-17: `work current` returns only work context

**Decision:** `meridian work current` returns just `work_id` and `work_dir`. No `fs_dir`, `state_root`, or `repo_root`.

**Reasoning:**
- `fs_dir` is always `{state_root}/fs` — static convention, not work-related
- `state_root` and `repo_root` are repo-level, not work-level
- Including them burns tokens for info that never changes
- Clean separation: work command returns work, conventions handle the rest

**Alternatives rejected:**
- Bundle all paths in one response — conflates concerns, wastes tokens
- Separate `meridian context` command for static paths — over-engineering for stable conventions

## 2026-04-17: Keep `MERIDIAN_CHAT_ID` and `MERIDIAN_DEPTH`

**Decision:** Continue injecting `MERIDIAN_CHAT_ID` and `MERIDIAN_DEPTH` as env vars.

**Reasoning:**
- `CHAT_ID` is needed for session identity and work context resolution
- `DEPTH` is needed for spawn nesting detection and nested-agent warnings
- These are internal plumbing, not user-facing context
- They don't suffer from the same confusion as work paths

## 2026-04-17: Output just work_id, derive paths from convention

**Decision:** `meridian work current` returns only `work_id`. Agents derive paths using conventions (`.meridian/work/{work_id}/`).

**Reasoning:**
- Absolute paths waste tokens for derivable info
- Convention is stable: `.meridian/work/{id}/`, `.meridian/fs/`
- Only dynamic value is the work_id itself
- Simpler output, simpler parsing

## 2026-04-17: Human-friendly default, JSON only for agents

**Decision:** Default output is human-readable text. JSON when `--json` flag or `MERIDIAN_DEPTH > 0`.

**Reasoning:**
- Humans at terminal want copy-pasteable output
- Agents in spawns (depth > 0) want parseable JSON
- Explicit `--json` for scripts that need it
- Consistent with "human first, agent detection automatic"
