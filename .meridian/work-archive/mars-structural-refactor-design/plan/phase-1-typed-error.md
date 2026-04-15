# Phase 1: Typed Error for Unmanaged Collisions (F17)

## Scope
Add `MarsError::UnmanagedCollision` variant so repair.rs matches on type instead of parsing error message strings.

## Files to Modify
- `src/error.rs` — add `UnmanagedCollision { source_name: String, path: PathBuf }` variant
- `src/sync/target.rs` — change `check_unmanaged_collisions()` to construct the new variant (line 372)
- `src/cli/repair.rs` — replace string parsing with pattern match (line 99-107)

## Interface Contract
```rust
// In MarsError enum:
#[error("source error: {source_name}: refusing to overwrite unmanaged path `{}`", path.display())]
UnmanagedCollision {
    source_name: String,
    path: PathBuf,
}

// Exit code: 3 (same as Source)
```

## Implementation Notes
- Add `UnmanagedCollision` to the exit_code() match alongside `Source` → 3
- The Display format must match the current `MarsError::Source` output exactly so CLI behavior is unchanged
- Add a test in `src/error.rs` for the new variant's exit code and display format
- Update the existing `mars_error_exit_codes_match_spec` test to include the new variant

## Verification Criteria
- [ ] `cargo test` passes (352+ tests)
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] `repair.rs` no longer contains `strip_prefix` / string parsing
- [ ] Error display output unchanged (same message format)
