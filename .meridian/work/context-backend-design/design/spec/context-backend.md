# Context Backend Behavioral Specification

## Purpose

Externalize business-sensitive context (`work/`, `work-archive/`) to private locations while keeping code documentation (`fs/`) in-repo.

---

## EARS Statements

### Configuration Resolution

**CTX-CFG-001**: When the system starts, it SHALL resolve context paths using the precedence: `meridian.local.toml` > `meridian.toml` > `~/.meridian/config.toml`.

**CTX-CFG-002**: When `[context.work]` is absent from all config files, the system SHALL default to `local` (`.meridian/work/`).

**CTX-CFG-003**: When `[context.fs]` is absent from all config files, the system SHALL default to `local` (`.meridian/fs/`).

**CTX-CFG-004**: When `context.work.path = "local"`, the system SHALL resolve to `.meridian/work/` within the repo root.

**CTX-CFG-005**: When `context.work.path` starts with `~`, the system SHALL expand it relative to the user's home directory.

**CTX-CFG-006**: When `context.work.path` starts with `/`, the system SHALL treat it as an absolute path.

**CTX-CFG-007**: When `context.work.path` contains `{project}`, the system SHALL substitute the project UUID from `.meridian/id`.

### Environment Variable Export

**CTX-ENV-001**: When a spawn launches with a work item active, the system SHALL set `MERIDIAN_WORK_DIR` to the resolved work path joined with the work item name.

**CTX-ENV-002**: When a spawn launches, the system SHALL set `MERIDIAN_FS_DIR` to the resolved fs path.

**CTX-ENV-003**: When `context.work.path` resolves to a non-existent directory, the system SHALL create it on first use.

### Git Sync Layer

**CTX-GIT-001**: When `context.work.git.auto_pull = true` AND a session starts, the system SHALL execute `git pull --rebase` in the context directory.

**CTX-GIT-002**: When `context.work.git.auto_commit = true` AND a work item is written, the system SHALL execute `git add . && git commit -m "work: <item>"` in the context directory.

**CTX-GIT-003**: When `context.work.git.auto_push = true` AND a commit succeeds, the system SHALL execute `git push` in the context directory.

**CTX-GIT-004**: When `git pull --rebase` results in a conflict, the system SHALL commit the file with conflict markers and push, preserving both sides.

**CTX-GIT-005**: When git sync fails due to network error, the system SHALL log a warning and continue operation without blocking the session.

**CTX-GIT-006**: When a context directory is not a git repository AND git sync is configured, the system SHALL skip sync operations with a warning.

### CLI Surface

**CTX-CLI-001**: When the user runs `meridian context`, the system SHALL display the resolved paths for `work` and `fs` with sync status.

**CTX-CLI-002**: When the user runs `meridian context sync work`, the system SHALL execute pull then push for the work context.

**CTX-CLI-003**: When the user runs `meridian context sync work --pull`, the system SHALL execute only pull for the work context.

**CTX-CLI-004**: When the user runs `meridian context sync work --push`, the system SHALL execute only push for the work context.

**CTX-CLI-005**: When the context is not git-backed AND the user runs `meridian context sync`, the system SHALL report "not a git repository" and exit 1.

### Migration

**CTX-MIG-001**: When a user sets `context.work.path` to a non-local path AND `.meridian/work/` contains data, the system SHALL NOT automatically migrate data.

**CTX-MIG-002**: When the user runs `meridian context migrate work`, the system SHALL move `.meridian/work/` contents to the configured path.

**CTX-MIG-003**: When the configured work path already contains data AND the user runs `meridian context migrate work`, the system SHALL refuse with "destination not empty" and exit 1.

**CTX-MIG-004**: When migration completes successfully, the system SHALL remove the original `.meridian/work/` directory.

### Backward Compatibility

**CTX-COMPAT-001**: When no `[context]` section exists in any config file, the system SHALL behave identically to the pre-feature baseline.

**CTX-COMPAT-002**: When `MERIDIAN_WORK_DIR` is set explicitly in the environment, it SHALL override config-based resolution.

**CTX-COMPAT-003**: When `MERIDIAN_FS_DIR` is set explicitly in the environment, it SHALL override config-based resolution.

---

## Acceptance Criteria

1. Zero config produces current behavior — no regressions
2. Single `~/.meridian/config.toml` line externalizes work for all repos
3. Git sync operations never block on failure
4. Conflict markers are preserved and visible, never silently dropped
5. `meridian context` output is clear about source (config file, env, default)
