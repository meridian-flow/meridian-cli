# Resolve Pipeline: Detailed Design

## Current Flow (Buggy)

```
plan.py:
  cli_overrides = RuntimeOverrides.from_launch_request(request)
  env_overrides = RuntimeOverrides.from_env()
  config_overrides = RuntimeOverrides.from_config(config)
  pre_resolved = resolve(cli_overrides, env_overrides)       # <-- config excluded!
  
  policies = resolve_policies(overrides=pre_resolved, ...)   # <-- ad-hoc model/harness
  
  profile_overrides = RuntimeOverrides.from_agent_profile(profile)
  resolved = resolve(cli, env, profile, config)              # <-- used only for effort/etc.
```

Problems:
- `resolve_policies()` receives only CLI+ENV, never sees config model/harness
- Model/harness resolved via if/elif inside `resolve_policies()`, not via layer merge
- Harness locked in before config default model is even considered
- Two separate `resolve()` calls with different layer sets

## Target Flow

```
plan.py:
  cli_overrides = RuntimeOverrides.from_launch_request(request)
  env_overrides = RuntimeOverrides.from_env()
  config_overrides = RuntimeOverrides.from_config(config)
  
  # Step 1: Load profile (needs agent from layers)
  agent = first_non_none(cli.agent, env.agent, config.agent) or builtin_default
  profile = load_agent_profile(agent, ...)
  profile_overrides = RuntimeOverrides.from_agent_profile(profile)
  
  # Step 2: Single resolution pass — all fields, all layers, correct order
  resolved = resolve(cli_overrides, env_overrides, profile_overrides, config_overrides)
  
  # Step 3: Derive dependent fields
  harness_id = derive_harness(
      explicit_model=resolved.model,
      explicit_harness=resolved.harness,
      config=config,
      harness_registry=harness_registry,
      repo_root=repo_root,
  )
  
  # Step 4: Resolve adapter, skills, build ResolvedPolicies
  adapter = harness_registry.get_subprocess_harness(harness_id)
  ...
```

## Key Functions

### `resolve()` (overrides.py) — No change needed

```python
def resolve(*layers: RuntimeOverrides) -> RuntimeOverrides:
    """Merge layers with first-non-none precedence."""
    resolved: dict[str, object] = {}
    for field_name in RuntimeOverrides.model_fields:
        for layer in layers:
            value = getattr(layer, field_name)
            if value is not None:
                resolved[field_name] = value
                break
    return RuntimeOverrides.model_validate(resolved)
```

Already generic. Works for any field on RuntimeOverrides.

### `derive_harness()` (resolve.py) — New function

```python
def derive_harness(
    *,
    explicit_model: str | None,
    explicit_harness: str | None,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    repo_root: Path,
    default_harness: str = "claude",
) -> tuple[HarnessId, str | None]:
    """Derive final harness from resolved fields. Returns (harness_id, warning).
    
    Rules:
    1. If explicit_harness is set: use it. Validate against model if model also set.
    2. If only model is set: derive harness from model via route_model().
    3. If neither: use config.default_harness or builtin default.
    
    Harness-specific default model (config.default_model_for_harness) is NOT
    applied here — that's a model default, resolved during the model derivation
    step when the final harness is known.
    """
```

This replaces lines 199-256 of resolve.py — the entire ad-hoc if/elif chain.

### `resolve_final_model()` (resolve.py) — New function

```python
def resolve_final_model(
    *,
    layer_model: str | None,
    harness_id: HarnessId,
    config: MeridianConfig,
    repo_root: Path,
) -> str:
    """Apply harness-specific and global model defaults after harness is known.
    
    Precedence:
    1. layer_model (already resolved from CLI > ENV > profile > config.primary.model)
    2. config.default_model_for_harness(harness_id)
    3. config.default_model
    4. "" (empty — adapter will use its own default)
    """
```

This replaces lines 233-248 of resolve.py.

### Updated `resolve_policies()` signature

```python
def resolve_policies(
    *,
    repo_root: Path,
    layers: tuple[RuntimeOverrides, ...],   # <-- replaces single 'overrides'
    profile: AgentProfile | None,           # <-- pre-loaded
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    configured_default_harness: str = "claude",
    skills_readonly: bool = True,
) -> ResolvedPolicies:
```

Or alternatively, keep the `overrides` parameter but require callers to pass the full merged result. The key change is that the caller controls the layer stack and `resolve_policies()` doesn't do its own ad-hoc resolution.

