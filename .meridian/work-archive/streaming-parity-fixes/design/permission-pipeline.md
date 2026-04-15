# Permission Pipeline

## Purpose

Make permission enforcement explicit and fail-closed across all launch entry points for meridian's own coordination logic, while forwarding user and harness decisions without second-guessing.

Revision round 3 reframes the boundary:

- **Strict** for meridian-owned internal state (resolver non-optional, config immutable, REST server default rejection, fail-closed on unrepresentable intent).
- **Forgiving** for user and harness data (no reserved-flag stripping, no validation of "weird" permission combinations, no policing of `extra_args` content).

## Core Contract

- `PermissionResolver` is non-optional everywhere launch spec is constructed.
- `PermissionResolver.config` is required.
- `PermissionResolver.resolve_flags()` takes **no harness parameter** (K4) — projections read abstract intent from `config` and translate per harness.
- `PermissionConfig` is frozen at construction (K7) — `model_config = ConfigDict(frozen=True)`.
- No `cast("PermissionResolver", None)` is allowed.

```python
from pydantic import BaseModel, ConfigDict
from typing import Literal


class PermissionConfig(BaseModel):
    """Transport-neutral permission intent.

    Literals enumerate known values as of v2. They are relaxed to str at
    the projection boundary if required, and they are extensible at source
    without an API break — adding `danger-yolo-with-fireworks` to the sandbox
    tuple is a one-line edit here (D5).

    K7: `model_config = ConfigDict(frozen=True)` protects meridian's own
    internal state. The config is NOT a validator of which combinations
    "look right" — the harness decides that. Meridian does not refuse a
    spawn because `approval=confirm` and `sandbox=yolo` appear together;
    if the harness accepts the combo, meridian accepts it too (D2).
    """

    model_config = ConfigDict(frozen=True)

    sandbox: Literal[
        "default",
        "read-only",
        "workspace-write",
        "danger-full-access",
    ] = "default"
    approval: Literal[
        "default",
        "auto",
        "yolo",
        "confirm",
    ] = "default"
```

### Extension Path for PermissionConfig Literals (D5)

The Literals above are a typed enumeration of **known values at this point in time**. They are not a closed world, and they are not a policy statement about what values are allowed in the system.

When a new sandbox tier or approval mode ships in a downstream harness:

1. Add the new value to the corresponding Literal tuple.
2. Add a projection mapping for every harness in `transport-projections.md`.
3. No other meridian code needs to change.

This is an intentional friction-free path. Meridian does not attempt to auto-detect values from `--help` output or probe-derived catalogs. The Literals are developer-facing documentation + type-checker support, not a runtime gate.

### No combination validator (D2)

Meridian does NOT ship a `@model_validator` that rejects combinations like `approval=confirm + sandbox=yolo`. Any combination the harness accepts, meridian accepts. The revision round 3 reframe explicitly drops this.

## Resolver Protocol (K4)

```python
class PermissionResolver(Protocol):
    @property
    def config(self) -> PermissionConfig: ...

    def resolve_flags(self) -> tuple[str, ...]:
        """Return harness-agnostic flag hints (or `()`).

        The `harness` parameter was removed in revision round 3. It invited
        `if harness == CLAUDE` branching inside the resolver, re-introducing
        the harness-id dispatch that `adapter.preflight()` was meant to
        eliminate. The new shape is: resolvers expose intent via `config`
        and MAY emit harness-agnostic hints via `resolve_flags`; projections
        translate intent to wire format per harness.
        """
        ...
```

### Why `resolve_flags` is kept

Some legacy resolvers (e.g., `ExplicitToolsResolver` for Claude) still return pre-formatted tool lists. Their output flows through the Claude projection, which is the only consumer that knows about Claude-specific flag shapes. The resolver itself does not know or care about Claude.

`resolve_flags` is deprecated in direction but retained as an escape hatch for migration. It may be deleted in a later revision once every resolver is intent-based.

### Resolver-internal invariant

A resolver implementation **must not** branch on harness id at any layer (own methods, helper functions, base class implementations). This is documented as an invariant in the resolver module and enforced by convention — there is no automated check because resolvers are user-extensible plugins and static enforcement would require AST analysis.

Projections are the only layer that knows about harness-specific wire format.

## Unsafe Opt-Out Class

`UnsafeNoOpPermissionResolver` is the explicit unsafe opt-out resolver.

```python
class UnsafeNoOpPermissionResolver(BaseModel):
    model_config = ConfigDict(frozen=True)

    def __init__(self, *, _suppress_warning: bool = False, **data: object) -> None:
        super().__init__(**data)
        if not _suppress_warning:
            logger.warning(
                "UnsafeNoOpPermissionResolver constructed; no permission enforcement will be applied"
            )

    @property
    def config(self) -> PermissionConfig:
        return PermissionConfig()

    def resolve_flags(self) -> tuple[str, ...]:
        return ()
```

Tests that intentionally construct this class may pass `_suppress_warning=True`.

## REST Server Policy (strict by default)

Default behavior for missing permission metadata is rejection:

- Missing permission block -> `HTTP 400 Bad Request`
- No implicit fallback resolver in default mode

Explicit opt-out is available only via server knob:

- `--allow-unsafe-no-permissions`
- When enabled, missing permission metadata uses `UnsafeNoOpPermissionResolver`
- Warning log is emitted on construction and request handling

This is a meridian-owned policy: the server refuses to guess what permission semantics the API caller wanted. The knob is an explicit unlock for local development and testing.

## `extra_args` is NOT inspected for permission flags (D1)

Round 2 introduced `_RESERVED_CLAUDE_ARGS`, `_RESERVED_CODEX_ARGS`, and `strip_reserved_passthrough(...)`. These have been **deleted** in round 3.

Rationale:

- `extra_args` is the supported escape hatch for users who need to override meridian's permission projection temporarily. If a user passes `-c sandbox_mode=yolo` through `extra_args`, that is forwarded to Codex verbatim.
- Meridian is not the security gate for `extra_args`. The harness is. The user could invoke the harness directly with the same flags.
- Stripping or rewriting `extra_args` provides a false sense of security and silently surprises users when their flag disappears.
- Claude-side `--allowedTools` dedupe still runs **inside the resolver** for resolver-internal consistency (e.g., parent-forwarded + explicit + profile-defaults merging) — but the dedupe never touches user `extra_args`.

The only "audit trail" meridian provides for `extra_args` is a debug log listing the verbatim arguments at the projection boundary, so operators can see what reached the harness.

## Codex Boundary Semantics

- Subprocess and streaming both read permission intent from `spec.permission_resolver.config`.
- Streaming maps config values to app-server directives.
- If the `PermissionConfig` values the caller requested cannot be expressed on the actual app-server interface, spawn fails before launch with `HarnessCapabilityMismatch` (D20 fail-closed rule in `decisions.md`).

Fail-closed is still in scope because it protects **meridian's own request**: when a caller says `sandbox=read-only` and Codex cannot express that, meridian refuses to silently downgrade to `default`. This is a strict check on meridian-internal drift (promise-vs-capability mismatch), not a policy on user behavior.

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): `CodexLaunchSpec` stores no sandbox/approval fields.
- [transport-projections.md](transport-projections.md): wire mapping, `extra_args` verbatim forwarding, `mcp_tools` projection.
- [typed-harness.md](typed-harness.md): non-optional resolver signature, immutable spec, cancel/interrupt semantics.
