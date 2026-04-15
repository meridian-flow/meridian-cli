# Newtypes and Source Spec Parser

Fixes requirements #6 (SSH URL misparse), #8 (stringly-typed identities), #9 (name-keyed dependency identity), #15 (EffectiveConfig bundling), #16 (parse_source_specifier mixed concerns).

## Problem Statement

### String Confusion

The codebase uses `String` for six semantically distinct concepts: source names, item names, destination paths, URLs, commit SHAs, and content hashes. The compiler can't distinguish them — any `String` goes into any `String` slot.

Concrete bugs this enables:
- A source name passed where a dest path is expected compiles fine, fails silently at runtime
- Rename maps (`IndexMap<String, String>`) don't communicate whether keys/values are item names, dest paths, or arbitrary text
- Two sources providing the same item name are conflated because dependency identity uses name strings, not (URL, name) tuples

### Dependency Identity

`ResolvedGraph.nodes` is keyed by `String` (source name). Two sources with different URLs but the same TOML key name silently collide in the graph. The source name is a user-chosen alias, not a stable identifier — renaming a source in `agents.toml` changes its identity in the resolver.

### Source Spec Parser

`cli/add.rs::parse_source_specifier` performs four operations in one function:
1. Detect input format (path vs URL vs shorthand)
2. Extract version constraint (split on `@`)
3. Normalize URL (strip protocol, resolve shorthand)
4. Derive display name

The `@` split happens before format classification, so `git@github.com:org/repo.git` splits into `git` + `github.com:org/repo.git` — SSH URLs are corrupted. The function cannot be fixed incrementally because the operations are interleaved.

## Newtype Definitions

### Module: `src/types.rs`

All newtypes live in one module, re-exported from `lib.rs`. This keeps the definitions together (easier to audit trait impls) and avoids circular dependencies between modules that use them.

```rust
// src/types.rs

use std::fmt;
use std::ops::Deref;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Macro: all string newtypes share the same boilerplate
// ---------------------------------------------------------------------------

macro_rules! string_newtype {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Debug, Clone, Hash, Eq, PartialEq, Ord, PartialOrd)]
        pub struct $name(String);

        impl $name {
            pub fn new(s: impl Into<String>) -> Self {
                Self(s.into())
            }

            pub fn as_str(&self) -> &str {
                &self.0
            }

            pub fn into_inner(self) -> String {
                self.0
            }
        }

        impl Deref for $name {
            type Target = str;
            fn deref(&self) -> &str {
                &self.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str(&self.0)
            }
        }

        impl From<String> for $name {
            fn from(s: String) -> Self {
                Self(s)
            }
        }

        impl From<&str> for $name {
            fn from(s: &str) -> Self {
                Self(s.to_owned())
            }
        }

        impl Serialize for $name {
            fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
                self.0.serialize(serializer)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
                String::deserialize(deserializer).map(Self)
            }
        }
    };
}

// ---------------------------------------------------------------------------
// Newtype definitions
// ---------------------------------------------------------------------------

string_newtype!(
    /// User-chosen alias for a source in agents.toml.
    /// Example: "meridian-base", "my-local-agents"
    /// This is a display name, not a stable identity — use SourceId for deduplication.
    SourceName
);

string_newtype!(
    /// The name portion of an item identity.
    /// For agents: stem of the .md file (e.g., "coder", "dev-orchestrator").
    /// For skills: directory name (e.g., "__meridian-spawn", "frontend-design").
    ItemName
);

string_newtype!(
    /// Canonical URL for a git source, protocol-stripped and normalized.
    /// Example: "github.com/haowjy/meridian-base"
    /// Constructed only by SourceSpecParser — no raw string construction.
    SourceUrl
);

string_newtype!(
    /// 40-character hex git commit SHA.
    /// Example: "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
    CommitHash
);

string_newtype!(
    /// SHA-256 content hash, prefixed with algorithm.
    /// Example: "sha256:abc123def456..."
    ContentHash
);

// ---------------------------------------------------------------------------
// DestPath: path newtype (wraps PathBuf, not String)
// ---------------------------------------------------------------------------

/// Relative path under .agents/ for an installed item.
/// Example: "agents/coder.md", "skills/__meridian-spawn"
/// Always uses forward slashes. Never absolute.
#[derive(Debug, Clone, Hash, Eq, PartialEq, Ord, PartialOrd)]
pub struct DestPath(PathBuf);

impl DestPath {
    pub fn new(p: impl Into<PathBuf>) -> Self {
        Self(p.into())
    }

    pub fn as_path(&self) -> &Path {
        &self.0
    }

    pub fn into_inner(self) -> PathBuf {
        self.0
    }

    /// Join with the .agents/ root to get absolute path
    pub fn resolve(&self, agents_root: &Path) -> PathBuf {
        agents_root.join(&self.0)
    }
}

impl Deref for DestPath {
    type Target = Path;
    fn deref(&self) -> &Path {
        &self.0
    }
}

impl fmt::Display for DestPath {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0.display())
    }
}

impl Serialize for DestPath {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.to_string_lossy().serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for DestPath {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        String::deserialize(deserializer).map(|s| Self(PathBuf::from(s)))
    }
}

// ---------------------------------------------------------------------------
// SourceId: composite identity for dependency deduplication
// ---------------------------------------------------------------------------

/// Stable identity for a package source, independent of the user-chosen alias.
///
/// Two sources with different SourceName but same canonical URL are the SAME
/// source — the resolver must detect this. SourceId makes that comparison
/// type-safe. Path sources use the canonicalized absolute path as identity.
#[derive(Debug, Clone, Hash, Eq, PartialEq)]
pub enum SourceId {
    Git { url: SourceUrl },
    Path { canonical: PathBuf },
}

impl SourceId {
    pub fn git(url: SourceUrl) -> Self {
        Self::Git { url }
    }

    /// Canonicalize a path source relative to the project root.
    /// Fails if the path doesn't exist (can't canonicalize).
    pub fn path(base: &Path, relative: &Path) -> std::io::Result<Self> {
        let canonical = base.join(relative).canonicalize()?;
        Ok(Self::Path { canonical })
    }
}

impl fmt::Display for SourceId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Git { url } => write!(f, "git:{url}"),
            Self::Path { canonical } => write!(f, "path:{}", canonical.display()),
        }
    }
}

// ---------------------------------------------------------------------------
// RenameRule: replaces IndexMap<String, String>
// ---------------------------------------------------------------------------

/// A single rename mapping: install `from` as `to`.
///
/// Both fields are ItemName, not DestPath — the rename applies to the item
/// identity, and the dest path is derived from the renamed name plus the
/// item kind prefix (agents/ or skills/).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RenameRule {
    pub from: ItemName,
    pub to: ItemName,
}

/// Ordered collection of rename rules for a source.
/// Ordered because config order matters — first match wins if multiple
/// rules could apply (though that's a config error we should warn about).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RenameMap(Vec<RenameRule>);

impl RenameMap {
    pub fn new() -> Self {
        Self(Vec::new())
    }

    pub fn push(&mut self, rule: RenameRule) {
        self.0.push(rule);
    }

    pub fn resolve(&self, name: &ItemName) -> Option<&ItemName> {
        self.0.iter()
            .find(|r| r.from == *name)
            .map(|r| &r.to)
    }

    pub fn iter(&self) -> impl Iterator<Item = &RenameRule> {
        self.0.iter()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }
}
```

