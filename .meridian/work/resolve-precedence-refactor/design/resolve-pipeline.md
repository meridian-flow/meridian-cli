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
  config_overrides = RuntimeOverrides.from_config(config)  # primary path: config.primary.*
  
  # Step 1: Load profile (needs agent from layers — agent resolved first)
  agent = first_non_none(cli.agent, env.agent, config.agent) or builtin_default
  profile = load_agent_profile(agent, ...)
  profile_overrides = RuntimeOverrides.from_agent_profile(profile)
  
  # Step 2: Build layer tuple in precedence order
  layers = (cli_overrides, env_overrides, profile_overrides, config_overrides)
  
  # Step 3: Derive harness by scanning layers (layer-aware, not merged)
  harness_id, _ = derive_harness(
      layers=layers,
      config=config,
      harness_registry=harness_registry,
      repo_root=repo_root,
      default_harness=config.default_harness,
  )
  
  # Step 4: Resolve scalar fields via standard merge (effort, sandbox, etc.)
  resolved = resolve(*layers)
  
  # Step 5: Resolve final model (apply harness-specific defaults if needed)
  final_model = resolve_final_model(
      layer_model=resolved.model,
      harness_id=harness_id,
      config=config,
      repo_root=repo_root,
  )
  
  # Step 6: Resolve adapter, skills, build ResolvedPolicies
  adapter = harness_registry.get_subprocess_harness(harness_id)
  ...
```

Note: `prepare.py` (spawn path) uses a different `from_config()` variant that reads
`config.default_*` instead of `config.primary.*`. See "Primary vs Spawn Config" below.

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

### `derive_harness()` (resolve.py) — New function, LAYER-AWARE

**Critical design point**: This function scans layers directly, NOT the pre-merged
resolved output. The pre-merged output loses which layer contributed model vs harness,
which breaks the "derived fields inherit source precedence" invariant.

```python
def derive_harness(
    *,
    layers: tuple[RuntimeOverrides, ...],
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    repo_root: Path,
    default_harness: str = "claude",
) -> tuple[HarnessId, str]:
    """Derive final harness by scanning layers in precedence order.
    
    Scans layers from highest to lowest precedence. At each layer:
    - If the layer specifies harness: return that harness immediately.
    - If the layer specifies model (but no harness): derive harness from 
      model via route_model() and return immediately.
    - If the layer specifies neither: continue to next layer.
    
    If no layer specifies either: return config.default_harness or builtin.
    
    This ensures a CLI model (-m sonnet) derives 'claude' harness and wins
    over a profile's explicit harness: codex, because the CLI layer is scanned
    first. The derived harness inherits the precedence of the model that
    produced it.
    
    Returns (harness_id, resolved_model_or_empty).
    """
    for layer in layers:
        harness = (layer.harness or "").strip()
        model = (layer.model or "").strip()
        if harness:
            # This layer explicitly sets harness — use it
            return HarnessId(harness), model
        if model:
            # This layer sets model but not harness — derive harness from model
            routed = _route_harness_for_model(model, repo_root=repo_root)
            return routed, model
    # No layer set either — use configured default
    return HarnessId(default_harness or "claude"), ""
```

This replaces lines 199-256 of resolve.py — the entire ad-hoc if/elif chain.

**Why layer-aware, not merged**: If CLI sets `-m sonnet` and profile sets
`harness: codex`, a merged resolve() produces `model="sonnet", harness="codex"`.
derive_harness would see "both set" and either error (current bug) or pick one
arbitrarily. By scanning layers, we see CLI has model (higher precedence) before
profile has harness (lower precedence), so we derive from model. The invariant
is structurally enforced.

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

Three phases, with harness derivation scanning layers directly:

```
Phase 1: Resolve agent, load profile
  - agent = first_non_none(cli.agent, env.agent, config.agent) or builtin
  - profile = load(agent)
  - profile_overrides = RuntimeOverrides.from_agent_profile(profile)
  - layers = (cli, env, profile, config)  -- in strict precedence order

Phase 2: derive_harness(layers=layers, ...)  -- LAYER-AWARE scan
  - For each layer in precedence order:
    - If layer.harness: return that harness
    - If layer.model: derive harness from model, return
    - Else: continue
  - Fallback: config.default_harness

Phase 3: resolve_final_model(layer_model=resolved.model, harness_id, config)
  - If layer_model set: resolve alias, done
  - If not: config.default_model_for_harness(harness_id) || config.default_model || ""
```

Phase 2 is the critical change. By scanning layers instead of using merged output:
- CLI `-m sonnet` derives claude harness, beats profile's `harness: codex` (CLI layer scanned first)
- Profile `harness: codex` beats config model (profile layer scanned before config)
- Config `primary.model` participates (config layer is in the stack)
- No circular dependency: harness derivation reads layers directly, model defaults come after

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

Same layer-aware pattern as plan.py, but **different config layer construction**.

Primary path uses `config.primary.*` (per-session overrides):
```python
config_overrides = RuntimeOverrides.from_config(config)  # reads config.primary.*
```

Spawn path uses `config.default_*` (spawn-level defaults):
```python
config_overrides = RuntimeOverrides.from_spawn_config(config)  # reads config.default_*
```

This distinction already exists implicitly — `prepare.py` passes `config.default_agent`
and `config.default_harness` as separate arguments. The refactor makes it explicit by
having two `from_config` variants (or a `context` parameter). The layer stack mechanics
are identical; only what the config layer contains differs.

Add `RuntimeOverrides.from_spawn_config(config)` that reads:
- `config.default_model` (not `config.primary.model`)
- `config.default_harness` (not `config.primary.harness`)
- `config.default_agent` (not `config.primary.agent`)
- Other fields from `config.primary.*` where they exist (effort, sandbox, etc.)

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
