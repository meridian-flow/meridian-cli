# Sandbox Simplification: Design Overview

## Problem

The `PermissionTier` enum in `src/meridian/lib/safety/permissions.py` defines 5 abstract sandbox values (`read-only`, `workspace-write`, `full-access`, `danger-full-access`, `unrestricted`) that create a false validation layer between profiles and harnesses:

1. **False validation**: The enum validates that a value is one of 5 known tiers, but this doesn't guarantee the harness will accept it. Codex rejects `unrestricted`; the enum accepts it. Codex accepts `none`; the enum rejects it.
2. **Maintenance burden**: Adding a new harness or sandbox mode requires updating the central enum, the translation function, and validation sets in 3 files (`overrides.py`, `settings.py`, `permissions.py`) — when the harness adapter is the only code that knows what values are valid.
3. **Unnecessary abstraction**: The enum converts string -> enum -> string with no transformation or semantic enrichment in between.

Note: profiles that use `sandbox: unrestricted` (which Codex rejects) are a separate fix in the source submodules. This design removes the abstraction layer; it does not fix profile values.

## Target State

Remove the `PermissionTier` enum. Make `sandbox` a plain `str | None` passthrough at every layer. Profiles declare sandbox values in the harness's own vocabulary, and harness adapters pass them through without a central abstraction.

This aligns with the project's "Separate Policy from Mechanism" principle: the profile declares the sandbox intent, the harness adapter knows how to express it.

## Scope

**In scope:**
- Remove `PermissionTier` enum and all parsing/validation functions around it
- Simplify `PermissionConfig.tier` from `PermissionTier | None` to `str | None` (rename to `sandbox`)
- Remove `KNOWN_SANDBOX_VALUES` from `overrides.py` and the `_validate_sandbox` validator in `RuntimeOverrides`
- Remove `_validate_sandbox` validator in `settings.py` `PrimaryConfig` class
- Simplify `permission_flags_for_harness` to pass sandbox string through to harnesses
- Remove `permission_tier_from_profile` (no longer needed, sandbox flows through as-is)
- Remove agent profile loader warning for unknown sandbox values (`catalog/agent.py`)
- Rename `permission_tier` field in `execute.py` `BackgroundWorkerParams` to `sandbox`
- Update all test files referencing `PermissionTier` or `TieredPermissionResolver`
- Update CLI help text for `--sandbox` to remove the enum value list

**Out of scope:**
- Approval modes (`yolo`/`auto`/`confirm`/`default`) — these work correctly and are separate
- `allowed_tools`/`disallowed_tools` resolver system — orthogonal, stays as-is
- Tool-level permission resolvers — unchanged
- Agent profile YAML in `.agents/` — generated from submodules, profile value fixes (e.g., `unrestricted` -> `none`) are a separate change
- Harness adapter `env_overrides()` method — stays, OpenCode uses it for `OPENCODE_PERMISSION`

## Migration Edge Case

`BackgroundWorkerParams` in `execute.py` is serialized to disk. Renaming `permission_tier` to `sandbox` changes the serialized field name. Any in-flight background spawns queued before the upgrade will deserialize with `sandbox=None` (Pydantic ignores unknown fields). Per CLAUDE.md: "No backwards compatibility needed," so this is acceptable.

## Design Documents

- [permissions.md](permissions.md) — target state of the permission module
- [harness-integration.md](harness-integration.md) — how harness adapters consume sandbox values
- [overrides-and-cli.md](overrides-and-cli.md) — changes to override resolution, config, and CLI

## Files Affected

### Core changes:
- `src/meridian/lib/safety/permissions.py` — remove enum, simplify PermissionConfig and resolvers
- `src/meridian/lib/core/overrides.py` — remove `KNOWN_SANDBOX_VALUES`, remove validator
- `src/meridian/lib/config/settings.py` — remove `_validate_sandbox`, remove `KNOWN_SANDBOX_VALUES` import
- `src/meridian/lib/catalog/agent.py` — remove unknown-sandbox warning and `_KNOWN_SANDBOX_VALUES` import
- `src/meridian/lib/ops/spawn/execute.py` — rename `permission_tier` to `sandbox`
- `src/meridian/cli/spawn.py` — update `--sandbox` help text

### Import-only updates (PermissionConfig.tier -> .sandbox):
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/launch/env.py`
- `src/meridian/lib/launch/command.py`

### Test updates:
- `tests/exec/test_permissions.py` — remove PermissionTier imports, update assertions
- `tests/test_launch_process.py` — TieredPermissionResolver reference
- `tests/exec/test_claude_cwd_isolation.py` — TieredPermissionResolver reference
- `tests/exec/test_signals.py` — TieredPermissionResolver reference
- `tests/exec/test_pipe_drain.py` — TieredPermissionResolver reference
- `tests/exec/test_lifecycle.py` — TieredPermissionResolver reference
