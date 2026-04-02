# Source Fetch Rewrite: Architectural Review

Review of [overview.md](overview.md) against the mars-agents codebase architecture, the [v1 refactor designs](../../mars-agents-v1-refactor/design/overview.md), and the [original architecture spec](../../agent-package-management/design/rust-architecture.md).

## 1. Blast Radius: git2 Removal

### The merge/mod.rs Gap

The design identifies 6 files to modify but **misses `src/merge/mod.rs`**, which uses `git2::merge_file()` for three-way merge with conflict markers. From the [rust-architecture spec](../../agent-package-management/design/rust-architecture.md) (line 537):

> Wraps `git2::merge_file()` — libgit2's built-in three-way merge with conflict markers (`git2` is already a dependency for git operations, no extra crate needed).

This is called from `sync/apply.rs` during the `PlannedAction::Merge` path — when a user has local modifications AND upstream changes, mars does three-way merge using `git2::merge_file(base, local, theirs)` with configurable labels and conflict markers.

**Impact**: If git2 is dropped, three-way merge breaks. This is the sync pipeline's conflict resolution mechanism (step 11 in the pipeline). Without it, any `Conflict` diff entry silently fails.

**Fix**: Add `diffy` (or `similar`) as a dependency for three-way merge. The API replacement:

```rust
// BEFORE (merge/mod.rs)
let result = git2::merge_file(
    &ancestor, &ours, &theirs, Some(&merge_opts)
)?;

// AFTER — pure Rust three-way merge
// Option A: diffy crate (simple, line-level)
// Option B: similar crate (more control, supports word-level)
// Option C: imara-diff (fast, used by gitoxide)
```

**Recommendation**: Add `diffy` or `similar` to the dependency additions alongside `ureq`, `flate2`, `tar`. The merge module is ~50-100 lines and self-contained, so the replacement is isolated. Must be listed in the design's "Files to Modify" and "Dependency Changes" sections.

### Complete git2 Surface Area

Based on the architecture docs and design specs:

| File | git2 Usage | Replacement |
|------|-----------|-------------|
| `src/source/git.rs` | `Repository::clone`, `Remote::list`, `fetch`, `checkout_tree`, `set_head_detached`, `find_commit`, `Oid` | System `git` subprocess + `ureq` archive download |
| `src/merge/mod.rs` | `merge_file()` | **MISSING** — needs `diffy` or `similar` |
| `src/error.rs` | `Git(#[from] git2::Error)` | Replace with `GitCli` + `Http` variants |
| `src/resolve/mod.rs` | `git2::Oid` in test mocks (`Oid::zero()`) | `String` / `CommitHash` newtype |
| `Cargo.toml` | `git2` dependency | Remove |

No other files import git2 directly — the API is properly isolated behind `source/git.rs` and `merge/mod.rs`.

---

## 2. Cache Architecture

### Default Branch: Unstable Cache Keys

The design uses `{url_dirname}_{sha}` as the cache key for archives. This works for tagged versions where the SHA is stable. But for **default branch sources** (no version constraint), the SHA changes on every commit upstream.

**Problem sequence**:
1. User adds `owner/repo` (no version) — resolves to HEAD commit `abc123`
2. Cache: `~/.mars/cache/archives/github.com_owner_repo_abc123/`
3. Next sync — HEAD is now `def456`
4. New cache: `~/.mars/cache/archives/github.com_owner_repo_def456/`
5. Old `abc123` entry is orphaned forever

Over time, each versionless source accumulates dead cache entries. With 5 sources tracking HEAD, 10 syncs each = 50 dead directories.

**Proposed fix**: Add a **garbage collection** mechanism:

```rust
/// Cache entry metadata (written alongside extracted content)
struct CacheEntry {
    url: String,
    sha: String,
    fetched_at: SystemTime,
    last_used: SystemTime,
}

/// GC strategy: remove entries not referenced by any project's lock file
/// AND not accessed within a threshold (e.g., 7 days)
pub fn gc(cache_dir: &Path, max_age: Duration) -> Result<GcReport>;
```

Expose as `mars cache gc` CLI command. Don't auto-gc during sync — that adds latency and complexity to the hot path. A separate command is simpler and predictable.

