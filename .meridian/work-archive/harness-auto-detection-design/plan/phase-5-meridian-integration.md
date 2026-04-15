# Phase 5: Meridian Integration — Accept model_id Field

## Scope

Minimal Python change: accept `model_id` as a field name alongside `resolved_model` in the mars JSON parsing. This is the only meridian change needed — the existing harness fallback routing already handles null-harness aliases correctly.

## Files to Modify

**`/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/models/model_aliases.py`**:

1. In the `_mars_list_to_entries()` function (or equivalent function that parses `mars models list --json` output), find the line that reads `resolved_model` from the JSON dict and update it to also accept `model_id`:

   ```python
   # Accept both field names (mars v1 uses resolved_model, v2 uses model_id)
   resolved_model = item.get("model_id") or item.get("resolved_model")
   ```

   This is a one-line change. The `or` fallback ensures both old and new mars output works.

2. **Do NOT** add any filtering based on `harness_source` or `harness: null`. Per D12, meridian keeps all aliases and uses its own `model_policy.py` routing as the authoritative fallback.

## Dependencies

- **Requires:** Phase 3 complete (so mars actually outputs `model_id` field).
- **Independent of:** Phase 4 (CLI formatting doesn't affect meridian's JSON parsing).

## Constraints

- **No changes to `model_policy.py`** (D7) — meridian's existing routing stays as-is.
- **No changes to `resolve.py`** — the fallback chain is already correct.
- **Keep null-harness aliases** (D12) — do NOT skip them.

## Verification Criteria

- [ ] `uv run pyright` passes (in meridian-channel repo)
- [ ] `uv run ruff check .` passes
- [ ] Manually verify: parse a JSON blob with `model_id` field → alias entry created
- [ ] Manually verify: parse a JSON blob with `resolved_model` field → still works (backwards compat)
- [ ] Manually verify: parse a JSON blob with `harness: null` → alias entry created (not skipped)
