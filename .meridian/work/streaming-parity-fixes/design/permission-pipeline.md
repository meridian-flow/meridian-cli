# Permission Pipeline

## Purpose

Make permission enforcement explicit and fail-closed across all launch entry points.

## Core Contract

- `PermissionResolver` is non-optional.
- `PermissionResolver.config` is required.
- `PermissionConfig.approval` is typed as `Literal["default", "auto", "yolo", "confirm"]`.
- No `cast("PermissionResolver", None)` is allowed.

```python
class PermissionConfig(BaseModel):
    sandbox: Literal["default", "read-only", "workspace-write", "danger-full-access"] = "default"
    approval: Literal["default", "auto", "yolo", "confirm"] = "default"
```

This pushes approval drift detection to pyright and model validation.

## Unsafe Opt-Out Class

`UnsafeNoOpPermissionResolver` is the explicit unsafe opt-out resolver.

```python
class UnsafeNoOpPermissionResolver(BaseModel):
    def __init__(self, *, _suppress_warning: bool = False, **data: object) -> None:
        super().__init__(**data)
        if not _suppress_warning:
            logger.warning(
                "UnsafeNoOpPermissionResolver constructed; no permission enforcement will be applied"
            )

    @property
    def config(self) -> PermissionConfig:
        return PermissionConfig()

    def resolve_flags(self, harness: HarnessId) -> tuple[str, ...]:
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

## Reserved Flags

Projection layers strip user passthrough args that attempt to override enforced permission policy.

```python
# src/meridian/lib/harness/projections/_reserved_flags.py
_RESERVED_CODEX_ARGS: frozenset[str] = frozenset({
    "sandbox",
    "sandbox_mode",
    "approval_policy",
    "full-auto",
    "ask-for-approval",
})

_RESERVED_CLAUDE_ARGS: frozenset[str] = frozenset({
    "--allowedTools",
    "--disallowedTools",
})

def strip_reserved_passthrough(
    args: list[str],
    reserved: frozenset[str],
    *,
    logger: logging.Logger,
) -> list[str]: ...
```

Rules:

- Codex: reserved passthrough args are stripped, with one warning log per stripped arg.
- Claude: reserved permission flags are merged/deduped by projection policy; user cannot override resolver-derived permission envelope.
- Unit tests assert attempted overrides do not change effective permission behavior.

## Codex Boundary Semantics

- Subprocess and streaming both read permission intent from `spec.permission_resolver.config`.
- Streaming maps config values to app-server directives.
- If a requested sandbox/approval policy cannot be represented on the actual app-server interface, spawn fails before launch (see D20 fail-closed rule in `decisions.md`).

## Interaction with Other Docs

- [launch-spec.md](launch-spec.md): `CodexLaunchSpec` stores no sandbox/approval fields.
- [transport-projections.md](transport-projections.md): wire mapping and reserved-flag stripping.
- [typed-harness.md](typed-harness.md): non-optional resolver signature.
