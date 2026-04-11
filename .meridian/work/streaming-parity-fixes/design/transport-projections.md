# Transport Projections

## Purpose

Define how each harness-specific launch spec becomes transport wire data. Projections are shared by subprocess and streaming paths where possible, and guarded so field drift fails at import time.

Revision round 3 changes:

- All reserved-flag stripping and the `_reserved_flags.py` module are deleted (D1). `extra_args` is forwarded verbatim to every transport.
- `mcp_tools` is projected into harness-specific wire format (D4).
- Projection modules are imported eagerly by `harness/__init__.py` so drift guards always execute (C2).
- `project_codex_streaming.py` carries an explicit line-budget marker (C3).

## Projection Modules

```text
src/meridian/lib/harness/projections/
  _guards.py
  project_claude.py
  project_codex_subprocess.py
  project_codex_streaming.py
  project_opencode_subprocess.py
  project_opencode_streaming.py
```

Naming invariant: one module per `(harness, transport)` conceptual thing.

`harness/projections/_reserved_flags.py` no longer exists. Any remaining `from ... _reserved_flags import ...` lines must be deleted during migration. S037 ("reserved-flag stripping") is retired and replaced by S045 ("extra_args forwarded verbatim to every transport").

## Eager Import Bootstrapping (C2)

`src/meridian/lib/harness/__init__.py` imports every projection module eagerly:

```python
# src/meridian/lib/harness/__init__.py
from meridian.lib.harness.projections import (
    project_claude,
    project_codex_subprocess,
    project_codex_streaming,
    project_opencode_subprocess,
    project_opencode_streaming,
)
```

This is load-bearing: the drift guard in each projection module runs at module import time, so it only protects against drift if the module is actually imported. Dispatch lookups happen on demand, so without eager imports a buggy projection could linger undetected until the first spawn for that harness/transport. Eager import makes the drift check a package-load-time failure instead.

## Guard Helper

All projection modules call a shared helper:

```python
# src/meridian/lib/harness/projections/_guards.py
def _check_projection_drift(
    spec_cls: type[BaseModel],
    projected: frozenset[str],
    delegated: frozenset[str],
) -> None:
    expected = set(spec_cls.model_fields)
    accounted = projected | delegated
    if expected != accounted:
        missing = expected - accounted
        stale = accounted - expected
        raise ImportError(
            f"{spec_cls.__name__} projection drift. "
            f"missing={sorted(missing)} stale={sorted(stale)}"
        )
```

Each module executes `_check_projection_drift(...)` at import time.

Unit tests exercise `_check_projection_drift` directly with synthetic spec classes for:

- happy path
- missing field
- stale field

No monkey-patching `model_fields` is required.

## Claude Projection (`project_claude.py`)

```python
_PROJECTED_FIELDS: frozenset[str] = frozenset({
    "model",
    "effort",
    "agent_name",
    "appended_system_prompt",
    "agents_payload",
    "continue_session_id",
    "continue_fork",
    "permission_resolver",
    "extra_args",
    "prompt",
    "interactive",
    "mcp_tools",
})

_DELEGATED_FIELDS: frozenset[str] = frozenset()

_check_projection_drift(ClaudeLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)
```

`project_claude_spec_to_cli_args(spec, base_command=...)` rules:

- Maintains one canonical order for Meridian-managed flags, then appends `spec.extra_args` verbatim at the tail.
- Reads `spec.permission_resolver.config` for sandbox/approval/allowed-tools intent and emits the corresponding Claude flags in canonical position.
- Does **not** inspect `extra_args` for "reserved" flags. If the user passes `--allowedTools C,D` through `extra_args`, both the resolver-derived `--allowedTools A,B` and the user's `--allowedTools C,D` appear in the command. Claude's own flag-handling decides the effective behavior. Meridian logs a debug note when it detects a known managed flag also present in `extra_args`, to help the user understand why both are in the command line, but it does not merge or strip.
- Resolver-internal `--allowedTools` dedupe still runs inside the resolver layer, because the resolver may merge multiple internal sources (parent-Claude forwarding + explicit user tools + profile defaults) and must not emit the same flag twice from its own output. This is internal consistency, not a policy on user passthrough.
- `--append-system-prompt` collision policy: Meridian-managed flag appears in canonical position; user passthrough copy remains later in the tail; user wins by last-wins behavior. Projection emits a debug log noting the collision so users understand both flags appear.

