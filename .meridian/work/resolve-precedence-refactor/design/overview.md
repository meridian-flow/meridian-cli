# Resolve Precedence Refactor: Design Overview

## Problem

The resolve pipeline has two separate resolution mechanisms:

1. **`RuntimeOverrides.resolve()`** — clean layered first-non-None for scalar fields (effort, sandbox, approval, autocompact, timeout). Works correctly.
2. **Ad-hoc if/elif chains in `resolve_policies()`** — handles model, harness, and agent. Violates the precedence invariant in multiple ways (see requirements.md).

The root cause: model/harness resolution was built as procedural logic with implicit ordering, rather than as a declarative layer stack with a generic merge.

## Invariant

```
CLI override > ENV > profile > project config > user config > builtin default
```

Derived fields (harness from model) inherit the precedence of their source.

## Approach: Unified Layer Stack with Two-Phase Resolution

Extend the existing `RuntimeOverrides` pattern to cover ALL resolvable fields uniformly, then add a second derivation pass for dependent fields.

### Phase 1: Resolve Primary Fields

All sources produce the same `RuntimeOverrides` shape. A single `resolve(*layers)` call merges them with first-non-None semantics in strict precedence order. This already works for effort/sandbox/etc. The change is to **actually pass all layers into `resolve_policies()`** and use the resolved result for model selection too.

Currently, `plan.py` does:
```python
pre_resolved = resolve(cli_overrides, env_overrides)  # excludes config!
policies = resolve_policies(..., overrides=pre_resolved, ...)
# Inside resolve_policies: ad-hoc model/harness resolution
```

After refactor:
```python
all_layers = (cli_overrides, env_overrides, profile_overrides, config_overrides)
resolved = resolve(*all_layers)
# resolved.model, resolved.harness now follow correct precedence
```

The challenge: **profile_overrides aren't known until the profile is loaded**, and which profile to load may depend on config. So resolution happens in two steps:

1. **Load profile**: Use agent from CLI > ENV > config > builtin default (simple first-non-None on agent field only)
2. **Resolve all fields**: `resolve(cli, env, profile, config)` for model, harness, effort, etc.

### Phase 2: Derive Dependent Fields

After all primary fields are resolved, derive dependent fields:

- If `resolved.harness` is set (explicitly by some layer): validate it's compatible with `resolved.model`
- If `resolved.harness` is None but `resolved.model` is set: derive harness from model via `route_model()`
- If neither is set: use `config.default_harness` builtin

This is a pure function: `derive_harness(resolved_model, resolved_harness, config) -> HarnessId`. It runs once, after resolution, and cannot violate precedence because it only fills in what wasn't explicitly set.

### Why Not Build Something New?

The `RuntimeOverrides` + `resolve()` pattern already works. It's tested, understood, and handles the hard parts (validation, normalization, first-non-None merge). Building a new resolution framework would be more work and more risk for no additional capability.

## Changes by File

### `overrides.py` — Minimal changes
- Add `agent` field to `RuntimeOverrides` (currently agent resolution is outside the override system)
- Fix `from_launch_request()` to preserve `approval="default"` as a real value (violation #7)
- No structural changes needed — the `resolve()` function is already correct

### `resolve.py` — Core refactor
- **Delete** the ad-hoc if/elif chain in `resolve_policies()` for model/harness
- **Add** `derive_harness()` function: takes resolved model + resolved harness + config, returns final HarnessId
- **Refactor** `resolve_policies()` signature: accept the full list of `RuntimeOverrides` layers instead of a pre-merged `overrides` parameter
- Move config default model into the layer stack (it belongs in `config_overrides`, not as a post-hoc fallback)

### `plan.py` / `prepare.py` — Caller simplification
- Delete the split between `pre_resolved` and `resolved` — there's only one resolution pass now
- Profile loading moves before `resolve_policies()` (it already effectively does, but the flow becomes clearer)
- Config overrides participate in model/harness resolution (fixing violations #1, #2, #3)

### `settings.py` — No changes
- pydantic-settings source ordering is already correct
- `default_model_for_harness()` still needed for the derivation phase

## Key Design Decisions

### Agent field in RuntimeOverrides
Agent resolution currently lives outside the override system. Adding it to `RuntimeOverrides` means the same first-non-None mechanism handles agent precedence, eliminating violation #4 (`primary.agent` being dead).

### Config default model as a layer vs. fallback
Currently `config.default_model` is applied as a post-hoc fallback after harness resolution. In the new design, `RuntimeOverrides.from_config()` already reads `config.primary.model` — we just need to ensure the harness default model (`config.default_model_for_harness()`) is also accessible. This goes into the derivation phase, not the layer stack, because it depends on the resolved harness (a derived field).

### Approval "default" sentinel
`from_launch_request` currently maps `approval="default"` to `None`, making it invisible. Fix: use `"default"` as a real value that propagates through layers. The harness adapter already understands `"default"` — it's the only consumer that needs to distinguish "not set" from "explicitly default".

### Harness-model compatibility validation
Currently scattered across resolution. In the new design, validation happens exactly once in `derive_harness()`, after both model and harness are resolved. If both are explicitly set and incompatible, error. If only model is set, derive harness. If only harness is set, no validation needed (model may come from harness default).

## What This Doesn't Change

- `MeridianConfig` and pydantic-settings loading — already correct
- `RuntimeOverrides` field set and validation — already correct  
- How skills are resolved — orthogonal to precedence
- How permissions/approval are applied — downstream of resolution
- The `ResolvedPolicies` return type — same shape, different internals

## Migration

This is internal refactoring. No config format changes, no CLI flag changes, no profile format changes. Existing tests should pass (or fail in ways that reveal they were testing buggy behavior). New tests should verify:

1. `-m sonnet` on a codex-profiled agent derives claude harness (not codex)
2. `config.primary.model` actually takes effect when no CLI/env/profile model is set
3. `config.primary.agent` participates in agent resolution
4. `--approval default` overrides profile approval
5. Config default harness is used when no model or harness is specified anywhere
