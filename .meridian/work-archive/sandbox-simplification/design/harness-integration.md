# Harness Integration

## Current State

Each harness adapter receives permissions through two paths:
1. `build_command(run, perms)` — `perms.resolve_flags(harness_id)` returns CLI flags
2. `env_overrides(config)` — returns env vars (only OpenCode uses this, for `OPENCODE_PERMISSION`)

The `permission_flags_for_harness()` function currently translates `PermissionTier` enum values to harness-specific flags. In practice:

| Harness  | Uses sandbox flags? | Uses env vars? | Notes |
|----------|-------------------|----------------|-------|
| Codex    | Yes: `--sandbox <value>` | No | Only harness that uses sandbox |
| Claude   | No (returns `[]`) | No | Uses approval modes only |
| OpenCode | No (returns `[]`) | Yes: `OPENCODE_PERMISSION` | Per-tool JSON, not sandbox |

## Target State

No changes to the harness adapter interface. The change is entirely in `permission_flags_for_harness()`:

- **Codex**: `["--sandbox", config.sandbox]` when `config.sandbox` is set. The string passes through verbatim — if it's `workspace-write`, Codex gets `--sandbox workspace-write`. If it's `none` (a Codex-native value), Codex gets `--sandbox none`.
- **Claude**: Still returns `[]` for sandbox (approval flags handle Claude's permission model).
- **OpenCode**: Still returns `[]` for sandbox (tool-level JSON handles OpenCode's permission model).

## Adapter `env_overrides()` Method

Unchanged. `PermissionConfig` still carries `opencode_permission_override`, and `OpenCodeAdapter.env_overrides()` still reads it. The field rename from `tier` to `sandbox` doesn't affect this — `env_overrides` reads `opencode_permission_override`, not `tier`.

## `build_harness_command()` in `common.py`

Unchanged. It calls `perms.resolve_flags(harness_id)` and appends the result. The resolver is the only thing that changes (it reads `config.sandbox` instead of `config.tier.value`).

## Harness-Specific Sandbox Values

After this change, valid sandbox values depend on the target harness. The known Codex sandbox values are:
- `read-only` — read filesystem, no writes
- `workspace-write` — write within project dir
- `full-access` — full filesystem access
- `danger-full-access` — full access including network
- `none` — no sandbox

Meridian no longer validates against this set. Codex validates its own inputs. If a profile sets `sandbox: none` and targets Codex, it works. If it sets `sandbox: unrestricted` and targets Codex, Codex rejects it at launch — which is the correct behavior (fail fast at the harness, not silently translate at the coordinator layer).

## Impact on `disallowed_tools` Codex Fallback

`DisallowedToolsResolver.resolve_flags()` falls back to `permission_flags_for_harness(harness_id, self.fallback_config)` for Codex (since Codex doesn't support per-tool denylists). This still works — the fallback config now carries `sandbox: str | None` instead of `tier: PermissionTier | None`, but the codepath is identical.
