# Context Backend Technical Architecture

## Overview

The context backend introduces a resolution layer between config and path usage, enabling work items to live outside the repo while fs docs remain in-repo. An optional git sync layer provides automatic push/pull for git-backed context directories.

---

## Config Schema Extension

### TOML Structure

```toml
# meridian.toml, meridian.local.toml, or ~/.meridian/config.toml

[context.work]
path = "~/.meridian/context/{project}/work"  # or "local"

[context.work.git]
auto_pull = true           # pull on session start
auto_commit = true         # commit on work item changes  
auto_push = true           # push after commit
pull_strategy = "rebase"   # "rebase" | "merge"
on_conflict = "commit_markers"  # only supported strategy

[context.fs]
path = "local"  # fs stays in-repo by default
```

### Path Value Semantics

| Value | Resolution |
|-------|------------|
| `"local"` | `.meridian/work/` or `.meridian/fs/` in repo |
| `"~/..."` | Expands `~` to home directory |
| `"/..."` | Absolute path, used as-is |
| `"..."` (relative) | Relative to repo root |
| `"{project}"` | Substituted with project UUID from `.meridian/id` |

### Config Models

```python
# src/meridian/lib/config/context_config.py

class ContextGitConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    auto_pull: bool = False
    auto_commit: bool = False
    auto_push: bool = False
    pull_strategy: Literal["rebase", "merge"] = "rebase"
    on_conflict: Literal["commit_markers"] = "commit_markers"

class ContextPathConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    path: str = "local"
    git: ContextGitConfig | None = None

class ContextConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    work: ContextPathConfig = Field(default_factory=ContextPathConfig)
    fs: ContextPathConfig = Field(default_factory=ContextPathConfig)
```

---

## Resolution Layer

### Path Resolver

```python
# src/meridian/lib/context/resolver.py

@dataclass(frozen=True)
class ResolvedContext:
    work_root: Path      # resolved work directory root
    fs_root: Path        # resolved fs directory root
    work_git: ContextGitConfig | None
    fs_git: ContextGitConfig | None

def resolve_context(
    repo_root: Path,
    config: ContextConfig,
) -> ResolvedContext:
    """Resolve context paths from config + repo root."""
    
    project_uuid = get_project_uuid(repo_root / ".meridian")
    
    work_root = _resolve_path(
        config.work.path,
        repo_root=repo_root,
        project_uuid=project_uuid,
        context_type="work",
    )
    
    fs_root = _resolve_path(
        config.fs.path,
        repo_root=repo_root,
        project_uuid=project_uuid,
        context_type="fs",
    )
    
    return ResolvedContext(
        work_root=work_root,
        fs_root=fs_root,
        work_git=config.work.git,
        fs_git=config.fs.git,
    )

def _resolve_path(
    path_spec: str,
    repo_root: Path,
    project_uuid: str | None,
    context_type: str,
) -> Path:
    """Resolve one context path specification."""
    
    if path_spec == "local":
        return repo_root / ".meridian" / context_type
    
    # Substitute {project}
    if "{project}" in path_spec:
        if project_uuid is None:
            project_uuid = get_or_create_project_uuid(repo_root / ".meridian")
        path_spec = path_spec.replace("{project}", project_uuid)
    
    # Expand ~ and resolve
    expanded = Path(path_spec).expanduser()
    if expanded.is_absolute():
        return expanded
    return repo_root / expanded
```

### Integration Points

The resolver integrates at two points:

1. **`resolve_repo_state_paths()`** — Extended to accept optional `ContextConfig`
2. **`_normalize_meridian_fs_dir()` / `_normalize_meridian_work_dir()`** — Use resolver when config present

---

## Git Sync Layer

### Sync Operations

```python
# src/meridian/lib/context/git_sync.py

@dataclass(frozen=True)
class SyncResult:
    success: bool
    operation: str
    message: str
    conflicts: list[str] = field(default_factory=list)

def sync_pull(context_dir: Path, strategy: str = "rebase") -> SyncResult:
    """Execute git pull on context directory."""
    
    if not (context_dir / ".git").exists():
        return SyncResult(False, "pull", "not a git repository")
    
    try:
        flag = "--rebase" if strategy == "rebase" else "--no-rebase"
        subprocess.run(
            ["git", "pull", flag],
            cwd=context_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return SyncResult(True, "pull", "ok")
    except subprocess.CalledProcessError as e:
        # Check for conflict markers
        conflicts = _find_conflict_files(context_dir)
        if conflicts:
            return SyncResult(False, "pull", "conflicts", conflicts)
        return SyncResult(False, "pull", e.stderr)

def sync_commit(context_dir: Path, message: str) -> SyncResult:
    """Stage all and commit."""
    
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=context_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty-message"],
            cwd=context_dir,
            check=True,
            capture_output=True,
        )
        return SyncResult(True, "commit", "ok")
    except subprocess.CalledProcessError as e:
        if b"nothing to commit" in e.stdout:
            return SyncResult(True, "commit", "nothing to commit")
        return SyncResult(False, "commit", e.stderr.decode())

def sync_push(context_dir: Path) -> SyncResult:
    """Push to remote."""
    
    try:
        subprocess.run(
            ["git", "push"],
            cwd=context_dir,
            check=True,
            capture_output=True,
        )
        return SyncResult(True, "push", "ok")
    except subprocess.CalledProcessError as e:
        return SyncResult(False, "push", e.stderr.decode())
```

