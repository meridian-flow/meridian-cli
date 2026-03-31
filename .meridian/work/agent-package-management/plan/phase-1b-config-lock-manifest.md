# Phase 1b: Config + Lock + Manifest Parsing

## Scope

Implement TOML parsing and serialization for the three configuration files: `agents.toml` (user config), `agents.lock` (lock file), and `mars.toml` (per-package manifest). This phase produces the data model that the rest of the pipeline operates on — pure serde structs with load/save functions.

## Why This Order

The sync pipeline consumes `Config` at the top and produces `LockFile` at the bottom. The resolver reads `Manifest` from fetched sources. Every module above the data layer depends on these types. Getting the serde models right first means all later phases code against stable, tested structures.

## Files to Modify

### `src/config/mod.rs` — User Config (`agents.toml` + `agents.local.toml`)

Types from the architecture doc:

```rust
/// Top-level agents.toml
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub sources: IndexMap<String, SourceEntry>,
    #[serde(default)]
    pub settings: Settings,
}

/// A declared source. Uses `url` XOR `path` to determine type.
/// NOT internally tagged — uses presence of fields to determine variant.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceEntry {
    pub url: Option<String>,
    pub path: Option<PathBuf>,
    pub version: Option<String>,
    pub agents: Option<Vec<String>>,
    pub skills: Option<Vec<String>>,
    pub exclude: Option<Vec<String>>,
    pub rename: Option<IndexMap<String, String>>,
}

/// Dev override config (agents.local.toml)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LocalConfig {
    #[serde(default)]
    pub overrides: IndexMap<String, OverrideEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverrideEntry {
    pub path: PathBuf,
}

/// Merged view of config + local overrides
pub struct EffectiveConfig {
    pub sources: IndexMap<String, EffectiveSource>,
    pub settings: Settings,
}

pub struct EffectiveSource {
    pub name: String,
    pub spec: SourceSpec,
    pub filter: FilterMode,
    pub rename: IndexMap<String, String>,
    pub is_overridden: bool,
    pub original_git: Option<GitSpec>,
}

pub enum SourceSpec {
    Git(GitSpec),
    Path(PathBuf),
}

pub struct GitSpec {
    pub url: String,
    pub version: Option<String>,
}

pub enum FilterMode {
    All,
    Include { agents: Vec<String>, skills: Vec<String> },
    Exclude(Vec<String>),
}
```

Functions:
```rust
/// Load agents.toml from .agents/ root
pub fn load(root: &Path) -> Result<Config>;

/// Load agents.local.toml (returns Default if absent)
pub fn load_local(root: &Path) -> Result<LocalConfig>;

/// Merge config + local overrides into EffectiveConfig
pub fn merge(config: Config, local: LocalConfig) -> Result<EffectiveConfig>;

/// Write agents.toml atomically
pub fn save(root: &Path, config: &Config) -> Result<()>;
```

**Validation in `merge()`**:
- Error if a source has both `url` and `path` set
- Error if a source has neither `url` nor `path`
- Error if a source has both `agents`/`skills` AND `exclude` (pick one filter mode)
- Warn if an override references a source name not in config

### `src/lock/mod.rs` — Lock File (`agents.lock`)

