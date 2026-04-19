# Context Backend Design

## Problem

Work items (`work/`, `work-archive/`) contain business context — strategy, direction, design decisions — that shouldn't be published in public repos. Currently these live in `.meridian/` and get pushed to GitHub.

The codebase mirror (`fs/`) documents the code itself and should stay in-repo.

## Requirements

### Separation of Concerns

- `fs/` stays in-repo at `.meridian/fs/` — versions with code, useful for any contributor
- `work/` and `work-archive/` can be externalized to a private location

### Configuration

Config precedence (highest to lowest):
1. `.meridian/config.local.toml` — personal, gitignored
2. `.meridian/config.toml` — repo default, checked in
3. `~/.meridian/config.toml` — global fallback

Each context type independently configurable:

```toml
[context.work]
path = "~/.meridian/context/meridian-cli/work"

[context.fs]
path = "local"  # means .meridian/fs/ in repo
```

### Defaults

- `fs`: `local` (`.meridian/fs/`)
- `work`: `local` (`.meridian/work/`)
- No config = current behavior, nothing changes

### Git Sync Layer

Optional sync for git-backed context folders:

```toml
[context.work]
path = "~/.meridian/context/meridian-cli/work"

[context.work.git]
auto_pull = true       # pull on session start
auto_commit = true     # commit on work item changes
auto_push = true       # push after commit
pull_strategy = "rebase"
on_conflict = "commit_markers"
```

### Sync Behavior

| Setting | When | Action |
|---------|------|--------|
| `auto_pull` | Session start, `meridian work` | `git pull --rebase` |
| `auto_commit` | Work item written | `git add . && git commit -m "work: <item>"` |
| `auto_push` | After commit | `git push` |

### Conflict Handling

On rebase conflict:
1. File contains `<<<<<<<` conflict markers
2. Commit anyway with markers
3. Push
4. User or AI resolves markers on future pass

No data loss, explicit visibility, manual resolution.

### CLI

```bash
$ meridian context
work: /home/user/.meridian/context/project/work (git: synced 2m ago)
fs:   /home/user/repo/.meridian/fs (local)

$ meridian context sync work        # manual pull + push
$ meridian context sync work --pull # just pull
$ meridian context sync work --push # just push
```

## Success Criteria

1. Zero config = current behavior unchanged
2. Single global config line externalizes work for all repos
3. Git sync is transparent — pull/commit/push happen automatically
4. Conflicts are visible, never silent data loss
5. `meridian context` shows resolved paths clearly
