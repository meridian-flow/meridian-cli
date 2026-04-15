# Phase 2: Harness Detection Module

## Scope

Add the `which` crate dependency and create `src/models/harness.rs` — the module that detects installed harness binaries on PATH and maps providers to harnesses via a preference table. This is the core detection logic, used by Phase 3's `resolve_all`.

## Files to Modify

All changes are in **`/home/jimyao/gitrepos/mars-agents/`**:

### `Cargo.toml`

1. Add `which` dependency:
   ```toml
   which = "7"
   ```

### `src/models/harness.rs` (NEW FILE)

Create this file with three components:

2. **`detect_installed_harnesses()`** — checks PATH for known harness binaries:
   ```rust
   use std::collections::HashSet;

   const HARNESS_BINARIES: &[(&str, &str)] = &[
       ("claude", "claude"),
       ("codex", "codex"),
       ("opencode", "opencode"),
       ("gemini", "gemini"),
   ];

   pub fn detect_installed_harnesses() -> HashSet<String> {
       HARNESS_BINARIES.iter()
           .filter(|(_, binary)| which::which(binary).is_ok())
           .map(|(name, _)| name.to_string())
           .collect()
   }
   ```
   
   Error handling: `which::which()` returns `Err` for both "not found" and unexpected errors. Treating all errors as "not installed" is correct per D2/D6.

3. **`PROVIDER_HARNESS_PREFERENCES`** constant + **`resolve_harness_for_provider()`**:
   ```rust
   const PROVIDER_HARNESS_PREFERENCES: &[(&str, &[&str])] = &[
       ("anthropic", &["claude", "opencode", "gemini"]),
       ("openai",    &["codex", "opencode"]),
       ("google",    &["gemini", "opencode"]),
       ("meta",      &["opencode"]),
       ("mistral",   &["opencode"]),
       ("deepseek",  &["opencode"]),
       ("cohere",    &["opencode"]),
   ];

   pub fn resolve_harness_for_provider(
       provider: &str,
       installed: &HashSet<String>,
   ) -> Option<String> {
       let provider_lower = provider.to_lowercase();
       PROVIDER_HARNESS_PREFERENCES.iter()
           .find(|(p, _)| *p == provider_lower)
           .and_then(|(_, prefs)| {
               prefs.iter()
                   .find(|h| installed.contains(**h))
                   .map(|h| h.to_string())
           })
   }
   ```

4. **`harness_candidates_for_provider()`** — returns the full preference list (for `harness_candidates` in resolve output):
   ```rust
   pub fn harness_candidates_for_provider(provider: &str) -> Vec<String> {
       let provider_lower = provider.to_lowercase();
       PROVIDER_HARNESS_PREFERENCES.iter()
           .find(|(p, _)| *p == provider_lower)
           .map(|(_, prefs)| prefs.iter().map(|h| h.to_string()).collect())
           .unwrap_or_default()
   }
   ```

### `src/models/mod.rs`

5. Add `pub mod harness;` declaration near the top (after the existing imports/module structure). Re-export the public functions:
   ```rust
   pub mod harness;
   ```

### Tests in `src/models/harness.rs`

6. Add unit tests:
   ```rust
   #[cfg(test)]
   mod tests {
       use super::*;

       #[test]
       fn resolve_harness_anthropic_with_claude() {
           let installed: HashSet<String> = ["claude"].iter().map(|s| s.to_string()).collect();
           assert_eq!(resolve_harness_for_provider("anthropic", &installed), Some("claude".to_string()));
       }

       #[test]
       fn resolve_harness_anthropic_falls_back_to_opencode() {
           let installed: HashSet<String> = ["opencode"].iter().map(|s| s.to_string()).collect();
           assert_eq!(resolve_harness_for_provider("anthropic", &installed), Some("opencode".to_string()));
       }

       #[test]
       fn resolve_harness_none_installed() {
           let installed: HashSet<String> = HashSet::new();
           assert_eq!(resolve_harness_for_provider("anthropic", &installed), None);
       }

       #[test]
       fn resolve_harness_unknown_provider() {
           let installed: HashSet<String> = ["claude"].iter().map(|s| s.to_string()).collect();
           assert_eq!(resolve_harness_for_provider("unknown-provider", &installed), None);
       }

       #[test]
       fn resolve_harness_case_insensitive_provider() {
           let installed: HashSet<String> = ["claude"].iter().map(|s| s.to_string()).collect();
           assert_eq!(resolve_harness_for_provider("Anthropic", &installed), Some("claude".to_string()));
       }

       #[test]
       fn candidates_for_known_provider() {
           let candidates = harness_candidates_for_provider("openai");
           assert_eq!(candidates, vec!["codex", "opencode"]);
       }

       #[test]
       fn candidates_for_unknown_provider() {
           let candidates = harness_candidates_for_provider("unknown");
           assert!(candidates.is_empty());
       }
   }
   ```

   Note: `detect_installed_harnesses()` depends on system PATH — don't unit test it (it's a thin wrapper around `which`). Smoke test it instead.

## Dependencies

- **Requires:** Phase 1 complete (the module references types from `mod.rs`, and `mod.rs` needs to compile with `Option<String>` harness).
- **Produces:** `detect_installed_harnesses()`, `resolve_harness_for_provider()`, `harness_candidates_for_provider()` — consumed by Phase 3.
- **Independent of:** Phases 4, 5.

## Constraints

- No mars.toml configuration for preferences (D9) — hardcoded table only.
- No caching of detection results (D2) — called fresh each invocation.
- The `detect_installed_harnesses` function is intentionally not `pub(crate)` — it's `pub` so the CLI could use it for a future `mars harness list` command (D8, deferred).

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] `cargo test` — all harness module unit tests pass
- [ ] `cargo test` — all existing tests still pass
- [ ] `cargo clippy` clean
- [ ] The `which` crate is in Cargo.toml and Cargo.lock
