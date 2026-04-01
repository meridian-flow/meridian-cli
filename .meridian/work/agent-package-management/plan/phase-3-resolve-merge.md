# Phase 3: Dependency Resolution + Three-Way Merge

## Scope

Implement two modules: `resolve/` (dependency graph resolution with semver constraints, topological sort, and transitive dependency handling) and `merge/` (three-way merge producing git-style conflict markers). These are the two most algorithmically complex modules in mars.

## Why This Order

Resolution sits between source fetching (Phase 2b) and the sync pipeline (Phase 4). The resolver takes fetched sources, reads their manifests, discovers transitive dependencies, and produces a `ResolvedGraph` that the sync pipeline consumes. Merge is used by `sync/apply.rs` when both source and local have changed. Both are medium-risk modules — resolution has the constraint intersection algorithm, merge wraps `git2::merge_file` — so building them in Round 3 gives time to validate against real scenarios before integration.

## Files to Modify

### `src/resolve/mod.rs` — Dependency Resolution

```rust
/// The resolved dependency graph — all sources with concrete versions
#[derive(Debug, Clone)]
pub struct ResolvedGraph {
    pub nodes: IndexMap<String, ResolvedNode>,
    pub order: Vec<String>,  // topological order (deps before dependents)
}

#[derive(Debug, Clone)]
pub struct ResolvedNode {
    pub source_name: String,
    pub resolved_ref: ResolvedRef,
    pub manifest: Option<Manifest>,
    pub deps: Vec<String>,  // source names this depends on
}

/// Resolve all sources and their transitive dependencies.
///
/// Algorithm:
/// 1. Start with user's declared sources from EffectiveConfig
/// 2. Fetch each source, read mars.toml if present
/// 3. Discover transitive deps from manifests (sources without manifest have none)
/// 4. For each dep URL seen from multiple dependents, intersect version constraints
/// 5. If intersection is empty → error with constraint chain
/// 6. Resolve each constraint to a concrete version (prefer locked version if still valid)
/// 7. Topological sort the graph (error on cycles)
/// 8. Return ResolvedGraph
pub fn resolve(
    config: &EffectiveConfig,
    cache_dir: &Path,
    locked: Option<&LockFile>,
) -> Result<ResolvedGraph>;
```

**Version constraint resolution**:
- Parse version strings using `semver::VersionReq` for constraints (`>=0.5.0`, `^2.0`, `~1.2`).
- Parse `@v0.5.0` as exact version, `@v2` as `>=2.0.0, <3.0.0`, `@latest` as any version (newest wins).
- `@branch` and `@commit` are ref pins — no semver constraint, just checkout that ref.
- When multiple dependents constrain the same source URL: intersect `VersionReq` constraints. If any version satisfies all constraints → success. If no version satisfies all → error with the full constraint chain showing who requires what.

**Locked version preference**:
- When a lock file exists and has a version for a source, prefer that version if it still satisfies the constraint.
- This gives reproducible builds — `mars sync` with unchanged config produces no changes.

**Minimum version selection** (Go-style MVS):
- When no locked version exists, select the **minimum** version satisfying all constraints. Not the latest. This is conservative and reproducible — the same constraint always resolves to the same version on any machine. Users who want latest use `@latest` explicitly.

**Maximize versions mode** (for `mars upgrade`):
- The resolver needs an alternate mode where it finds the **newest** compatible versions across all upgrade targets simultaneously. `mars upgrade` passes the set of sources to upgrade; the resolver finds the maximum version for each that still satisfies all cross-source constraints. This is the inverse of MVS — used only when the user explicitly asks to upgrade.

**Transitive dependency discovery**:
- Sources without `mars.toml`: no transitive deps. They contribute items but don't pull in other sources.
- Sources with `mars.toml`: read `[dependencies]` section. Each dep is a new source to fetch and resolve.
- Transitive deps inherit version constraints from their manifest `DepSpec`, not from the user's `agents.toml`.
- If the user also declares a transitive dep in their `agents.toml`, the user's constraint takes precedence (intersection still applies).

**Topological sort**:
- Kahn's algorithm (BFS-based, simpler to implement than DFS variant).
- Detect cycles: if the queue empties but unvisited nodes remain → cycle. Error with the cycle path.

**Constraint intersection**:
```rust
/// Intersect multiple version constraints for the same source URL.
/// Returns the narrowest constraint that satisfies all inputs.
fn intersect_constraints(
    constraints: &[(String, semver::VersionReq)],  // (dependent_name, constraint)
    available: &[AvailableVersion],
) -> Result<semver::Version>;
```

Find all available versions that satisfy every constraint. If the set is empty → error listing each constraint and its source. If non-empty → pick the minimum (MVS).

### `src/merge/mod.rs` — Three-Way Merge

```rust
pub struct MergeResult {
    pub content: Vec<u8>,
    pub has_conflicts: bool,
    pub conflict_count: usize,
}

pub struct MergeLabels {
    pub base: String,     // e.g., "base (last sync)"
    pub local: String,    // e.g., "local"
    pub theirs: String,   // e.g., "meridian-base@v0.6.0"
}

/// Perform three-way merge using git2::merge_file.
///
/// base: what mars installed last time (from cache/lock)
/// local: current file on disk
/// theirs: new source content
///
/// Returns merged content. If conflicts exist, content contains
/// standard git conflict markers (<<<<<<<, =======, >>>>>>>).
pub fn merge_content(
    base: &[u8],
    local: &[u8],
    theirs: &[u8],
    labels: &MergeLabels,
) -> Result<MergeResult>;

/// Check if file content contains unresolved conflict markers
pub fn has_conflict_markers(content: &[u8]) -> bool;
```

