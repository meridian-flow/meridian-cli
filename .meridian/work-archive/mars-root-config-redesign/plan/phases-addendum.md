# Phase 1 Addendum: Pre-Refactor Cleanup (from refactor-reviewer p766)

These findings should be addressed in Phase 1 alongside the config model changes:

1. **Dead mutation paths**: Remove `ConfigMutation::{SetLink,ClearLink}` and `LinkMutation::Set` — they're unused. Consolidate link config writes into one path. (src/sync/mod.rs:62, src/sync/mod.rs:92, src/cli/link.rs)

2. **Config struct conflation**: The unification of [sources]+[dependencies] into [dependencies] naturally fixes this — the Config struct will have `package`, `dependencies`, and `settings` with clear separation. The `load_manifest()` projection function can be simplified or removed.

3. **Init idempotency for custom roots**: Phase 1 already adds `settings.managed_root` persistence. Init must read existing config first to discover the persisted managed root before falling back to defaults.
