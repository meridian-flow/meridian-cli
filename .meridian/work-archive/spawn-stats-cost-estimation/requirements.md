# Spawn Stats Cost Estimation

## Problem
Codex (and potentially other harnesses) report token counts but not cost. This leaves ~500 spawns with no cost data in `spawn stats`. The pricing data exists in the models.dev catalog (already cached locally) — we just need to connect the dots.

## Requirements

### 1. Extract cached_input_tokens
Codex reports `cached_input_tokens` in `turn.completed` events (see `.meridian/spawns/p2/output.jsonl`). Currently ignored by `common.py` extraction.

- Add `cached_input_tokens` to `TokenUsage` model
- Extract from harness output alongside existing token fields
- Key names to search: `cached_input_tokens`, `cached_tokens`, `cache_read_input_tokens`

### 2. Calculate cost from tokens at display time
When `total_cost_usd` is null but tokens are present, compute estimated cost using models.dev pricing.

- Look up model in `load_discovered_models()` cache — `DiscoveredModel.cost_input` and `cost_output` are per-million-token rates
- Formula: `(input_tokens - cached_input_tokens) * cost_input/1M + cached_input_tokens * cached_rate/1M + output_tokens * cost_output/1M`
- Cached rate: use 50% of input rate as default (standard OpenAI/Anthropic discount). Could make configurable later.
- Mark estimated costs distinctly (e.g., `~$0.45` with tilde prefix) so users know it's calculated vs harness-reported

### 3. Where to calculate
At display time in `spawn_stats_sync`, not at finalize time. Reasons:
- Pricing changes — display-time calculation uses latest cached rates
- No schema migration needed for existing spawns
- Keeps finalize path simple

### 4. Report tokens in stats output
Add `input_tokens` and `output_tokens` totals to `SpawnStatsOutput.format_text()` and per-model breakdown. Currently only cost is shown, but tokens are the underlying data and useful on their own.

## Key Files
- `src/meridian/lib/harness/common.py` — token/cost extraction, `TOKEN_KEY_PAIRS`, `COST_KEYS`
- `src/meridian/lib/core/domain.py` — `TokenUsage` model
- `src/meridian/lib/catalog/models.py` — `DiscoveredModel` with `cost_input`/`cost_output`, `load_discovered_models()`
- `src/meridian/lib/ops/spawn/api.py` — `spawn_stats_sync` where calculation would go
- `src/meridian/lib/ops/spawn/models.py` — `SpawnStatsOutput`, `ModelStats` formatting

## Evidence
```
# Codex output.jsonl shows:
{"type":"turn.completed","usage":{"input_tokens":34664,"cached_input_tokens":29312,"output_tokens":784}}

# models.dev pricing (cached in .meridian/cache/models.json):
{"id": "gpt-5.2-codex", "cost_input": 1.75, "cost_output": 14.0}  # per million tokens
```