### Serde for RenameMap: TOML compatibility

The current config serializes renames as `{ "coder" = "cool-coder" }` in TOML. To preserve this format, `RenameMap` implements custom serde that serializes as an `IndexMap<String, String>` on the wire:

```rust
// In the Serialize/Deserialize impls for RenameMap (replaces the derive):

impl Serialize for RenameMap {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut map = serializer.serialize_map(Some(self.0.len()))?;
        for rule in &self.0 {
            map.serialize_entry(rule.from.as_str(), rule.to.as_str())?;
        }
        map.end()
    }
}

impl<'de> Deserialize<'de> for RenameMap {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let map = IndexMap::<String, String>::deserialize(deserializer)?;
        Ok(Self(map.into_iter().map(|(k, v)| RenameRule {
            from: ItemName::new(k),
            to: ItemName::new(v),
        }).collect()))
    }
}
```

This means `agents.toml` keeps the familiar `rename = { "coder" = "cool-coder" }` syntax while the Rust code works with typed `RenameRule` values.

## How Existing Types Change

### `config/mod.rs`

```rust
// BEFORE
pub struct EffectiveConfig {
    pub sources: IndexMap<String, EffectiveSource>,
    pub settings: Settings,
}

pub struct EffectiveSource {
    pub name: String,
    pub spec: SourceSpec,
    pub is_overridden: bool,
    pub original_git: Option<GitSpec>,
}

pub enum SourceEntry {
    Git {
        url: String,
        version: Option<String>,
        agents: Option<Vec<String>>,
        skills: Option<Vec<String>>,
        exclude: Option<Vec<String>>,
        rename: Option<IndexMap<String, String>>,
    },
    Path { /* same pattern */ },
}

// AFTER
pub struct EffectiveConfig {
    pub sources: IndexMap<SourceName, EffectiveSource>,
    pub settings: Settings,
}

pub struct EffectiveSource {
    pub name: SourceName,
    pub id: SourceId,               // NEW: canonical identity for dedup
    pub spec: SourceSpec,
    pub is_overridden: bool,
    pub original_git: Option<GitSpec>,
}

pub enum SourceEntry {
    Git {
        url: SourceUrl,             // was String
        version: Option<String>,    // stays String — version constraint is its own type in resolve/
        agents: Option<Vec<ItemName>>,   // was Vec<String>
        skills: Option<Vec<ItemName>>,   // was Vec<String>
        exclude: Option<Vec<ItemName>>,  // was Vec<String>
        rename: Option<RenameMap>,       // was IndexMap<String, String>
    },
    Path {
        path: PathBuf,              // stays PathBuf
        agents: Option<Vec<ItemName>>,
        skills: Option<Vec<ItemName>>,
        exclude: Option<Vec<ItemName>>,
        rename: Option<RenameMap>,
    },
}
```