## RuntimeOverrides Changes

### Add `agent` field

```python
class RuntimeOverrides(BaseModel):
    model: str | None = None
    harness: str | None = None
    agent: str | None = None      # <-- NEW
    effort: str | None = None
    sandbox: str | None = None
    approval: str | None = None
    autocompact: int | None = None
    timeout: float | None = None
```

Update factory methods:
- `from_launch_request()`: read `request.agent`
- `from_env()`: read `MERIDIAN_AGENT` env var
- `from_config()`: read `config.primary.agent`
- `from_agent_profile()`: no agent field (profile IS the agent, doesn't override itself)
- `from_spawn_input()`: read `payload.agent`

### Fix approval="default"

```python
@classmethod
def from_launch_request(cls, request: LaunchRequest) -> RuntimeOverrides:
    return cls(
        ...
        approval=request.approval if request.approval else None,  # <-- was != "default"
        ...
    )
```

Wait — this needs more thought. The CLI default for `--approval` is `"default"`. If the user doesn't pass `--approval`, the value is still `"default"`. We need to distinguish "user explicitly passed `--approval default`" from "user didn't pass `--approval` at all."

**Solution**: Change the CLI default for `--approval` from `"default"` to `None`. When `None`, it means "not specified." When `"default"`, it means explicitly requested. This is a CLI-layer change, not a resolve-layer change.

If changing the CLI default isn't feasible (backwards compat), keep the current behavior and document it as a known limitation. The `--approval default` use case is edge-case — users rarely want to explicitly reset to default.

## Derivation Order

The two-phase approach means:

```
Phase 1: resolve(cli, env, profile, config) → resolved
  - resolved.model: first non-None across layers (may be None)
  - resolved.harness: first non-None across layers (may be None)
  - resolved.agent: first non-None across layers (used earlier for profile loading)
  - resolved.effort, .sandbox, .approval, etc.

Phase 2: derive_harness(resolved.model, resolved.harness, config)
  - If both set: validate compatibility
  - If only model: derive harness from model
  - If only harness: keep it
  - If neither: config.default_harness

Phase 3: resolve_final_model(resolved.model, harness_id, config)
  - If model set: resolve alias, done
  - If model not set: config.default_model_for_harness(harness_id) || config.default_model
```

This ensures:
- A CLI `-m sonnet` always beats a profile harness (harness derived from model)
- A config `primary.model` participates in resolution (it's in the layer stack)
- Harness derivation sees the fully-resolved model, not a partial one
- Config default model is applied after harness is known (for harness-specific defaults)

## Caller Impact

### `plan.py` (resolve_primary_launch_plan)

Before: 
- Creates `pre_resolved` without config, calls `resolve_policies()`, then creates full `resolved` separately
- Two resolution passes with different semantics

After:
- Loads profile using resolved agent
- Single `resolve()` call with all four layers
- Passes resolved + profile to `resolve_policies()` (or inlines the logic)
- `resolve_policies()` becomes simpler — just derivation + adapter lookup + skills

### `prepare.py` (spawn prepare)

Same pattern as plan.py. Currently mirrors the same bugs. After refactor, mirrors the same fix.

## Edge Cases

### Model alias resolution timing
`resolve_model()` (catalog lookup) currently happens inside `resolve_policies()`. It should happen in `resolve_final_model()` — after all layers are merged but before harness derivation uses the model. Actually, harness derivation needs the resolved model to route correctly, so alias resolution must happen between Phase 1 and Phase 2.

Revised order:
1. `resolve(cli, env, profile, config)` → raw resolved
2. Resolve model alias: `resolved.model` → canonical model ID
3. `derive_harness(canonical_model, resolved.harness, ...)` → harness_id  
4. `resolve_final_model(canonical_model, harness_id, ...)` → final model (fills defaults)

### Profile with harness but no model
A profile specifying `harness: codex` but no model should use the codex harness and let the codex adapter pick its default model. The new design handles this: `resolved.harness = "codex"`, `resolved.model = None`, derivation keeps codex, final model comes from `config.default_model_for_harness("codex")`.

### Config model + no harness anywhere
`config.primary.model = "sonnet"`, no harness specified anywhere. New design: `resolved.model = "sonnet"`, `resolved.harness = None`, derivation derives harness from sonnet → claude. Correct.
