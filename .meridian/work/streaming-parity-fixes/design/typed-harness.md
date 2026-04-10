# Typed Harness Contract

## Purpose

Bind each adapter and connection to a concrete launch-spec subtype so harness dispatch cannot silently downcast into generic behavior. Runtime and static enforcement are both explicit.

## Module: `launch/launch_types.py`

```python
# src/meridian/lib/launch/launch_types.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Protocol, TypeVar
from pydantic import BaseModel, ConfigDict, model_validator

SpecT = TypeVar("SpecT", bound="ResolvedLaunchSpec")

class PermissionResolver(Protocol):
    @property
    def config(self) -> PermissionConfig: ...
    def resolve_flags(self, harness: HarnessId) -> tuple[str, ...]: ...


class ResolvedLaunchSpec(BaseModel):
    """Transport-neutral resolved configuration for one harness launch."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # Identity
    model: str | None = None

    # Execution parameters
    effort: str | None = None
    prompt: str = ""

    # Session continuity
    continue_session_id: str | None = None
    continue_fork: bool = False

    # Permissions
    permission_resolver: PermissionResolver

    # Passthrough args
    extra_args: tuple[str, ...] = ()

    # Interactive mode
    interactive: bool = False

    @model_validator(mode="after")
    def _validate_continue_fork_requires_session(self) -> "ResolvedLaunchSpec":
        if self.continue_fork and not self.continue_session_id:
            raise ValueError("continue_fork=True requires continue_session_id")
        return self


@dataclass(frozen=True)
class PreflightResult:
    expanded_passthrough_args: tuple[str, ...]
    extra_env: dict[str, str] = field(default_factory=dict)
```

`adapter.py` and `launch_spec.py` both import from this leaf module to avoid cycles.

## Bundle Registry

```python
# src/meridian/lib/harness/bundle.py
from dataclasses import dataclass
from typing import Generic
from meridian.lib.launch.launch_types import SpecT, ResolvedLaunchSpec
from meridian.lib.harness.adapter import HarnessAdapter
from meridian.lib.harness.connections.base import HarnessConnection

@dataclass(frozen=True)
class HarnessBundle(Generic[SpecT]):
    harness_id: str
    adapter: HarnessAdapter[SpecT]
    spec_cls: type[SpecT]
    connection_cls: type[HarnessConnection[SpecT]]

_REGISTRY: dict[str, HarnessBundle] = {}  # populated by harness modules at import time

def get_harness_bundle(harness_id: str) -> HarnessBundle:
    try:
        return _REGISTRY[harness_id]
    except KeyError:
        raise KeyError(f"unknown harness: {harness_id}") from None
```

## Adapter Contract

Two mechanisms are used and they have different roles:

- `@runtime_checkable Protocol` (`HarnessAdapter[SpecT]`) for structural type checking in pyright.
- `abc.ABC` abstract methods (`BaseSubprocessHarness(Generic[SpecT], ABC)`) for runtime instantiation rejection.

Protocol conformance does not raise `TypeError` at instantiation. ABC abstract-method enforcement does.

```python
# src/meridian/lib/harness/adapter.py
@runtime_checkable
class HarnessAdapter(Protocol, Generic[SpecT]):
    @property
    def id(self) -> HarnessId: ...

    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT: ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult: ...


class BaseSubprocessHarness(Generic[SpecT], ABC):
    @abstractmethod
    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT:
        ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult:
        return PreflightResult(expanded_passthrough_args=passthrough_args)
```

`ClaudeAdapter.preflight(...)` performs Claude-specific parent-permission and `--add-dir` expansion. `CodexAdapter` and `OpenCodeAdapter` use the base default.

## Connection Contract

Use one interface: `HarnessConnection[SpecT]` ABC. Facet protocols (`HarnessLifecycle`, `HarnessSender`, `HarnessReceiver`) are removed in v2 to avoid duplicate method surfaces drifting.

```python
class HarnessConnection(Generic[SpecT], ABC):
    @abstractmethod
    async def start(self, config: ConnectionConfig, spec: SpecT) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send_user_message(self, text: str) -> None: ...

    @abstractmethod
    async def send_interrupt(self) -> None: ...

    @abstractmethod
    async def send_cancel(self) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[HarnessEvent]: ...
```

