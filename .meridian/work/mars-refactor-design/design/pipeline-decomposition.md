# Pipeline Decomposition (Phase A)

Decompose the sync pipeline for extensibility. Five changes: typed phases, first-class local packages, dependency entry split, shared reconciliation, and structured diagnostics.

See [overview](overview.md) for context and ordering.

## A1: Typed Pipeline Phases

### Problem

`sync::execute()` is a single 240-line function with 17 numbered steps. The function signature is `(ctx, request) -> SyncReport`, hiding all intermediate state. This means:

- New pipeline stages (capability materialization, runtime config generation) can only be added by growing the function further
- Testing individual phases requires running the whole pipeline
- The `inject_self_items` call at step 13b mutates the plan after creation, breaking the principle that each phase consumes the previous phase's output immutably

### Design

Decompose into explicit phase functions, each consuming the previous phase's output struct:

```rust
/// Phase 1: Load and validate configuration under sync lock.
pub struct LoadedConfig {
    pub config: Config,
    pub local: LocalConfig,
    pub effective: EffectiveConfig,
    pub old_lock: LockFile,
    pub dependency_changes: Vec<DependencyUpsertChange>,
    pub _sync_lock: FileLock,  // held for duration
}

/// Phase 2: Resolved dependency graph.
pub struct ResolvedState {
    pub loaded: LoadedConfig,
    pub graph: ResolvedGraph,
}

/// Phase 3: Desired target state after discovery + filtering.
pub struct TargetedState {
    pub resolved: ResolvedState,
    pub target: TargetState,
    pub renames: Vec<RenameAction>,
    pub warnings: Vec<ValidationWarning>,
}

/// Phase 4: Diff + plan ready for execution.
pub struct PlannedState {
    pub targeted: TargetedState,
    pub plan: SyncPlan,
}

/// Phase 5: Applied results.
pub struct AppliedState {
    pub planned: PlannedState,
    pub applied: ApplyResult,
}
```

