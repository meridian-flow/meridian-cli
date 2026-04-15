# Phase 1: Schema Changes — Optional Harness + Provider on Pinned

## Scope

Make `harness` optional in `ModelAlias` and add `provider: Option<String>` to `ModelSpec::Pinned`. Update all deserialization, serialization, constructors, and tests to handle these changes. This is pure data model work — no new behavior yet.

## Files to Modify

All changes are in **`/home/jimyao/gitrepos/mars-agents/`**:

### `src/models/mod.rs`

1. **`ModelAlias` struct** (line 25): Change `harness: String` → `harness: Option<String>`. Add `#[serde(skip_serializing_if = "Option::is_none")]`.

2. **`ModelSpec::Pinned` variant** (line 37): Add `provider: Option<String>` field.

3. **`ModelSpec` Serialize impl** (line 48): For `Pinned`, serialize `provider` when `Some`:
   ```rust
   ModelSpec::Pinned { model, provider } => {
       let mut count = 1;
       if provider.is_some() { count += 1; }
       let mut map = serializer.serialize_map(Some(count))?;
       map.serialize_entry("model", model)?;
       if let Some(p) = provider {
           map.serialize_entry("provider", p)?;
       }
       map.end()
   }
   ```

4. **`RawModelAlias` struct** (line 80): Change `harness: String` → `harness: Option<String>`. The `provider` field already exists and is already `Option<String>` — no change needed there.

5. **`ModelAlias::deserialize` impl** (line 96): 
   - `raw.harness` is now `Option<String>` — pass directly to `ModelAlias { harness: raw.harness, ... }`.
   - When building `ModelSpec::Pinned`, include provider: `ModelSpec::Pinned { model, provider: raw.provider }`.
   - When building `ModelSpec::AutoResolve`, provider is still required (the `ok_or_else` stays).

6. **`builtin_aliases()` function** (line 423): Change `harness` param from `&str` to `None` in the closure. All builtins get `harness: None`. Remove the `harness` parameter from the inner `add` closure entirely.

7. **`resolve_all()` function** (line 541): Update the `Pinned` match arm to destructure the new field: `ModelSpec::Pinned { model, provider: _ }` (provider unused in this phase — Phase 3 will use it).

8. **`infer_provider_from_model_id()` function**: Add this new function (from design doc) after `resolve_all`. It's used in Phase 3 but defining it here keeps the data model complete:
   ```rust
   fn infer_provider_from_model_id(model_id: &str) -> Option<&'static str> {
       let id = model_id.to_lowercase();
       if id.starts_with("claude-") { return Some("anthropic"); }
       if id.starts_with("gpt-") || id.starts_with("o1") || id.starts_with("o3")
          || id.starts_with("o4") || id.starts_with("codex-") { return Some("openai"); }
       if id.starts_with("gemini") { return Some("google"); }
       if id.starts_with("llama") { return Some("meta"); }
       if id.starts_with("mistral") || id.starts_with("codestral") { return Some("mistral"); }
       if id.starts_with("deepseek") { return Some("deepseek"); }
       if id.starts_with("command") { return Some("cohere"); }
       None
   }
   ```

### Test Updates in `src/models/mod.rs`

9. **`pinned_alias()` helper** (line 785): Change signature to accept `Option<&str>` for harness, add `provider: None`:
   ```rust
   fn pinned_alias(harness: Option<&str>, model: &str) -> ModelAlias {
       ModelAlias {
           harness: harness.map(|h| h.to_string()),
           description: None,
           spec: ModelSpec::Pinned {
               model: model.to_string(),
               provider: None,
           },
       }
   }
   ```

10. **All callers of `pinned_alias()`**: Update from `pinned_alias("claude", "model")` to `pinned_alias(Some("claude"), "model")`. Affects tests: `merge_consumer_overrides_dependency_alias`, `merge_dep_overrides_builtin`, `merge_consumer_beats_dep`, `merge_dep_conflict_warns`, `resolve_all_pinned`, `resolve_all_empty_cache_omits_unresolvable`.

11. **`ModelSpec::Pinned` comparisons in assertions**: All `ModelSpec::Pinned { model: ... }` patterns in test assertions need `provider: None` added.

12. **Serde roundtrip tests**: Update existing tests + add new ones:
    - Pinned alias with harness omitted in TOML (should deserialize to `harness: None`)
    - Pinned alias with explicit provider in TOML
    - Existing pinned alias with harness (should still work — backwards compat)

13. **Add `infer_provider_from_model_id` tests**:
    - `claude-opus-4-6` → `Some("anthropic")`
    - `gpt-5.3-codex` → `Some("openai")`
    - `gemini-2.5-pro` → `Some("google")`
    - `llama-4-maverick` → `Some("meta")`
    - `unknown-model` → `None`

## Dependencies

- **Requires:** Nothing — this is the foundation phase.
- **Produces:** `Option<String>` harness on `ModelAlias`, `provider: Option<String>` on `Pinned`, `infer_provider_from_model_id()` function.

## Patterns to Follow

Look at how `description: Option<String>` is already handled in `ModelAlias` — same pattern for `harness`. The `#[serde(skip_serializing_if = "Option::is_none")]` attribute is already used on `description`.

## Constraints

- **Backwards compatibility**: All existing mars.toml configs with `harness = "claude"` must still parse. The `harness` field in TOML/JSON becomes optional, not removed.
- **No behavior changes**: `resolve_all` still returns `IndexMap<String, String>` in this phase. The new `provider` field on Pinned is destructured but unused.
- **Merge logic unchanged**: `merge_model_config` compares by alias name, not harness. No changes needed.

## Verification Criteria

- [ ] `cargo build` succeeds with no errors
- [ ] `cargo test` — all existing tests pass (updated for new signatures)
- [ ] `cargo test` — new serde roundtrip tests pass (harness optional, provider on pinned)
- [ ] `cargo test` — `infer_provider_from_model_id` tests pass
- [ ] Existing mars.toml files with `harness = "..."` still parse correctly
- [ ] `cargo clippy` clean
