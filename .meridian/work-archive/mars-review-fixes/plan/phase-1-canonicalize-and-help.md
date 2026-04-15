# Phase 1: Canonicalize Fix + Help Text (F4, F5, F6)

Tier 1 fixes — small, independent, low risk.

## Scope

Three changes in one phase because each is <10 lines and they touch different code paths with no interaction.

## Files to Modify

### F4: `src/cli/doctor.rs` — `check_link_health()`

Replace the `Option` comparison with `match` on `Result`:

```rust
// Lines ~145-150, replace:
let resolved_canon = resolved.canonicalize().ok();
let expected_canon = expected.canonicalize().ok();
if resolved_canon != expected_canon {

// With:
let points_to_managed = match (resolved.canonicalize(), expected.canonicalize()) {
    (Ok(a), Ok(b)) => a == b,
    _ => false,
};
if !points_to_managed {
```

### F5: `src/cli/doctor.rs` — missing skill hint

In the `MissingSkill` match arm (around line ~115), update the `None` suggestion case:

```rust
None => format!(
    "agent `{}` references missing skill `{skill_name}` — \
     add a source that provides it, or create it locally in skills/{skill_name}/",
    agent.name
),
```

### F6: `src/cli/mod.rs` — help text

Update the doc comments on the `Check` and `Doctor` enum variants:

```rust
/// Validate a source package before publishing (structure, frontmatter, deps).
Check(check::CheckArgs),

/// Diagnose problems in an installed mars project (config, lock, files, links).
Doctor(doctor::DoctorArgs),
```

## Dependencies

None — this phase can run first.

## Verification Criteria

- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] `mars doctor --help` shows updated description
- [ ] `mars check --help` shows updated description
