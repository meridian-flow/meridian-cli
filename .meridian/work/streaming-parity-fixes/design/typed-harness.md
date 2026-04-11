# Typed Harness Contract

## Purpose

Bind each adapter, connection, and extractor to a concrete launch-spec subtype so harness dispatch cannot silently downcast into generic behavior. Runtime and static enforcement are both explicit.

Revision round 3 reframes the invariants this doc carries: every check here exists to protect meridian's own internal coordination logic from drift. Nothing here validates or polices the content of user-supplied `extra_args`, permission combinations, or harness decisions.

## Module: `harness/ids.py` (single source for `HarnessId` / `TransportId`)

`HarnessId` and `TransportId` are defined **exactly once**, in `src/meridian/lib/harness/ids.py`. Every other module — adapter, bundle, connection, extractor, dispatch, launch context, runner, launch_spec guard — imports them from that path:

```python
from meridian.lib.harness.ids import HarnessId, TransportId
```

No other module may re-export or redefine these enums. They are standalone leaves with **zero** downstream imports inside the `meridian.lib.harness` package (see §Import Topology); this makes them safe to import from any module without triggering an import cycle. This pin is load-bearing for K1 (`(harness_id, transport_id)` dispatch) and K2 (`_REGISTRY: dict[HarnessId, HarnessBundle[Any]]`) — both invariants key on identity of the enum values, which only holds if there is one definition site.

## Module: `launch/launch_types.py`

```python
# src/meridian/lib/launch/launch_types.py
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar
from pydantic import BaseModel, ConfigDict, model_validator

SpecT = TypeVar("SpecT", bound="ResolvedLaunchSpec")


class PermissionResolver(Protocol):
    """Transport-neutral permission intent.

    Revision round 3 (K4): `resolve_flags` no longer takes a harness parameter.
    The resolver exposes abstract intent via `config`; projections translate
    that intent into harness-specific wire format. This prevents resolvers
    from re-introducing `if harness == CLAUDE` branching internally.
    """

    @property
    def config(self) -> PermissionConfig: ...

    def resolve_flags(self) -> tuple[str, ...]:
        """Return harness-agnostic flag hints (or `()`).

        The preferred shape for all v2 resolvers is to return `()` and let
        projections read everything from `config`. `resolve_flags` is kept
        as a deprecated escape hatch for legacy resolvers that still emit
        pre-formatted flags; its output is passed through the projection's
        harness-specific formatter and may be dropped entirely in a later
        revision. Never branch on harness id inside a resolver.
        """
        ...


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

    # Passthrough args — forwarded verbatim to the harness. Never stripped
    # or rewritten by meridian. This is an explicit escape hatch.
    extra_args: tuple[str, ...] = ()

    # Interactive mode
    interactive: bool = False

    # MCP tool specifications. Harness-agnostic list of MCP tool identifiers
    # (or path refs) resolved into harness-specific wire format by each
    # projection. Restored in revision round 3 (D4). Auto-packaging through
    # mars is out of scope for v2; manual configuration via SpawnParams works.
    mcp_tools: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_continue_fork_requires_session(self) -> "ResolvedLaunchSpec":
        if self.continue_fork and not self.continue_session_id:
            raise ValueError("continue_fork=True requires continue_session_id")
        return self


@dataclass(frozen=True)
class PreflightResult:
    """Result of adapter-owned preflight.

    K7: `extra_env` is wrapped in `MappingProxyType` at construction to
    protect meridian's own merge pipeline from downstream mutation.
    """

    expanded_passthrough_args: tuple[str, ...]
    extra_env: MappingProxyType[str, str]

    @classmethod
    def build(
        cls,
        *,
        expanded_passthrough_args: tuple[str, ...],
        extra_env: dict[str, str] | None = None,
    ) -> "PreflightResult":
        return cls(
            expanded_passthrough_args=expanded_passthrough_args,
            extra_env=MappingProxyType(dict(extra_env or {})),
        )
```

