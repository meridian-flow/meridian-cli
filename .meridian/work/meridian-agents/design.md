# Design: `meridian-agents` Repo + Auto-Sync + Remove Bundled Resources

## Summary

Move all meridian skills and agent profiles out of the Python package into an external `meridian-agents` git repo. On every launch (`meridian` or `meridian spawn`), auto-sync core agents/skills from GitHub before the harness comes online. Remove `importlib.resources` bundling, remove the materialization pipeline. `--append-system-prompt` is the sole skill delivery mechanism.

Core skills/agents are prefixed with `__` to signal system-level (e.g., `__meridian-primary`).

## 1. `meridian-agents` Repo Structure

```
meridian-agents/
  agents/
    __meridian-primary.md
    __meridian-subagent.md
  skills/
    __meridian-orchestrate/
      SKILL.md
    __meridian-spawn-agent/
      SKILL.md
      resources/
        advanced-commands.md
        configuration.md
        creating-agents.md
        debugging.md
  README.md
  LICENSE
```

### Core (prefixed with `__`)
These are required for meridian to function:
- `__meridian-primary` — primary agent profile (orchestrator)
- `__meridian-subagent` — default subagent profile
- `__meridian-orchestrate` — orchestration skill (for primary)
- `__meridian-spawn-agent` — spawn coordination skill (for primary + subagents)

### Optional (no prefix, added later)
Curated extras users can opt into:
- `reviewer` agent, `reviewing` skill
- `documenter` agent, `documenting` skill
- `smoke-tester` agent
- `scratchpad` skill
- `mermaid` skill
- etc.

Users can sync everything or filter: `meridian sync install meridian-agents --skills reviewing,mermaid`

## 2. Well-Known Source + Auto-Sync

### Well-known source shorthand

```python
# In sync bootstrap or config helper
WELL_KNOWN_SOURCES = {
    "meridian-agents": SyncSourceConfig(
        name="meridian-agents",
        repo="haowjy/meridian-agents",
    ),
}
```

`meridian sync install meridian-agents` resolves via this table before treating as a repo path.

### Git-free sync via GitHub API tarball

Not all users have git installed. The sync engine should support a tarball fallback:

1. **Primary path**: `git clone` / `git fetch` (fast, incremental)
2. **Fallback**: `GET https://api.github.com/repos/{owner}/{repo}/tarball/{ref}` — download + extract
3. Tarball path can't do incremental updates, so every `sync update` re-downloads (acceptable for a small repo)
4. Detection: check `shutil.which("git")` at sync time, not startup

```python
def _resolve_source(source: SyncSourceConfig, cache_dir: Path) -> Path:
    """Clone or download source repo. Falls back to tarball if git unavailable."""
    if shutil.which("git"):
        return _git_clone_or_fetch(source, cache_dir)
    return _tarball_download(source, cache_dir)
```

### Auto-sync on launch

Before the harness comes online (both `meridian` primary and `meridian spawn`), ensure core skills/agents are in place:

1. Check if `meridian-agents` source exists in `.meridian/config.toml`
2. If not, auto-install: equivalent to `meridian sync install meridian-agents`
3. If yes, verify core items are on disk (`.agents/skills/__meridian-orchestrate/`, etc.)
4. If missing, run `meridian sync update --source meridian-agents`
5. Best-effort — if sync fails (network issue, etc.), warn and continue with whatever's on disk

For Claude harness, this also ensures `.claude/skills/` symlinks exist (sync engine already handles this).

```python
# In launch path (command.py / execute.py)
def ensure_core_agents(repo_root: Path) -> None:
    """Best-effort sync of core meridian agents before harness launch."""
    config = load_sync_config(repo_root)
    if not _has_source(config, "meridian-agents"):
        _auto_install_meridian_agents(repo_root)
    elif not _core_items_present(repo_root):
        _sync_update(repo_root, source="meridian-agents")
```

### Harness-specific sync targets

