# Phase 1: Error Model & Shared Constants

**Design refs**: [error-model.md](../design/error-model.md), [root-context.md](../design/root-context.md)

## Scope

Foundation phase — add the `MarsError::Link` variant and extract shared directory constants. No behavior changes yet; this phase only adds types and constants that later phases consume.

## Files to Modify

- `src/error.rs` — Add `MarsError::Link { target: String, message: String }` variant + exit code mapping
- `src/cli/mod.rs` — Extract `WELL_KNOWN` and `TOOL_DIRS` as module-level `pub const` arrays

## Interface Contract

```rust
// src/error.rs
pub enum MarsError {
    // ... existing variants ...
    #[error("link error: {target}: {message}")]
    Link { target: String, message: String },
}

// In exit_code():
MarsError::Link { .. } => 2,

// src/cli/mod.rs
/// Directories where mars manages agents.toml as the primary root.
pub const WELL_KNOWN: &[&str] = &[".agents"];

/// Tool-specific directories that commonly need linking.
pub const TOOL_DIRS: &[&str] = &[".claude", ".cursor"];
```

## Changes

### error.rs
1. Add `Link { target: String, message: String }` variant to `MarsError` enum
2. Add `#[error("link error: {target}: {message}")]` derive
3. Add `MarsError::Link { .. } => 2` arm to `exit_code()`
4. Add a test for the new variant format and exit code

### cli/mod.rs
1. Add `pub const WELL_KNOWN: &[&str] = &[".agents"];` at module level
2. Add `pub const TOOL_DIRS: &[&str] = &[".claude", ".cursor"];` at module level
3. Update `find_agents_root` to use the constants instead of the local `const`:
   ```rust
   // Before (line 185):
   const WELL_KNOWN: &[&str] = &[".agents", ".claude"];
   // After:
   // Use module-level WELL_KNOWN and TOOL_DIRS
   for subdir in WELL_KNOWN.iter().chain(TOOL_DIRS.iter()) {
   ```

## Dependencies

- **Requires**: Nothing (foundation phase)
- **Produces**: `MarsError::Link` variant, `WELL_KNOWN`/`TOOL_DIRS` constants — consumed by phases 2-5

## Verification Criteria

- [ ] `cargo build` succeeds with no warnings
- [ ] `cargo test` passes (existing tests unbroken)
- [ ] New test: `MarsError::Link` formats correctly and returns exit code 2
- [ ] `find_agents_root` behavior unchanged (still finds `.agents` and `.claude` roots)
