# Meridian Integration

## Current State

Meridian already handles harness resolution gracefully when mars doesn't provide one:

1. **`model_aliases.py`**: `AliasEntry.harness` property falls back to `route_model_with_patterns()` when `resolved_harness` is `None`.
2. **`model_policy.py`**: `DEFAULT_HARNESS_PATTERNS` maps model ID patterns to harnesses (e.g., `claude-*` → claude harness).
3. **`resolve.py`**: `resolve_policies()` has a full fallback chain: explicit harness → profile harness → model-based routing → config default.

This means **meridian needs minimal changes**. The main improvement is consuming the richer mars resolve output.

## Changes to `model_aliases.py`

### `_mars_list_to_entries` — Consume new fields

The `mars models list --json` output now includes `provider`, `harness_source`, and `harness_candidates`. Meridian should:

1. **Use `harness`** from mars JSON when present (already does this).
2. **Accept `model_id` field name** alongside existing `resolved_model` for forward compatibility.
3. **Keep aliases with `harness: null`** — do NOT skip them. Meridian's own routing in `model_policy.py` can resolve the harness from the model ID. Skipping them would break `meridian spawn -m opus` when mars reports the alias as "unavailable" (e.g., because the user's mars binary runs in a different environment than meridian).

```python
def _mars_list_to_entries(aliases_list: list[dict[str, object]]) -> list[AliasEntry]:
    entries: list[AliasEntry] = []
    for item in aliases_list:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        # Accept both field names (mars v1 uses resolved_model, v2 uses model_id)
        resolved_model = item.get("model_id") or item.get("resolved_model")
        harness = item.get("harness")
        description = item.get("description")

        # Skip aliases that didn't resolve to a concrete model ID
        if not isinstance(resolved_model, str) or not resolved_model.strip():
            continue

        # harness can be None (unavailable) — that's fine, meridian routing handles it
        entries.append(entry(
            alias=name.strip(),
            model_id=resolved_model.strip(),
            harness=str(harness) if isinstance(harness, str) else None,
            description=str(description) if isinstance(description, str) else None,
        ))
    return entries
```

### `_mars_merged_to_entries` — Handle missing harness

The `models-merged.json` file may now have aliases without a `harness` field. No change needed — the code already treats `harness` as optional.

## Changes to `resolve.py`

### No changes needed

The `resolve_policies` function already handles the full fallback chain. When mars provides a harness, it flows through `AliasEntry.resolved_harness`. When mars doesn't, `AliasEntry.harness` property falls back to `model_policy.py` routing.

## Key Design Choice: Don't Skip Null-Harness Aliases

A previous version of this design said to skip aliases with `harness: null`. This was incorrect because:

1. **`meridian spawn -m opus`** would fail with "unknown alias" instead of "known alias, resolving harness via routing". The alias is valid — it just couldn't auto-detect a harness in the mars environment.
2. **Meridian's routing is the authoritative fallback.** Mars auto-detection is an improvement, not a gate. If mars can't detect a harness, meridian can still route based on model ID patterns.
3. **Environment differences.** Mars might report `harness: null` because it doesn't see a binary that meridian's harness registry knows about (e.g., direct API harness).

## Summary of Meridian Changes

| File | Change | Risk |
|------|--------|------|
| `model_aliases.py` | Accept `model_id` field name alongside `resolved_model` | Low — additive |
| `model_aliases.py` | Keep null-harness aliases (no skip) | Low — preserves existing behavior |
| Everything else | No changes | None |

Meridian's existing `model_policy.py` routing remains the authoritative fallback for harness resolution. Mars auto-detection improves the mars standalone experience but doesn't gate meridian's resolution path.
