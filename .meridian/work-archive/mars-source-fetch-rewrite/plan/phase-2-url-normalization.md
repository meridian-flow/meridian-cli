# Phase 2: URL Normalization — Preserve Scheme

**Risk:** Medium — changes stored URLs, affects config loading  
**Design doc:** [overview.md](../design/overview.md) §URL Storage

## Scope

Fix `source/parse.rs` to preserve URL scheme in normalized output. Add legacy auto-upgrade for bare domain URLs. Update config types if needed.

## Steps

1. **src/source/parse.rs** — `normalize()`:
   - `GitHubShorthand "owner/repo"` → `"https://github.com/owner/repo"` (was `"github.com/owner/repo"`)
   - `HttpsUrl "https://github.com/org/repo.git"` → `"https://github.com/org/repo"` (was `"github.com/org/repo"`)
   - `SshUrl "git@github.com:org/repo.git"` → `"git@github.com:org/repo.git"` (preserve as-is, including `.git` suffix for SSH)
   - `BareDomain "github.com/org/repo"` → `"https://github.com/org/repo"` (was `"github.com/org/repo"`)
   - Update all test assertions in `normalize_handles_all_git_formats` and `parse_matrix_examples`

2. **src/source/parse.rs** — add `derive_fetch_url()`:
   - Extract host from URL for `is_github_host()` checks
   - This is used by git.rs to decide archive vs git clone

3. **src/config/mod.rs** — legacy migration:
   - When loading `agents.toml`, if a git source URL has no scheme and contains `/` and `.`, prepend `https://`
   - This auto-upgrades old `github.com/owner/repo` to `https://github.com/owner/repo`

4. **src/source/git.rs** — update `url_to_dirname()` tests if needed (it already strips schemes)

5. **src/types.rs** — optionally rename `SourceUrl` to `FetchUrl` if we want the type distinction now, or keep `SourceUrl` and derive identity separately. Simplest: keep `SourceUrl` as the stored type, it now includes the scheme.

## Verification

- `cargo test` — all unit tests in parse.rs pass with updated assertions
- `cargo test` — config loading with old-format URLs works (write a test)
- Integration tests still fail (fetch is stubbed)

## Dependencies

Requires Phase 1 (type changes).
