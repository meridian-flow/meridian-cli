# plugin-api/ — Plugin API v1

## What This Is

`src/meridian/plugin_api/` is the stable, versioned interface for hooks and
plugins. It is the **only** surface that builtin hooks and external plugins may
import. Internal builtins (`lib/hooks/builtin/`) are validated against this
constraint — they must not import from `meridian.lib.*`.

Version: `1.0.0` (exposed as `meridian.plugin_api.__version__`).

## Module Location

```
src/meridian/plugin_api/
  __init__.py   Re-exports all public symbols; version declaration
  types.py      Hook, HookContext, HookResult, HookEventName, HookOutcome, FailurePolicy
  state.py      get_project_home, get_user_home
  git.py        generate_repo_slug, normalize_repo_url, resolve_clone_path
  config.py     get_user_config, get_git_overrides
  fs.py         file_lock
```

## Public Exports

### Types (`meridian.plugin_api.types`)

```python
HookEventName = Literal[
    "spawn.created", "spawn.running", "spawn.start",
    "spawn.finalized", "work.start", "work.started", "work.done",
]
HookOutcome    = Literal["success", "failure", "timeout", "skipped"]
FailurePolicy  = Literal["fail", "warn", "ignore"]

@dataclass(frozen=True)
class Hook:
    """Plugin-facing hook configuration."""
    name:            str
    event:           HookEventName
    source:          str              # config source layer: "user" | "project" | "local" | …
    builtin:         str | None
    command:         str | None
    enabled:         bool
    priority:        int
    require_serial:  bool
    exclude:         tuple[str, ...]
    options:         Mapping[str, object]
    failure_policy:  FailurePolicy | None
    remote:          str | None       # git remote URL (primary)
    repo:            str | None       # deprecated alias for remote

@dataclass(frozen=True)
class HookContext:
    """Structured event context delivered to each hook execution."""
    event_name:          HookEventName
    event_id:            UUID
    timestamp:           str           # ISO 8601
    project_root:        str
    runtime_root:        str
    schema_version:      int = 1
    spawn_id:            str | None
    spawn_status:        SpawnStatus | None
    spawn_agent:         str | None
    spawn_model:         str | None
    spawn_duration_secs: float | None
    spawn_cost_usd:      float | None
    spawn_error:         str | None
    work_id:             str | None
    work_dir:            str | None

    def to_env(self) -> dict[str, str]:  # → MERIDIAN_* env vars for command hooks
    def to_json(self) -> str             # → JSON for stdin transport

@dataclass
class HookResult:
    """Result of one hook execution."""
    hook_name:   str
    event:       HookEventName
    outcome:     HookOutcome
    success:     bool
    skipped:     bool = False
    skip_reason: str | None
    error:       str | None
    exit_code:   int | None
    duration_ms: int
    stdout:      str | None
    stderr:      str | None
```

### State helpers (`meridian.plugin_api.state`)

```python
get_user_home() -> Path
    # Returns ~/.meridian/ (or $MERIDIAN_HOME/)
    # Resolution: MERIDIAN_HOME env var → platform default

get_project_home(project_uuid: str) -> Path
    # Returns per-project state root path under user state root
```

### Git helpers (`meridian.plugin_api.git`)

```python
generate_repo_slug(repo_url: str) -> str
    # Produces filesystem-safe slug from a remote URL.
    # SSH: git@github.com:org/repo.git  → "github.com-org-repo"
    # HTTPS: https://github.com/org/repo → "github.com-org-repo"
    # Fallback: replace non-alphanumeric chars with '-', truncate to 100

normalize_repo_url(url: str) -> str
    # Strips trailing slash and .git suffix for comparison.
    # "git@github.com:org/repo.git" == "git@github.com:org/repo"

resolve_clone_path(repo_url: str) -> Path
    # Returns absolute local clone path for a remote URL.
    # Priority:
    #   1. [git."<url>"].path override from user config
    #   2. <meridian_home>/git/<generate_repo_slug(repo_url)>
    # Does NOT clone — only resolves where the clone would live.
```

### Config helpers (`meridian.plugin_api.config`)

```python
get_user_config() -> dict[str, Any]
    # Loads <meridian_home>/config.toml as a dict.
    # Returns {} if file is missing.
    # Raises tomllib.TOMLDecodeError on invalid TOML.

get_git_overrides() -> dict[str, dict[str, str]]
    # Returns the [git."<url>"] tables from user config.
    # Used by resolve_clone_path() for path overrides.
    # Returns {} if [git] section is absent.
```

### File locking (`meridian.plugin_api.fs`)

```python
@contextmanager
file_lock(
    path: Path | str,
    *,
    timeout: float = 60.0,
    mode: Literal["exclusive", "shared"] = "exclusive",
) -> Generator[None, None, None]:
    # Cross-platform file lock with timeout (fcntl on Unix, msvcrt on Windows).
    # Creates parent directory if absent.
    # Writes PID to lock file in exclusive mode (useful for debugging contention).
    # Raises TimeoutError if lock not acquired within timeout seconds.
    # Spins at 100ms intervals.
```

## Usage Pattern

```python
from meridian.plugin_api import (
    Hook, HookContext, HookResult, HookOutcome,
    file_lock,
    get_user_home,
    resolve_clone_path,
    normalize_repo_url,
    generate_repo_slug,
    get_user_config,
    get_git_overrides,
)
```

Never import from `meridian.lib.*` in hooks or plugins. The plugin API is the
isolation boundary.

## Design Rationale

- **Stable API contract** — plugins written against v1 should not break as
  internal implementation evolves. The `__version__` field enables future
  version-gated behavior.

- **Builtins as validators** — the git-autosync builtin (`lib/hooks/builtin/git_autosync.py`)
  imports only from `meridian.plugin_api`. This makes it both a real feature and
  a continuous integration test for the API surface. If a builtin needs something
  that isn't in the API, it means the API is incomplete.

- **`resolve_clone_path` is in the API, not the context resolver** — both the
  context resolver and the git-autosync hook need the same clone-path logic.
  Placing it in the plugin API means neither subsystem reimplements it, and
  external plugins get the same behavior for free.

- **`get_git_overrides`** — exposes user config's `[git."<url>"].path` tables
  so plugins can respect user-configured clone location overrides without
  parsing config themselves.

## Related Docs

- `hooks/overview.md` — hook system and git-autosync that consumes this API
- `context/overview.md` — context resolver that calls `resolve_clone_path`