`adapter.py`, `launch_spec.py`, `bundle.py`, and the extractor base all import from this leaf module to avoid cycles.

## Bundle Registry (K1, K2)

v2 dispatches on `(harness_id, transport_id)` so adding a new transport for an existing harness (e.g., Claude-over-HTTP) is a one-line addition to an existing bundle's `connections` mapping, not a rewiring of dispatch code.

```python
# src/meridian/lib/harness/bundle.py
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic

from meridian.lib.launch.launch_types import SpecT, ResolvedLaunchSpec
from meridian.lib.harness.adapter import HarnessAdapter
from meridian.lib.harness.connections.base import HarnessConnection
from meridian.lib.harness.extractors.base import HarnessExtractor
from meridian.lib.harness.ids import HarnessId, TransportId


@dataclass(frozen=True)
class HarnessBundle(Generic[SpecT]):
    harness_id: HarnessId
    adapter: HarnessAdapter[SpecT]
    spec_cls: type[SpecT]
    extractor: HarnessExtractor[SpecT]
    connections: Mapping[TransportId, type[HarnessConnection[SpecT]]]


_REGISTRY: dict[HarnessId, HarnessBundle[Any]] = {}


def register_harness_bundle(bundle: HarnessBundle[Any]) -> None:
    """Sole mutation site for the harness bundle registry (K2).

    Validates bundle completeness at registration time — this is the single
    enforcement point for bundle-level invariants. Any bundle that reaches
    `_REGISTRY` has been proven well-formed.

    Raises:
        TypeError: if `bundle.extractor is None` (K6 requires every harness to
            declare an extractor for session-id fallback parity).
        ValueError: if `bundle.connections` is empty (a bundle with no
            transports is useless and indicates a wiring bug).
        ValueError: if a bundle for the same `harness_id` is already
            registered — catches duplicate registrations caused by double-import
            or by two modules claiming the same harness id.
    """
    if bundle.extractor is None:  # type: ignore[comparison-overlap]
        raise TypeError(
            f"HarnessBundle for {bundle.harness_id} is missing extractor "
            f"(K6: every harness must declare a HarnessExtractor[SpecT])"
        )
    if not bundle.connections:
        raise ValueError(
            f"HarnessBundle for {bundle.harness_id} has no connections; "
            f"must declare at least one (TransportId, HarnessConnection[SpecT]) entry"
        )
    if bundle.harness_id in _REGISTRY:
        existing = type(_REGISTRY[bundle.harness_id].adapter).__name__
        incoming = type(bundle.adapter).__name__
        raise ValueError(
            f"duplicate harness bundle for {bundle.harness_id}: "
            f"existing adapter={existing}, incoming adapter={incoming}"
        )
    _REGISTRY[bundle.harness_id] = bundle


def get_harness_bundle(harness_id: HarnessId) -> HarnessBundle[Any]:
    try:
        return _REGISTRY[harness_id]
    except KeyError:
        raise KeyError(f"unknown harness: {harness_id}") from None


def get_connection_cls(
    harness_id: HarnessId,
    transport_id: TransportId,
) -> type[HarnessConnection[Any]]:
    bundle = get_harness_bundle(harness_id)
    try:
        return bundle.connections[transport_id]
    except KeyError:
        raise KeyError(
            f"harness {harness_id} has no connection for transport {transport_id}"
        ) from None
```

### Bootstrap Sequence (canonical `harness/__init__.py`)

The `harness/` package load order is **load-bearing**: concrete adapters must register bundles before the cross-adapter field accounting check runs; projection modules must execute their per-module drift guards before any dispatch; extractors must be imported so Protocol runtime checks bind correctly. The canonical form is a single authoritative block.

