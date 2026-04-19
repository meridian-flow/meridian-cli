# Context Backend Design Decisions

## DEC-CTX-001: Local Config at Project Root

**Decision**: Add `meridian.local.toml` at project root, not `.meridian/config.local.toml`.

**Reasoning**: 
- `meridian.toml` is at project root, so local override should be adjacent
- Follows the workspace.local.toml pattern but at the right level
- Cleaner than introducing a new `.meridian/config.toml` layer

**Alternatives rejected**:
- `.meridian/config.local.toml`: Would require new config file convention separate from existing `meridian.toml`
- `.meridian/config.toml` as project config: Would break existing repos using `meridian.toml` at root

---

## DEC-CTX-002: Git Sync via Subprocess

**Decision**: Use direct `git` subprocess calls, not a git library.

**Reasoning**:
- No new dependencies required
- Git CLI is universal and well-tested
- Simple operations (pull, add, commit, push) don't need library abstractions
- Easier to debug — users can reproduce commands manually

**Alternatives rejected**:
- GitPython: Adds dependency, abstracts away useful error messages
- dulwich: Pure Python but heavier than needed for simple ops

---

## DEC-CTX-003: Conflict Markers Strategy

**Decision**: On rebase conflict, commit with conflict markers and push.

**Reasoning**:
- No data loss — both sides preserved
- Explicit visibility — markers are obvious grep targets
- Manual resolution required but not blocking
- Same strategy used by many sync tools (Obsidian Sync, Syncthing)

**Alternatives rejected**:
- Abort and retry: Would lose changes
- Automatic resolution via `theirs`/`ours`: Loses data silently
- Block until resolved: Stops work

---

## DEC-CTX-004: Path Substitution Variables

**Decision**: Support `{project}` variable in path specs, expand on first use.

**Reasoning**:
- Enables single global config that works across all repos
- `~/.meridian/context/{project}/work` is natural pattern
- UUID ensures no collisions even for repos with same name

**Alternatives rejected**:
- `{repo_name}`: Collisions when multiple repos have same name
- `{repo_path_hash}`: Harder to navigate than UUID

---

## DEC-CTX-005: Non-Blocking Sync

**Decision**: Git sync failures log warnings but don't block session startup.

**Reasoning**:
- Network issues are common and transient
- Work should continue even when offline
- User can manually sync via `meridian context sync`
- Blocking makes the tool unusable on planes, trains, etc.

**Alternatives rejected**:
- Block until sync succeeds: Too fragile
- Retry loop with backoff: Delays startup, still fails eventually

---

## DEC-CTX-006: Separate Resolver Module

**Decision**: Create `src/meridian/lib/context/` module rather than extend `state/paths.py`.

**Reasoning**:
- Keeps path resolution concerns separate from state storage concerns
- Git sync logic doesn't belong in state module
- Clean import graph — context imports from state, not vice versa
- Easier to test in isolation

**Alternatives rejected**:
- Extend `paths.py`: Would conflate path resolution with git sync
- Inline in config loading: Would duplicate resolution logic