**Note**: `SourceSpec` (the enum distinguishing Git vs Path at the spec level) should carry `SourceUrl` for Git and `PathBuf` for Path, matching the pattern.

### `lock/mod.rs`

```rust
// BEFORE
pub struct LockFile {
    pub version: u32,
    pub sources: IndexMap<String, LockedSource>,
    pub items: IndexMap<ItemId, LockedItem>,
}

pub struct LockedSource {
    pub url: Option<String>,
    pub path: Option<String>,
    pub version: Option<String>,
    pub commit: Option<String>,
    pub tree_hash: Option<String>,
}

pub struct LockedItem {
    pub source: String,
    pub kind: ItemKind,
    pub version: Option<String>,
    pub source_checksum: String,
    pub installed_checksum: String,
    pub dest_path: String,
}

pub struct ItemId {
    pub kind: ItemKind,
    pub name: String,
}

// AFTER
pub struct LockFile {
    pub version: u32,
    pub sources: IndexMap<SourceName, LockedSource>,
    pub items: IndexMap<ItemId, LockedItem>,
}

pub struct LockedSource {
    pub url: Option<SourceUrl>,         // was Option<String>
    pub path: Option<PathBuf>,          // was Option<String> — should be PathBuf
    pub version: Option<String>,        // stays — resolved semver string
    pub commit: Option<CommitHash>,     // was Option<String>
    pub tree_hash: Option<ContentHash>, // was Option<String>
}

pub struct LockedItem {
    pub source: SourceName,             // was String
    pub kind: ItemKind,
    pub version: Option<String>,
    pub source_checksum: ContentHash,   // was String
    pub installed_checksum: ContentHash, // was String
    pub dest_path: DestPath,            // was String
}

pub struct ItemId {
    pub kind: ItemKind,
    pub name: ItemName,                 // was String
}
```

### `resolve/mod.rs`

```rust
// BEFORE
pub struct ResolvedGraph {
    pub nodes: IndexMap<String, ResolvedNode>,
    pub order: Vec<String>,
}

pub struct ResolvedNode {
    pub source_name: String,
    pub resolved_ref: ResolvedRef,
    pub manifest: Option<Manifest>,
    pub deps: Vec<String>,
}

pub struct ResolvedRef {
    pub source_name: String,
    pub version: Option<semver::Version>,
    pub commit: Option<String>,
    pub tree_path: PathBuf,
}

// AFTER
pub struct ResolvedGraph {
    pub nodes: IndexMap<SourceName, ResolvedNode>,   // keyed by SourceName
    pub order: Vec<SourceName>,
    pub id_index: HashMap<SourceId, SourceName>,     // NEW: SourceId→SourceName for dedup
}

pub struct ResolvedNode {
    pub source_name: SourceName,
    pub source_id: SourceId,                         // NEW: canonical identity
    pub resolved_ref: ResolvedRef,
    pub manifest: Option<Manifest>,
    pub deps: Vec<SourceName>,
}

pub struct ResolvedRef {
    pub source_name: SourceName,
    pub version: Option<semver::Version>,
    pub commit: Option<CommitHash>,                  // was Option<String>
    pub tree_path: PathBuf,
}
```

The `id_index` on `ResolvedGraph` enables the deduplication check: before inserting a new node, look up its `SourceId` in `id_index`. If found, the source is already in the graph under a different name — error with a clear message:

```
error: source "my-base" (github.com/haowjy/meridian-base) and source
"meridian-base" (github.com/haowjy/meridian-base) resolve to the same
package. Remove one or rename it.
```

### `sync/target.rs`