### Conflict Handling Flow

```
git pull --rebase
    │
    ├─ success → done
    │
    └─ conflict →
         │
         ├─ git add .
         ├─ git rebase --continue (or abort + merge)
         ├─ commit with markers
         └─ push
              │
              └─ User/AI resolves markers later
```

The conflict-with-markers strategy ensures:
- No data loss — both sides preserved
- Explicit visibility — markers are obvious
- Manual resolution — human or AI fixes on next pass

### Trigger Points

| Event | Sync Action |
|-------|-------------|
| Session start (`meridian` CLI launch) | `auto_pull` → pull |
| Work item write | `auto_commit` → add + commit |
| Post-commit | `auto_push` → push |
| `meridian context sync` | Manual pull + push |

---

## CLI Surface

### Command Structure

```
meridian context                    # show resolved paths + sync status
meridian context sync <target>      # sync work or fs
meridian context sync <target> --pull   # pull only
meridian context sync <target> --push   # push only
meridian context migrate <target>   # move from .meridian/ to configured path
```

### Output Format

```
$ meridian context
context.work:
  path: ~/.meridian/context/abc123/work (from: ~/.meridian/config.toml)
  resolved: /home/user/.meridian/context/abc123/work
  git: synced 2m ago (auto_pull, auto_commit, auto_push)

context.fs:
  path: local (default)
  resolved: /home/user/repo/.meridian/fs
  git: (not configured)
```

### Implementation

```python
# src/meridian/cli/context_cmd.py

@click.group(name="context")
def context_group():
    """Manage context directories (work, fs)."""
    pass

@context_group.command(name="show")
@click.pass_context
def context_show(ctx):
    """Show resolved context paths."""
    ...

@context_group.command(name="sync")
@click.argument("target", type=click.Choice(["work", "fs"]))
@click.option("--pull", is_flag=True)
@click.option("--push", is_flag=True)
def context_sync(target, pull, push):
    """Sync context directory with remote."""
    ...

@context_group.command(name="migrate")
@click.argument("target", type=click.Choice(["work", "fs"]))
@click.option("--force", is_flag=True)
def context_migrate(target, force):
    """Migrate context from .meridian/ to configured path."""
    ...
```

---

## Migration Strategy

### Migration Flow

```
meridian context migrate work
    │
    ├─ Check: is current path "local"?
    │    └─ No → error "already migrated"
    │
    ├─ Check: destination empty?
    │    └─ No → error "destination not empty" (unless --force)
    │
    ├─ Create destination directory
    │
    ├─ Copy .meridian/work/* → destination
    │
    ├─ Verify copy integrity
    │
    └─ Remove .meridian/work/
```

### Safety Guarantees

1. **Atomic-ish**: Copy completes before delete
2. **Integrity check**: Compare file counts/sizes before delete
3. **No force by default**: Destination must be empty
4. **Dry-run mode**: `--dry-run` shows what would happen

---

## File Layout

```
src/meridian/lib/
├── config/
│   ├── context_config.py      # ContextConfig, ContextPathConfig, ContextGitConfig
│   └── settings.py            # Extended to load [context] section
├── context/
│   ├── __init__.py
│   ├── resolver.py            # ResolvedContext, resolve_context()
│   └── git_sync.py            # sync_pull, sync_commit, sync_push
├── state/
│   └── paths.py               # resolve_repo_state_paths() extended
└── ops/
    └── context.py             # context_show, context_sync, context_migrate

src/meridian/cli/
└── context_cmd.py             # CLI commands
```

---

## Environment Variable Resolution Order

When resolving `MERIDIAN_WORK_DIR` for spawns:

```
1. Explicit MERIDIAN_WORK_DIR in environment → use as-is
2. Config-based resolution:
   a. Load context config (local.toml > config.toml > user config.toml)
   b. Resolve path spec → absolute path
   c. Join with work_id if active
3. Fallback: .meridian/work/<work_id>
```

---

## Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| No `[context]` in any config | Current behavior unchanged |
| `MERIDIAN_WORK_DIR` set explicitly | Env var wins over config |
| Config set but directory missing | Created on first use |
| `context.work.path = "local"` | Explicit current behavior |

---

## Error Handling

| Error | Response |
|-------|----------|
| Git not installed | Warning, skip sync, continue |
| Network unreachable | Warning, skip push/pull, continue |
| Conflict markers | Commit with markers, push, log warning |
| Invalid config path | Error on startup, refuse to run |
| Migration destination not empty | Error, suggest --force |
