# Source Fetch Rewrite: Proposed Refinements

Concrete changes to [overview.md](overview.md) based on the [architectural review](review.md).

## Refinement 1: Add merge/mod.rs to Scope

### Problem

`merge/mod.rs` uses `git2::merge_file()` for three-way merge during conflict resolution. Dropping git2 without replacing this breaks the `PlannedAction::Merge` path in `sync/apply.rs`.

### Change to overview.md

**Dependency Changes — Add:**
```
- `diffy` — three-way merge with conflict markers (replaces git2::merge_file)
```

**Files to Modify — Add:**
```
### `src/merge/mod.rs` → rewrite merge implementation
- Remove `git2::merge_file()` call
- Replace with `diffy::merge()` or equivalent
- Preserve: `MergeResult` struct, `MergeLabels` struct, `merge_content()` signature
- The merge module is self-contained (~50-100 lines) — straightforward replacement
```

### Concrete Implementation

```rust
// merge/mod.rs — AFTER

use diffy::{merge as diffy_merge};

pub fn merge_content(
    base: &[u8],
    local: &[u8],
    theirs: &[u8],
    labels: &MergeLabels,
) -> Result<MergeResult, MarsError> {
    let base_str = std::str::from_utf8(base)
        .map_err(|_| MarsError::Merge("base content is not valid UTF-8".into()))?;
    let local_str = std::str::from_utf8(local)
        .map_err(|_| MarsError::Merge("local content is not valid UTF-8".into()))?;
    let theirs_str = std::str::from_utf8(theirs)
        .map_err(|_| MarsError::Merge("upstream content is not valid UTF-8".into()))?;

    match diffy_merge(base_str, local_str, theirs_str) {
        Ok(merged) => Ok(MergeResult {
            content: merged.into_bytes(),
            has_conflicts: false,
            conflict_count: 0,
        }),
        Err(conflicted) => {
            // diffy returns conflict-marker-annotated content on Err
            let content = conflicted.to_string();
            let conflict_count = content.matches("<<<<<<<").count();
            Ok(MergeResult {
                content: content.into_bytes(),
                has_conflicts: true,
                conflict_count,
            })
        }
    }
}
```

**Note**: `diffy::merge` uses standard `<<<<<<<`/`=======`/`>>>>>>>` conflict markers. Custom labels require `diffy::MergeOptions` (check API — if not supported, the default labels work fine for agent files).

**Alternative**: If `diffy` doesn't support custom labels, use `similar` crate which has `TextDiff` with more control, or `imara-diff` (used by gitoxide, most performant).

---

## Refinement 2: Non-GitHub HTTPS Fallback

### Problem

The design only handles GitHub archive URLs. Non-GitHub HTTPS sources (GitLab, Gitea, self-hosted) get no special handling and would fail with a bad archive URL.

### Change to Fetch Strategy Table

Replace the current table with:

| User input | SourceFormat | Fetch strategy | Cache location |
|---|---|---|---|
| `owner/repo` | GitHubShorthand | Archive download (HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `owner/repo@v1.0` | GitHubShorthand | Archive download (HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `https://github.com/org/repo` | HttpsUrl (GitHub) | Archive download (HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `https://gitlab.com/org/repo` | HttpsUrl (non-GitHub) | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `github.com/org/repo` | BareDomain (GitHub) | Archive download (HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `gitlab.com/org/repo` | BareDomain (non-GitHub) | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `git@github.com:org/repo.git` | SshUrl | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `/path/to/local` | LocalPath | Direct copy | No cache |

### Implementation

```rust
fn is_github_host(url: &str) -> bool {
    // For v1: only github.com gets archive optimization
    // GitHub Enterprise (custom domains) falls back to git clone
    let host = extract_host(url);
    host == "github.com"
}

pub fn fetch(
    url: &str,
    version_req: Option<&str>,
    format: &SourceFormat,
    cache_dir: &GlobalCache,
    options: &FetchOptions,
) -> Result<ResolvedRef, MarsError> {
    match format {
        SourceFormat::GitHubShorthand | SourceFormat::BareDomain | SourceFormat::HttpsUrl
            if is_github_host(url) =>
        {
            fetch_archive(url, version_req, cache_dir, options)
        }
        SourceFormat::SshUrl => {
            fetch_git_clone(url, version_req, cache_dir, options)
        }
        _ => {
            // Non-GitHub HTTPS: fall back to system git
            fetch_git_clone(url, version_req, cache_dir, options)
        }
    }
}
```

---

## Refinement 3: FetchUrl / SourceUrl Split

### Problem

The v1 refactor defines `SourceUrl` as protocol-stripped (for identity comparison). This design stores full URL with scheme (for fetch dispatch). Both are needed.

### Change to URL Storage Section

Replace "URL Storage" in overview.md with:

**Two URL types:**

```rust
/// What's stored in agents.toml — full URL with scheme, used for fetching
pub struct FetchUrl(String);

/// Canonical identity URL — derived from FetchUrl, scheme-stripped, normalized
/// Used only for SourceId comparison (deduplication in resolver)
/// Never stored — always derived
pub struct SourceUrl(String);
```

**agents.toml stores FetchUrl:**
```toml
[sources.meridian-base]
# GitHubShorthand "haowjy/meridian-base" stored as full HTTPS URL
url = "https://github.com/haowjy/meridian-base"

[sources.private-agents]
# SSH URL stored as-is
url = "git@company.com:team/agents.git"
```

**No `format` field.** Format is derived from the URL at load time:
- Starts with `git@` or `ssh://` → SSH → system git
- Starts with `https://github.com` → HTTPS GitHub → archive download
- Starts with `https://` (non-GitHub) → HTTPS generic → system git clone
- Relative or absolute path → local

**Legacy migration (auto-upgrade):**
```rust
// In config::load — handle bare domain URLs from old agents.toml
fn normalize_url(raw: &str) -> FetchUrl {
    if raw.starts_with("https://") || raw.starts_with("http://")
       || raw.starts_with("git@") || raw.starts_with("ssh://") {
        FetchUrl(raw.to_string())
    } else if raw.contains('/') && !raw.starts_with('/') && !raw.starts_with('.') {
        // Bare domain like "github.com/owner/repo" → prepend https://
        FetchUrl(format!("https://{raw}"))
    } else {
        // Local path — not a URL
        FetchUrl(raw.to_string())
    }
}
```

---

## Refinement 4: Cache Atomicity

### Problem

Killed-mid-extraction leaves incomplete cache entries that look valid on next run.

### Add to overview.md Cache Section

**Cache write protocol:**

1. Create temp dir: `{cache_path}.downloading.{pid}`
2. Extract archive content into temp dir
3. Atomic rename: `rename(temp_dir, cache_path)`
4. If rename fails (another process won the race), delete temp dir — the winner's content is valid

```rust
fn cache_archive(tarball: &[u8], target: &Path) -> Result<(), MarsError> {
    if target.exists() {
        return Ok(()); // Already cached
    }
    
    let tmp = target.with_extension(format!(".tmp.{}", std::process::id()));
    std::fs::create_dir_all(&tmp)?;
    
    // Extract with prefix stripping and path sanitization
    extract_and_strip(tarball, &tmp)?;
    
    // Atomic publish
    match std::fs::rename(&tmp, target) {
        Ok(()) => Ok(()),
        Err(e) if target.exists() => {
            // Race: another process created it first. Clean up our tmp.
            let _ = std::fs::remove_dir_all(&tmp);
            Ok(())
        }
        Err(e) => {
            let _ = std::fs::remove_dir_all(&tmp);
            Err(MarsError::Io(e))
        }
    }
}
```

---

## Refinement 5: Graduated Lock Parse Failure

### Problem

The design proposes treating lock parse failure as empty lock in `repair.rs`. This is too aggressive for normal `mars sync`.

### Change to cli/repair.rs Section

Replace:
> **Bonus fix**: Handle corrupt lock file by treating parse failure as empty lock

With:
> **Bonus fix**: `mars repair` handles corrupt lock gracefully:
> - **Version mismatch** (lock written by newer mars): Error with "upgrade mars or delete agents.lock"
> - **Parse corruption** (invalid TOML, missing fields): Warn and treat as empty lock — re-resolves all sources
> - **Normal `mars sync` with corrupt lock**: Errors with "lock file is corrupt — run `mars repair`"
>
> Only `mars repair` auto-recovers from corruption. Normal operations surface the error to avoid silently discarding lock provenance.

---

## Refinement 6: Error.rs Additions

### Problem

The design adds `Http` and `GitCli` variants but doesn't account for the merge module or URL validation.

### Expanded Error Variants

```rust
pub enum MarsError {
    // ... existing variants ...

    // NEW — source fetch rewrite
    #[error("HTTP request failed: {url} — {status}: {message}")]
    Http { url: String, status: u16, message: String },

    #[error("git command failed: `{command}` — {message}")]
    GitCli { command: String, message: String },

    #[error("three-way merge failed: {0}")]
    Merge(String),  // NEW — replaces git2 merge errors

    // exit_code() mapping:
    // Http → 3 (I/O / infrastructure)
    // GitCli → 3 (I/O / infrastructure)
    // Merge → 1 (conflict / user action needed)
}
```

---

## Refinement 7: Tarball Security

### Problem

Tarball extraction without path sanitization enables path traversal attacks.

### Add to Archive Download Flow

After step 2 ("Extract tarball"), add:

**Path sanitization during extraction:**
- Reject entries containing `..` path components
- Reject absolute paths
- Reject symlinks (addresses security review p652 finding #1 for fetched content)
- Strip first path component (the `{repo}-{sha}/` prefix)

```rust
fn extract_and_strip(tarball: &[u8], target: &Path) -> Result<(), MarsError> {
    let gz = flate2::read::GzDecoder::new(tarball);
    let mut archive = tar::Archive::new(gz);
    
    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?;
        
        // Security: reject symlinks
        if entry.header().entry_type().is_symlink() 
           || entry.header().entry_type().is_hard_link() {
            continue; // skip silently — agent packages shouldn't have symlinks
        }
        
        // Strip first component (repo-sha/ prefix)
        let stripped: PathBuf = path.components().skip(1).collect();
        if stripped.components().count() == 0 {
            continue;
        }
        
        // Security: reject path traversal
        for component in stripped.components() {
            if matches!(component, std::path::Component::ParentDir) {
                return Err(MarsError::Source {
                    source_name: String::new(),
                    message: format!(
                        "archive contains path traversal: {}",
                        path.display()
                    ),
                });
            }
        }
        
        let dest = target.join(&stripped);
        entry.unpack(&dest)?;
    }
    Ok(())
}
```