| Harness | Skills synced to | Agents synced to |
|---------|-----------------|-----------------|
| Claude  | `.agents/skills/` + symlink `.claude/skills/` | `.agents/agents/` + symlink `.claude/agents/` |
| Codex   | `.agents/skills/` | `.agents/agents/` |
| OpenCode| `.agents/skills/` | `.agents/agents/` |

Sync engine already creates the `.claude/` symlinks. No changes needed.

## 3. Agent Profile Changes

### Rename with `__` prefix

Agent profiles move from hardcoded `_builtin_profiles()` to synced files:

**Before** (Python code):
```python
def _builtin_profiles() -> dict[str, AgentProfile]:
    return {"meridian-agent": AgentProfile(...), "meridian-primary": AgentProfile(...)}
```

**After** (synced `.md` files in `.agents/agents/`):
- `.agents/agents/__meridian-primary.md`
- `.agents/agents/__meridian-subagent.md`

`_builtin_profiles()` becomes a minimal fallback with just enough to launch if sync hasn't happened yet:

```python
def _builtin_profiles() -> dict[str, AgentProfile]:
    """Bare-minimum fallbacks. Full profiles come from meridian-agents sync."""
    subagent = AgentProfile(
        name="__meridian-subagent",
        description="Default subagent",
        model="sonnet",
    )
    return {
        "__meridian-subagent": subagent,
        "meridian-subagent": subagent,   # alias without prefix
        "meridian-agent": subagent,      # legacy alias
        "__meridian-primary": AgentProfile(
            name="__meridian-primary",
            description="Primary agent",
            model="claude-opus-4-6",
        ),
        "meridian-primary": AgentProfile(  # alias without prefix
            name="__meridian-primary",
            description="Primary agent",
            model="claude-opus-4-6",
        ),
    }
```

In `settings.py`:
```python
default_agent: str = "__meridian-subagent"  # was "meridian-agent"
```

### Graceful degradation

If sync hasn't run, the built-in fallback profiles have no skills attached. Meridian launches but the primary session won't have orchestration/spawn instructions. Warning:

```
Core meridian agents not synced. Running with minimal defaults.
  Run 'meridian sync install meridian-agents' or wait for auto-sync on next launch.
```

### `__` prefix convention — don't edit system items

The `__` prefix signals "managed by meridian, will be overwritten on sync." This is communicated via YAML frontmatter in the files themselves — not CLI warnings. The LLM doesn't read frontmatter, so this is purely for humans who open the file:

```yaml
---
name: __meridian-orchestrate
managed: true
warning: >
  This file is managed by meridian sync. Local edits will be overwritten.
  To customize, copy this skill and configure your agent to use it:
    cp -r .agents/skills/__meridian-orchestrate .agents/skills/my-orchestrate
    meridian config set primary.skills my-orchestrate
---
```

Agent profiles get the same treatment:

```yaml
---
name: __meridian-primary
managed: true
warning: >
  This file is managed by meridian sync. Local edits will be overwritten.
  To customize, copy this agent and set it as default:
    cp .agents/agents/__meridian-primary.md .agents/agents/my-primary.md
    meridian config set default-agent my-primary
---
```

This keeps the guidance exactly where users encounter it — in the file itself. No CLI warnings, no README to find. The `meridian config set` commands need to exist (or similar — could be `meridian config` edits to `.meridian/config.toml`).

### Remove materialization gitignore auto-add

`_ensure_materialized_gitignore()` in `materialize.py` auto-appended `__meridian--*` patterns to the repo's `.gitignore`. This dies with materialization deletion — no separate cleanup needed.

The `.meridian/.gitignore` in `paths.py` (protecting internal state files) is unrelated and stays.

## 4. Removing Bundled Resources

### Delete
- `src/meridian/resources/.agents/` (entire directory — agents/ and skills/)

### Keep
- `src/meridian/resources/default-aliases.toml` (model aliases stay bundled)
- `src/meridian/resources/__init__.py`

