# Model Discovery Overhaul

**Status:** completed (Steps 1-7, 2026-03-06)

## Summary

Replace the hardcoded 6-model catalog with:
1. **Live model discovery** via `models.dev/api.json` (public, no auth, rich metadata)
2. **Alias-only config** — `.meridian/models.toml` becomes a pure alias table
3. **Built-in aliases** shipped as a TOML file with the package
4. **Routing unchanged** — prefix-based matching stays as-is

## Context: Current System (What's Wrong)

**`catalog.py`** hardcodes 6 models with metadata (role, strengths, cost_tier, aliases). Goes stale.

**`routing.py`** does prefix matching (`claude-*`→claude, `gpt-*`→codex, `gemini-*`→opencode). Works on *any* model string — doesn't need the catalog.

**`settings.py`** has `HarnessConfig` with default models per harness + global `default_model`.

The catalog conflates "available models" (should be dynamic) with "aliases" (user config). The real value is aliases; metadata should come from a live source.

## Design

### Layer 1: Routing (unchanged)
`routing.py` — prefix matching routes any model string to a harness. This is the source of truth for "what harness runs this model."

### Layer 2: Model Discovery (new)
New module: `src/meridian/lib/config/discovery.py`
- Fetches `https://models.dev/api.json`
- Filters by relevant providers: `anthropic`, `openai`, `google`
- Maps provider → harness: anthropic→claude, openai→codex, google→opencode
- Caches locally in `.meridian/cache/models.json` with TTL (24h)
- Returns structured model entries with: id, name, family, cost, context limits, capabilities
- Graceful degradation: if fetch fails and no cache, return empty (routing still works)

### Layer 3: Aliases (replaces catalog)
**Built-in aliases**: shipped as `src/meridian/resources/default-aliases.toml`
```toml
[aliases]
opus = "claude-opus-4-6"
sonnet = "claude-sonnet-4-6"
haiku = "claude-haiku-4-5"
codex = "gpt-5.3-codex"
gpt52h = "gpt-5.2-high"
gemini = "gemini-3.1-pro"
```

**User aliases**: `.meridian/models.toml` (same format, overrides built-in)
```toml
[aliases]
opus = "claude-opus-4-6"     # override built-in
fast = "claude-haiku-4-5"    # add new alias
```

Optional metadata per alias (for model guidance):
```toml
[aliases.opus]
model_id = "claude-opus-4-6"
role = "Default / all-rounder"
strengths = "Best primary agent brain"
```

### Layer 4: CLI Commands
`meridian models list` — shows discovered models from models.dev + aliases
`meridian models show <id-or-alias>` — shows model detail (from models.dev + alias info)
`meridian models refresh` — force refresh the models.dev cache

## Implementation Steps

### Step 1: Create discovery module
New file: `src/meridian/lib/config/discovery.py`
- `DiscoveredModel` dataclass: id, name, family, provider, harness, cost_input, cost_output, context_limit, output_limit, capabilities
- `fetch_models_dev()` — HTTP GET to models.dev, parse JSON, filter providers
- `load_discovered_models(cache_dir)` — load from cache or fetch, with TTL
- `refresh_models_cache(cache_dir)` — force fetch + cache
- Provider→harness mapping: anthropic→claude, openai→codex, google→opencode
- Filter out non-coding models (embeddings, TTS, etc.) by checking `tool_call` capability

### Step 2: Create default aliases file
New file: `src/meridian/resources/default-aliases.toml`
- Ship the current 6 aliases as defaults
- Pure TOML, no Python

### Step 3: Refactor catalog.py → aliases.py
- Rename file to `aliases.py` (or keep `catalog.py` name and gut it)
- `AliasEntry` dataclass: alias, model_id, role?, strengths?
- `load_builtin_aliases()` — read from `resources/default-aliases.toml`
- `load_user_aliases(repo_root)` — read from `.meridian/models.toml`
- `load_merged_aliases()` — built-in + user, user wins
- `resolve_alias(name)` → model_id
- Keep backward compat: `resolve_model()` function signature stays, but internals change

### Step 4: Update models ops + CLI
- `meridian models list` — merge discovered models + aliases into unified view
- `meridian models show` — show model detail from discovery + alias info
- Add `meridian models refresh` command
- Update `ModelsListOutput` / `CatalogModel` types

### Step 5: Update consumers
- `_spawn_prepare.py` — uses `resolve_model()` (should just work if we keep the function)
- `settings.py` — `HarnessConfig` default models stay, alias resolution unchanged
- `_spawn_prepare.py::_model_validation_context` — update to use discovered models for suggestions
- `config.py` — references to catalog entries → alias entries

### Step 6: Update/add tests
- Test discovery with mocked HTTP
- Test alias loading (built-in, user, merged)
- Test resolve_model still works
- Test graceful degradation (no network, no cache)

### Step 7: Clean up
- Remove `builtin_model_catalog()` function
- Remove `CatalogModel` (or rename to `AliasEntry`)
- Update model guidance to use models.dev metadata instead of hardcoded strings
- Update state paths if needed for cache directory

## Files Modified
- `src/meridian/lib/config/catalog.py` → gut/refactor to alias-only
- `src/meridian/lib/config/discovery.py` → NEW
- `src/meridian/resources/default-aliases.toml` → NEW
- `src/meridian/lib/ops/models.py` → update for new types
- `src/meridian/cli/models_cmd.py` → add refresh command
- `src/meridian/lib/ops/_spawn_prepare.py` → update model validation context
- `src/meridian/lib/config/settings.py` → minimal changes (HarnessConfig stays)
- `src/meridian/lib/state/paths.py` → add cache_dir path
- Tests: new + updated

## Files NOT Modified
- `src/meridian/lib/config/routing.py` — unchanged
- Harness adapters — unchanged
- `src/meridian/lib/harness/registry.py` — unchanged

## Open Questions
- Should `meridian models list` default to showing aliases-only (fast, no network) with a `--all` flag for full discovery? Or default to full discovery?
- Cache location: `.meridian/cache/models.json` in repo root? Or user-level `~/.meridian/cache/`?
- Should we filter models.dev to only coding-capable models (tool_call=true)? Probably yes.
