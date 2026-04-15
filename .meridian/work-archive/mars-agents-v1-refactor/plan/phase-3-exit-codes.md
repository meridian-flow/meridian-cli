# Phase 3: Exit Code Mapping

**Fixes:** #7 (exit code mapping broken)
**Design doc:** [resolver-and-errors.md](../design/resolver-and-errors.md) §Exit Code Mapping
**Risk:** Very low — adds a method, changes one line in main.rs

## Scope and Intent

Add `exit_code()` method on `MarsError` with exhaustive match (no wildcard). Change `main.rs` from hardcoded `exit(3)` to `exit(e.exit_code())`. Also add `InvalidRequest` and `FrozenViolation` error variants needed by phase 4.

## Files to Modify

- **`src/error.rs`** — Add `MarsError::InvalidRequest`, `MarsError::FrozenViolation`, `MarsError::LockedCommitUnreachable` variants. Add `exit_code()` method with exhaustive match.
- **`src/main.rs`** — Change `3` → `e.exit_code()` in the error path.

## Dependencies

- **Requires:** Nothing — independent.
- **Produces:** Error variants that phases 4 and 5 use. `exit_code()` method.
- **Independent of:** Phases 1, 2.

## Interface Contract

```rust
// src/error.rs additions

impl MarsError {
    pub fn exit_code(&self) -> i32 {
        match self {
            MarsError::Conflict { .. } => 1,
            MarsError::Config(_) | MarsError::Lock(_) | MarsError::Resolution(_)
            | MarsError::Validation(_) | MarsError::Collision { .. }
            | MarsError::InvalidRequest { .. } | MarsError::FrozenViolation { .. }
            | MarsError::LockedCommitUnreachable { .. } => 2,
            MarsError::Source { .. } | MarsError::Io(_) | MarsError::Git(_) => 3,
        }
    }
}
```

## Verification Criteria

- [ ] `cargo test` — all 281 existing tests pass
- [ ] New unit test: each `MarsError` variant returns correct exit code
- [ ] `cargo clippy -- -D warnings` — clean
- [ ] No wildcard arm in `exit_code()` match

## Agent Staffing

- **Implementer:** `coder` (quick, straightforward)
- **Tester:** `verifier`
