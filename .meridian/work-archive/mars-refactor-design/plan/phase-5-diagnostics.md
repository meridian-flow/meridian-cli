# Phase 5: A5 — Structured Diagnostics

**Round:** 2 (parallel with Phase 3 and Phase 4)
**Depends on:** Phase 1 (A1 — typed pipeline phases)
**Risk:** Low — mechanical replacement of eprintln! with collector pattern
**Estimated delta:** ~+80 LOC (Diagnostic type, collector), ~-30 LOC (removed eprintln! calls)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Replace all `eprintln!("warning: ...")` calls in library code with structured `Diagnostic` values. Introduce a `DiagnosticCollector` threaded through phase functions. The CLI layer becomes the only place that renders diagnostics — to stderr in human mode, to a `"diagnostics"` array in JSON mode.

## Why This Matters

Phase 6 (B4) and Phase 7 (B3) both emit diagnostics (model merge conflicts, target sync failures). Without structured diagnostics, they'd add more `eprintln!` calls that bypass `--json` mode. Getting the pattern right now means B4/B3 use it from the start.

## Files to Create

| File | Contents |
|------|----------|
| `src/diagnostic.rs` | `Diagnostic` struct, `DiagnosticLevel` enum, `DiagnosticCollector` struct. |

## Files to Modify

| File | Changes |
|------|---------|
| `src/lib.rs` (or `src/main.rs`) | Add `mod diagnostic;` |
| `src/sync/mod.rs` | Thread `DiagnosticCollector` through phase function calls. Accumulate into `SyncReport.diagnostics`. |
| `src/config/mod.rs` | Replace `eprintln!` warnings (deprecated fields, etc.) with `collector.warn(...)` or return `Vec<Diagnostic>` alongside config. |
| `src/sync/target.rs` | Replace collision warnings with `collector.warn(...)`. |
| `src/sync/self_package.rs` | Replace shadow/collision warnings with `collector.warn(...)`. (If Phase 3 runs first and deletes inject_self_items, fewer touch points here.) |
| `src/resolve/mod.rs` | Replace version constraint warnings with `collector.warn(...)`. |
| `src/sync/mod.rs` | Merge existing `warnings: Vec<ValidationWarning>` in `SyncReport` into the new `diagnostics: Vec<Diagnostic>` field. |
| `src/cli/sync.rs` | Render `SyncReport.diagnostics` — stderr for human mode, JSON array for `--json`. |
| `src/cli/output.rs` | Add diagnostic rendering helpers. |

## Interface Contract

```rust
// src/diagnostic.rs

/// A diagnostic message from library code.
#[derive(Debug, Clone)]
pub struct Diagnostic {
    pub level: DiagnosticLevel,
    /// Machine-readable code, e.g. "shadow-collision", "manifest-path-dep".
    pub code: &'static str,
    /// Human-readable message.
    pub message: String,
    /// Optional context (source name, item path, etc.).
    pub context: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DiagnosticLevel {
    Warning,
    Info,
}

/// Collects diagnostics during pipeline execution.
pub struct DiagnosticCollector {
    diagnostics: Vec<Diagnostic>,
}

impl DiagnosticCollector {
    pub fn new() -> Self { Self { diagnostics: Vec::new() } }
    pub fn warn(&mut self, code: &'static str, message: impl Into<String>) { ... }
    pub fn info(&mut self, code: &'static str, message: impl Into<String>) { ... }
    pub fn warn_with_context(&mut self, code: &'static str, message: impl Into<String>, context: impl Into<String>) { ... }
    pub fn drain(&mut self) -> Vec<Diagnostic> { std::mem::take(&mut self.diagnostics) }
    pub fn is_empty(&self) -> bool { self.diagnostics.is_empty() }
}
```

## Threading Strategy

Two options — pick the one that's cleaner given Phase 1's output:

**Option A: Collector as parameter.** Thread `&mut DiagnosticCollector` through phase functions:
```rust
fn resolve_graph(ctx: &MarsContext, loaded: LoadedConfig, request: &SyncRequest, diag: &mut DiagnosticCollector) -> Result<ResolvedState, MarsError>;
```

**Option B: Collector in context.** Add collector to `MarsContext` (requires `RefCell` or similar):
```rust
pub struct MarsContext {
    // ... existing fields
    pub diagnostics: RefCell<DiagnosticCollector>,
}
```

**Recommendation: Option A.** It's explicit, no interior mutability needed, and matches the design's collector pattern. The extra parameter on each phase function is fine — it's clear what it does.

## SyncReport Changes

```rust
pub struct SyncReport {
    pub applied: ApplyResult,
    pub pruned: Vec<ActionOutcome>,
    pub diagnostics: Vec<Diagnostic>,  // replaces warnings: Vec<ValidationWarning>
    pub dependency_changes: Vec<DependencyUpsertChange>,
    pub dry_run: bool,
}
```

The existing `ValidationWarning` type can be converted to `Diagnostic` with appropriate codes.

## Known eprintln! Sites to Replace

Search for `eprintln!` in library code (not CLI code — CLI stderr output is fine):

- `config/mod.rs`: deprecated field warnings
- `sync/mod.rs` or `sync/target.rs`: unmanaged collision warnings
- `sync/self_package.rs`: shadow warnings, collision warnings
- `resolve/mod.rs`: version constraint warnings
- `config/mod.rs` (from Phase 2): manifest path-dep warning

## Constraints

- **CLI code is the only renderer.** No `eprintln!` in `src/` outside of `src/cli/`.
- **JSON mode compatibility.** `--json` output must include diagnostics in the JSON structure.
- **Don't change warning semantics.** Same conditions produce same warnings — just delivered via Diagnostic instead of stderr.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass
- [ ] `cargo clippy` — no new warnings
- [ ] `grep -rn 'eprintln!' src/` returns matches only in `src/cli/` (no library code uses eprintln)
- [ ] `mars sync --json` on a project with warnings includes a `"diagnostics"` array in JSON output
- [ ] Human-mode `mars sync` still shows the same warnings on stderr

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 1x — correctness (verify all eprintln sites replaced, JSON output includes diagnostics)
