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

/// Phase 2: Resolved dependency graph with merged model aliases.
pub struct ResolvedState {
    pub loaded: LoadedConfig,
    pub graph: ResolvedGraph,
    /// Model aliases merged from dependency tree + builtins.
    /// consumer mars.toml > deps (declaration order) > builtins > fallback IDs.
    /// Available for rule discovery (per-model rule classification) and
    /// capability materialization.
    pub model_aliases: IndexMap<String, ModelAlias>,
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

/// Phase 5: Applied results (content written to .mars/).
pub struct AppliedState {
    pub planned: PlannedState,
    pub applied: ApplyResult,
}

/// Phase 6: All managed targets synced.
pub struct SyncedState {
    pub applied: AppliedState,
    pub target_outcomes: Vec<TargetSyncOutcome>,
}
```

The `execute()` function becomes an orchestrator that calls phase functions. **Phase functions consume prior state by value** (moved, not borrowed) — this is what makes the nesting work without cloning or lifetimes:

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    validate_request(request)?;
    
    let loaded = load_config(ctx, request)?;
    let resolved = resolve_graph(ctx, loaded, request)?;       // loaded moved in
    let targeted = build_target(ctx, resolved, request)?;      // resolved moved in
    let planned = create_plan(ctx, targeted, request)?;        // targeted moved in
    
    if request.options.frozen {
        check_frozen_gate(&planned)?;  // borrow is fine for read-only check
    }
    
    let applied = apply_plan(ctx, planned, request)?;          // writes to .mars/
    
    // Phase B: sync all managed targets from .mars/
    // let synced = sync_managed_targets(ctx, applied, request)?;
    
    let report = finalize(ctx, applied, request)?;             // applied moved in
    
    Ok(report)
}
```

Each phase function is independently testable. Extension points insert as new phases. Notably, the Phase B target sync phase inserts between `apply_plan` (which writes to `.mars/`) and `finalize`:

```rust
// Phase B: after apply_plan writes canonical content, sync all targets
let synced = sync_managed_targets(ctx, applied, request)?;  // .agents/, .claude/, etc.
let report = finalize(ctx, synced, request)?;
```

### Phase Function Signatures

All phase functions **consume** the prior phase state by value. This matches the "moved, not cloned" nesting model — `LoadedConfig` is moved into `ResolvedState` when `resolve_graph` returns, not borrowed.

```rust
fn load_config(ctx: &MarsContext, request: &SyncRequest) -> Result<LoadedConfig, MarsError>;
fn resolve_graph(ctx: &MarsContext, loaded: LoadedConfig, request: &SyncRequest) -> Result<ResolvedState, MarsError>;
fn build_target(ctx: &MarsContext, resolved: ResolvedState, request: &SyncRequest) -> Result<TargetedState, MarsError>;
fn create_plan(ctx: &MarsContext, targeted: TargetedState, request: &SyncRequest) -> Result<PlannedState, MarsError>;
fn apply_plan(ctx: &MarsContext, planned: PlannedState, request: &SyncRequest) -> Result<AppliedState, MarsError>;
fn sync_managed_targets(ctx: &MarsContext, applied: AppliedState, request: &SyncRequest) -> Result<SyncedState, MarsError>;
fn finalize(ctx: &MarsContext, synced: SyncedState, request: &SyncRequest) -> Result<SyncReport, MarsError>;
```

Note: `ctx` and `request` are borrowed — they're read-only context that doesn't participate in phase ownership transfer.

### What Moves Where

| Current step | New phase function | Notes |
|---|---|---|
| Steps 1-4b (lock, config, mutation, merge) | `load_config()` | Config loading + mutation under sync lock |
| Steps 5-7 (validate targets, load lock, resolve) | `resolve_graph()` | Resolution with options from request. Merges `[models]` from dependency tree + builtins into `ResolvedState.model_aliases`. |
| Steps 8-11 (target, collisions, rewrites, validation) | `build_target()` | Discovery, filtering, collision detection |
| Steps 12-13c (diff, plan, _self injection) | `create_plan()` | _self handled inside target building, not here (see A2) |
| Step 14 (frozen gate) | `check_frozen_gate()` | Standalone check between plan and apply |
| Steps 15-16 (persist config, apply) | `apply_plan()` | Config persistence + apply to `.mars/` |
| (new) | `sync_managed_targets()` | Copy from `.mars/` to all configured targets |
| Step 17 (write lock) | `finalize()` | Lock rebuild + report construction |

### Nesting vs Flattening

The phase structs above nest (`ResolvedState` contains `LoadedConfig`). This preserves access to earlier data without passing many arguments. However, the nesting means `SyncedState` transitively contains everything. This is fine because:

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

Instead of `inject_self_items` mutating the plan post-hoc, the project root is modeled as a synthetic source that goes through the same discovery pipeline as every dependency:

```rust
fn build_target(ctx: &MarsContext, resolved: ResolvedState, request: &SyncRequest) -> Result<TargetedState, MarsError> {
    let mut target = build_target_from_graph(&resolved.graph, &resolved.loaded.effective)?;
    
    // Local package: treat project root as a source and run it through
    // the same discover → filter → target pipeline as dependency sources.
    if resolved.loaded.config.package.is_some() {
        let local_items = discover_source(&ctx.project_root, Some("_self"))?;
        // Filter local items the same way as dependency items
        // (respects the same DiscoveryConvention registry from Phase B)
        for item in local_items {
            let target_item = TargetItem {
                id: item.id,
                origin: SourceOrigin::LocalPackage,
                materialization: Materialization::Symlink {
                    source_abs: ctx.project_root.join(&item.source_path),
                },
                // ... other fields
            };
            // Shadow check: local items win over dependency items
            if let Some(existing) = target.items.get(&target_item.dest_path) {
                collector.warn("shadow", format!(
                    "local {} `{}` shadows dependency `{}` item",
                    item.id.kind, item.id.name, existing.origin
                ));
                target.items.shift_remove(&target_item.dest_path);
            }
            target.items.insert(target_item.dest_path.clone(), target_item);
        }
    }
    
    // ... collision detection, validation, etc.
}
```

**Key change from review feedback**: local packages use the *same* `discover_source()` function as dependency sources. This means when Phase B adds new item kinds with new `DiscoveryConvention` entries, local packages automatically discover them too — no separate `discover_local_items` to update.

Only two things remain local-specific:
1. **Materialization strategy** — local items use `Symlink` in `.mars/` (so edits propagate without re-running sync). When targets are synced from `.mars/`, the symlink is followed and the content is copied to the target.
2. **Shadow precedence** — local items always win over dependency items (with warning)

The shadow check and unmanaged collision avoidance remain in `build_target`, but they operate on the same `TargetItem` type as dependency items.

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
    pub materialization: Materialization,  // how to apply this item to .mars/
}

