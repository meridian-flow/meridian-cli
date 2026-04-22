# context/ — Context Backend

## What This Is

The context backend controls where meridian reads and writes its two primary data
stores — **work** (work items, active work dir) and **kb** (knowledge base). Each
store can be backed by a local path or a remote git repository. The resolver
translates config into concrete `Path` objects that the rest of the system uses.

## Config Sections

Defined in `src/meridian/lib/config/context_config.py`. The `[context]`
table is loaded from (in precedence order, last wins): user config
(`~/.meridian/config.toml`), project config (`meridian.toml` at repo root),
and local override (`meridian.local.toml` at repo root, gitignored).

```toml
[context.work]
source  = "local"           # "local" | "git"
path    = ".meridian/work"  # relative (from repo root) or absolute; supports {project}
archive = ".meridian/archive/work"  # work-only; no archive for kb

[context.kb]
source = "local"
path   = ".meridian/kb"

# Git-backed example:
[context.work]
source = "git"
remote = "git@github.com:org/meridian-context.git"
path   = "work"   # relative to the auto-cloned repo root
```

### Field semantics

| Field     | Type          | Default                    | Notes |
|-----------|---------------|----------------------------|-------|
| `source`  | `"local"\|"git"` | `"local"`                | Selects backend type |
| `remote`  | `str \| null` | `null`                     | Git remote URL; required when `source = "git"` |
| `path`    | `str`         | store-specific default     | Relative or absolute; supports `{project}` placeholder |
| `archive` | `str`         | `.meridian/archive/work`   | Work only; same substitution rules as `path` |

### Deprecated alias: `repo`

The `repo` field is a deprecated alias for `remote` on both hook config and
context config. Reading `repo` emits a `DeprecationWarning` and copies the value
to `remote`. Use `remote` in all new config.

### Arbitrary contexts

`ContextConfig` accepts extra TOML keys beyond `work` and `kb`. Each extra key
is validated as `ArbitraryContextConfig` (same `source`/`remote`/`path` shape,
no `archive`). Extra contexts are resolved and returned in
`ResolvedContextPaths.extra`.

## Resolver

`src/meridian/lib/context/resolver.py` — `resolve_context_paths(project_root, config, project_uuid?) → ResolvedContextPaths`

### Path resolution rules

1. **`{project}` substitution** — if `project_uuid` is available and `{project}`
   appears in the path spec, it is replaced with the UUID before any other
   resolution. UUID is read from `.meridian/id` if not passed explicitly.

2. **Git-backed path** — when `source = "git"` and `remote` is set:
   - Calls `plugin_api.resolve_clone_path(remote)` to get the local clone root
   - Resolves `path` relative to that clone root (not the project root)
   - Clone is managed by the git-autosync hook or manual `git clone`; the
     resolver itself does **not** clone — it only computes the path

3. **Local absolute path** — returned as-is (after `~` expansion)

4. **Local relative path** — resolved relative to `project_root`

### Output type

```python
@dataclass(frozen=True)
class ResolvedContextPaths:
    work_root:    Path
    work_archive: Path
    work_source:  ContextSourceType   # "local" | "git"
    kb_root:      Path
    kb_source:    ContextSourceType
    extra:        dict[str, tuple[Path, ContextSourceType]]
```

## Context Command

`meridian context` (CLI + MCP) — queries resolved context paths at runtime.

- Handler: `src/meridian/lib/ops/context.py:context_sync`
- Input: `ContextInput(verbose: bool = False)`
- Output: `ContextOutput` — work/kb paths, resolved absolute paths, source types
- `meridian work current` returns the resolved work dir for the active work item

Surface allocation: `context` is CLI + MCP; `work.current` is CLI only (not
in manifest as of this writing — exposed via `meridian work current` subcommand).

## Config Model

```python
# context_config.py
class ContextSourceType(StrEnum):
    LOCAL = "local"
    GIT   = "git"

class WorkContextConfig(BaseModel):   # frozen
    source:  ContextSourceType = LOCAL
    remote:  str | None = None
    path:    str = ".meridian/work"
    archive: str = ".meridian/archive/work"

class KbContextConfig(BaseModel):     # frozen
    source:  ContextSourceType = LOCAL
    remote:  str | None = None
    path:    str = ".meridian/kb"

class ArbitraryContextConfig(BaseModel):  # frozen
    source:  ContextSourceType = LOCAL
    remote:  str | None = None
    path:    str         # required

class ContextConfig(BaseModel):  # frozen, extra="allow"
    work: WorkContextConfig = WorkContextConfig()
    kb:   KbContextConfig   = KbContextConfig()
    # extra keys → ArbitraryContextConfig
```

## Design Rationale

- **`source` field instead of magic path prefix** — explicit source type avoids
  ambiguous path heuristics. A path like `org/repo/work` looks the same
  whether it's relative-local or inside a git clone; `source = "git"` makes
  the intent unambiguous.

- **Resolver does not clone** — cloning is a side-effecting operation that
  belongs to the hook lifecycle (git-autosync), not path resolution. The
  resolver only computes where the clone would be (via `resolve_clone_path`),
  so it is always safe to call without network access.

- **`{project}` placeholder** — enables per-project isolation inside a shared
  remote context repo. Without it, all projects on the same machine would share
  the same work/kb root when using a global git-backed context.

## Related Docs

- `hooks/overview.md` — git-autosync hook that keeps git-backed contexts synced
- `plugin-api/overview.md` — `resolve_clone_path`, `generate_repo_slug` used by resolver