**Cache size awareness**: Consider `mars cache info` showing total size, entry count, staleness. Users on CI want to know if the cache is growing unbounded.

### System Git Clones: Cache Update Strategy

For SSH sources cached as shallow clones at `~/.mars/cache/git/{url_dirname}/`, the design says:

> On update: `git fetch --depth 1 origin tag {tag}`

But shallow clones with `--depth 1` have a gotcha: fetching a new tag into an existing depth-1 clone doesn't prune the old commit. Over many upgrades, the "shallow" clone grows. Consider:

```bash
# Instead of updating in place:
git fetch --depth 1 origin tag v2.0.0

# Consider: delete and re-clone (cheap for depth-1)
rm -rf <cache_path>
git clone --depth 1 --branch v2.0.0 <url> <cache_path>
```

Re-cloning depth-1 is ~same cost as fetch for small repos (agent packages are small), and guarantees the cache stays minimal.

### Cache Atomicity

The design doesn't mention atomicity of cache writes. If mars is killed mid-extraction:

```
~/.mars/cache/archives/github.com_owner_repo_abc123/
  agents/           # extracted
  skills/           # partially extracted — missing files
```

Next sync sees the directory exists, assumes cached, uses incomplete content.

**Fix**: Extract to a temp directory, then atomic rename:

```rust
fn extract_archive(tarball: &[u8], target: &Path) -> Result<()> {
    let tmp = target.with_extension(".tmp");
    // extract to tmp
    tar::Archive::new(GzDecoder::new(tarball)).unpack(&tmp)?;
    // atomic rename
    std::fs::rename(&tmp, target)?;
    Ok(())
}
```

This follows mars's own crash-only design principle (CLAUDE.md: "Every write is atomic (tmp+rename)").

---

## 3. URL Storage: Breaking Change

### The Conflict

The [v1 refactor newtypes design](../../mars-agents-v1-refactor/design/newtypes-and-parsing.md) defines `SourceUrl` as:

> Canonical URL for a git source, **protocol-stripped** and normalized.
> Example: "github.com/haowjy/meridian-base"

The source fetch rewrite design says:

> Store the **fetch URL** (with scheme) in `agents.toml`

These two designs directly contradict. The v1 refactor strips the scheme for a canonical identity form; the fetch rewrite preserves it for fetch strategy dispatch.

**Resolution**: Both goals are legitimate. The fetch rewrite is correct that you need the scheme for dispatching (HTTPS → archive, SSH → git clone). The v1 refactor is correct that identity comparison should be scheme-agnostic (`https://github.com/foo/bar` and `github.com/foo/bar` should be the same source).

**Proposed design**:

```rust
/// What's stored in agents.toml — full URL with scheme for fetching
pub struct FetchUrl(String);

/// What's used for identity comparison — normalized, scheme-stripped
/// Derived from FetchUrl, never stored directly
pub struct SourceUrl(String);

impl FetchUrl {
    /// Derive the canonical identity URL (strip scheme, normalize)
    pub fn to_source_url(&self) -> SourceUrl {
        // https://github.com/owner/repo → github.com/owner/repo
        // git@github.com:owner/repo.git → github.com/owner/repo
        // github.com/owner/repo → github.com/owner/repo
        normalize_to_identity(&self.0)
    }
    
    /// Determine fetch strategy from the URL
    pub fn fetch_strategy(&self) -> FetchStrategy {
        if self.0.starts_with("git@") || self.0.starts_with("ssh://") {
            FetchStrategy::SystemGit
        } else {
            FetchStrategy::Archive
        }
    }
}
```

This means: `agents.toml` stores `FetchUrl` (with scheme), `SourceId` uses `SourceUrl` (stripped for comparison), and fetch dispatch uses `FetchUrl` directly.

### Migration Path

Current `agents.toml` files store bare URLs like `github.com/owner/repo` (from the current `normalize()` which strips the scheme). The new design stores `https://github.com/owner/repo`.

**Migration approach**: Read-time normalization with write-time upgrade.

