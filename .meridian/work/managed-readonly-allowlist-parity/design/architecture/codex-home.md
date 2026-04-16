# Architecture — Codex Home Materializer

Detail sub-doc for the codex-side machinery. Implements SC-1 through SC-12.

## Data shape

```python
# harness/codex_home.py

@dataclass(frozen=True)
class CodexHomePlan:
    profile_name: str                 # "meridian" by convention
    sandbox_mode: str                 # "read-only" | "workspace-write" | "danger-full-access"
    approval_policy: str              # "never" | "on-request" | "untrusted" | "on-failure"
    features_disabled: tuple[str, ...]
    disable_default_apps: bool
    default_permissions_name: str | None     # "read_only" when sandbox == read-only
    permissions: dict[str, PermissionRule]   # keyed by permissions-block name
    inherit_auth: bool                # default True; copies/symlinks auth files

@dataclass(frozen=True)
class PermissionRule:
    filesystem: dict[str, str]        # ":project_roots" -> "read"
    network_enabled: bool
```

## Plan derivation

```python
def build_codex_home_plan(
    config: PermissionConfig,
    resolver: PermissionResolver,
) -> CodexHomePlan:
    sandbox = config.sandbox
    approval = _map_approval(config.approval)   # reuses existing map

    features_off: list[str] = []
    if sandbox == "read-only":
        features_off.extend((
            "apps", "connectors", "plugins",
            "memory_tool", "memories", "image_generation",
            "web_search", "js_repl",
        ))

    disable_apps = sandbox == "read-only" or _has_allowlist(resolver)

    permissions: dict[str, PermissionRule] = {}
    default_perms: str | None = None
    if sandbox == "read-only":
        default_perms = "read_only"
        permissions["read_only"] = PermissionRule(
            filesystem={":project_roots": "read"},
            network_enabled=False,
        )

    return CodexHomePlan(
        profile_name="meridian",
        sandbox_mode=sandbox if sandbox != "default" else "workspace-write",
        approval_policy=approval,
        features_disabled=tuple(features_off),
        disable_default_apps=disable_apps,
        default_permissions_name=default_perms,
        permissions=permissions,
        inherit_auth=True,
    )
```

## Rendering

`format_codex_config_toml(plan) -> str` emits TOML in a stable key order so
the generated file is reproducible and diff-friendly. Example for
`sandbox: read-only`:

```toml
# meridian-managed — do not edit by hand
profile = "meridian"
default_permissions = "read_only"

[profiles.meridian]
approval_policy = "never"
sandbox_mode = "read-only"

[features]
apps = false
connectors = false
image_generation = false
js_repl = false
memories = false
memory_tool = false
plugins = false
web_search = false

[apps._default]
enabled = false

[permissions.read_only.filesystem]
":project_roots" = "read"

[permissions.read_only.network]
enabled = false
```

## Materialization

```python
def materialize_codex_home(
    spawn_id: SpawnId,
    plan: CodexHomePlan,
    *,
    user_codex_home: Path = Path.home() / ".codex",
) -> Path:
    codex_home = resolve_spawn_log_dir(spawn_id) / "codex-home"
    codex_home.mkdir(parents=True, exist_ok=True)

    config_text = format_codex_config_toml(plan)
    _atomic_write_text(codex_home / "config.toml", config_text)

    if plan.inherit_auth:
        _narrow_copy(user_codex_home / "auth.json",
                     codex_home / "auth.json")
        _narrow_copy(user_codex_home / ".credentials.json",
                     codex_home / ".credentials.json")

    return codex_home
```

`_narrow_copy` is symlink-by-default (cheaper, honors rotation of auth
tokens) with copy-fallback when the source is on a different filesystem or
when running on Windows where symlinks require privileges. See
`refactors.md` R3 for Windows handling.

## Invocation site

The only caller is the codex connection-start hook. Both the subprocess
path (`launch/process.py`/`launch/streaming_runner.py` for codex exec) and
the streaming path (`connections/codex_ws.py`) call
`materialize_codex_home` exactly once per spawn, before the child
process is launched, after the spawn log directory has been created. The
returned path flows into the env-overrides merge step that already
applies `adapter.env_overrides(config)` values.

## Failure modes

- `PermissionError` on `config.toml` write: propagate as a launch failure
  with `exit_reason = "codex_home_materialization_failed"`.
- Missing `~/.codex/auth.json` when user is not yet logged in: log a
  warning and proceed. Codex will prompt for login on first use.
- Concurrent spawn writing to a different `spawn_id` directory: no race,
  each spawn owns its directory by construction.

## Cleanup policy

The per-spawn `codex-home/` directory lives under
`.meridian/spawns/<spawn_id>/` which is already subject to the spawn
artifact retention policy; no new cleanup is introduced.