### MCP Projection

```python
def _project_mcp_tools_claude(mcp_tools: tuple[str, ...]) -> list[str]:
    """Map mcp_tools to --mcp-config arguments.

    For v2, mcp_tools entries are treated as paths or identifiers to an
    mcp-config JSON file. Claude accepts one --mcp-config flag per entry.
    Auto-packaging through mars is out of scope.
    """
    return [arg for tool in mcp_tools for arg in ("--mcp-config", tool)]
```

## Codex Subprocess Projection (`project_codex_subprocess.py`)

Post-D15, `CodexLaunchSpec` fields are:

- base `ResolvedLaunchSpec` fields (including `mcp_tools`)
- `report_output_path`

No `sandbox_mode` or `approval_mode` field exists on the spec.

```python
_PROJECTED_FIELDS: frozenset[str] = frozenset({
    "model",
    "effort",
    "prompt",
    "continue_session_id",
    "continue_fork",
    "permission_resolver",
    "extra_args",
    "interactive",
    "mcp_tools",
    "report_output_path",
})

_DELEGATED_FIELDS: frozenset[str] = frozenset()

_check_projection_drift(CodexLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)
```

Command projection reads permissions through `spec.permission_resolver.config` and appends `spec.extra_args` verbatim at the tail. No filtering.

### MCP Projection

```python
def _project_mcp_tools_codex(mcp_tools: tuple[str, ...]) -> list[str]:
    """Map mcp_tools to Codex `-c mcp.servers.<name>.command=<value>` args.

    mcp_tools entries for Codex are name=command pairs (validated at
    SpawnParams construction). This projection expands them into the
    repeated `-c` TOML override form that codex understands.
    """
    out: list[str] = []
    for entry in mcp_tools:
        name, _, command = entry.partition("=")
        if not name or not command:
            # Malformed entries are a developer error, not a user error,
            # because SpawnParams validates the shape. Surface loudly.
            raise ValueError(f"Invalid mcp_tools entry: {entry!r}")
        out.extend(("-c", f'mcp.servers.{name}.command="{command}"'))
    return out
```

## Codex Streaming Projection (`project_codex_streaming.py`)

This module replaces `codex_appserver.py` + `codex_jsonrpc.py` and exports:

- `project_codex_spec_to_appserver_command(...)`
- `project_codex_spec_to_thread_request(...)`

### Line Budget (C3)

`project_codex_streaming.py` is on a soft line budget of **400 lines**. If it exceeds the budget, split into three modules so the drift guard and shared field constants stay in one place:

- `project_codex_streaming_fields.py` — shared `_APP_SERVER_ARG_FIELDS`, `_JSONRPC_PARAM_FIELDS`, `_METHOD_SELECTION_FIELDS`, `_PROMPT_SENDER_FIELDS`, `_ENV_FIELDS`, `_MCP_FIELDS`, `_ACCOUNTED_FIELDS` frozensets + the `_check_projection_drift(CodexLaunchSpec, ...)` call at import time.
- `project_codex_streaming_appserver.py` — command assembly (`project_codex_spec_to_appserver_command(...)`). Imports field constants from `_fields`.
- `project_codex_streaming_rpc.py` — thread request / payload builders (`project_codex_spec_to_thread_request(...)`, `_select_thread_method(...)`, `_build_user_input_payload(...)`). Imports field constants from `_fields`.

`project_codex_streaming.py` becomes a thin re-export facade so existing imports keep working:

```python
# src/meridian/lib/harness/projections/project_codex_streaming.py
from meridian.lib.harness.projections.project_codex_streaming_appserver import (
    project_codex_spec_to_appserver_command,
)
from meridian.lib.harness.projections.project_codex_streaming_rpc import (
    project_codex_spec_to_thread_request,
)
# fields module is imported for side-effect drift check at package load
from meridian.lib.harness.projections import project_codex_streaming_fields  # noqa: F401
```

`harness/__init__.py` imports `project_codex_streaming_fields` alongside the other projection modules so the drift guard still runs at package load (C2). Document the split in `decisions.md` as a round-3 follow-up when triggered.

### Field Accounting Pattern (transport-wide)

