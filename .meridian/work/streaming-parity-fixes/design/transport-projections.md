# Transport Projections

## Purpose

Define how each harness-specific launch spec becomes transport wire data. Projections are shared by subprocess and streaming paths where possible, and guarded so field drift fails at import time.

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
})

_DELEGATED_FIELDS: frozenset[str] = frozenset()

_check_projection_drift(ClaudeLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)
```

`project_claude_spec_to_cli_args(spec, base_command=...)` maintains one canonical order and one `--allowedTools` dedupe pass.

Policy for `--append-system-prompt` collisions: Meridian-managed flag appears in canonical position; user passthrough copy remains later in tail; user wins by last-wins behavior. Projection emits a warning when known managed flags appear in `extra_args`.

## Codex Subprocess Projection (`project_codex_subprocess.py`)

Post-D15, `CodexLaunchSpec` fields are:

- base `ResolvedLaunchSpec` fields
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
    "report_output_path",
})

_DELEGATED_FIELDS: frozenset[str] = frozenset()

_check_projection_drift(CodexLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)
```

Command projection reads permissions through resolver flags and applies reserved-flag filtering to passthrough args before append.

## Codex Streaming Projection (`project_codex_streaming.py`)

This module replaces `codex_appserver.py` + `codex_jsonrpc.py` and exports:

- `project_codex_spec_to_appserver_command(...)`
- `project_codex_spec_to_thread_request(...)`

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

```python
# src/meridian/lib/harness/projections/project_codex_streaming.py
_APP_SERVER_ARG_FIELDS: frozenset[str] = frozenset({
    "permission_resolver",
    "extra_args",
    # consumed for debug-only "ignored by wire" audit behavior
    "report_output_path",
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
from meridian.lib.harness.projections._reserved_flags import (
    _RESERVED_CODEX_ARGS,
    strip_reserved_passthrough,
)

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

    if spec.report_output_path is not None:
        logger.debug(
            "Codex streaming ignores report_output_path; reports extracted from artifacts",
            path=spec.report_output_path,
        )

    filtered_extra = strip_reserved_passthrough(
        args=list(spec.extra_args),
        reserved=_RESERVED_CODEX_ARGS,
        logger=logger,
    )
    if filtered_extra:
        logger.debug("Forwarding passthrough args to codex app-server", extra_args=list(filtered_extra))
        command.extend(filtered_extra)

    return command
```

## OpenCode Subprocess Projection (`project_opencode_subprocess.py`)

Projects CLI args for `opencode run`. `permission_resolver` is consumed via env projection, not CLI flags.

## OpenCode Streaming Projection (`project_opencode_streaming.py`)

Exports both:

- `project_opencode_spec_to_session_payload(...)`
- `project_opencode_spec_to_serve_command(...)`

Passthrough debug logging lives in `project_opencode_spec_to_serve_command` (not session payload).

## Reserved Flags Policy

Projection modules strip reserved passthrough args and emit warning logs per stripped arg.

```python
# src/meridian/lib/harness/projections/_reserved_flags.py
_RESERVED_CLAUDE_ARGS = frozenset({...})
_RESERVED_CODEX_ARGS = frozenset({...})

def strip_reserved_passthrough(
    args: list[str],
    reserved: frozenset[str],
    *,
    logger: logging.Logger,
) -> list[str]: ...
```

- Codex reserved args: `sandbox`, `sandbox_mode`, `approval_policy`, `full-auto`, `ask-for-approval`
- Claude reserved args: `--allowedTools`, `--disallowedTools` (merged/deduped, not overridden)

## Codex Approval Semantics

The matrix requirement is semantic behavior and auditability, not unique wire strings for every cell. Wire values may collapse (`auto`/`yolo`/`confirm` all mapping to `on-request`) while Meridian-side handling and logs distinguish behavior.

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): authoritative spec fields.
- [permission-pipeline.md](permission-pipeline.md): resolver config type and strict policy.
- [typed-harness.md](typed-harness.md): dispatch guard and generic contracts.