The `execute()` function becomes an orchestrator that calls phase functions:

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    validate_request(request)?;
    
    let loaded = load_config(ctx, request)?;
    let resolved = resolve_graph(ctx, &loaded, request)?;
    let targeted = build_target(ctx, &resolved, request)?;
    let planned = create_plan(ctx, &targeted, request)?;
    
    if request.options.frozen {
        check_frozen_gate(&planned)?;
    }
    
    let applied = apply_plan(ctx, &planned, request)?;
    let report = finalize(ctx, &applied, request)?;
    
    Ok(report)
}
```

Each phase function is independently testable. Extension points insert as new phases:

```rust
// Future: after apply_plan, before finalize
let materialized = materialize_capabilities(ctx, &applied)?;
```

### Phase Function Signatures

```rust
fn load_config(ctx: &MarsContext, request: &SyncRequest) -> Result<LoadedConfig, MarsError>;
fn resolve_graph(ctx: &MarsContext, loaded: &LoadedConfig, request: &SyncRequest) -> Result<ResolvedState, MarsError>;
fn build_target(ctx: &MarsContext, resolved: &ResolvedState, request: &SyncRequest) -> Result<TargetedState, MarsError>;
fn create_plan(ctx: &MarsContext, targeted: &TargetedState, request: &SyncRequest) -> Result<PlannedState, MarsError>;
fn apply_plan(ctx: &MarsContext, planned: &PlannedState, request: &SyncRequest) -> Result<AppliedState, MarsError>;
fn finalize(ctx: &MarsContext, applied: &AppliedState, request: &SyncRequest) -> Result<SyncReport, MarsError>;
```

### What Moves Where

| Current step | New phase function | Notes |
|---|---|---|
| Steps 1-4b (lock, config, mutation, merge) | `load_config()` | Config loading + mutation under sync lock |
| Steps 5-7 (validate targets, load lock, resolve) | `resolve_graph()` | Resolution with options from request |
| Steps 8-11 (target, collisions, rewrites, validation) | `build_target()` | Discovery, filtering, collision detection |
| Steps 12-13c (diff, plan, _self injection) | `create_plan()` | _self handled inside target building, not here (see A2) |
| Step 14 (frozen gate) | `check_frozen_gate()` | Standalone check between plan and apply |
| Steps 15-16 (persist config, apply) | `apply_plan()` | Config persistence + plan execution |
| Step 17 (write lock) | `finalize()` | Lock rebuild + report construction |

### Nesting vs Flattening

The phase structs above nest (`ResolvedState` contains `LoadedConfig`). This preserves access to earlier data without passing many arguments. However, the nesting means `AppliedState` transitively contains everything. This is fine because:

1. Phase structs are moved, not cloned — no memory overhead
2. Later phases legitimately need earlier data (lock building needs the graph from resolution)
3. The alternative (flattening into many separate arguments per phase function) makes signatures unwieldy

If memory pressure becomes an issue (unlikely for ~5k LOC tool), phase structs can be destructured between phases to drop intermediate data.

---

## A2: First-Class LocalPackage

### Problem

`_self` is a string sentinel (`"_self"`) that leaks across:
- `config/mod.rs`: `config.package.is_some()` checked as a boolean, no typed origin
- `sync/self_package.rs`: discovers local items, then **mutates the already-built plan** via `inject_self_items`
- `lock/mod.rs`: `SourceName::from("_self")` as a magic string in lock building
- `sync/plan.rs`: `PlannedAction::Symlink` variant exists only for _self items

The `inject_self_items` function is the worst offender: it runs after the plan is created, mutating `sync_plan.actions` to inject symlinks and remove conflicting entries. This breaks the pipeline's phase ordering — the plan is not final after `create_plan()`.

### Design

Make local packages a first-class source origin that participates in the standard pipeline from the start.

**New type: `SourceOrigin`**

```rust
/// Where an item came from — used for lock provenance and display.
pub enum SourceOrigin {
    /// From a dependency (git or path source).
    Dependency(SourceName),
    /// From the local project's [package] declaration.
    LocalPackage,
}
```

This replaces `SourceName::from("_self")` everywhere. The lock serialization maps `LocalPackage` to/from `"_self"` for backwards compatibility:

```rust
impl Serialize for SourceOrigin {
    fn serialize<S>(&self, s: S) -> Result<S::Ok, S::Error> {
        match self {
            Self::Dependency(name) => name.serialize(s),
            Self::LocalPackage => "_self".serialize(s),
        }
    }
}
```

**Local items participate in target building**

Instead of `inject_self_items` mutating the plan post-hoc, local items are discovered during `build_target()` and included in `TargetState`:

```rust
fn build_target(ctx: &MarsContext, resolved: &ResolvedState, request: &SyncRequest) -> Result<TargetedState, MarsError> {
    let mut target = build_target_from_graph(&resolved.graph, &resolved.loaded.effective)?;
    
    // Local package items are added to target state here, not after plan creation
    if resolved.loaded.config.package.is_some() {
        let local_items = discover_local_items(&ctx.project_root)?;
        integrate_local_items(&mut target, &local_items, &resolved.loaded.old_lock)?;
    }
    
    // ... collision detection, validation, etc.
}
```

`integrate_local_items` handles:
- Shadow detection (local items shadow external items, with warning)
- Unmanaged collision avoidance
- Adding local items to `TargetState` with `SourceOrigin::LocalPackage`

**TargetItem changes**

```rust
pub struct TargetItem {
    pub id: ItemId,
    pub origin: SourceOrigin,       // replaces source_name: SourceName
    pub source_id: SourceId,
    pub source_path: PathBuf,
    pub dest_path: DestPath,
    pub source_hash: ContentHash,
    pub is_flat_skill: bool,
    pub rewritten_content: Option<String>,
    pub materialization: Materialization,  // how to apply this item
}

