# Phase 3: resolve_all Returns ResolvedAlias

## Scope

Change `resolve_all` from returning `IndexMap<String, String>` (alias → model_id) to `IndexMap<String, ResolvedAlias>` — a rich type that includes model_id, provider, harness, harness_source, and candidates. This wires together Phase 1's schema and Phase 2's detection into the unified resolve pipeline. Callers will break — Phase 4 fixes the CLI callers.

## Files to Modify

All changes are in **`/home/jimyao/gitrepos/mars-agents/src/models/mod.rs`**:

### New Types

1. **`HarnessSource` enum** — add after the `ModelSpec` definition (around line 44):
   ```rust
   #[derive(Debug, Clone, PartialEq, Serialize)]
   #[serde(rename_all = "snake_case")]
   pub enum HarnessSource {
       Explicit,
       AutoDetected,
       Unavailable,
   }
   ```

2. **`ResolvedAlias` struct** — add after `HarnessSource`:
   ```rust
   #[derive(Debug, Clone, Serialize)]
   pub struct ResolvedAlias {
       pub name: String,
       pub model_id: String,
       pub provider: String,
       pub harness: Option<String>,
       pub harness_source: HarnessSource,
       pub harness_candidates: Vec<String>,
       #[serde(skip_serializing_if = "Option::is_none")]
       pub description: Option<String>,
   }
   ```

### Updated Functions

3. **`resolve_all()`** (line 541) — new implementation. Same 2-param signature (`aliases`, `cache`), new return type:
   ```rust
   pub fn resolve_all(
       aliases: &IndexMap<String, ModelAlias>,
       cache: &ModelsCache,
   ) -> IndexMap<String, ResolvedAlias> {
       let installed = harness::detect_installed_harnesses();
       let mut resolved = IndexMap::new();

       for (name, alias) in aliases {
           let Some((model_id, provider)) = resolve_model_and_provider(alias, cache) else {
               continue; // unresolvable — omit
           };

           let candidates = harness::harness_candidates_for_provider(&provider);
           let (h, source) = resolve_harness(alias, &provider, &installed);

           resolved.insert(name.clone(), ResolvedAlias {
               name: name.clone(),
               model_id,
               provider,
               harness: h,
               harness_source: source,
               harness_candidates: candidates,
               description: alias.description.clone(),
           });
       }
       resolved
   }
   ```

4. **`resolve_model_and_provider()`** — new private helper:
   ```rust
   fn resolve_model_and_provider(
       alias: &ModelAlias,
       cache: &ModelsCache,
   ) -> Option<(String, String)> {
       match &alias.spec {
           ModelSpec::Pinned { model, provider } => {
               let p = provider.clone()
                   .or_else(|| infer_provider_from_model_id(model).map(str::to_string))
                   .unwrap_or_else(|| "unknown".to_string());
               Some((model.clone(), p))
           }
           ModelSpec::AutoResolve {
               provider,
               match_patterns,
               exclude_patterns,
           } => {
               let id = auto_resolve(provider, match_patterns, exclude_patterns, cache)?;
               Some((id, provider.clone()))
           }
       }
   }
   ```

5. **`resolve_harness()`** — new private helper:
   ```rust
   fn resolve_harness(
       alias: &ModelAlias,
       provider: &str,
       installed: &HashSet<String>,
   ) -> (Option<String>, HarnessSource) {
       if let Some(h) = &alias.harness {
           if installed.contains(h) {
               (Some(h.clone()), HarnessSource::Explicit)
           } else {
               (Some(h.clone()), HarnessSource::Unavailable)
           }
       } else {
           match harness::resolve_harness_for_provider(provider, installed) {
               Some(h) => (Some(h), HarnessSource::AutoDetected),
               None => (None, HarnessSource::Unavailable),
           }
       }
   }
   ```
   Add `use std::collections::HashSet;` to imports if not already present.

### Test Updates

6. **`resolve_all_pinned` test** — update to check `ResolvedAlias` fields:
   ```rust
   #[test]
   fn resolve_all_pinned() {
       let mut aliases = IndexMap::new();
       aliases.insert(
           "fast".to_string(),
           pinned_alias(Some("claude"), "claude-haiku-4-5"),
       );
       let cache = ModelsCache { models: vec![], fetched_at: None };
       let resolved = resolve_all(&aliases, &cache);
       let entry = resolved.get("fast").unwrap();
       assert_eq!(entry.model_id, "claude-haiku-4-5");
       assert_eq!(entry.provider, "anthropic"); // inferred from model ID
   }
   ```

7. **`resolve_all_empty_cache_omits_unresolvable` test** — update similarly. Auto-resolve aliases with empty cache still omitted.

8. **New tests**:
   - `resolve_all_auto_detect_harness` — alias with `harness: None`, auto-resolve spec, verify `harness_source` is `AutoDetected` (when the relevant binary is installed) or `Unavailable`.
   - `resolve_model_and_provider_pinned_explicit_provider` — pinned with `provider: Some("anthropic")` returns that provider.
   - `resolve_model_and_provider_pinned_inferred` — pinned without provider, model `claude-opus-4-6` → provider `"anthropic"`.
   - `resolve_model_and_provider_pinned_unknown` — unknown model prefix → provider `"unknown"`.
   - `resolve_harness_explicit_installed` — explicit harness + installed → `Explicit`.
   - `resolve_harness_explicit_not_installed` — explicit harness + not installed → `Unavailable`.
   - `resolve_harness_auto_detected` — no harness + provider with installed preference → `AutoDetected`.
   - `resolve_harness_unavailable` — no harness + no installed preference → `Unavailable`.

   Note: Tests for `resolve_harness` and `resolve_model_and_provider` can call these helpers directly (they're private but in the same module's test block).

## Dependencies

- **Requires:** Phase 1 (optional harness, provider on Pinned), Phase 2 (harness detection module).
- **Produces:** `ResolvedAlias`, `HarnessSource`, updated `resolve_all()` — consumed by Phase 4.
- **Breaks:** `src/cli/models.rs` — callers of `resolve_all` expect `IndexMap<String, String>`. Phase 4 fixes these. **Expect compile errors in cli/models.rs until Phase 4.**

## Constraints

- Detection is encapsulated inside `resolve_all` (D13) — callers pass only `aliases` + `cache`.
- `HarnessSource` is an enum, not a string (D14).
- Unresolvable aliases (model can't resolve) are still omitted from the map — same as before.
- Aliases where the model resolves but no harness is available are **included** with `harness: None, harness_source: Unavailable`.

## Verification Criteria

- [ ] `cargo test` in `src/models/` passes — all resolve tests updated and new tests pass
- [ ] `cargo build` may fail on `src/cli/models.rs` — that's expected and fixed in Phase 4
- [ ] `HarnessSource` serializes to snake_case: `"explicit"`, `"auto_detected"`, `"unavailable"`
- [ ] `ResolvedAlias` serializes to JSON with all expected fields