## Dispatch Boundary (authoritative site)

The single cast boundary is in `SpawnManager.start_spawn` dispatch, not in `prepare_launch_context`.

```python
from typing import cast

async def dispatch_start(
    bundle: HarnessBundle[SpecT],
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> HarnessConnection[SpecT]:
    if not isinstance(spec, bundle.spec_cls):
        raise TypeError(
            f"HarnessBundle invariant violated: adapter for "
            f"{bundle.harness_id} returned {type(spec).__name__}, "
            f"expected {bundle.spec_cls.__name__}"
        )
    connection = bundle.connection_cls()
    await connection.start(config, cast(SpecT, spec))
    return connection
```

This runtime guard is the S002 runtime trigger. It is the only allowed boundary-type guard.

Inside concrete `Connection.start(...)` methods, behavior-switching `isinstance` branches are disallowed.

## Import Topology

```
launch/launch_types.py
    ↑
    ├── harness/adapter.py
    ├── harness/launch_spec.py
    └── harness/bundle.py
         ↑
         └── launch/context.py

launch/constants.py
    ↑
    ├── launch/context.py
    ├── harness/claude_preflight.py
    └── harness/projections/project_codex_streaming.py

launch/text_utils.py
    ↑
    ├── harness/claude_preflight.py
    └── harness/projections/project_claude.py

harness/projections/_guards.py
    ↑
    ├── harness/projections/project_claude.py
    ├── harness/projections/project_codex_subprocess.py
    ├── harness/projections/project_codex_streaming.py
    ├── harness/projections/project_opencode_subprocess.py
    └── harness/projections/project_opencode_streaming.py

harness/projections/_reserved_flags.py
    ↑
    ├── harness/projections/project_claude.py
    └── harness/projections/project_codex_streaming.py

harness/adapter.py
    ↑
    ├── harness/claude.py (uses harness/claude_preflight.py)
    ├── harness/codex.py
    └── harness/opencode.py

harness/launch_spec.py
    ↑
    ├── harness/projections/project_claude.py
    ├── harness/projections/project_codex_subprocess.py
    ├── harness/projections/project_codex_streaming.py
    ├── harness/projections/project_opencode_subprocess.py
    └── harness/projections/project_opencode_streaming.py

harness/connections/base.py
    ↑
    ├── harness/connections/subprocess.py
    ├── harness/connections/claude_streaming.py
    ├── harness/connections/codex_streaming.py
    └── harness/connections/opencode_streaming.py

harness/errors.py
    ↑
    ├── runner.py
    └── streaming_runner.py

launch/context.py
    ↑
    ├── runner.py
    └── streaming_runner.py
```

This is the acyclic dependency DAG used by S031.

## Migration Shape

1. Introduce `launch_types.py` and move shared leaf types there.
2. Make `BaseSubprocessHarness` an `ABC` and `resolve_launch_spec` abstract.
3. Add `preflight(...) -> PreflightResult` to `HarnessAdapter` and base class.
4. Collapse connection facet protocols into `HarnessConnection[SpecT]` ABC.
5. Convert concrete adapters/connections to generic bindings.
6. Introduce `HarnessBundle` registry and dispatch runtime guard.
7. Delete legacy fallback (`spec or ResolvedLaunchSpec(...)`).
8. Audit `BaseSubprocessHarness` default methods (`fork_session`, `owns_untracked_session`, `blocked_child_env_vars`, `seed_session`, `filter_launch_content`, `detect_primary_session_id`, `mcp_config`, `extract_report`, `resolve_session_file`, `run_prompt_policy`, `build_adhoc_agent_payload`) and delete methods that are dead or universally overridden.

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): concrete spec fields and construction-side accounting.
- [transport-projections.md](transport-projections.md): projection accounting and wire contracts.
- [runner-shared-core.md](runner-shared-core.md): shared context assembly calls `adapter.preflight(...)`; it does not host dispatch casting.
