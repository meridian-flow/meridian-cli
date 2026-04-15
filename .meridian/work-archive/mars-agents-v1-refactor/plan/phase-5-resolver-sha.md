# Phase 5: Resolver Locked SHA Replay

**Fixes:** #5 (resolver ignores locked commit SHA)
**Design doc:** [resolver-and-errors.md](../design/resolver-and-errors.md) §Locked SHA Replay
**Risk:** Medium — changes resolution path, affects reproducibility guarantees

## Scope and Intent

Make the resolver use locked commit SHAs as the checkout target when a lock file exists. Frozen sync guarantees reproducible checkout by replaying locked SHAs. Force-pushed tags produce a clear error in frozen mode and a warning in normal mode.

## Files to Modify

- **`src/source/git.rs`** — Add `FetchOptions { preferred_commit: Option<String> }` struct. Extract `checkout_commit()` from existing OID path in `checkout_version()`. Update `fetch()` signature to accept `FetchOptions`.
- **`src/resolve/mod.rs`** — Update lock preference path to pass `locked.commit` as `preferred_commit`. Handle `LockedCommitUnreachable` per resolution mode (frozen → error, normal → warn + fallback, maximize → ignore lock).
- **All callers of `git::fetch`** (in `sync/mod.rs` and `resolve/mod.rs`) — Pass `FetchOptions { preferred_commit: None }` where no lock replay is needed.

## Dependencies

- **Requires:** Phase 3 (the `MarsError::LockedCommitUnreachable` variant) AND Phase 4 (uses `ResolutionMode` to determine behavior: Normal warns on unreachable SHA, Frozen errors, Maximize ignores lock)
- **Produces:** Reproducible frozen sync

## Interface Contract

```rust
// src/source/git.rs
pub struct FetchOptions {
    pub preferred_commit: Option<String>,
}

pub fn fetch(
    url: &str,
    version: Option<&str>,
    cache: &CacheDir,
    options: &FetchOptions,
) -> Result<ResolvedRef, MarsError>;

fn checkout_commit(repo: &Repository, sha: &str) -> Result<PathBuf, MarsError>;
```

## Verification Criteria

- [ ] `cargo test` — all existing tests pass
- [ ] New integration tests:
  - Create repo with tag v1.0.0 at commit A, sync, force-push tag to B, sync → content still from A
  - Same with `--frozen` → content from A
  - Force-push AND delete old commit, `--frozen` → exit code 2 with `LockedCommitUnreachable`
  - `mars upgrade` after force-push → resolves fresh to B
- [ ] `cargo clippy -- -D warnings` — clean

## Agent Staffing

- **Implementer:** `coder` (git2 knowledge helpful)
- **Reviewer:** 1 reviewer focused on git edge cases (shallow clones, annotated tags, packed refs)
- **Tester:** `verifier`