/// How an item should be materialized in the canonical store (.mars/).
pub enum Materialization {
    /// Copy source content to destination (standard for dependency items).
    Copy,
    /// Create a symlink to the source (for local package items — edits propagate).
    Symlink { source_abs: PathBuf },
}
```

Note: `Materialization` describes how content reaches `.mars/` (the canonical store). The subsequent target sync phase always *copies* from `.mars/` to targets, following symlinks as needed. This means local package edits propagate to targets on the next `mars sync` without needing to re-resolve.

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

**Policy for path-only manifest deps**: Path-only deps in a manifest are filtered out during `load_manifest()` and a structured `Diagnostic::Warning` is emitted (not an error). This matches the current runtime behavior (resolver silently skips them) but makes the filtering explicit and visible:

```rust
pub fn load_manifest(source_root: &Path) -> Result<(Option<Manifest>, Vec<Diagnostic>), MarsError> {
    // ...
    let mut diagnostics = Vec::new();
    let deps: IndexMap<String, ManifestDep> = parsed.dependencies
        .into_iter()
        .filter_map(|(name, entry)| {
            match entry.url {
                Some(url) => Some((name.to_string(), ManifestDep { url, version: entry.version })),
                None => {
                    diagnostics.push(Diagnostic::warning(
                        "manifest-path-dep",
                        format!("manifest dependency `{name}` has no URL and will not propagate to consumers"),
                    ));
                    None
                }
            }
        })
        .collect();
    // ...
}
```

**Serde compatibility**: Both `InstallDep` and `ManifestDep` deserialize from the same TOML format as the current `DependencyEntry`. The split is internal — the on-disk format doesn't change.

```rust
// mars.toml [dependencies] section deserializes as InstallDep
// Manifest extraction converts InstallDep → ManifestDep (warning + filtering)
```

---

## A4: Shared Reconciliation Layer

### Problem

`mars link` has its own scan/conflict/apply/persist flow in `link.rs` and `cli/link.rs`, separate from the sync pipeline. The sync pipeline applies changes through `sync/apply.rs`. Both handle:
- Detecting existing content at destinations
- Conflict detection (hash comparison)
- Atomic file operations (copy, move, symlink)
- Cleanup (removing old content)

This duplication will drift on atomicity guarantees, diagnostics, force semantics, and safety fixes. With the `.mars/` canonical store model, reconciliation becomes even more critical — it's used for both writing to `.mars/` AND copying from `.mars/` to all managed targets.

### Design

Extract a shared `reconcile` module with two layers: low-level atomic filesystem operations (used by content apply, target sync, and link) and higher-level item-level reconciliation (used by sync apply and target sync).

### Layer 1: Atomic Filesystem Operations

```rust
// src/reconcile/fs_ops.rs