```rust
// BEFORE
pub struct TargetState {
    pub items: IndexMap<String, TargetItem>,  // keyed by dest_path string
}

pub struct TargetItem {
    pub id: ItemId,
    pub source_name: String,
    pub source_url: Option<String>,
    pub source_path: PathBuf,
    pub dest_path: PathBuf,
    pub source_hash: String,
}

// AFTER
pub struct TargetState {
    pub items: IndexMap<DestPath, TargetItem>,  // keyed by DestPath
}

pub struct TargetItem {
    pub id: ItemId,                             // ItemId.name is now ItemName
    pub source_name: SourceName,                // was String
    pub source_id: SourceId,                    // NEW: for collision auto-rename extraction
    pub source_path: PathBuf,
    pub dest_path: DestPath,                    // was PathBuf
    pub source_hash: ContentHash,               // was String
}
```

### `manifest/mod.rs`

```rust
// BEFORE
pub struct DepSpec {
    pub url: String,
    pub version: String,
    pub items: Option<Vec<String>>,
}

// AFTER
pub struct DepSpec {
    pub url: SourceUrl,                 // was String
    pub version: String,                // stays — constraint string
    pub items: Option<Vec<ItemName>>,   // was Vec<String>
}
```

## Source Spec Parser

### Module: `src/source/parse.rs`

The parser converts CLI input strings (what the user types after `mars add`) into structured `ParsedSourceSpec` values. It replaces the monolithic `parse_source_specifier` in `cli/add.rs`.

### The Parse Pipeline

```
user input string
       │
       ▼
  ┌─────────┐    InputFormat enum
  │ classify │──────────────────┐
  └─────────┘                   │
       │                        ▼
       │               ┌──────────────┐    (url_part, Option<version_part>)
       │               │ split_version │
       │               └──────────────┘
       │                        │
       │                        ▼
       │               ┌─────────────┐    SourceUrl (canonical)
       │               │ normalize   │
       │               └─────────────┘
       │                        │
       │                        ▼
       │               ┌──────────────┐    SourceName (derived)
       │               │ derive_name  │
       │               └──────────────┘
       │                        │
       ▼                        ▼
  ParsedSourceSpec { format, url, version, name }
```

Each step is a pure function with a typed input and output. The pipeline short-circuits on errors with context about which step failed and what the input looked like.

### Type Definitions

```rust
// src/source/parse.rs

use crate::types::{SourceName, SourceUrl};

/// The result of parsing a CLI source specifier.
#[derive(Debug, Clone)]
pub struct ParsedSourceSpec {
    /// What kind of source this is
    pub format: SourceFormat,
    /// The raw input (preserved for error messages)
    pub raw: String,
    /// Canonical URL (None for local paths)
    pub url: Option<SourceUrl>,
    /// Local path (None for git sources)
    pub path: Option<PathBuf>,
    /// Version constraint extracted from input (e.g., "v1.0", ">=2.0")
    pub version: Option<String>,
    /// Derived display name for use as the agents.toml key
    pub name: SourceName,
}

/// Classification of the input format.
/// Determined BEFORE any '@' splitting — this is the key fix for SSH URLs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SourceFormat {
    /// Starts with `.`, `..`, `/`, or `~` — local filesystem path
    LocalPath,
    /// Matches `owner/repo` (exactly one `/`, no dots before it)
    GitHubShorthand,
    /// Starts with `https://` or `http://`
    HttpsUrl,
    /// Starts with `git@` or matches `user@host:path` pattern
    SshUrl,
    /// Contains dots and slashes but no protocol — e.g., `github.com/owner/repo`
    BareDomain,
}

/// Errors during source spec parsing, with context for user-facing messages.
#[derive(Debug, thiserror::Error)]
pub enum ParseError {
    #[error("cannot determine source type for {input:?} — expected a path, URL, or owner/repo shorthand")]
    UnrecognizedFormat { input: String },

    #[error("SSH URL {input:?} is missing the colon-separated path (expected git@host:owner/repo)")]
    MalformedSshUrl { input: String },

    #[error("cannot derive a name from {input:?} — use `mars add {input} --name <name>`")]
    CannotDeriveName { input: String },

