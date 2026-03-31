# Phase 2b: Source Fetching (Git + Path Adapters)

## Scope

Implement the `source/` module: the `SourceFetcher` trait and its two implementations — `GitFetcher` (using `git2` for clone/fetch/tag operations) and `PathFetcher` (resolving local paths). This is the I/O boundary where external content enters the pipeline.

## Why This Order

The resolver (Phase 3) needs to fetch sources to read their `mars.toml` manifests and discover available versions. The sync pipeline (Phase 4) needs fetched source trees to discover items. Source fetching is the most I/O-heavy module and the most likely to surface dependency issues (`git2` build, libgit2 behavior). Building it alongside the pure-logic modules (Phase 2a, Phase 3) reduces risk.

## Files to Modify

### `src/source/mod.rs` — Trait + Types

```rust
pub mod git;
pub mod path;

/// A resolved source reference — pinned to a specific version/commit
#[derive(Debug, Clone)]
pub struct ResolvedRef {
    pub source_name: String,
    pub version: Option<semver::Version>,
    pub version_tag: Option<String>,      // original tag name (e.g., "v0.5.2")
    pub commit: Option<String>,           // git commit SHA
    pub tree_path: PathBuf,               // where the fetched content lives on disk
}

/// Source specification (what to fetch)
pub enum SourceSpec {
    Git(GitSpec),
    Path(PathBuf),
}

pub struct GitSpec {
    pub url: String,
    pub version_constraint: Option<String>,
}

/// Available version from a git remote
#[derive(Debug, Clone)]
pub struct AvailableVersion {
    pub tag: String,
    pub version: semver::Version,
    pub commit_id: git2::Oid,
}

/// Dispatch to the right fetcher based on source spec
pub fn fetch_source(
    spec: &SourceSpec,
    source_name: &str,
    cache_dir: &Path,
) -> Result<ResolvedRef>;

/// List available versions from a git remote (for resolution)
pub fn list_versions(url: &str, cache_dir: &Path) -> Result<Vec<AvailableVersion>>;
```

### `src/source/git.rs` — Git Adapter

Uses `git2` exclusively. No subprocess spawning.

**Core operations**:

1. **`list_versions(url)`**: Use `git2::Remote::create_detached(url)` then `remote.list()` (equivalent to `git ls-remote --tags`). Parse tag names into semver versions. Return sorted `Vec<AvailableVersion>`.

2. **`fetch(url, ref, cache_dir)`**:
   - Cache directory: `{cache_dir}/{url_to_dirname}/` where `url_to_dirname` replaces `/` with `_` and strips protocol.
   - If cache dir exists: `git2::Repository::open()` then `remote.fetch()` to update.
   - If cache dir doesn't exist: `git2::Repository::clone()` into cache dir.
   - Checkout the target ref (tag, branch, or commit SHA).
   - Return `ResolvedRef` with the path to the checked-out tree.

3. **`url_to_dirname(url)`**: Normalize URL to filesystem-safe directory name. Strip `https://`, replace `/` with `_`. Example: `github.com/haowjy/meridian-base` → `github.com_haowjy_meridian-base`.

**Version tag parsing**:
- Tags matching `v{semver}` (e.g., `v0.5.2`, `v2.0.0`) are parsed as semver versions.
- Tags not matching semver pattern are available for `@branch` or `@commit` pinning but not for semver constraint resolution.
- Strip the `v` prefix before parsing with `semver::Version::parse()`.

**Force-push detection** (from review synthesis):
- When a locked commit exists for a tag, verify the tag still points to the same commit after fetch.
- If mismatch: return a warning (not error) with the old and new commits.
- Store both `version_tag` and `commit` in `ResolvedRef` for the lock to record.

**Error handling**:
- Network errors: wrap `git2::Error` with source name context.
- Auth errors: clear message suggesting SSH key or token configuration.
- Invalid URL: structured error before attempting any network operation.

### `src/source/path.rs` — Path Adapter

Simple: resolve relative path against the project root, verify the directory exists, return it directly.

```rust
pub fn fetch_path(
    path: &Path,
    project_root: &Path,
    source_name: &str,
) -> Result<ResolvedRef>;
```

- Resolve relative paths against `project_root` (parent of `.agents/`).
- Verify the path exists and is a directory.
- Return `ResolvedRef` with `tree_path = resolved_path`, no version/commit.
- No caching, no copying — path sources are always "live."

## Dependencies

- Requires: Phase 0 (module stubs), Phase 1a (`MarsError`, `fs/` primitives), Phase 1b (`SourceSpec`, `GitSpec` from config)
- Produces: `fetch_source()`, `list_versions()`, `ResolvedRef` — consumed by `resolve/` (Phase 3) and `sync/` (Phase 4)
- Independent of: Phase 2a (discover), Phase 3 (resolve — though resolve calls this, it can be tested with mocked fetchers)

## Interface Contract

Consumers:
- `resolve/` calls `list_versions(url)` to discover available versions for constraint matching
- `resolve/` calls `fetch_source()` on each resolved source to get the tree for manifest reading
- `sync/` pipeline uses `ResolvedRef.tree_path` to discover items in each source

## Patterns to Follow

- All git operations via `git2`. No `std::process::Command("git", ...)`.
- Cache layout: `{cache_dir}/{url_to_dirname}/`. One directory per git URL.
- Path sources return the original path — no copies.
- Structured errors with source name context on every failure path.

## Verification Criteria

- [ ] `cargo build` succeeds (critical: verify `git2` builds on the CI target)
- [ ] Git adapter tests (require creating real git repos with `git2`):
  - Create a temp repo with tagged commits → `list_versions()` returns correct versions
  - `fetch()` clones the repo to cache → tree_path points to valid checkout
  - Second `fetch()` reuses cache (updates, doesn't re-clone)
  - Tag with `v` prefix parsed correctly as semver
  - Non-semver tags present but not included in version list
  - Invalid URL → clear error message
- [ ] Path adapter tests:
  - Relative path resolved against project root
  - Absolute path used as-is
  - Non-existent path → clear error with path in message
  - Returns ResolvedRef with no version/commit
- [ ] URL normalization tests:
  - `github.com/haowjy/meridian-base` → `github.com_haowjy_meridian-base`
  - `https://github.com/foo/bar` → `github.com_foo_bar`
  - `git@github.com:foo/bar.git` → `github.com_foo_bar`
- [ ] `cargo clippy -- -D warnings` passes

## Constraints

- Do NOT shell out to `git`. Use `git2` exclusively.
- Cache management is basic for v1 — no content-addressed cache, no pruning. Just one cloned repo per URL.
- Path fetcher does NOT copy files. It returns the original path.
- All git network operations must have timeout handling (or at least document the limitation).
- `url_to_dirname` must handle: `github.com/`, `https://github.com/`, `git@github.com:` URL formats.

## Risk: `git2` Build Complexity

`git2` depends on `libgit2` (C library). Build may need `cmake`, `pkg-config`, or vendored `libgit2-sys`. The `git2` crate has a `vendored` feature that bundles libgit2 — consider enabling it for simpler builds:

```toml
git2 = { version = "0.19", features = ["vendored"] }
```

Test the build on a clean environment. If vendored builds are too slow or have issues, document the system dependency requirements.