```python
# src/meridian/lib/harness/__init__.py
# Import order is load-bearing. Do not reorder without updating
# typed-harness.md §Bootstrap Sequence and re-running S044.

# 1. Concrete adapters. Each module calls register_harness_bundle(...)
#    as a top-level side effect. After this block every
#    HarnessId has a bundle in _REGISTRY.
from meridian.lib.harness import claude as _claude  # noqa: F401
from meridian.lib.harness import codex as _codex    # noqa: F401
from meridian.lib.harness import opencode as _opencode  # noqa: F401

# 2. Projection modules. Each module calls _check_projection_drift(...)
#    at top level, so stale or missing fields in per-harness wire
#    formats raise ImportError during package load.
from meridian.lib.harness.projections import (  # noqa: F401
    project_claude,
    project_codex_subprocess,
    project_codex_streaming,
    project_opencode_subprocess,
    project_opencode_streaming,
)

# 3. Extractors. Runtime-checkable Protocol binding; imported explicitly
#    so isinstance checks against HarnessExtractor succeed even if a
#    concrete adapter imports its extractor lazily.
from meridian.lib.harness.extractors import (  # noqa: F401
    claude as _claude_ext,
    codex as _codex_ext,
    opencode as _opencode_ext,
)

# 4. Cross-adapter field-ownership accounting. This call MUST run AFTER
#    every register_harness_bundle() above so _REGISTRY is fully populated.
#    Do NOT invoke this as a module-load side effect in launch_spec.py —
#    import order there is not deterministic across harnesses.
from meridian.lib.harness.launch_spec import _enforce_spawn_params_accounting
_enforce_spawn_params_accounting()
```

The explicit final call to `_enforce_spawn_params_accounting()` replaces any module-load side effect in `launch_spec.py`. Scenario S044 targets this ordering: loading `harness.__init__` from a fresh interpreter with a fixture registry that drops a `handled_fields` entry must raise `ImportError` naming the missing `SpawnParams` field.

### Import-time invariants enforced by bundle / registry

- `register_harness_bundle(bundle)` rejects duplicate `harness_id` with `ValueError` (S039).
- `register_harness_bundle(bundle)` rejects `extractor is None` with `TypeError` (S043).
- `register_harness_bundle(bundle)` rejects empty `connections` mapping with `ValueError`.
- Every bundle's `adapter` is a `HarnessAdapter[SpecT]` and its `spec_cls` matches the generic binding at import time (Protocol runtime-check).
- Every bundle exposes an `extractor: HarnessExtractor[SpecT]` (K6) validated by registration.

## Adapter Contract (K3, K9)

> **Note.** Round 3 renames `BaseSubprocessHarness` → `BaseHarnessAdapter`. All three harnesses (Claude, Codex, OpenCode) now support streaming connections, and all three inherit the same base. The old name suggested a `BaseStreamingHarness` counterpart that does not exist; the ABC is about adapter contract (`resolve_launch_spec` + `preflight` + `id` + `handled_fields`), not about any specific transport.

Two mechanisms are used and they have different roles:

- `@runtime_checkable Protocol` (`HarnessAdapter[SpecT]`) for structural type checking in pyright.
- `abc.ABC` abstract methods (`BaseHarnessAdapter(Generic[SpecT], ABC)`) for runtime instantiation rejection.

Protocol conformance does not raise `TypeError` at instantiation. ABC abstract-method enforcement does. K3 requires that the Protocol and ABC expose the same required method set so a subclass cannot be ABC-instantiable while Protocol-noncompliant.