```rust
fn load_source_entry(raw: &RawSourceEntry) -> SourceEntry {
    let url = if raw.url.starts_with("https://") 
        || raw.url.starts_with("http://")
        || raw.url.starts_with("git@") 
        || raw.url.starts_with("ssh://") {
        // Already has scheme — use as-is
        FetchUrl(raw.url.clone())
    } else {
        // Legacy bare domain — prepend https://
        FetchUrl(format!("https://{}", raw.url))
    };
    // ...
}
```

On the next `mars sync` or `mars add`, the config is persisted with the new format. This is a **non-breaking** migration: old configs are read correctly, new writes use the new format.

**`format` field**: The design proposes storing `format = "github"` in agents.toml. This is unnecessary if the format can be inferred from the URL. Storing it adds a field users can get wrong. **Recommend: derive format from URL at load time, don't store it.**

---

## 4. Archive URL Patterns

### GitHub-Only Is Correct for v1

The design correctly punts on GitLab/Bitbucket/Gitea for v1. But the fallback behavior needs to be explicit.

**Current design gap**: What happens when a user adds `https://gitlab.com/org/repo`? The archive URL construction will produce `https://gitlab.com/org/repo/archive/{sha}.tar.gz` which 404s. The user gets a cryptic HTTP error.

**Proposed: Host detection with clear errors**:

```rust
enum ArchiveHost {
    GitHub,        // /archive/{sha}.tar.gz
    // GitLab,     // v2: /-/archive/{sha}/{repo}-{sha}.tar.gz
    // Gitea,      // v2: /archive/{sha}.tar.gz (same as GitHub)
    Unknown,       // Fall back to system git
}

fn detect_host(url: &FetchUrl) -> ArchiveHost {
    let host = extract_host(url);
    match host {
        "github.com" => ArchiveHost::GitHub,
        // GitHub Enterprise: check for /api/v3 endpoint? Too complex for v1.
        _ => ArchiveHost::Unknown,
    }
}

fn fetch_source(url: &FetchUrl, sha: &str, cache: &Path) -> Result<PathBuf> {
    match detect_host(url) {
        ArchiveHost::GitHub => fetch_github_archive(url, sha, cache),
        ArchiveHost::Unknown => {
            // Fall back to system git clone for non-GitHub HTTPS sources
            // This handles GitLab, Gitea, self-hosted, etc.
            fetch_git_clone(url.as_str(), Some(sha), cache)
        }
    }
}
```

**Key insight**: The fallback for non-GitHub HTTPS sources should be `git clone --depth 1`, not an error. System git handles any git-compatible host. Archive download is an optimization for GitHub (which is 95%+ of agent sources), not the only path.

This means the strategy table should be:

| Source | Strategy |
|--------|----------|
| GitHub shorthand `owner/repo` | Archive download |
| `https://github.com/...` | Archive download |
| `https://gitlab.com/...` | System `git clone` (fallback) |
| `https://self-hosted.com/...` | System `git clone` (fallback) |
| `git@...` / `ssh://...` | System `git clone` |
| Local path | Direct copy |

### GitHub Enterprise

GitHub Enterprise uses the same archive URL pattern as github.com. Detection: the URL contains `/api/v3` or the host has a GHE-specific header. But for v1, treating it as `Unknown` (system git fallback) is safe and correct. Users with GHE who want archive downloads can wait for v2.

---

## 5. Version Listing Without Git

### The Problem

`git ls-remote --tags <url>` requires `git` in `$PATH`. The design uses this for ALL version listing, including archive-only HTTPS sources. A user on a locked-down CI image with `curl` but no `git` can't list versions.

### How Often This Matters

Rarely. The scenario is:
1. User installs mars via `cargo install` or pre-built binary
2. User's machine has no `git` installed
3. User adds a GitHub source with a version constraint

In practice, developers almost always have git. CI images that don't have git are unusual (even minimal Docker images include git for checkout).

### Proposed: GitHub API Fallback (v2)

For v1, **require system git for version listing** and document it. Error message:

```
error: `git` is not installed or not in PATH
  mars requires git for version discovery
  install git: https://git-scm.com/downloads
```

For v2, add GitHub API tag listing as a fallback (no auth needed for public repos):

```
GET https://api.github.com/repos/{owner}/{repo}/tags
```

This returns JSON with tag names and commit SHAs. Already using `ureq`, so the HTTP client is available. Rate limit: 60 req/hour unauthenticated, which is plenty for tag listing.