    #[error("URL {input:?} has no path component")]
    EmptyUrlPath { input: String },
}
```

### Step 1: Classify Input Format

Classification uses prefix/pattern matching — no splitting, no mutation. The order of checks matters: SSH must be detected before bare domain, because `git@github.com:org/repo` contains dots and slashes.

```rust
/// Classify the input string into a source format.
/// No mutation — pure pattern matching on the input.
pub fn classify(input: &str) -> SourceFormat {
    // Local paths: start with path indicators
    if input.starts_with('.')
        || input.starts_with('/')
        || input.starts_with('~')
    {
        return SourceFormat::LocalPath;
    }

    // HTTPS/HTTP URLs: explicit protocol
    if input.starts_with("https://") || input.starts_with("http://") {
        return SourceFormat::HttpsUrl;
    }

    // SSH URLs: git@host:path or user@host:path
    // Key insight: SSH URLs have @ BEFORE : with no // after the host.
    // We check for the user@host:path pattern.
    if let Some(at_pos) = input.find('@') {
        // Check if there's a colon after the @ (SSH pattern)
        if let Some(colon_pos) = input[at_pos..].find(':') {
            let colon_abs = at_pos + colon_pos;
            // Verify it's not a port number (colon followed by digits then /)
            let after_colon = &input[colon_abs + 1..];
            if !after_colon.starts_with("//") && !after_colon.chars().next().map_or(true, |c| c.is_ascii_digit()) {
                return SourceFormat::SshUrl;
            }
        }
    }

    // GitHub shorthand: owner/repo (exactly one slash, no dots before slash)
    // Must come after SSH check to avoid matching git@github.com:owner/repo
    let slash_count = input.chars().filter(|&c| c == '/').count();
    if slash_count == 1 && !input.contains('.') && !input.contains(':') {
        // Strip potential @version suffix for the check
        let base = input.split('@').next().unwrap_or(input);
        let slash_count = base.chars().filter(|&c| c == '/').count();
        if slash_count == 1 {
            return SourceFormat::GitHubShorthand;
        }
    }

    // Bare domain: contains dots and slashes (github.com/owner/repo)
    if input.contains('.') && input.contains('/') {
        return SourceFormat::BareDomain;
    }

    // Could be a registry short name (future) or unrecognized
    // For now, treat single-word inputs as potential shorthand
    SourceFormat::GitHubShorthand // fallback — will fail in normalize if invalid
}
```

### Step 2: Split Version (Format-Aware)

The version suffix `@version` is extracted AFTER classification. For SSH URLs, we know the first `@` is part of the URL itself — version, if present, is the LAST `@` after the colon-separated path.

```rust
/// Split the input into (url_part, optional_version_part).
/// Format-aware: SSH URLs don't split on the user@host '@'.
pub fn split_version(input: &str, format: SourceFormat) -> (&str, Option<&str>) {
    match format {
        SourceFormat::LocalPath => {
            // Local paths never have version suffixes
            (input, None)
        }

        SourceFormat::SshUrl => {
            // SSH: git@github.com:org/repo.git@v1.0
            // The version '@' is the LAST '@' — but only if it comes
            // after the colon-separated path begins.
            let colon_pos = input.find(':').unwrap_or(input.len());
            let path_part = &input[colon_pos..];
            if let Some(at_pos) = path_part.rfind('@') {
                let abs_pos = colon_pos + at_pos;
                (&input[..abs_pos], Some(&input[abs_pos + 1..]))
            } else {
                (input, None)
            }
        }

        SourceFormat::HttpsUrl | SourceFormat::BareDomain | SourceFormat::GitHubShorthand => {
            // Standard: split on last '@'
            if let Some(at_pos) = input.rfind('@') {
                (&input[..at_pos], Some(&input[at_pos + 1..]))
            } else {
                (input, None)
            }
        }
    }
}
```

### Step 3: Normalize URL

Converts the url_part to a canonical `SourceUrl`. All git URLs normalize to the bare-domain form `host/owner/repo` — no protocol prefix, no `.git` suffix.

```rust
/// Normalize a URL to canonical form.
/// Returns SourceUrl for git sources, PathBuf for local paths.
pub fn normalize(url_part: &str, format: SourceFormat) -> Result<NormalizedSource, ParseError> {
    match format {
        SourceFormat::LocalPath => {
            Ok(NormalizedSource::Path(PathBuf::from(url_part)))
        }

        SourceFormat::GitHubShorthand => {
            // "owner/repo" → "github.com/owner/repo"
            Ok(NormalizedSource::Git(SourceUrl::new(
                format!("github.com/{url_part}")
            )))
        }

        SourceFormat::HttpsUrl => {
            // "https://github.com/owner/repo.git" → "github.com/owner/repo"
            let stripped = url_part
                .strip_prefix("https://")
                .or_else(|| url_part.strip_prefix("http://"))
                .unwrap_or(url_part);
            let stripped = stripped.strip_suffix(".git").unwrap_or(stripped);
            let stripped = stripped.trim_end_matches('/');
            if stripped.is_empty() {
                return Err(ParseError::EmptyUrlPath { input: url_part.to_owned() });
            }
            Ok(NormalizedSource::Git(SourceUrl::new(stripped)))
        }

        SourceFormat::SshUrl => {
            // "git@github.com:owner/repo.git" → "github.com/owner/repo"
            let at_pos = url_part.find('@')
                .ok_or_else(|| ParseError::MalformedSshUrl { input: url_part.to_owned() })?;
            let after_at = &url_part[at_pos + 1..];
            let colon_pos = after_at.find(':')
                .ok_or_else(|| ParseError::MalformedSshUrl { input: url_part.to_owned() })?;
            let host = &after_at[..colon_pos];
            let path = after_at[colon_pos + 1..].strip_suffix(".git").unwrap_or(&after_at[colon_pos + 1..]);
            let path = path.trim_end_matches('/');
            Ok(NormalizedSource::Git(SourceUrl::new(format!("{host}/{path}"))))
        }

        SourceFormat::BareDomain => {
            // "github.com/owner/repo.git" → "github.com/owner/repo"
            let stripped = url_part.strip_suffix(".git").unwrap_or(url_part);
            let stripped = stripped.trim_end_matches('/');
            Ok(NormalizedSource::Git(SourceUrl::new(stripped)))
        }
    }
}