```python
# src/meridian/lib/harness/adapter.py
@runtime_checkable
class HarnessAdapter(Protocol, Generic[SpecT]):
    @property
    def id(self) -> HarnessId: ...

    @property
    def consumed_fields(self) -> frozenset[str]:
        """SpawnParams fields this adapter actively reads and maps onto its
        spec. These are fields that produce wire output — a new field listed
        here but not wired in the projection triggers the projection drift
        guard in `_check_projection_drift(...)`.
        """
        ...

    @property
    def explicitly_ignored_fields(self) -> frozenset[str]:
        """SpawnParams fields this adapter consciously does NOT map.

        Listing a field here is a conscious opt-out — e.g., Codex ignores
        `skills` because Codex has no skill injection path. Forgetting to
        wire a field is different from deciding not to wire it; K9 can't
        tell those apart from `handled_fields` alone. The split makes the
        intent explicit, and the projection drift guard cross-references
        `_PROJECTED_FIELDS` against `consumed_fields` only.
        """
        ...

    @property
    def handled_fields(self) -> frozenset[str]:
        """Convenience union: `consumed_fields | explicitly_ignored_fields`.

        The union of every registered adapter's `handled_fields` must equal
        `SpawnParams.model_fields`. An import-time guard in
        `harness/launch_spec.py` raises `ImportError` on drift (K9).
        """
        ...

    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT: ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult: ...


class BaseHarnessAdapter(Generic[SpecT], ABC):
    @property
    @abstractmethod
    def id(self) -> HarnessId:
        """Harness identifier. Marked abstract so subclasses that forget
        to declare `id` fail at instantiation instead of crashing deep in
        dispatch with `AttributeError` (K3).
        """
        ...

    @property
    @abstractmethod
    def consumed_fields(self) -> frozenset[str]:
        """Fields the adapter actively reads and projects onto the wire (K9).
        Abstract so every concrete adapter is forced to declare its own set —
        the base cannot provide a default without hiding drift."""
        ...

    @property
    @abstractmethod
    def explicitly_ignored_fields(self) -> frozenset[str]:
        """Fields the adapter consciously does not project. Abstract for the
        same reason as `consumed_fields` — forgetting to opt out is different
        from forgetting to consume."""
        ...

    @property
    def handled_fields(self) -> frozenset[str]:
        """Union helper; not abstract — derived from `consumed_fields` and
        `explicitly_ignored_fields`. K9 checks this against
        `SpawnParams.model_fields`."""
        return self.consumed_fields | self.explicitly_ignored_fields

    @abstractmethod
    def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT: ...

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult:
        return PreflightResult.build(expanded_passthrough_args=passthrough_args)
```

`ClaudeAdapter.preflight(...)` performs Claude-specific parent-permission and `--add-dir` expansion. `CodexAdapter` and `OpenCodeAdapter` use the base default.

A unit test reconciles `HarnessAdapter` Protocol attributes against the abstract method set on `BaseHarnessAdapter`. If they drift, the test fails (S040).

## Connection Contract (K8)

One interface: `HarnessConnection[SpecT]` ABC. Facet protocols (`HarnessLifecycle`, `HarnessSender`, `HarnessReceiver`) are removed in v2 to avoid duplicate method surfaces drifting.

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

### Cancel / Interrupt / SIGTERM Semantics (K8)

| Method / Signal | Trigger | Idempotency | Terminal status | Ordering guarantee |
|---|---|---|---|---|
| `send_cancel()` | Explicit cancel (user API, runner cleanup) | Idempotent — repeated calls after the first collapse to a no-op | Single `cancelled` terminal spawn status | Cancel event is enqueued before any `send_error` awaited by the cancel path |
| `send_interrupt()` | Mid-turn interrupt (soft stop) | Idempotent — repeated calls collapse to a no-op | Converges to `cancelled` if the harness does not resume; otherwise `completed` on natural finish | Interrupt event ordering is preserved relative to subsequent send_user_message calls |
| Runner SIGTERM / SIGINT | Host signal | Translated into exactly one `send_cancel()` invocation on every active connection | `cancelled` on terminal reconciliation | Signal handler records cancellation intent before connection unwind; reconciliation finalizes status crash-only |

Invariants:

