# Phase 6: B4 — Model Catalog

**Round:** 3 (parallel with Phase 7)
**Depends on:** Phase 1 (A1 — pipeline phases), Phase 2 (A3 — manifest extension), Phase 5 (A5 — diagnostics)
**Risk:** Medium — new subsystem, but mostly additive code
**Estimated delta:** ~+600 LOC (model types, auto-resolve, builtins, cache, merge, CLI commands)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Implement the two-mode `ModelAlias` (pinned + auto-resolve), builtin aliases, dependency-tree config merge during `resolve_graph()`, cache lifecycle, and CLI commands (`mars models refresh/list/resolve/alias`).

## Why This Matters

Model aliases are needed for agent spawning. Packages distribute model defaults with operational descriptions. The dependency-tree merge gives packages influence over model selection while consumers always win. This is the config merge pattern that B1 (rules) will follow for future item kinds.

## Files to Create

| File | Contents |
|------|----------|
| `src/models/mod.rs` | `ModelAlias`, `ModelSpec` (Pinned/AutoResolve), `ModelsCache`, `CachedModel`. `builtin_aliases()`, `fallback_model_ids()`. `auto_resolve()` algorithm. `merge_model_config()`. Cache read/write. `glob_match()`. |
| `src/cli/models.rs` | CLI handlers: `refresh`, `list`, `resolve`, `alias`. All support `--json`. |

## Files to Modify

| File | Changes |
|------|---------|
| `src/lib.rs` | Add `pub mod models;` |
| `src/config/mod.rs` | Add `models: IndexMap<String, ModelAlias>` to `Config`. Update `load()` to parse `[models]` section. Add `models: IndexMap<String, ModelAlias>` to `Manifest`. Update `load_manifest()` to extract `[models]`. |
| `src/sync/mod.rs` | Add `model_aliases: IndexMap<String, ModelAlias>` to `ResolvedState`. Call `merge_model_config()` in `resolve_graph()`. |
| `src/resolve/mod.rs` | During graph resolution, collect `[models]` from each dependency's manifest. Pass to `merge_model_config()`. |
| `src/cli/mod.rs` | Register `models` subcommand with `refresh`, `list`, `resolve`, `alias` subcommands. |

## Interface Contract — Core Types

```rust
// src/models/mod.rs

/// A model alias — either pinned or auto-resolved.
pub struct ModelAlias {
    pub harness: String,
    pub description: Option<String>,
    pub spec: ModelSpec,
}

pub enum ModelSpec {
    /// Explicit model ID.
    Pinned { model: String },
    /// Pattern-based resolution against models cache.
    AutoResolve {
        provider: String,
        match_patterns: Vec<String>,
        exclude_patterns: Vec<String>,
    },
}
```

**Serde deserialization** — distinguished by field presence:
- `model` field present → `Pinned`
- `match` field present → `AutoResolve`
- Both present → config validation error
- Neither present → config validation error

## Interface Contract — Auto-Resolve

```rust
pub fn auto_resolve(spec: &AutoResolve, cache: &ModelsCache) -> Option<String> {
    // 1. Filter by provider
    // 2. All match patterns must hit (AND)
    // 3. No exclude patterns may hit (OR)
    // 4. Skip *-latest suffix
    // 5. Sort by newest release_date, then shortest ID
    // 6. Pick first
}

/// Simple glob: * matches any character sequence. Everything else literal.
fn glob_match(pattern: &str, text: &str) -> bool;
```

## Interface Contract — Builtin Aliases

```rust
/// Default auto-resolve specs for common model families.
/// Lowest priority — overridden by packages and consumer.
pub fn builtin_aliases() -> IndexMap<String, ModelAlias>;
// Returns: opus, sonnet, haiku, codex, gpt, gemini

/// Fallback model IDs when cache is empty (first run, no network).
pub fn fallback_model_ids() -> IndexMap<&'static str, &'static str>;
// Returns: opus→claude-opus-4, sonnet→claude-sonnet-4, etc.
```

## Interface Contract — Dependency-Tree Merge

```rust
/// Merge model aliases from dependency tree.
/// Precedence: consumer > deps (declaration order) > builtins > fallback IDs.
pub fn merge_model_config(
    consumer: &IndexMap<String, ModelAlias>,
    deps: &[ResolvedDep],
    diag: &mut DiagnosticCollector,
) -> IndexMap<String, ModelAlias>;
```

Called during `resolve_graph()` after dependency resolution. Result stored in `ResolvedState.model_aliases`.

## Interface Contract — Cache

```rust
pub struct ModelsCache {
    pub models: Vec<CachedModel>,
    pub fetched_at: Option<DateTime<Utc>>,  // or timestamp string
}

pub struct CachedModel {
    pub id: String,
    pub provider: String,
    pub release_date: Option<String>,
    // other fields from models.dev API
}

/// Cache lives at .mars/models-cache.json
pub fn read_cache(mars_dir: &Path) -> Result<ModelsCache, MarsError>;
pub fn write_cache(mars_dir: &Path, cache: &ModelsCache) -> Result<(), MarsError>;
pub fn fetch_models() -> Result<Vec<CachedModel>, MarsError>;  // from models.dev API
```

## CLI Commands

| Command | Behavior |
|---------|----------|
| `mars models refresh` | Fetch models from API, write to `.mars/models-cache.json`. |
| `mars models list` | List all merged model aliases (consumer + deps + builtins). Show resolved model ID if cache exists. |
| `mars models resolve <alias>` | Show full resolution chain: source layer, pattern match, resolved ID. |
| `mars models alias <name> <model-id>` | Quick-add a pinned alias to mars.toml `[models]`. |

All commands support `--json` for structured output.

## Integration with Pipeline

In `resolve_graph()`, after the dependency graph is resolved:

```rust
fn resolve_graph(ctx: &MarsContext, loaded: LoadedConfig, request: &SyncRequest, diag: &mut DiagnosticCollector) -> Result<ResolvedState, MarsError> {
    let graph = /* existing resolution logic */;
    
    // Merge model config from dependency tree
    let model_aliases = merge_model_config(
        &loaded.config.models,
        &graph.resolved_deps,
        diag,
    );
    
    Ok(ResolvedState { loaded, graph, model_aliases })
}
```

## Constraints

- **D31:** Two modes — pinned and auto-resolve, distinguished by field presence.
- **D32:** Builtins are lowest priority, overridable. Fallback IDs for empty cache.
- **D33:** Same merge precedence as other config (consumer > deps > builtins).
- **D34:** Simple glob matching — `*` only wildcard.
- **Cache is optional.** `mars sync` works without a cache — auto-resolve aliases use fallback IDs. Cache is populated by `mars models refresh`.
- **Use structured diagnostics** (from Phase 5) for merge conflict warnings.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass + new model tests pass
- [ ] `cargo clippy` — no new warnings
- [ ] Unit tests for `auto_resolve()` — exact match, glob match, exclude, empty cache fallback
- [ ] Unit tests for `glob_match()` — standard patterns
- [ ] Unit tests for `merge_model_config()` — precedence ordering, conflict detection
- [ ] `mars models list` shows builtin aliases with no mars.toml `[models]` section
- [ ] `mars models resolve opus` shows resolution chain
- [ ] `mars sync` with `[models]` in mars.toml parses correctly
- [ ] A package with `[models]` in its mars.toml: models merge into consumer's resolved aliases

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 2x — correctness (auto-resolve algorithm, merge precedence), design alignment (verify decisions D31-D36 are respected)
- **Tester:** 1x unit-tester — auto_resolve edge cases, glob_match, merge precedence
