# Permission Module Target State

File: `src/meridian/lib/safety/permissions.py`

## What Gets Removed

### `PermissionTier` enum (lines 15-22)
Delete entirely. No replacement. The 5 string values (`read-only`, `workspace-write`, etc.) were only used to constrain sandbox values to a known set, but that set doesn't match what harnesses actually accept.

### `parse_permission_tier()` (lines 40-53)
Delete. No longer needed — sandbox values flow through as strings.

### `permission_tier_from_profile()` (lines 56-76)
Delete. This function existed to convert profile sandbox strings to `PermissionTier`, with a warning fallback for unknown values. With passthrough semantics, the string flows through directly.

### `_parse_permission_tier_value()` (lines 79-90)
Delete. Internal helper for the removed enum parsing.

## What Changes

### `PermissionConfig`

```python
class PermissionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    sandbox: str | None = None          # was: tier: PermissionTier | None
    approval: str = "default"
    opencode_permission_override: str | None = None
```

Field renamed from `tier` to `sandbox` because (a) the value is no longer a "tier" in an abstract hierarchy, it's the harness-native sandbox string, and (b) `sandbox` matches the field name everywhere else in the codebase (CLI flag, profile YAML, overrides).

### `build_permission_config()`

```python
def build_permission_config(
    sandbox: str | None,
    *,
    approval: str = "default",
) -> PermissionConfig:
    normalized = sandbox.strip().lower() if sandbox else None
    return PermissionConfig(
        sandbox=normalized or None,
        approval=_parse_approval_value(approval),
    )
```

No tier parsing. Just normalize whitespace and pass through. Approval validation stays (known set, harness-independent).

### `permission_flags_for_harness()`

```python
def permission_flags_for_harness(
    harness_id: HarnessId,
    config: PermissionConfig,
) -> list[str]:
    sandbox = config.sandbox
    approval = config.approval

    # --- approval-level flags (take precedence over sandbox) ---
    if approval == "yolo":
        if harness_id == HarnessId.CLAUDE:
            return ["--dangerously-skip-permissions"]
        if harness_id == HarnessId.CODEX:
            return ["--dangerously-bypass-approvals-and-sandbox"]
    elif approval == "auto":
        if harness_id == HarnessId.CLAUDE:
            return ["--permission-mode", "acceptEdits"]
        if harness_id == HarnessId.CODEX:
            return ["--full-auto"]
    elif approval == "confirm":
        if harness_id == HarnessId.CLAUDE:
            return ["--permission-mode", "default"]
        if harness_id == HarnessId.CODEX:
            return ["--ask-for-approval", "untrusted"]

    if sandbox is None:
        return []

    if harness_id == HarnessId.CODEX:
        return ["--sandbox", sandbox]

    # Other harnesses: no sandbox flag support yet.
    return []
```

Key change: `tier.value` becomes just `sandbox`. The string passes through to the harness as-is.

### `resolve_permission_pipeline()`

The function signature stays the same (it already takes `sandbox: str | None`). Internally it stops converting to/from `PermissionTier`:

```python
def resolve_permission_pipeline(
    *,
    sandbox: str | None,
    allowed_tools: tuple[str, ...] = (),
    disallowed_tools: tuple[str, ...] = (),
    approval: str = "default",
) -> tuple[PermissionConfig, ...]:
    config = build_permission_config(sandbox, approval=approval)
    # ... rest stays the same, uses config.sandbox instead of config.tier
```

## What Stays Unchanged

- `TieredPermissionResolver` — keeps its name (renaming adds churn across 6 test files for no simplification benefit)
- `_parse_approval_value()` — approval modes are a known, harness-independent set
- `opencode_permission_json_for_allowed_tools()` / `..._disallowed_tools()` — tool normalization is orthogonal
- `ExplicitToolsResolver`, `DisallowedToolsResolver`, `CombinedToolsResolver` — all unchanged
- `build_permission_resolver()` — unchanged
- `_normalize_tool_name()` — unchanged
- `PermissionConfig` as a class — still usefully packages sandbox, approval, and opencode_permission_override across boundaries

## All Files That Import From permissions.py

Core (need code changes):
- `src/meridian/lib/safety/permissions.py` — primary changes
- `src/meridian/lib/core/overrides.py` — remove KNOWN_SANDBOX_VALUES, remove validator
- `src/meridian/lib/config/settings.py` — remove _validate_sandbox, remove KNOWN_SANDBOX_VALUES import
- `src/meridian/lib/catalog/agent.py` — remove sandbox warning and KNOWN_SANDBOX_VALUES import
- `src/meridian/lib/ops/spawn/execute.py` — rename permission_tier to sandbox

Import-only (PermissionConfig.tier -> .sandbox where accessed):
- `src/meridian/lib/launch/plan.py` — uses `permission_config.tier`, needs `.sandbox`
- `src/meridian/lib/launch/env.py` — type annotation only, no field access
- `src/meridian/lib/launch/command.py` — type annotation only, no field access
- `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` — `env_overrides(config)` reads `opencode_permission_override`, not `tier`

Tests:
- `tests/exec/test_permissions.py` ��� remove PermissionTier imports, update assertions to string comparisons
- `tests/test_launch_process.py` — TieredPermissionResolver import (no change since we keep the name)
- `tests/exec/test_claude_cwd_isolation.py` — same
- `tests/exec/test_signals.py` — same
- `tests/exec/test_pipe_drain.py` — same
- `tests/exec/test_lifecycle.py` — same