- A single spawn cannot produce more than one terminal status. If cancel races completion, the first persisted terminal status wins and subsequent terminal writes are dropped by the spawn store's atomic write path.
- `send_cancel` and `send_interrupt` MUST be safe to call from signal handlers (no blocking I/O, no allocation-heavy operations).
- Cancellation event emission is exactly-once per spawn, ordered before any subsequent error-emission on the same connection.
- Runner-level signal handling is transport-neutral: the runner does not know whether the harness is subprocess or streaming; it calls `send_cancel` on the connection and relies on crash-only reconciliation for cleanup.

Scenarios S041 and S042 exercise cancel / interrupt parity across subprocess and streaming transports.

## Dispatch Boundary (authoritative site) — K1

The single runtime type-narrow boundary is in `SpawnManager.start_spawn` dispatch, not in `prepare_launch_context`.

```python
async def dispatch_start(
    *,
    harness_id: HarnessId,
    transport_id: TransportId,
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> HarnessConnection[Any]:
    bundle = get_harness_bundle(harness_id)
    if not isinstance(spec, bundle.spec_cls):
        raise TypeError(
            f"HarnessBundle invariant violated: adapter for "
            f"{bundle.harness_id} returned {type(spec).__name__}, "
            f"expected {bundle.spec_cls.__name__}"
        )
    try:
        connection_cls = bundle.connections[transport_id]
    except KeyError:
        raise KeyError(
            f"harness {bundle.harness_id} does not support transport {transport_id}"
        ) from None
    connection = connection_cls()
    # No cast needed: bundle.connections[transport_id] is typed as
    # type[HarnessConnection[Any]] (because _REGISTRY holds HarnessBundle[Any]),
    # and the isinstance guard above is the actual runtime narrow.
    # A free `cast(SpecT, spec)` here would either be a no-op or get flagged
    # by pyright for binding an unbound TypeVar (see Opus review p1439 #6).
    await connection.start(config, spec)
    return connection
```

The `isinstance(spec, bundle.spec_cls)` check is the single cast boundary — the runtime type narrow that S002 targets. It is the only allowed boundary-type guard.

Inside concrete `Connection.start(...)` methods, behavior-switching `isinstance` branches are disallowed.

## Extractor Contract (K6)

```python
# src/meridian/lib/harness/extractors/base.py
from collections.abc import Mapping
from typing import Generic, Protocol, runtime_checkable


@runtime_checkable
class HarnessExtractor(Protocol, Generic[SpecT]):
    """Harness-specific event and artifact extraction.

    Used symmetrically by subprocess and streaming runners so that
    session-id detection and report extraction stay transport-neutral.
    Closes the p1385 gap where streaming had no fallback session detection
    via harness-specific project files (Claude project files, Codex rollout
    files, OpenCode logs).

    `runtime_checkable` so `isinstance(obj, HarnessExtractor)` can verify
    the Protocol surface at bundle-registration time.
    """

    def detect_session_id_from_event(
        self,
        event: HarnessEvent,
    ) -> str | None:
        """Extract session id from a live event stream frame, if present."""
        ...

    def detect_session_id_from_artifacts(
        self,
        *,
        spec: SpecT,
        launch_env: Mapping[str, str],
        child_cwd: Path,
        state_root: Path,
    ) -> str | None:
        """Fallback session id detection from harness-specific artifacts.

        `launch_env` is the fully-merged env the child was launched with —
        the same `LaunchContext.env` exposed as a `MappingProxyType`. It is
        threaded here so extractors respect non-default paths set via
        `preflight.extra_env` (e.g., `CODEX_HOME`, `OPENCODE_*`). Without
        this, an extractor that reads `~/.codex/rollouts/...` would resolve
        to the orchestrator user's home instead of the child-process home.

        `spec: SpecT` gives the extractor access to harness-specific
        fields (e.g., `codex_cwd`) without a back-door to the run params.

        Required for every harness. Subprocess was already doing this;
        streaming now has parity via the same extractor.
        """
        ...

    def extract_report(
        self,
        *,
        spec: SpecT,
        launch_env: Mapping[str, str],
        child_cwd: Path,
        artifacts_dir: Path,
    ) -> str | None:
        """Extract the final report from post-run artifacts, if produced.

        `launch_env` is threaded for the same reason as in
        `detect_session_id_from_artifacts` — report paths may depend on
        harness-specific env overrides.
        """
        ...
```