**Add to design doc's "Not In Scope" section**: "GitHub API fallback for tag listing when git is not installed (v2)."

---

## 6. AvailableVersion.commit_id: Oid → String

### Ripple Analysis

The `AvailableVersion` struct currently lives in `src/source/mod.rs`:

```rust
pub struct AvailableVersion {
    pub version: String,
    pub commit_id: git2::Oid,
}
```

Consumers of `commit_id`:

| File | Usage | Impact |
|------|-------|--------|
| `src/source/git.rs` | Constructs `AvailableVersion`, uses `commit_id` for `repo.find_commit(oid)` | Rewritten entirely — no issue |
| `src/resolve/mod.rs` | Reads `commit_id` from `AvailableVersion`, stores in `ResolvedRef.commit` | `ResolvedRef.commit` is already `Option<String>` — conversion from `Oid.to_string()` exists today. Removing the conversion is a simplification. |
| `src/resolve/mod.rs` (tests) | Uses `git2::Oid::zero()` in test mocks | Replace with `String::from("0000000000000000000000000000000000000000")` or any hex string |

### Interaction with v1 Refactor Newtypes

The v1 refactor [introduces `CommitHash` newtype](../../mars-agents-v1-refactor/design/newtypes-and-parsing.md) (line 136):

```rust
string_newtype!(
    /// 40-character hex git commit SHA.
    CommitHash
);
```

And changes `ResolvedRef.commit` to `Option<CommitHash>`.

**Coordination point**: If the source fetch rewrite changes `commit_id` to `String` and the v1 refactor changes it to `CommitHash`, the intermediate `String` state is short-lived. Options:

1. **Source fetch rewrite first → String → v1 refactor wraps to CommitHash**: Clean sequence, each step is independent.
2. **Do both at once → go straight to CommitHash**: Fewer intermediate states, but couples two work items.

**Recommendation**: Option 1. The `String` intermediate is fine. `CommitHash::new(sha)` wrapping is trivial.

### AvailableVersion Should Use String