Types from the architecture doc with the dual-checksum enhancement from the review synthesis:

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockFile {
    pub version: u32,  // schema version, currently 1
    pub sources: IndexMap<String, LockedSource>,
    pub items: IndexMap<String, LockedItem>,  // key = "agents/name.md" or "skills/name"
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockedSource {
    pub url: Option<String>,
    pub path: Option<String>,
    pub version: Option<String>,
    pub commit: Option<String>,
    pub tree_hash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockedItem {
    pub source: String,
    pub kind: ItemKind,
    pub version: Option<String>,
    pub source_checksum: String,    // what upstream provided (pre-rewrite)
    pub installed_checksum: String, // what mars wrote to disk (post-rewrite, if any)
    pub dest_path: String,
}

#[derive(Debug, Clone, Copy, Hash, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ItemKind {
    Agent,
    Skill,
}

/// Stable item identity
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct ItemId {
    pub kind: ItemKind,
    pub name: String,
}
```

Functions:
```rust
/// Load agents.lock (returns empty LockFile if absent)
pub fn load(root: &Path) -> Result<LockFile>;

/// Write agents.lock atomically (uses fs::atomic_write)
pub fn write(root: &Path, lock: &LockFile) -> Result<()>;

/// Build a new lock file from resolved graph + apply results
pub fn build(graph: &ResolvedGraph, applied: &ApplyResult) -> Result<LockFile>;
```

**Lock serialization**: Keys sorted deterministically for clean git diffs. Items keyed by dest_path string (e.g., `[items."agents/coder.md"]`).

### `src/manifest/mod.rs` — Package Manifest (`mars.toml`)

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    pub package: PackageInfo,
    #[serde(default)]
    pub dependencies: IndexMap<String, DepSpec>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackageInfo {
    pub name: String,
    pub version: String,
    pub description: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DepSpec {
    pub url: String,
    pub version: String,
    pub items: Option<Vec<String>>,
}
```

Functions:
```rust
/// Load mars.toml from a source tree root. Returns None if absent.
pub fn load(source_root: &Path) -> Result<Option<Manifest>>;
```

## Dependencies

- Requires: Phase 0 (module stubs), Phase 1a (`fs::atomic_write` for `lock::write` and `config::save`, `MarsError` types)
- Produces: `Config`, `EffectiveConfig`, `LockFile`, `Manifest` — consumed by resolve, sync, and CLI
- Independent of: Phase 2a, Phase 2b (can run before them)

**Note on Phase 1a dependency**: The `load` functions only need `std::fs::read_to_string` + `toml::from_str`. The `save`/`write` functions need `fs::atomic_write` from Phase 1a. If running in parallel with 1a, stub the save functions initially and fill them in once 1a lands.

## Interface Contract

Other modules import:
- `crate::config::{Config, EffectiveConfig, EffectiveSource, SourceSpec, FilterMode, GitSpec}`
- `crate::lock::{LockFile, LockedSource, LockedItem, ItemId, ItemKind}`
- `crate::manifest::{Manifest, PackageInfo, DepSpec}`

## Patterns to Follow

- `IndexMap` for all ordered maps (deterministic serialization).
- `#[serde(default)]` on optional collection fields.
- `#[serde(rename_all = "lowercase")]` on enums serialized to TOML.
- All `load` functions return typed errors (`ConfigError`, `LockError`) that convert to `MarsError`.

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] Config parsing tests:
  - Parse valid `agents.toml` with git source, path source, mixed → correct `Config`
  - Parse with `agents`/`skills` filter → `FilterMode::Include`
  - Parse with `exclude` filter → `FilterMode::Exclude`
  - Error on both `agents` + `exclude` on same source
  - Error on source with neither `url` nor `path`
  - Roundtrip: construct `Config` → serialize → deserialize → assert equal
- [ ] Lock parsing tests:
  - Parse valid `agents.lock` → correct `LockFile` with dual checksums
  - Roundtrip: construct `LockFile` → serialize → deserialize → assert equal
  - Verify deterministic key ordering in serialized output
  - Empty lock file (no items) loads correctly
- [ ] Manifest parsing tests:
  - Parse valid `mars.toml` with deps → correct `Manifest`
  - `load()` returns `None` when file doesn't exist
  - Parse manifest without dependencies → empty `IndexMap`
- [ ] Config merge tests:
  - Local override replaces git source with path source
  - Override preserves `original_git` for lock reproducibility
  - Merge with empty local config → same as base config
- [ ] `cargo clippy -- -D warnings` passes

## Constraints

- TOML serialization must produce deterministic output (sorted keys via `IndexMap`).
- `SourceEntry` uses flat struct with optional fields, NOT internally tagged enum. TOML doesn't support serde's internal tagging well. Validation happens in `merge()`.
- Lock file always has `version = 1` (schema version).
- `load()` functions must return typed errors with file path context (not generic "parse error").