### Remove `bundled_agents_root()`
- Delete function from `src/meridian/lib/config/settings.py`
- Remove import + bundled fallback from `SkillRegistry.__init__()` in `skill.py`
- Remove import + bundled fallback from `load_agent_profile()` in `agent.py`

The fallback chain becomes: search paths → built-in fallback profiles → raise.

## 5. Removing Materialization

### 5a. Primary launch (`command.py`)
- Remove import of `materialize_for_harness`
- Remove the `materialize_for_harness()` call
- Agent name becomes bare profile name:
  ```python
  agent=profile.name if profile is not None else None,
  ```

### 5b. Spawn execution (`execute.py`)
- Remove imports of `cleanup_materialized, materialize_for_harness`
- Remove `_materialize_session_agent_name()` function
- Remove `_cleanup_session_materialized()` function
- Simplify `_session_execution_context()` — agent name passes through directly

### 5c. Primary launch process (`process.py`)
- Remove import of `cleanup_materialized`
- Remove `_cleanup_launch_materialized()` function
- Remove `_sweep_orphaned_materializations()` function

### 5d. CLI startup (`main.py`)
- Remove materialization cleanup from startup block

### 5e. Diagnostics (`diag.py`)
- Remove `cleanup_materialized` call in `_repair_stale_session_locks()`
- Replace with legacy cleanup (see §8)

### 5f. Delete materialize module
- Delete `src/meridian/lib/harness/materialize.py`
- Delete `tests/harness/test_materialize.py`

### 5g. Sync engine symlinks stay
The sync engine creates `.claude/skills/<name>` → `.agents/skills/<name>` symlinks. These are NOT materialization — they are sync-managed. Leave intact.

## 6. Skill Injection — No Changes Needed

`--append-system-prompt` already works for all paths:

| Harness | Primary | Spawn |
|---------|---------|-------|
| Claude | `--append-system-prompt` | `--append-system-prompt` |
| Codex | inline in prompt | inline in prompt |
| OpenCode | inline in prompt | inline in prompt |

Session resume: `filter_launch_content()` re-injects skills on resume. Skills stay fresh per design.

## 7. Migration Path

### Legacy `__meridian--` files
Add cleanup to `meridian doctor` that removes stale materialized files:

```python
def _cleanup_legacy_materializations(repo_root: Path) -> int:
    removed = 0
    for dir_name in (".claude/agents", ".claude/skills"):
        target = repo_root / dir_name
        if not target.is_dir():
            continue
        for item in target.glob("__meridian--*"):
            if item.is_file():
                item.unlink()
                removed += 1
            elif item.is_dir():
                shutil.rmtree(item)
                removed += 1
    return removed
```

### Backward compat aliases
- `"meridian-agent"` → `__meridian-subagent`
- `"meridian-subagent"` → `__meridian-subagent`
- `"meridian-primary"` → `__meridian-primary`

Keep aliases in `_builtin_profiles()`. Remove in a future release.

### `.gitignore` entries
Old patterns like `.claude/agents/__meridian--*` are harmless (match nothing). No cleanup needed.

## 8. Implementation Sequence

1. **Create `meridian-agents` repo** — copy skills + create agent profile files with `__` prefix
2. **Add well-known sources** — `meridian sync install meridian-agents` shorthand
3. **Add auto-sync on launch** — `ensure_core_agents()` in launch + spawn paths
4. **Update built-in profiles** — rename to `__` prefix, strip skills (fallback-only), update `default_agent`
5. **Remove bundled resources** — delete `.agents/`, remove `bundled_agents_root()` and fallbacks
6. **Remove materialization** — delete `materialize.py`, remove all call sites
7. **Add legacy cleanup** — `__meridian--*` removal in doctor
8. **Tests** — `uv run pytest-llm && uv run pyright`

Steps 1-2 are independent (repo setup). Step 3 is the key new behavior. Steps 4-5 are one commit. Step 6 is its own commit. Steps 7-8 are polish.
