# Phase 3: Implement Source Fetching — Archive + System Git

**Risk:** High — core functionality rewrite  
**Design doc:** [overview.md](../design/overview.md) §Archive Download Flow, §System Git Flow

## Scope

Implement the actual fetch logic in `source/git.rs`: archive downloads for GitHub, system `git` for SSH and non-GitHub HTTPS. This is the main phase.

## Steps

### 3a: Version listing via `git ls-remote`

```rust
/// Run `git ls-remote --tags <url>` and parse semver tags.
pub fn ls_remote_tags(url: &str) -> Result<Vec<AvailableVersion>, MarsError>

/// Run `git ls-remote <url> HEAD` to get default branch SHA.
pub fn ls_remote_head(url: &str) -> Result<String, MarsError>
```

- Parse `git ls-remote` output: `{sha}\trefs/tags/{tag}` lines
- Filter: skip `^{}` (peeled tags), only keep semver-parseable tags
- Return sorted by semver ascending
- Error handling: git not installed → clear error message

### 3b: Archive download (GitHub)

```rust
fn fetch_archive(
    url: &str,
    sha: &str, 
    cache: &GlobalCache,
) -> Result<PathBuf, MarsError>
```

- Construct archive URL: `https://github.com/{owner}/{repo}/archive/{sha}.tar.gz`
  - Extract owner/repo from the stored URL
- Check cache: `cache.archives_dir().join("{url_dirname}_{sha}")` — if exists, return early
- Download via `ureq::get(archive_url).call()`
- Extract to temp dir (`{cache_path}.tmp.{pid}`)
- Strip first path component during extraction (`{repo}-{sha}/` prefix)
- Security: reject symlinks, `..`, absolute paths
- Atomic rename to final cache path
- Return path to extracted source tree

### 3c: System git clone (SSH + non-GitHub HTTPS)

```rust
fn fetch_git_clone(
    url: &str,
    tag: Option<&str>,
    cache: &GlobalCache,
) -> Result<PathBuf, MarsError>
```

- Cache path: `cache.git_dir().join(url_to_dirname(url))`
- If cached: `git fetch --depth 1 origin tag {tag}` + `git checkout {tag}`
- If not cached: `git clone --depth 1 --branch {tag} {url} {cache_path}`
- If no tag: `git clone --depth 1 {url} {cache_path}` (default branch)
- Return path to cloned repo

### 3d: Version resolution — default to latest release

```rust
fn resolve_version(
    url: &str,
    version_req: Option<&str>,
) -> Result<(Option<String>, String), MarsError>  // (tag, sha)
```

- If `version_req` is Some: find matching tag via `ls_remote_tags`
- If None: pick highest semver tag from `ls_remote_tags`
- If no semver tags: fall back to `ls_remote_head` (default branch)
- Return (tag_name, commit_sha)

### 3e: Top-level dispatch

```rust
pub fn fetch(
    url: &str,
    version_req: Option<&str>,
    source_name: &str,
    cache: &GlobalCache,
    options: &FetchOptions,
) -> Result<ResolvedRef, MarsError>
```

- If `options.preferred_commit` is set (lock replay): use that SHA directly
- Determine fetch strategy: `is_github_host(url)` → archive, else → git clone
- Call `resolve_version()` → get tag + SHA
- Call `fetch_archive()` or `fetch_git_clone()` as appropriate
- Return `ResolvedRef { source_name, version, version_tag, commit, tree_path }`

### 3f: Update `list_versions()`

- Replace git2-based implementation with `ls_remote_tags()`
- Same return type but `commit_id` is now `String`

## Verification

- New unit tests: `ls_remote_tags` output parsing (mock git output)
- New unit tests: archive URL construction
- New unit tests: tarball extraction with path sanitization
- `cargo test` — all unit tests pass
- Manual smoke test: `mars add haowjy/meridian-base` → verify files installed
- All 24 integration tests pass (local path sources unaffected)

## Dependencies

Requires Phase 1 (types) and Phase 2 (URL normalization).