/// Intermediate result from normalize — either a git URL or a local path.
#[derive(Debug, Clone)]
pub enum NormalizedSource {
    Git(SourceUrl),
    Path(PathBuf),
}
```

### Step 4: Derive Name

Extracts a human-readable name from the URL or path for use as the `agents.toml` section key.

```rust
/// Derive a source name from a normalized URL or path.
///
/// Examples:
///   "github.com/haowjy/meridian-base" → "meridian-base"
///   "github.com/someone/cool-agents"   → "cool-agents"
///   "./my-agents"                       → "my-agents"
///   "../path/to/agents"                 → "agents"
pub fn derive_name(source: &NormalizedSource) -> Result<SourceName, ParseError> {
    let name = match source {
        NormalizedSource::Git(url) => {
            // Last path segment of the URL
            url.as_str()
                .rsplit('/')
                .next()
                .filter(|s| !s.is_empty())
                .ok_or_else(|| ParseError::CannotDeriveName {
                    input: url.to_string(),
                })?
                .to_owned()
        }
        NormalizedSource::Path(path) => {
            // Last component of the path
            path.file_name()
                .and_then(|n| n.to_str())
                .filter(|s| !s.is_empty())
                .ok_or_else(|| ParseError::CannotDeriveName {
                    input: path.display().to_string(),
                })?
                .to_owned()
        }
    };
    Ok(SourceName::new(name))
}
```

### Top-Level Parse Function

```rust
/// Parse a CLI source specifier into a structured spec.
///
/// This is the only public entry point. CLI commands call this,
/// never the individual pipeline steps.
pub fn parse(input: &str) -> Result<ParsedSourceSpec, ParseError> {
    let format = classify(input);
    let (url_part, version) = split_version(input, format);
    let normalized = normalize(url_part, format)?;
    let name = derive_name(&normalized)?;

    let (url, path) = match normalized {
        NormalizedSource::Git(u) => (Some(u), None),
        NormalizedSource::Path(p) => (None, Some(p)),
    };

    Ok(ParsedSourceSpec {
        format,
        raw: input.to_owned(),
        url,
        path,
        version: version.map(str::to_owned),
        name,
    })
}
```

### Parse Examples

| Input | Format | URL Part | Version | Canonical URL | Name |
|-------|--------|----------|---------|---------------|------|
| `./my-agents` | LocalPath | `./my-agents` | None | — | `my-agents` |
| `haowjy/meridian-base` | GitHubShorthand | `haowjy/meridian-base` | None | `github.com/haowjy/meridian-base` | `meridian-base` |
| `haowjy/meridian-base@v1.0` | GitHubShorthand | `haowjy/meridian-base` | `v1.0` | `github.com/haowjy/meridian-base` | `meridian-base` |
| `https://github.com/org/repo.git` | HttpsUrl | (full URL) | None | `github.com/org/repo` | `repo` |
| `https://github.com/org/repo@v2` | HttpsUrl | (URL without @v2) | `v2` | `github.com/org/repo` | `repo` |
| `git@github.com:org/repo.git` | SshUrl | (full URL) | None | `github.com/org/repo` | `repo` |
| `git@github.com:org/repo.git@v1.0` | SshUrl | (URL without @v1.0) | `v1.0` | `github.com/org/repo` | `repo` |
| `github.com/haowjy/meridian-base` | BareDomain | (full string) | None | `github.com/haowjy/meridian-base` | `meridian-base` |
| `github.com/haowjy/meridian-base@latest` | BareDomain | (without @latest) | `latest` | `github.com/haowjy/meridian-base` | `meridian-base` |

The SSH URL row is the critical fix — `git@github.com:org/repo.git` correctly classifies as SSH, the `@` in `git@` is never treated as a version separator, and the colon-path syntax normalizes to `github.com/org/repo`.

## SourceId: Fixing Dependency Identity

### The Bug