Transport-wide completeness is enforced by the union of all consumers in the streaming path, not only one projection function.

Codex streaming was merged to one module (`project_codex_streaming.py`), so accounted sets are per-consumer-function constants defined next to each consumer and aggregated once.

| Accounted set | Consumer | Source module |
|---|---|---|
| `_APP_SERVER_ARG_FIELDS` | `project_codex_spec_to_appserver_command(...)` | `harness/projections/project_codex_streaming.py` |
| `_JSONRPC_PARAM_FIELDS` | `project_codex_spec_to_thread_request(...)` | `harness/projections/project_codex_streaming.py` |
| `_METHOD_SELECTION_FIELDS` | `_select_thread_method(...)` | `harness/projections/project_codex_streaming.py` |
| `_PROMPT_SENDER_FIELDS` | `_build_user_input_payload(...)` | `harness/projections/project_codex_streaming.py` |
| `_ENV_FIELDS` | `build_codex_stream_env(...)` | `harness/projections/project_codex_streaming.py` |
| `_MCP_FIELDS` | `_project_mcp_tools_codex(...)` reused from subprocess | `harness/projections/project_codex_streaming.py` |

```python
# src/meridian/lib/harness/projections/project_codex_streaming.py
_APP_SERVER_ARG_FIELDS: frozenset[str] = frozenset({
    "permission_resolver",
    "extra_args",
    # consumed for debug-only "ignored by wire" audit behavior
    "report_output_path",
    # MCP tools are attached via -c overrides on the app-server command
    "mcp_tools",
})

_JSONRPC_PARAM_FIELDS: frozenset[str] = frozenset({
    "model",
    "effort",
})

_METHOD_SELECTION_FIELDS: frozenset[str] = frozenset({
    "continue_session_id",
    "continue_fork",
})

_PROMPT_SENDER_FIELDS: frozenset[str] = frozenset({
    "prompt",
})

_ENV_FIELDS: frozenset[str] = frozenset({
    # interactive mode is consumed by build_codex_stream_env(...)
    # to shape long-lived app-server environment behavior.
    "interactive",
})

_ACCOUNTED_FIELDS = (
    _APP_SERVER_ARG_FIELDS
    | _JSONRPC_PARAM_FIELDS
    | _METHOD_SELECTION_FIELDS
    | _PROMPT_SENDER_FIELDS
    | _ENV_FIELDS
)

_check_projection_drift(
    CodexLaunchSpec,
    projected=_ACCOUNTED_FIELDS,
    delegated=frozenset(),
)
```

### App-Server Command Example

```python
def project_codex_spec_to_appserver_command(
    spec: CodexLaunchSpec,
    *,
    host: str,
    port: int,
) -> list[str]:
    command = ["codex", "app-server", "--listen", f"ws://{host}:{port}"]

    sandbox = spec.permission_resolver.config.sandbox
    if sandbox and sandbox != "default":
        command.extend(("-c", f'sandbox_mode="{sandbox}"'))

    approval = spec.permission_resolver.config.approval
    policy = _map_approval_to_codex_policy(approval)
    if policy is not None:
        command.extend(("-c", f'approval_policy="{policy}"'))

    command.extend(_project_mcp_tools_codex(spec.mcp_tools))

    if spec.report_output_path is not None:
        logger.debug(
            "Codex streaming ignores report_output_path; reports extracted from artifacts",
            path=spec.report_output_path,
        )

    if spec.extra_args:
        logger.debug(
            "Forwarding passthrough args to codex app-server verbatim",
            extra_args=list(spec.extra_args),
        )
        command.extend(spec.extra_args)

    return command
```

Note: `spec.extra_args` is appended without any filtering. If the user passes `-c sandbox_mode=yolo` through `extra_args`, both the resolver-derived `-c sandbox_mode="read-only"` and the user's `-c sandbox_mode=yolo` are on the command line. Codex's own argument handling decides which wins. Meridian does not make that judgment call. This is the supported escape hatch for users who need to override meridian's permission projection temporarily.

### Debug Log on Streaming (S033)

`project_codex_spec_to_appserver_command(...)` emits one debug log line with the verbatim `extra_args` list (when non-empty). The `project_opencode_spec_to_serve_command(...)` path emits the equivalent.

