# catalog/models — Model Resolution Pipeline

## Resolution Entry Point

`resolve_model(name_or_alias, repo_root)` in `models.py` is the single caller-facing function. Returns `AliasEntry{alias, model_id, resolved_harness, description}`. Always resolves to a concrete harness or raises `ValueError`.

### Step 1: Mars resolve (authoritative)

`run_mars_models_resolve(name)` in `model_aliases.py` calls `mars models resolve <name> --json`. Mars is the **single authority** for alias→model_id mapping and harness routing.

- `harness_source == "unavailable"` → raises `ValueError` listing installable harness candidates
- `harness` present in result → use it directly
- `harness` absent → apply pattern fallback to the resolved model ID
- Mars returns `None` (unknown alias) → fall through to step 2

Mars binary is found via `_resolve_mars_binary()`: checks same Python `scripts/` dir first, then PATH. Missing mars → `RuntimeError` (not a soft failure; mars is bundled).

### Step 2: Pattern fallback (raw model IDs only)

`pattern_fallback_harness(model_id)` in `model_policy.py` matches against `DEFAULT_HARNESS_PATTERNS`:

```python
HarnessId.CLAUDE:    ("claude-*", "opus*", "sonnet*", "haiku*")
HarnessId.CODEX:     ("gpt-*", "o1*", "o3*", "o4*", "codex*")
HarnessId.OPENCODE:  ("opencode-*", "gemini*", "*/*")
```

Exactly one pattern must match; zero or multiple → `ValueError`. The `*/*` catch-all for OpenCode is intentional to absorb provider-scoped model IDs (e.g., `google/gemini-pro`).

## AliasEntry

```python
class AliasEntry(BaseModel):
    alias: str              # empty string for raw model IDs
    model_id: ModelId
    resolved_harness: HarnessId | None   # excluded from serialization
    description: str | None              # excluded from serialization

    @property
    def harness(self) -> HarnessId:
        # returns resolved_harness if set, else pattern_fallback_harness(model_id)
```

`harness` property always returns a concrete `HarnessId`. Callers should use the property, not the field.

## Mars CLI Integration

Two commands are used:

| Function | Command | Used for |
|---|---|---|
| `run_mars_models_resolve(name)` | `mars models resolve <name> --json` | Primary resolution at spawn time |
| `_run_mars_models_list()` | `mars models list --json` | Alias listing for `meridian models list` |

`run_mars_models_resolve` raises `RuntimeError` on binary failures; returns `None` when alias is unknown (not an error — callers check return value).

`_run_mars_models_list` returns `None` on failure; callers fall back to reading `.mars/models-merged.json` directly.

## Alias Loading (`meridian models list`)

`load_mars_aliases(repo_root)` in `model_aliases.py`:
1. Tries `mars models list --json` → `_mars_list_to_entries()`
2. Falls back to `.mars/models-merged.json` → `_mars_merged_to_entries()`
3. Returns `[]` if both unavailable

The merged-file fallback only has pinned aliases (explicit `model` key). Auto-resolve aliases are skipped — they require mars to resolve dynamically against the models cache.

## models.dev Discovery Cache

`load_discovered_models(cache_dir, force_refresh)` in `models.py` maintains a 24-hour TTL cache at `.meridian/cache/models.json`. Only used for `meridian models list` display metadata (cost, context, release date). **Not involved in spawn-time resolution.**

`fetch_models_dev()` hits `https://models.dev/api.json`, filters to `tool_call`-capable models only, maps providers: anthropic→Claude, openai→Codex, google→OpenCode.

Cache is written atomically via `atomic_write_text`. Stale/missing cache → re-fetch; fetch failure with stale cache → serve stale with a warning.

## Visibility Policy

`is_default_visible_model()` and `ModelVisibilityConfig` in `model_policy.py` control which discovered models appear in `meridian models list` by default:

- Excludes `*-latest`, `*-deep-research`, `gemini-live-*`, `o1*`, `o3*`, `o4*`
- Excludes models older than 120 days (`max_age_days`)
- Excludes models with `cost_input >= $10/M` (`max_input_cost`)
- Hides date-variant models when the non-dated version exists (e.g., `claude-3-5-sonnet-20241022` hidden when `claude-3-5-sonnet` exists)
- Hides superseded models within the same provider+lineage group

Pinned aliases always show regardless. No user-override surface exists currently (was in `models.toml`; that's gone).

`compute_superseded_ids(models)` groups models by `(provider, lineage)`, computes lineage by stripping version numbers and date suffixes. Within each group, all except the newest (by release_date, then shorter ID) are superseded.

## What Was Removed

Previously meridian had its own internal routing:
- `models_toml.py` / `models_config.py` — TOML-based model routing config
- `models_config_cmd.py` — `meridian models config` CLI surface
- `HarnessRegistry.route()` — registry-level routing method
- `harness_patterns` config surface — user-configurable patterns

All deleted. Mars is now sole authority. No migration needed (no real users).

## Why This Design

**Mars as single authority**: Moving alias→harness routing out of meridian means meridian has no model list to maintain. New models come from mars package updates, not meridian source edits. Enables per-project model customization without touching meridian config.

**Pattern fallback for raw IDs**: Users pass raw model IDs without defining aliases. Patterns handle this without requiring mars to enumerate every possible model ID.

**No builtin aliases**: Meridian has zero internal alias definitions. `model_aliases.py` comment is explicit: "all aliases come from mars dependency packages."