/// How an item should be materialized in the managed root.
pub enum Materialization {
    /// Copy source content to destination (standard for agents/skills).
    Copy,
    /// Create a symlink to the source (for local package items).
    Symlink { source_abs: PathBuf },
}
```

Now the diff/plan pipeline handles local items uniformly — `PlannedAction::Symlink` is generated from `Materialization::Symlink` during plan creation, not injected afterward.

**Orphan pruning**

Local item orphan pruning (removing stale `_self` entries) moves into the diff phase. The diff engine sees old lock entries with `SourceOrigin::LocalPackage` that aren't in the target, and generates `DiffEntry::Orphan` naturally — no special-case pruning needed.

**What gets deleted**

- `sync/self_package.rs::inject_self_items()` — replaced by `integrate_local_items` in target building
- The post-plan `_self` action retention filter in `inject_self_items`
- `SourceName::from("_self")` magic strings — replaced by `SourceOrigin::LocalPackage`

---

## A3: DependencyEntry Split

### Problem

`DependencyEntry` serves two incompatible purposes:

1. **Consumer install intent** (in consumer `mars.toml`): "install from this URL, version constraint, with these filters"
2. **Package manifest export** (in source `mars.toml`): "this package depends on these other packages"

`load_manifest()` claims to filter to package deps but forwards every dependency unchanged. The resolver compensates by silently skipping manifest deps without a URL. This is a correctness trap — adding a path-only dep to a manifest silently becomes a no-op for consumers.

### Design

Split into two distinct types at the config boundary:

```rust
/// Consumer install intent — what goes in [dependencies] of a consumer mars.toml.
/// Always has a source (URL or path) and optional filters.
pub struct InstallDep {
    pub url: Option<SourceUrl>,
    pub path: Option<PathBuf>,
    pub version: Option<String>,
    pub filter: FilterConfig,
}

/// Package manifest dependency — what a package declares its consumers need.
/// Always has a URL (packages can't declare path deps for consumers).
pub struct ManifestDep {
    pub url: SourceUrl,
    pub version: Option<String>,
}
```

**Config loading** (`load()`) returns `Config` with `dependencies: IndexMap<SourceName, InstallDep>` — unchanged, just renamed type.

**Manifest loading** (`load_manifest()`) returns `Manifest` with `dependencies: IndexMap<String, ManifestDep>`. The conversion from `DependencyEntry` to `ManifestDep` happens here:

```rust
pub fn load_manifest(source_root: &Path) -> Result<Option<Manifest>, MarsError> {
    let parsed: Config = ...;
    let Some(package) = parsed.package else { return Ok(None) };
    
    let deps: IndexMap<String, ManifestDep> = parsed.dependencies
        .into_iter()
        .filter_map(|(name, entry)| {
            // Manifest deps MUST have a URL — path deps are consumer-local
            let url = entry.url?;
            Some((name.to_string(), ManifestDep {
                url,
                version: entry.version,
            }))
        })
        .collect();
    
    Ok(Some(Manifest { package, dependencies: deps }))
}
```

**Breaking change**: Path-only deps in a manifest now warn (or error) instead of silently vanishing. This is a correctness improvement — if a package author writes a path dep in their manifest, they need to know it won't propagate to consumers.

**Serde compatibility**: Both `InstallDep` and `ManifestDep` deserialize from the same TOML format as the current `DependencyEntry`. The split is internal — the on-disk format doesn't change.

```rust
// mars.toml [dependencies] section deserializes as InstallDep
// Manifest extraction converts InstallDep → ManifestDep (filtering)
```

---

## A4: Shared Reconciliation Layer

### Problem

`mars link` has its own scan/conflict/apply/persist flow in `link.rs` and `cli/link.rs`, separate from the sync pipeline. The sync pipeline applies changes through `sync/apply.rs`. Both handle:
- Detecting existing content at destinations
- Conflict detection (hash comparison)
- Atomic file operations (copy, move, symlink)
- Cleanup (removing old content)

This duplication will drift on atomicity guarantees, diagnostics, force semantics, and safety fixes.

### Design

Extract a shared `reconcile` module that both sync apply and link use:

```rust
// src/reconcile/mod.rs