## OpenCode Subprocess Projection (`project_opencode_subprocess.py`)

Projects CLI args for `opencode run`. `permission_resolver` is consumed via env projection, not CLI flags. `extra_args` is appended verbatim.

```python
_PROJECTED_FIELDS: frozenset[str] = frozenset({
    "model",
    "effort",
    "prompt",
    "continue_session_id",
    "continue_fork",
    "permission_resolver",
    "extra_args",
    "interactive",
    "mcp_tools",
    "agent_name",
    "skills",
})
```

### `mcp_tools` behavior on OpenCode subprocess (S047)

OpenCode's subprocess CLI (`opencode run`) has no wire encoding for `mcp_tools` — MCP configuration is only carried by the HTTP streaming transport's session payload (see `_project_mcp_tools_opencode` below). The field is still **claimed** by the subprocess projection via `_PROJECTED_FIELDS` (so K9 accounting passes), but the projection function pins the behavior:

- If `spec.mcp_tools` is empty: the projection is a no-op for that field (current behavior).
- If `spec.mcp_tools` is non-empty: the projection raises `ValueError` with a clear message directing the user to the streaming transport. Meridian does **not** silently drop the field — silent drop would violate the K9 "claim it or fail" contract and would surprise users who expect their MCP config to reach the harness.

```python
def _project_mcp_tools_opencode_subprocess(mcp_tools: tuple[str, ...]) -> None:
    if mcp_tools:
        raise ValueError(
            "OpenCode subprocess transport does not carry mcp_tools. "
            "Switch to the streaming transport (HTTP session payload) "
            "to use MCP configuration with OpenCode."
        )
```

Streaming carries the full mcp session payload via `_project_mcp_tools_opencode` → `{"servers": [...]}` under the session payload `mcp` field. The split between subprocess (reject) and streaming (carry) is documented in S047 and referenced from the OpenCode projection docstring.

## OpenCode Streaming Projection (`project_opencode_streaming.py`)

Exports both:

- `project_opencode_spec_to_session_payload(...)` — includes `mcp` field in HTTP session payload when `spec.mcp_tools` is non-empty
- `project_opencode_spec_to_serve_command(...)` — appends `spec.extra_args` verbatim and emits the passthrough debug log

### MCP Session Payload Field

```python
def _project_mcp_tools_opencode(mcp_tools: tuple[str, ...]) -> dict[str, object] | None:
    """Map mcp_tools to OpenCode's HTTP session payload `mcp` field.

    Returns None when mcp_tools is empty so the payload omits the key
    entirely. Entries follow the OpenCode session-payload schema.
    """
    if not mcp_tools:
        return None
    return {"servers": list(mcp_tools)}
```

## Verbatim Passthrough Policy (replaces reserved-flags policy)

**Rule.** Every projection appends `spec.extra_args` verbatim at the tail of its command line (or inserts into its payload in the single agreed position). No projection inspects the contents of `extra_args` and decides to strip, merge, or rewrite.

**Rationale.** `extra_args` is an escape hatch for the user to pass through arbitrary harness-specific flags. Meridian is not the security boundary for these flags — the harness is. A user could invoke the harness directly with the same arguments. Silently stripping something the user typed would be surprising and would provide a false sense of security. If a user wants to override meridian's permission intent by passing `-c sandbox_mode=yolo`, that is between them and Codex.

**Debug logging** is still emitted when `extra_args` is non-empty, so the audit trail makes it obvious what passthrough arguments reached the harness.

**Known-managed-flag collision warning** (Claude only) is a debug log, not a strip: when `project_claude_spec_to_cli_args` detects a known meridian-managed flag (e.g., `--append-system-prompt`) in `extra_args`, it emits a debug log noting that the flag appears in both positions and that last-wins semantics apply. This is user-friendly, not policy.

## Codex Approval Semantics

The matrix requirement is semantic behavior and auditability, not unique wire strings for every cell. Wire values may collapse (`auto`/`yolo`/`confirm` all mapping to `on-request`) while Meridian-side handling and logs distinguish behavior.

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): authoritative spec fields (including restored `mcp_tools`).
- [permission-pipeline.md](permission-pipeline.md): resolver config type, immutable config, strict REST policy.
- [typed-harness.md](typed-harness.md): dispatch guard, generic contracts, bundle registration.
