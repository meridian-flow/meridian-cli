# F5 + F6: Help Text and Doctor Hints

## F5: Missing Skill Hints in Doctor

### Problem

When `mars doctor` reports a missing skill reference, it says:

> agent `coder` references missing skill `my-skill`

This doesn't tell the user what to do. They need to know it's a dependency they should add via a source.

### Fix

Update the missing-skill message in `doctor.rs` to include actionable guidance:

```rust
// When no fuzzy match:
None => format!(
    "agent `{}` references missing skill `{skill_name}` — \
     add a source that provides it, or create it locally in skills/{skill_name}/",
    agent.name
),
```

The fuzzy-match case (`did you mean ...?`) is already actionable — it suggests the correct name. Only the no-match case needs the hint.

## F6: Check vs Doctor Help Text

### Problem

`mars check` and `mars doctor` have similar-sounding descriptions. Users don't know when to use which.

Current:
- `check` → "Validate a source package directory (agents/ + skills/)."
- `doctor` → "Validate local installation (config, lock, files, links, deps)."

### Fix

Make the distinction explicit in the help text:

```rust
/// Validate a source package before publishing (structure, frontmatter, deps).
Check(check::CheckArgs),

/// Diagnose problems in an installed mars project (config, lock, files, links).
Doctor(doctor::DoctorArgs),
```

Key distinction: `check` validates a **source package** (pre-publish), `doctor` validates an **installed project** (post-install). The words "before publishing" and "installed" make the use case clear.

## Files to Modify

- `src/cli/doctor.rs` — missing skill hint text, ~3 lines
- `src/cli/mod.rs` — help text for `Check` and `Doctor` variants, ~2 lines

## Verification

- `cargo test` passes
- `mars check --help` and `mars doctor --help` show improved text
- `mars doctor` with a missing skill shows the new hint
