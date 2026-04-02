# Source Fetch Rewrite: Drop git2, Add Archive Downloads + System Git

## Goal

Replace git2 (libgit2 bindings) with archive downloads for HTTPS sources and system `git` for SSH sources. Fixes the blocking git TLS issue, reduces dependency tree by ~15 crates, and aligns with how Go/npm handle source fetching. Also introduces global cache at `~/.mars/cache/`.

## Current State

- `source/git.rs` uses git2 for clone, fetch, tag listing, checkout
- git2 compiled without working TLS → all remote git sources broken
- Cache is per-project at `.mars/cache/`
- URLs normalized by stripping scheme (`https://github.com/org/repo` → `github.com/org/repo`) — then passed to git2 which can't determine protocol

## Target State

### Fetch Strategy by Source Format

| User input | SourceFormat | Fetch strategy | Cache location |
|---|---|---|---|
| `owner/repo` | GitHubShorthand | Archive download (GitHub HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `owner/repo@v1.0` | GitHubShorthand | Archive download (GitHub HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `https://github.com/org/repo` | HttpsUrl (GitHub) | Archive download (GitHub HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `https://gitlab.com/org/repo` | HttpsUrl (non-GitHub) | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `github.com/org/repo` | BareDomain (GitHub) | Archive download (GitHub HTTPS) | `~/.mars/cache/archives/{url_dirname}_{sha}/` |
| `gitlab.com/org/repo` | BareDomain (non-GitHub) | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `git@github.com:org/repo.git` | SshUrl | System `git clone --depth 1` | `~/.mars/cache/git/{url_dirname}/` |
| `/path/to/local` | LocalPath | Direct copy | No cache |

GitHub detection: `is_github_host()` checks if the host is `github.com`. GitHub Enterprise and all other hosts fall back to system `git clone --depth 1`.

### Version Resolution Default

When no version is specified (`mars add owner/repo`):

1. **Latest semver tag** — `git ls-remote --tags` → parse semver tags → pick highest → download that version
2. **Fallback to default branch** — if no semver tags exist → use HEAD of default branch, warn: "no releases found for {source}, using latest commit from default branch"

Explicit version pin (`mars add owner/repo@v1.0`) uses that constraint. Explicit branch pin (`mars add owner/repo@main`) tracks that branch.

### URL Storage — FetchUrl vs SourceUrl

Two URL types:

```rust
/// What's stored in agents.toml — full URL with scheme, used for fetching.
pub struct FetchUrl(String);

/// Canonical identity — derived from FetchUrl, scheme-stripped, normalized.
/// Used for SourceId comparison (dedup in resolver). Never stored — always derived.
pub struct SourceUrl(String);
```

`agents.toml` stores `FetchUrl`:

```toml
[sources.meridian-base]
url = "https://github.com/haowjy/meridian-base"

[sources.private-agents]
url = "git@company.com:team/agents.git"
```

No `format` field stored — format is derived from URL at load time:
- `git@` or `ssh://` → SSH → system git
- `https://github.com` → GitHub HTTPS → archive download
- `https://` (non-GitHub) → generic HTTPS → system git clone
- Relative or absolute path → local

Legacy migration: bare domain URLs (`github.com/owner/repo` without scheme) auto-upgrade to `https://github.com/owner/repo` on config load. Next write persists the new format.

### Archive Download Flow

1. **Version listing**: `git ls-remote --tags <url>` via system `git` subprocess
   - Parse output: `{sha}\trefs/tags/{tag}` lines
   - Filter to semver tags, return `Vec<AvailableVersion>`
   - `AvailableVersion.commit_id` becomes `String` (SHA hex) instead of `git2::Oid`

2. **Version resolution** (when no version specified):
   - List all semver tags
   - Pick highest version → use its SHA
   - If no semver tags: `git ls-remote HEAD <url>` → get default branch SHA, warn user

3. **Content fetch**: HTTP GET to archive URL
   - GitHub: `https://github.com/{owner}/{repo}/archive/{sha}.tar.gz`
   - Cache key: `~/.mars/cache/archives/{url_dirname}_{sha}/`
   - If cached, skip download
   - Extract tarball → strip first path component (`{repo}-{sha}/` prefix)

4. **Cache atomicity** (crash-only design):
   - Extract to `{cache_path}.tmp.{pid}`
   - Atomic `rename()` to final path
   - If rename fails (another process won), delete our temp dir

5. **Tarball security**:
   - Reject symlinks and hard links
   - Reject `..` path components
   - Reject absolute paths
   - Strip first path component

6. **Lock replay**: Lock records commit SHA. On sync, check if `~/.mars/cache/archives/{url_dirname}_{sha}/` exists → use cached. If not, download by SHA.

### System Git Flow (SSH + non-GitHub HTTPS)

1. **Version listing**: `git ls-remote --tags <url>` subprocess (same as archive path)
2. **Content fetch**: `git clone --depth 1 --branch {tag} <url> <cache_path>`
   - Or `git clone --depth 1 <url> <cache_path>` for default branch
   - Cache at `~/.mars/cache/git/{url_dirname}/`
   - On update: `git fetch --depth 1 origin tag {tag}` + `git checkout`
3. **Auth**: System git handles SSH agent, credential helpers — no mars involvement

### Global Cache Layout

```
~/.mars/
  cache/
    archives/                                    # extracted tarballs (content-addressed by SHA)
      github.com_haowjy_meridian-base_{sha}/
        agents/
        skills/
    git/                                         # shallow clones (SSH + non-GitHub sources)
      company.com_team_agents/
        .git/
        agents/
        skills/
```

Override: `MARS_CACHE_DIR` env var (for CI, containers, custom paths).

Per-project `.mars/` retains:
- `sync.lock` — flock for concurrent sync
- `cache/bases/` — three-way merge base content (project-specific)

### Dependency Changes

**Remove:**
- `git2` (+ libgit2-sys, openssl-sys, openssl-src, libssh2-sys, ~15 transitive deps)

**Add:**
- `ureq` — sync HTTP client (minimal, ~4 deps)
- `flate2` — gzip decompression
- `tar` — tarball extraction

### Error Variants

```rust
pub enum MarsError {
    // existing variants...

    // NEW — replaces Git(git2::Error)
    #[error("HTTP request failed: {url} — {status}: {message}")]
    Http { url: String, status: u16, message: String },

    #[error("git command failed: `{command}` — {message}")]
    GitCli { command: String, message: String },

    // exit_code() mapping: Http → 3, GitCli → 3
}
```

## Files to Modify

### `Cargo.toml`
- Remove `git2`
- Add `ureq`, `flate2`, `tar`

### `src/source/git.rs` → complete rewrite
- Remove all git2 usage
- New functions:
  - `ls_remote_tags(url: &str) -> Result<Vec<AvailableVersion>>` — subprocess `git ls-remote --tags`
  - `ls_remote_head(url: &str) -> Result<String>` — subprocess `git ls-remote HEAD`
  - `fetch_archive(url: &str, sha: &str, cache: &GlobalCache) -> Result<PathBuf>` — HTTP download + extract
  - `fetch_git_clone(url: &str, version: Option<&str>, cache: &GlobalCache) -> Result<PathBuf>` — system `git clone --depth 1`
  - `fetch(url, version_req, source_name, cache, options) -> Result<ResolvedRef>` — dispatch by host
- Keep: `url_to_dirname()`, `FetchOptions`, `parse_semver_tag()`
- Rewrite tests to use `git init`/`git tag` subprocesses instead of git2 API

### `src/source/mod.rs`
- `AvailableVersion.commit_id`: change from `git2::Oid` to `String`
- `CacheDir` → `GlobalCache` with `archives_dir()` and `git_dir()` methods
- Default path: `~/.mars/cache/`, override: `MARS_CACHE_DIR`
- `fetch_source()`: dispatch by `is_github_host()` for archive vs git clone

### `src/source/parse.rs`
- `normalize()`: preserve URL scheme
  - `GitHubShorthand "owner/repo"` → `FetchUrl("https://github.com/owner/repo")`
  - `HttpsUrl "https://github.com/org/repo.git"` → `FetchUrl("https://github.com/org/repo")`
  - `SshUrl "git@github.com:org/repo.git"` → `FetchUrl("git@github.com:org/repo.git")` (preserve as-is)
  - `BareDomain "github.com/org/repo"` → `FetchUrl("https://github.com/org/repo")`
- Update all normalize tests

### `src/error.rs`
- Remove `Git(#[from] git2::Error)` variant
- Add `Http` and `GitCli` variants (exit code 3)

### `src/resolve/mod.rs`
- Update `AvailableVersion` usage — `commit_id` is now `String` not `git2::Oid`
- Test mock: use `String` commit IDs instead of `git2::Oid::zero()`

### `src/config/mod.rs`
- Auto-upgrade bare domain URLs to `https://` on load
- Store `FetchUrl` type in `SourceEntry` (or keep as `String` with auto-upgrade)

### `src/cli/repair.rs`
- Handle corrupt lock: parse failure → warn + treat as empty lock (re-resolve from config)
- Normal `mars sync` with corrupt lock → error with "lock is corrupt — run `mars repair`"

### `src/types.rs`
- Add `FetchUrl` newtype (or rename current `SourceUrl` to `FetchUrl` and add derived `SourceUrl`)

## Test Strategy

- All existing 24 integration tests must pass (local path sources, unaffected)
- git.rs unit tests: rewrite using `git init`/`git commit`/`git tag` subprocesses
- New integration test: `mars add haowjy/meridian-base` → verify HTTPS archive download
- New unit tests: `ls_remote_tags` output parsing, archive URL construction, tarball extraction with path sanitization
- Verify `mars repair` recovers from corrupt lock

## Not In Scope

- GitLab/Gitea archive URL patterns (GitHub only, others fall back to system git)
- Auth tokens for private HTTPS archives (v2)
- GitHub API for tag listing without git (v2 — `git ls-remote` requires git installed)
- Content hash verification beyond git SHA (v2)
- Source trust tiers (v2)