/// Atomic file write via tmp+rename.
pub fn atomic_write_file(dest: &Path, content: &[u8]) -> Result<(), MarsError>;

/// Atomic directory install: copy tree to tmp dir, then rename.
pub fn atomic_install_dir(source: &Path, dest: &Path) -> Result<(), MarsError>;

/// Create a symlink atomically (remove existing + create).
pub fn atomic_symlink(link_path: &Path, target: &Path) -> Result<(), MarsError>;

/// Remove a file or directory tree safely.
pub fn safe_remove(path: &Path) -> Result<(), MarsError>;

/// Compute hash of file or directory for comparison.
pub fn content_hash(path: &Path, kind: ItemKind) -> Result<ContentHash, MarsError>;

/// Atomic copy: read source (following symlinks), write to tmp, rename to dest.
/// This is the primary mechanism for target materialization.
pub fn atomic_copy_file(source: &Path, dest: &Path) -> Result<(), MarsError>;

/// Atomic directory copy: deep copy source tree (following symlinks) to tmp, rename to dest.
pub fn atomic_copy_dir(source: &Path, dest: &Path) -> Result<(), MarsError>;
```

These are the primitives that content apply, target sync, and link all need. Currently duplicated across `sync/apply.rs`, `link.rs`, and `fs/mod.rs`. The `atomic_copy_*` functions are new — they support the copy-based target materialization model where content is always copied (not symlinked) to managed targets.

### Layer 2: Item-Level Reconciliation

```rust
// src/reconcile/mod.rs

/// What exists at a destination path.
pub enum DestinationState {
    Empty,
    File { hash: ContentHash },
    Directory { hash: ContentHash },  // tree hash for skills/hooks
    Symlink { target: PathBuf },
    ForeignSymlink { target: PathBuf },  // symlink to unexpected location
}

/// What we want at a destination path.
pub enum DesiredState {
    /// Copy a single file from source to destination.
    CopyFile { source: PathBuf, hash: ContentHash },
    /// Copy a directory tree from source to destination.
    CopyDir { source: PathBuf, hash: ContentHash },
    /// Create symlink to target (only used for local items in .mars/).
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

**Content apply** (to `.mars/`) uses `reconcile_one` for each planned action. Dependency items use `CopyFile`/`CopyDir`; local items use `Symlink`.

**Target sync** (from `.mars/` to managed targets) uses `reconcile_one` with `CopyFile`/`CopyDir` for every item — always copying, even for items that are symlinks in `.mars/` (the copy follows the symlink). This is the key mechanism that makes local package edits propagate: `.mars/agents/foo.md` is a symlink → target sync copies the symlink target's content to `.claude/agents/foo.md`.

**Link** uses the Layer 1 atomic fs ops directly. Link's "merge unique files into managed root" algorithm is genuinely different from sync's item-level reconciliation — it scans a target directory for user files, moves non-conflicting files into the managed root, and replaces the directory with a symlink. This remains link-specific logic, but it uses the shared atomic primitives (`atomic_copy_file`, `safe_remove`, `content_hash`) instead of duplicating them.

**What's shared vs. link-specific:**
- **Shared**: atomic fs ops, content hashing, destination scanning, item-level reconciliation
- **Link-specific**: the merge-unique-files-then-adopt algorithm (one-time adoption of an existing target directory)

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

The collector is threaded through phase functions and accumulated into `SyncReport`:

```rust
pub struct SyncReport {
    pub applied: ApplyResult,
    pub pruned: Vec<ActionOutcome>,
    pub diagnostics: Vec<Diagnostic>,        // replaces warnings: Vec<ValidationWarning>
    pub dependency_changes: Vec<DependencyUpsertChange>,
    pub target_outcomes: Vec<TargetSyncOutcome>,  // NEW: per-target sync results
    pub dry_run: bool,
}
```

The CLI layer is the **only** place that renders diagnostics — to stderr in human mode, or as a `"diagnostics"` array in JSON output. No library code calls `eprintln!` directly.

**Touch points**: Replace each `eprintln!("warning: ...")` with `collector.warn(...)`. Approximately 8-10 call sites across config, sync, self_package, and resolve. The existing `warnings: Vec<ValidationWarning>` in `SyncReport` merges into the new `diagnostics` field.

### Testing

Diagnostics become testable — unit tests can assert that specific warnings are emitted for specific conditions without capturing stderr.
