# F4: Canonicalize Comparison Safety

## Problem

Two locations compare canonicalized paths using `.canonicalize().ok()` — when both sides fail to canonicalize, `None == None` evaluates to `true`, treating two broken paths as equivalent.

### Affected Code

**`src/cli/link.rs` — `scan_link_target()`** (line ~320):
```rust
let actual_resolved = link_path
    .parent()
    .map(|p| p.join(&actual_target))
    .and_then(|p| p.canonicalize().ok());
let expected_resolved = managed_subdir.canonicalize().ok();

match (actual_resolved, expected_resolved) {
    (Some(a), Some(b)) if a == b => return ScanResult::AlreadyLinked,
    _ => return ScanResult::ForeignSymlink { target: actual_target },
}
```

This code is already correct — it uses `match` on `(Some, Some)` and falls through to `ForeignSymlink` for any other combination. No fix needed here.

**`src/cli/doctor.rs` — `check_link_health()`** (line ~145):
```rust
let resolved_canon = resolved.canonicalize().ok();
let expected_canon = expected.canonicalize().ok();

if resolved_canon != expected_canon {
    // reports wrong target
}
```

This is the bug. If both `resolved` and `expected` fail to canonicalize (e.g., broken symlink pointing nowhere, AND the managed subdir doesn't exist yet), `None != None` is `false`, so the "wrong target" check passes silently.

**Partial mitigation:** The code below this comparison checks `!link_path.exists()` and reports broken symlinks. So a completely broken symlink IS caught by the exists check. However, the canonicalize comparison still gives a misleading pass — it treats "both paths unresolvable" as "they match," which is semantically wrong. The fix ensures the comparison correctly reports "can't verify this points to the right place" rather than silently passing.

**`src/cli/link.rs` — `unlink()`** (line ~530):
The unlink function was already fixed in a prior commit to use the safe pattern:
```rust
let matches = match (resolved.canonicalize(), expected.canonicalize()) {
    (Ok(a), Ok(b)) => a == b,
    _ => false,
};
```

## Fix

Apply the same `match (Ok, Ok)` pattern to `check_link_health()` in doctor.rs:

```rust
// Before:
let resolved_canon = resolved.canonicalize().ok();
let expected_canon = expected.canonicalize().ok();
if resolved_canon != expected_canon {

// After:
let points_to_managed = match (resolved.canonicalize(), expected.canonicalize()) {
    (Ok(a), Ok(b)) => a == b,
    _ => false,
};
if !points_to_managed {
```

This means:
- Both canonicalize successfully and match → healthy
- Both canonicalize successfully but differ → wrong target (existing behavior)
- Either fails → treated as wrong target (new behavior, was silently passing)

The broken-symlink check below this comparison already handles the case where the symlink exists but its target is missing, so the two checks compose correctly.

## Files to Modify

- `src/cli/doctor.rs` — `check_link_health()`, ~5 lines changed

## Verification

- `cargo test` passes
- Existing `doctor` tests still pass
- Manual: create a broken symlink in a link target dir, run `mars doctor` — should report the issue