**Implementation**: Use `git2::merge_file()` which provides the same three-way merge algorithm as `git merge-file`. This is already a dependency via `git2` — no extra crate needed.

```rust
use git2::MergeFileInput;

pub fn merge_content(base: &[u8], local: &[u8], theirs: &[u8], labels: &MergeLabels) -> Result<MergeResult> {
    let ancestor = MergeFileInput::new().content(base).label(&labels.base);
    let ours = MergeFileInput::new().content(local).label(&labels.local);
    let their = MergeFileInput::new().content(theirs).label(&labels.theirs);

    let opts = git2::MergeFileOptions::new();
    let result = git2::merge_file(&ancestor, &ours, &their, Some(&opts))?;

    let content = result.content().unwrap_or_default().to_vec();
    let has_conflicts = result.automergeable() == false;
    // Count conflicts by counting "<<<<<<< " markers
    let conflict_count = content.windows(7).filter(|w| w == b"<<<<<<<").count();

    Ok(MergeResult { content, has_conflicts, conflict_count })
}
```

**Note on `threeway-merge` crate**: The architecture doc mentions it, but `git2::merge_file()` does the same thing and `git2` is already a dependency. Using `git2` directly avoids adding another crate. **Decision**: Drop `threeway-merge` from Cargo.toml, use `git2::merge_file()` exclusively.

**Conflict marker format**:
```
<<<<<<< local
local content here
=======
upstream content here
>>>>>>> meridian-base@v0.6.0
```

Standard git format. IDEs (VS Code, JetBrains) recognize these and provide "Accept Current/Incoming/Both" UI.

## Dependencies

- Requires: Phase 0 (stubs), Phase 1a (error types, hash), Phase 1b (config types, manifest types, lock types)
- Uses at runtime: Phase 2b (`source::list_versions`, `source::fetch_source`) — but can be unit-tested with mock data
- Produces: `resolve()` → `ResolvedGraph` consumed by Phase 4; `merge_content()` consumed by `sync/apply.rs` in Phase 4
- Independent of: Phase 2a (discover/validate)

## Interface Contract

Consumers:
- `sync/` calls `resolve::resolve(config, cache, lock)` → gets `ResolvedGraph` with topological order
- `sync/apply.rs` calls `merge::merge_content(base, local, theirs, labels)` when both source and local changed
- `cli/why.rs` uses `ResolvedGraph.nodes[x].deps` to trace dependency chains

## Patterns to Follow

- `IndexMap` for graph nodes — preserves insertion order, deterministic.
- Error messages for constraint conflicts include the full chain: "source A requires >=0.5.0, source B requires <0.4.0 — no version satisfies both"
- Merge labels always include version info for readable conflict markers.

## Verification Criteria

### Resolution tests:
- [ ] Single source, no deps → graph with one node
- [ ] Two sources, no deps → graph with two nodes (either order is valid topo sort)
- [ ] Source with manifest dep → transitive dep is fetched and included
- [ ] Two dependents with compatible constraints → minimum satisfying version selected
- [ ] Two dependents with incompatible constraints → clear error with constraint chain
- [ ] Cycle in dependencies → error naming the cycle
- [ ] Locked version preferred when still satisfies constraint
- [ ] Locked version ignored when constraint changed and no longer satisfied
- [ ] `@latest` resolves to newest available version
- [ ] `@v2` resolves to latest `2.x.x`
- [ ] `@branch` resolves to that branch ref (no semver)
- [ ] Source without manifest → no transitive deps, still works

### Merge tests:
- [ ] Base = local = theirs → no changes, clean merge
- [ ] Base ≠ theirs, base = local → theirs wins (clean update)
- [ ] Base ≠ local, base = theirs → local wins (keep local)
- [ ] All three differ, non-overlapping changes → clean merge (auto-merged)
- [ ] All three differ, overlapping changes → conflict markers in output
- [ ] Conflict markers match git format (`<<<<<<<`, `=======`, `>>>>>>>`)
- [ ] Labels appear in conflict markers
- [ ] `has_conflict_markers()` detects markers correctly
- [ ] Binary content → treated as conflict (can't line-merge binary)
- [ ] Empty base (new file with local and upstream) → handled gracefully

- [ ] `cargo clippy -- -D warnings` passes
- [ ] All tests pass

## Constraints

- Resolution uses semver crate for ALL version parsing and comparison. No custom version logic.
- Minimum version selection (MVS), not latest. Be explicit about this in code comments.
- `merge_content` uses `git2::merge_file()`, NOT a separate `threeway-merge` crate. Remove `threeway-merge` from deps if present.
- Conflict count is approximate (counting marker lines). Exact count isn't critical — `has_conflicts` boolean is the authoritative flag.
- The resolver calls `source::fetch_source()` and `source::list_versions()` — for unit tests, either create real temp git repos OR restructure so the resolver takes a trait/closure for fetching (enabling mocks). Prefer real repos for higher confidence.

## Risk

This phase has the highest algorithmic complexity. The constraint intersection algorithm is straightforward for small graphs but must handle:
- The same URL appearing as both a direct dependency and a transitive dependency (constraint intersection)
- A locked version that's no longer available (tag deleted) — graceful fallback
- Dev overrides: when a source is overridden to a local path, skip version resolution for it entirely

If the resolver proves too complex for a single phase, split into: (a) single-level resolution (direct deps only, no transitive) and (b) transitive resolution. But this should be avoidable — the graph is small.