### Extractor bundle-registration guard

`register_harness_bundle(bundle)` rejects `bundle.extractor is None` with `TypeError` (see §Bundle Registry). This is the single enforcement point: registration-time validation, not a separate eager-import side effect. `src/meridian/lib/harness/extractors/__init__.py` still imports every concrete extractor eagerly so the Protocol `runtime_checkable` binding is in place before bundle modules execute, but the load-bearing check lives in `register_harness_bundle`. S043 targets the registration-time failure.

## Import Topology

**Convention:** `A → B` means "A imports B" (consumer on the left, dependency on the right). Every edge below is acyclic.

```
# Leaf types (nothing inside harness/ imports from launch/ except these):
launch/launch_types.py   ← (no upstream harness/ imports)
launch/constants.py      ← (no upstream harness/ imports)
launch/text_utils.py     ← (no upstream harness/ imports)

# Contract leaves (imported by everything that implements them):
harness/adapter.py             → launch/launch_types.py
harness/connections/base.py    → launch/launch_types.py
harness/extractors/base.py     → launch/launch_types.py
harness/ids.py                 → (standalone enums)
harness/errors.py              → (standalone)
harness/projections/_guards.py → launch/launch_types.py

# Bundle glues the contracts together (all four edges are load-bearing):
harness/bundle.py → harness/adapter.py
                  → harness/connections/base.py
                  → harness/extractors/base.py
                  → harness/ids.py
                  → launch/launch_types.py

# Concrete adapter modules — each calls register_harness_bundle(...) at
# top level, so importing these modules has a side effect on _REGISTRY:
harness/claude.py   → harness/adapter.py
                    → harness/bundle.py
                    → harness/claude_preflight.py
                    → harness/projections/project_claude.py
                    → harness/extractors/claude.py
harness/codex.py    → harness/adapter.py
                    → harness/bundle.py
                    → harness/projections/project_codex_subprocess.py
                    → harness/projections/project_codex_streaming.py
                    → harness/extractors/codex.py
harness/opencode.py → harness/adapter.py
                    → harness/bundle.py
                    → harness/projections/project_opencode_subprocess.py
                    → harness/projections/project_opencode_streaming.py
                    → harness/extractors/opencode.py

# Claude preflight is the only adapter-specific preflight module:
harness/claude_preflight.py → launch/constants.py
                            → launch/text_utils.py

# Projection modules all import the same guard leaf and a spec class:
harness/projections/project_claude.py             → harness/projections/_guards.py
                                                  → launch/text_utils.py
harness/projections/project_codex_subprocess.py   → harness/projections/_guards.py
harness/projections/project_codex_streaming.py    → harness/projections/_guards.py
                                                  → launch/constants.py
harness/projections/project_opencode_subprocess.py → harness/projections/_guards.py
harness/projections/project_opencode_streaming.py  → harness/projections/_guards.py

# launch_spec.py aggregates every adapter's handled_fields for K9:
harness/launch_spec.py → harness/bundle.py
                       → harness/adapter.py
                       → launch/launch_types.py

# Connection implementations each inherit the base ABC:
harness/connections/subprocess.py         → harness/connections/base.py
harness/connections/claude_streaming.py   → harness/connections/base.py
harness/connections/codex_streaming.py    → harness/connections/base.py
harness/connections/opencode_streaming.py → harness/connections/base.py

# Extractor implementations each inherit the base Protocol:
harness/extractors/claude.py   → harness/extractors/base.py
harness/extractors/codex.py    → harness/extractors/base.py
harness/extractors/opencode.py → harness/extractors/base.py

# Runners use shared context and errors, never concrete adapters:
launch/context.py   → launch/launch_types.py
                    → launch/constants.py
                    → harness/bundle.py
runner.py           → launch/context.py
                    → harness/errors.py
streaming_runner.py → launch/context.py
                    → harness/errors.py

# harness/__init__.py ties the whole bootstrap together:
harness/__init__.py → harness/claude.py
                    → harness/codex.py
                    → harness/opencode.py
                    → harness/projections/project_claude.py
                    → harness/projections/project_codex_subprocess.py
                    → harness/projections/project_codex_streaming.py
                    → harness/projections/project_opencode_subprocess.py
                    → harness/projections/project_opencode_streaming.py
                    → harness/extractors/claude.py
                    → harness/extractors/codex.py
                    → harness/extractors/opencode.py
                    → harness/launch_spec.py (for _enforce_spawn_params_accounting)
```