Current resolver keys the graph by `SourceName` (the user's TOML key). If two sources point to the same git repo under different names:

```toml
[sources.base]
url = "github.com/haowjy/meridian-base"

[sources.meridian-base]
url = "github.com/haowjy/meridian-base"
```

The resolver creates two nodes, fetches the repo twice, and installs duplicate items. Worse, if a transitive dependency resolves to a URL that a direct dependency already provides under a different name, they're treated as unrelated.

### The Fix

Every `EffectiveSource` carries a `SourceId`. The resolver maintains an `id_index: HashMap<SourceId, SourceName>` on the graph. Before inserting a new node:

```rust
// In resolve/mod.rs, when adding a node:
if let Some(existing_name) = graph.id_index.get(&source.id) {
    return Err(ResolutionError::DuplicateSource {
        name_a: existing_name.clone(),
        name_b: source.name.clone(),
        id: source.id.clone(),
    });
}
graph.id_index.insert(source.id.clone(), source.name.clone());
```

For transitive dependencies discovered from manifests, the resolver constructs a `SourceId` from the manifest's URL and checks against the index before adding the transitive source to the graph.

### SourceUrl Canonicalization

`SourceId::Git` comparison depends on `SourceUrl` being canonical. Two URLs that point to the same repo must produce the same `SourceUrl`:

```
https://github.com/haowjy/meridian-base.git  →  github.com/haowjy/meridian-base
git@github.com:haowjy/meridian-base.git      →  github.com/haowjy/meridian-base
github.com/haowjy/meridian-base              →  github.com/haowjy/meridian-base
```

This canonicalization happens in `normalize()` (Step 3 of the parser). The `SourceUrl` newtype is only constructable through the parser, enforcing that all URLs are canonical.

**Important**: `SourceUrl::new()` is `pub` for test construction convenience, but production code should only create `SourceUrl` values through `parse()`. Consider making `new()` `pub(crate)` and providing a `#[cfg(test)] pub fn test_url(s: &str) -> SourceUrl` constructor.

## Migration Strategy

### Phase 7: Foundation Newtypes

Introduce `SourceName` and `ItemName` first — they touch the most call sites but have the simplest migration path because they're thin wrappers.

**Step 7a: Define types.rs module**
- Add `src/types.rs` with the `string_newtype!` macro and all newtype definitions
- Re-export from `lib.rs`
- Zero behavior change — just new types available

**Step 7b: ItemName into ItemId**
- Change `ItemId.name: String` → `ItemId.name: ItemName`
- Update `ItemId::new()`, `Display`, `Hash`, `Eq` impls
- Touch count: ItemId is constructed in ~8 places (discover, target, lock, validate)
- All tests that construct `ItemId` update to `ItemName::new("coder")`

**Step 7c: SourceName into config types**
- Change `EffectiveConfig.sources` key and `EffectiveSource.name`
- Change `SourceEntry` rename field to `RenameMap`
- Touch count: config is loaded in ~3 places, source names are read in ~15 places
- RenameMap custom serde preserves TOML format — no config file changes needed

**Step 7d: SourceName into resolve/lock/target**
- Change `ResolvedGraph.nodes` keys, `ResolvedNode.source_name/deps`, `ResolvedRef.source_name`
- Change `LockedSource` keys, `LockedItem.source`
- Change `TargetItem.source_name`
- Touch count: ~25 call sites across resolve, lock, target, sync, CLI

**Step 7e: CommitHash and ContentHash**
- Change `ResolvedRef.commit`, `LockedSource.commit` → `CommitHash`
- Change `LockedSource.tree_hash`, `LockedItem.source_checksum/installed_checksum`, `TargetItem.source_hash` → `ContentHash`
- Touch count: ~12 call sites (hash computation, lock read/write, diff comparison)

Each sub-step compiles and passes tests before proceeding.

### Phase 8: Path Newtypes, SourceId, RenameRule

**Step 8a: DestPath**
- Change `TargetState.items` key and `TargetItem.dest_path` → `DestPath`
- Change `LockedItem.dest_path` → `DestPath`
- Touch count: ~10 call sites (target build, diff, apply, prune)

**Step 8b: SourceUrl**
- Change `SourceEntry::Git.url`, `LockedSource.url`, `DepSpec.url` → `SourceUrl`
- Touch count: ~8 call sites

**Step 8c: SourceId**
- Add `SourceId` enum, `EffectiveSource.id` field
- Add `ResolvedGraph.id_index`, `ResolvedNode.source_id`
- Add `TargetItem.source_id`
- Wire dedup check into resolver
- Touch count: ~6 call sites (config load, resolve, target build)

**Step 8d: RenameMap in collision handling**
- Replace auto-rename `Vec<RenameAction>` internals with `RenameRule` values
- Update collision detection to use `SourceId` for `{owner}_{repo}` extraction from canonical URLs
- Touch count: ~4 call sites (collision detection, frontmatter rewrite)

### Phase 2: Source Spec Parser (independent of newtypes)

The parser can ship early because it's a new module — no existing code needs to change until `cli/add.rs` is updated to call it.

**Step 2a: Add `src/source/parse.rs`**
- Implement `classify`, `split_version`, `normalize`, `derive_name`, `parse`
- Comprehensive tests for every format × version combination, especially SSH URLs

**Step 2b: Wire into cli/add.rs**
- Replace `parse_source_specifier` body with a call to `source::parse::parse()`
- Map `ParsedSourceSpec` to the existing `SourceEntry` construction
- Delete old parsing code

**Step 2c: Wire into cli/init.rs or other entry points**
- Any other CLI command that parses source specifiers should route through the parser

## Test Strategy

### Parser Tests

Every row in the parse examples table becomes a test. Additionally:

```rust
#[test]
fn ssh_url_not_split_on_user_at() {
    let spec = parse("git@github.com:org/repo.git").unwrap();
    assert_eq!(spec.format, SourceFormat::SshUrl);
    assert_eq!(spec.url.unwrap().as_str(), "github.com/org/repo");
    assert!(spec.version.is_none());
}

#[test]
fn ssh_url_with_version() {
    let spec = parse("git@github.com:org/repo.git@v1.0").unwrap();
    assert_eq!(spec.format, SourceFormat::SshUrl);
    assert_eq!(spec.url.unwrap().as_str(), "github.com/org/repo");
    assert_eq!(spec.version.as_deref(), Some("v1.0"));
}

#[test]
fn https_and_ssh_canonicalize_to_same_url() {
    let https = parse("https://github.com/org/repo.git").unwrap();
    let ssh = parse("git@github.com:org/repo.git").unwrap();
    assert_eq!(https.url, ssh.url); // Both → github.com/org/repo
}

#[test]
fn local_path_never_has_version() {
    let spec = parse("./my-agents@v1.0").unwrap();
    assert_eq!(spec.format, SourceFormat::LocalPath);
    assert!(spec.version.is_none()); // "@v1.0" is part of the path
}
```

### Newtype Tests

Newtypes are thin — the main value is compile-time checking, not runtime behavior. Tests focus on:

1. **Serde roundtrip**: `SourceName` serializes to/from TOML as a bare string
2. **RenameMap TOML format**: `{ "coder" = "cool-coder" }` survives serialize → deserialize
3. **SourceId equality**: HTTPS and SSH URLs to the same repo produce equal `SourceId`
4. **DestPath resolve**: `DestPath("agents/coder.md").resolve(root)` produces the correct absolute path
5. **CommitHash display**: 40-char hex string round-trips correctly

### Integration Tests

The existing 281 tests should continue passing after each migration step. The newtype changes are transparent to TOML serialization (serde impls preserve the wire format), so existing test fixtures don't need updating.

## Decisions

### Why a macro for string newtypes instead of a trait?

Traits can't add `Serialize`/`Deserialize` impls for foreign types, and a blanket impl for a `NewtypeString` trait would conflict with orphan rules. The macro generates the full impl block per type, which is more code but zero runtime cost and maximum flexibility (each type can diverge later if needed, e.g., adding validation to `CommitHash::new()`).

### Why SourceId is an enum, not a struct with Option fields?

A git source and a path source have fundamentally different identity semantics — a git source is identified by URL, a path source by canonical filesystem location. Putting both in one struct with `Option<SourceUrl>` + `Option<PathBuf>` creates the possibility of both-Some or both-None, which is nonsensical. The enum makes invalid states unrepresentable.

### Why DestPath wraps PathBuf instead of String?

Destination paths are real filesystem paths that get joined with roots, compared for existence, and passed to `std::fs` functions. Wrapping `String` would require conversion at every fs call site. Wrapping `PathBuf` means `Deref<Target=Path>` provides all the path methods for free.

### Why not validate SourceUrl contents in the constructor?

Validation belongs in the parser, not the constructor. The constructor is `pub(crate)` — only the parser and serde deserialization create `SourceUrl` values. The parser validates format during construction. Serde deserialization trusts the lock/config file (if the file is corrupted, validation at load time catches it). Adding URL validation to the constructor would make lock file loading fail on slightly non-canonical URLs that were written by an older version — bad for forwards compatibility.

### Why RenameMap instead of IndexMap<ItemName, ItemName>?

`IndexMap<ItemName, ItemName>` works for the common case but doesn't express that order matters or that we might want per-rule metadata later (e.g., `explicit: bool` to distinguish user renames from auto-renames). The wrapper type costs nothing now and provides an extension point.