/// What exists at a destination path.
pub enum DestinationState {
    Empty,
    File { hash: ContentHash },
    Directory,
    Symlink { target: PathBuf },
}

/// What we want at a destination path.
pub enum DesiredState {
    /// Copy content from source to destination.
    FileContent { source: PathBuf, hash: ContentHash },
    /// Create symlink to target.
    Symlink { target: PathBuf },
    /// Remove whatever is there.
    Absent,
}

/// Result of reconciling one destination.
pub enum ReconcileOutcome {
    Created,
    Updated,
    Removed,
    Skipped { reason: &'static str },
    Conflict { existing: DestinationState, desired: DesiredState },
}

/// Reconcile a single destination path.
pub fn reconcile_one(
    dest: &Path,
    desired: DesiredState,
    force: bool,
) -> Result<ReconcileOutcome, MarsError>;

/// Scan a destination to determine its current state.
pub fn scan_destination(path: &Path) -> DestinationState;
```

**Sync apply** uses `reconcile_one` for each planned action. The existing `sync/apply.rs` becomes a thin layer that translates `PlannedAction` → `DesiredState` and calls into reconcile.

**Link** uses `scan_destination` + `reconcile_one` for its scan-and-link flow. The existing `link.rs::ScanResult` maps to `DestinationState`, and `merge_and_link` becomes a sequence of `reconcile_one` calls.

**Atomicity lives in one place**. The `reconcile_one` function handles tmp+rename for file writes, proper cleanup ordering, and cross-filesystem copy. Bug fixes to atomicity propagate to both sync and link.

### Migration

This is a pure refactor of internal implementation — the public API of `mars sync` and `mars link` doesn't change. The existing tests for both commands serve as regression guards.

---

## A5: Structured Diagnostics

### Problem

Library code emits warnings directly to stderr:
- `config/mod.rs`: warns about deprecated fields
- `sync/mod.rs`: warns about unmanaged collisions
- `sync/self_package.rs`: warns about shadowed items and collisions
- `resolve/mod.rs`: warns about version constraints

This bypasses JSON-mode contracts (`--json` flag) and makes warning handling untestable.

### Design

Return `Diagnostic` values from library layers:

```rust
/// A diagnostic message from library code.
pub struct Diagnostic {
    pub level: DiagnosticLevel,
    pub code: &'static str,     // machine-readable, e.g. "shadow-collision"
    pub message: String,        // human-readable
    pub context: Option<String>, // e.g. source name, item path
}

pub enum DiagnosticLevel {
    Warning,
    Info,
}
```

Phase functions return diagnostics alongside their results:

```rust
fn build_target(...) -> Result<(TargetedState, Vec<Diagnostic>), MarsError>;
```

Or use a collector pattern to avoid changing every return type:

```rust
/// Collects diagnostics during pipeline execution.
pub struct DiagnosticCollector {
    diagnostics: Vec<Diagnostic>,
}

impl DiagnosticCollector {
    pub fn warn(&mut self, code: &'static str, message: impl Into<String>);
    pub fn drain(&mut self) -> Vec<Diagnostic>;
}
```

The collector is passed through phase functions. The CLI layer renders diagnostics to stderr (human mode) or includes them in JSON output (json mode).

**Touch points**: Replace each `eprintln!("warning: ...")` with `collector.warn(...)`. Approximately 8-10 call sites across config, sync, self_package, and resolve.

### Testing

Diagnostics become testable — unit tests can assert that specific warnings are emitted for specific conditions without capturing stderr.