The change is correct and low-risk. The only place `Oid` is used as an actual opaque type (not immediately `.to_string()`'d) is inside `git.rs` for `repo.find_commit(oid)`. Since that entire function is being rewritten, there's no regression risk.

---

## 7. Lock File Parse Failure as Empty Lock

### Current Behavior (from design spec)

The `cli/repair.rs` bonus fix proposes treating lock parse failure as empty lock.

### Risk Analysis

**Scenario A: Fully corrupt lock** (e.g., truncated write, disk error)
- Treating as empty → full re-resolve and re-sync. Safe — same as a clean install. Any local modifications are preserved because the sync diff will show everything as `Add` and won't overwrite existing files unless `--force`.

**Scenario B: Partially corrupt lock** (e.g., valid TOML but one entry has a bad field)
- Treating as empty → **loses all lock provenance**. The lock records which versions are pinned, which commits are locked, which checksums are expected. Starting from empty means a full re-resolve which may pick different versions (newer tags, different commits).

**Scenario C: Schema version mismatch** (e.g., lock was written by a newer mars version with `version: 2`)
- Treating as empty → silently downgrades. The newer lock format is discarded, resolved from scratch with the older schema. **This is dangerous** — the user might not realize they've lost lock integrity.

### Proposed: Graduated Error Handling

```rust
fn load_lock(root: &Path) -> Result<LockFile, MarsError> {
    let path = root.join(".mars").join("agents.lock");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            return Ok(LockFile::default()); // No lock = empty lock (normal)
        }
        Err(e) => return Err(MarsError::Io(e)),
    };
    
    match toml::from_str::<LockFile>(&content) {
        Ok(lock) => Ok(lock),
        Err(parse_err) => {
            // Check if it's a version mismatch
            if let Ok(partial) = toml::from_str::<LockVersion>(&content) {
                if partial.version > CURRENT_LOCK_VERSION {
                    return Err(MarsError::Lock(format!(
                        "lock file version {} is newer than supported version {} \
                         — upgrade mars or delete agents.lock",
                        partial.version, CURRENT_LOCK_VERSION
                    )));
                }
            }
            // Genuine corruption — warn and treat as empty for repair only
            Err(MarsError::Lock(format!(
                "lock file is corrupt: {parse_err}"
            )))
        }
    }
}
```

For `mars repair` specifically:

```rust
// cli/repair.rs
fn run_repair(root: &Path) -> Result<i32, MarsError> {
    let lock = match lock::load(root) {
        Ok(lock) => lock,
        Err(MarsError::Lock(msg)) => {
            eprintln!("warning: {msg}");
            eprintln!("  treating as empty lock — will re-resolve all sources");
            LockFile::default()
        }
        Err(e) => return Err(e),
    };
    // proceed with re-sync using empty or loaded lock
}
```

**Key principle**: Only `mars repair` treats corrupt lock as empty. Normal `mars sync` should **error** on a corrupt lock, because silently discarding lock data during routine operation is surprising. The user should explicitly choose to repair.

---

## 8. Missing Pieces

### 8a. Three-Way Merge Replacement (Critical)

Covered in section 1. Must add a pure-Rust merge library (`diffy`, `similar`, or `imara-diff`) and rewrite `merge/mod.rs`. Without this, dropping git2 breaks the conflict resolution pipeline.

### 8b. HTTP Error Handling and Retries

The design adds `ureq` for HTTP downloads but doesn't specify error handling:

- **Connection timeout**: `ureq` default is 30s. Should be configurable for slow networks.
- **HTTP 404**: GitHub returns 404 for private repos without auth. Error message should distinguish "repo not found" from "repo is private."
- **HTTP 429 (rate limit)**: GitHub rate-limits unauthenticated archive downloads. Should retry with backoff.
- **Large archives**: No size limit. A malicious or misconfigured source could serve a multi-GB tarball. Should cap at a reasonable limit (e.g., 100MB).
- **Redirect following**: GitHub archives redirect (301 → CDN). `ureq` follows redirects by default, but the design should note this.

```rust
fn fetch_archive(url: &str, sha: &str, cache: &Path) -> Result<PathBuf> {
    let archive_url = format!("{url}/archive/{sha}.tar.gz");
    let resp = ureq::get(&archive_url)
        .timeout(Duration::from_secs(60))
        .call()
        .map_err(|e| match e {
            ureq::Error::Status(404, _) => MarsError::Http {
                url: archive_url.clone(),
                status: 404,
                message: "repository not found (may be private — \
                         use SSH URL for private repos)".into(),
            },
            ureq::Error::Status(429, _) => MarsError::Http {
                url: archive_url.clone(),
                status: 429,
                message: "rate limited — try again in a few minutes".into(),
            },
            _ => MarsError::Http {
                url: archive_url.clone(),
                status: 0,
                message: e.to_string(),
            },
        })?;
    
    // Size guard
    let content_length = resp.header("content-length")
        .and_then(|s| s.parse::<u64>().ok());
    if let Some(len) = content_length {
        if len > 100 * 1024 * 1024 { // 100MB
            return Err(MarsError::Http {
                url: archive_url,
                status: 200,
                message: format!("archive too large ({len} bytes, max 100MB)"),
            });
        }
    }
    // ... extract
}
```

### 8c. Archive Integrity Verification

The design's cache key includes the SHA, and GitHub's archive is deterministic for a given commit. But there's no verification that the downloaded content actually corresponds to the expected SHA.

**Minimal approach**: After extraction, compute a tree hash (hash of all file contents in the extracted directory) and store it in the lock file's `tree_hash` field (currently always `None`). On cache hit, verify the tree hash matches. This detects cache corruption and CDN serving errors.

The security review (p652) noted: "locked commit replay is useful, but `tree_hash` is unset, so there is no extra post-fetch integrity check beyond git identity." This is the right place to fix that.

### 8d. Progress Indication

Archive downloads can take seconds for large repos. No progress indication means the user sees a hang. Consider:

```rust
// During download
eprintln!("  downloading {url}/archive/{sha}.tar.gz ...");
// After extraction
eprintln!("  extracted to cache ({} files)", file_count);
```

Minimal, no progress bars. Keep it simple for v1.

### 8e. MARS_CACHE_DIR Validation

The design mentions `MARS_CACHE_DIR` env var for overriding cache location but doesn't specify validation. What if:
- Path doesn't exist? → Create it (like `~/.mars/cache`)
- Path exists but isn't writable? → Clear error
- Path is on a network filesystem (NFS, SMB)? → Works but slow. No special handling needed.

### 8f. Tarball Prefix Stripping

GitHub archives contain a `{repo}-{sha}/` prefix directory. The design notes this but doesn't specify the stripping logic:

```
repo-abc123def456/
  agents/
    coder.md
  skills/
    ...
```

After extraction, content should be at `cache/archives/{key}/agents/coder.md`, not `cache/archives/{key}/repo-abc123def456/agents/coder.md`.

**Implementation note**: The `tar` crate supports `strip_components(1)` via `Archive::entries()` with manual path manipulation, but not via `unpack()` directly. The code will need:

```rust
let gz = flate2::read::GzDecoder::new(bytes.as_slice());
let mut archive = tar::Archive::new(gz);
for entry in archive.entries()? {
    let mut entry = entry?;
    let path = entry.path()?;
    // Strip first component (the {repo}-{sha}/ prefix)
    let stripped: PathBuf = path.components().skip(1).collect();
    if stripped.components().count() == 0 {
        continue; // skip the prefix directory itself
    }
    entry.unpack(target.join(&stripped))?;
}
```

**Security concern**: Path traversal in tarball entries. A malicious tarball could contain `../../../etc/passwd`. Use the `tar` crate's built-in path sanitization, or explicitly reject entries with `..` components.

### 8g. Concurrent Cache Access

Multiple mars invocations (different projects) sharing `~/.mars/cache/` may race on the same archive entry. Two concurrent `mars sync` for projects using the same source will both try to download and extract.

**Fix**: Per-entry lock file, or atomic rename (already proposed in 2. Cache Atomicity). The atomic rename approach handles this naturally — the second writer's rename succeeds or fails (depending on platform), and either way the content is complete.

### 8h. Security Findings Integration

The security review (p652) found:
1. **Symlink traversal in discovery** — fetched source trees could contain symlinks pointing outside the tree.
2. **Unvalidated URLs** — arbitrary git transports possible.
3. **Destination path escape** — rename entries could write outside `.agents/`.

The source fetch rewrite should address finding #2 directly since it's rewriting the URL handling:

```rust
fn validate_fetch_url(url: &FetchUrl) -> Result<(), MarsError> {
    let s = url.as_str();
    // Allow: https://, git@, ssh://, local paths
    // Deny: file://, git://, other arbitrary protocols
    if s.starts_with("file://") || s.starts_with("git://") {
        return Err(MarsError::Config(format!(
            "unsupported URL scheme in {s} — use https:// or SSH"
        )));
    }
    Ok(())
}
```

Findings #1 and #3 are independent of this rewrite but should be tracked.

---

## Summary of Recommendations

### Must Fix Before Implementation

1. **Add `merge/mod.rs` to scope** — it depends on git2 and is not listed in "Files to Modify"
2. **Add merge library to dependencies** — `diffy` or `similar` alongside `ureq`, `flate2`, `tar`
3. **Add non-GitHub fallback** — HTTPS sources for non-GitHub hosts should fall back to `git clone`, not error
4. **Add cache atomicity** — extract to temp dir + rename, per mars's crash-only design principle
5. **Resolve `SourceUrl` / `FetchUrl` conflict with v1 refactor** — two types, one for fetching (scheme-included), one for identity (scheme-stripped)

### Should Fix

6. **Cache GC strategy** — at minimum, document that cache grows unbounded and add `mars cache gc` to roadmap
7. **Lock parse failure should error on normal sync** — only `mars repair` treats it as empty
8. **HTTP error messages** — distinguish 404 (not found) from private repo from rate limit
9. **Tarball path sanitization** — reject `..` components in tar entries
10. **URL scheme validation** — reject `file://` and `git://` protocols (security review finding)

### Nice to Have (v2)

11. GitHub API tag listing as fallback when git isn't installed
12. Archive size limits
13. Tree hash verification (populate `lock.tree_hash`)
14. Progress indication for downloads
15. `mars cache info` / `mars cache gc` commands
