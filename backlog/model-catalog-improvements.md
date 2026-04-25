# Model Catalog Improvements

## ~~1. Auto-resolve default aliases to latest model per family~~ (done)

Builtin aliases are now derived from the models.dev catalog at runtime, picking the latest model per alias family by `release_date`. Hardcoded fallbacks used only when cache is unavailable. User auto-resolve specs supported in `models.toml`. `default-aliases.toml` deleted.

## 2. CLI for managing models.toml

**Current:** Users must manually edit `.meridian/models.toml` to set aliases, roles, strengths. No CLI support.

**Proposed:**
```bash
meridian models describe codex --role "primary code implementer" --strengths "fast, structured edits"
meridian models alias mymodel gpt-5.4
meridian models unalias mymodel
```

Writes to `.meridian/models.toml`. Follows existing manifest-driven CLI pattern (`models_cmd.py`).

## ~~3. Model filtering (include/exclude)~~ (done)

All visibility settings are user-configurable in `[model_visibility]` section of `models.toml`: `include`, `exclude`, `hide_date_variants`, `hide_superseded`, `max_age_days`, `max_input_cost`. Defaults: 120-day window, hide superseded models, hide date variants. Aliased models always pass through. CLI flags: `--show-superseded`, `--all`.

## 4. Skill for model management

Add a skill in `meridian-base/` teaching agents how to manage models, aliases, descriptions, and filtering via CLI. Replace hardcoded model names in skills (like `review-orchestration`) with references to `meridian mars models list`.

## 5. Fix review-orchestration model references

`meridian-dev-workflow/skills/review-orchestration/SKILL.md` lists specific model names (gpt-5.4, opus, gpt-5.3-codex) in the Model Selection section. Replace with characteristic-based guidance and point to `meridian mars models list`. Same pattern: guidance should describe model characteristics and point to `meridian mars models list` instead of hardcoding model IDs.

## ~~6. Fix docs drift~~ (done)

`docs/configuration.md` updated with current `[aliases]` format, auto-resolve specs, and full visibility settings table.

## Research notes

- Models discovered from `https://models.dev/api.json` (providers: anthropic, openai, google)
- Only models with `tool_call` capability are kept
- Cache: `.meridian/cache/models.json`, 24h TTL
- Alias resolution: builtins loaded first, user `models.toml` overwrites by alias key
- `resolve_model()` chain: exact alias lookup → direct model ID → route_model validation
- Key files: `src/meridian/lib/catalog/models.py`, `src/meridian/lib/ops/catalog.py`, `src/meridian/cli/models_cmd.py`