Revision round 3 removes `harness/projections/_reserved_flags.py` from the topology (H1).

This is the acyclic dependency DAG used by S031. The `harness/__init__.py` eager-import edge (C2) — see [§Bootstrap Sequence](#bootstrap-sequence-canonical-harness__init__py) for the canonical module body — guarantees projection drift guards, bundle registrations, and cross-adapter accounting all execute before the first dispatch. Any import-time error surfaces during package load, not after a dispatch failure.

## Migration Shape

1. Introduce `launch_types.py` and move shared leaf types there.
2. Make `BaseHarnessAdapter` an `ABC`, and mark `id`, `handled_fields`, and `resolve_launch_spec` abstract (K3, K9).
3. Add `preflight(...) -> PreflightResult` to `HarnessAdapter` and base class; wrap `PreflightResult.extra_env` in `MappingProxyType` (K7).
4. Collapse connection facet protocols into `HarnessConnection[SpecT]` ABC; document cancel/interrupt semantics table (K8).
5. Convert concrete adapters/connections/extractors to generic bindings.
6. Introduce `HarnessBundle` registry with `register_harness_bundle()` helper and `(harness_id, transport_id)` dispatch (K1, K2); add extractor to bundle (K6).
7. Delete legacy fallback (`spec or ResolvedLaunchSpec(...)`).
8. Delete reserved-flag machinery (`_RESERVED_*`, `strip_reserved_passthrough`) — do NOT keep in `projections/_reserved_flags.py` (D1).
9. Restore `mcp_tools: tuple[str, ...]` on `ResolvedLaunchSpec` and wire each projection's MCP mapping (D4).
10. Update `PermissionResolver.resolve_flags` signature to drop the `harness` parameter (K4).
11. Add `model_config = ConfigDict(frozen=True)` to `PermissionConfig` (K7).
12. Add eager imports in `harness/__init__.py` and `harness/extractors/__init__.py` (C2).
13. Audit `BaseHarnessAdapter` default methods (`fork_session`, `owns_untracked_session`, `blocked_child_env_vars`, `seed_session`, `filter_launch_content`, `detect_primary_session_id`, `mcp_config`, `extract_report`, `resolve_session_file`, `run_prompt_policy`, `build_adhoc_agent_payload`) and delete methods that are dead or universally overridden. `detect_primary_session_id` and `extract_report` move into `HarnessExtractor`.

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): concrete spec fields, construction-side accounting, per-adapter `handled_fields` guard.
- [transport-projections.md](transport-projections.md): projection accounting and wire contracts, `mcp_tools` mapping, verbatim `extra_args` forwarding.
- [permission-pipeline.md](permission-pipeline.md): resolver contract (no harness parameter), immutable `PermissionConfig`.
- [runner-shared-core.md](runner-shared-core.md): shared context assembly calls `adapter.preflight(...)`, it does not host dispatch casting; `MERIDIAN_*` sole-producer invariant.
