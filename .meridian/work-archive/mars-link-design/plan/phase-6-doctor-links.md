# Phase 6: Doctor Link Validation

**Design refs**: [doctor-links.md](../design/doctor-links.md)

## Scope

Add link health checks to `mars doctor`. After existing checks, iterate `settings.links` and validate symlink targets, existence, and staleness.

## Files to Modify

- `src/cli/doctor.rs` — Add `check_link_health()` function and call it from `run()`

## Changes

### doctor.rs

Add after the existing agent→skill reference checks (around line 85):

```rust
// Check link health
if let Ok(config) = crate::config::load(&ctx.managed_root) {
    for link_target in &config.settings.links {
        check_link_health(ctx, link_target, &mut issues);
    }
}
```

Add `check_link_health` function:

```rust
fn check_link_health(ctx: &MarsContext, target: &str, issues: &mut Vec<String>) {
    let target_dir = ctx.project_root.join(target);

    if !target_dir.exists() {
        issues.push(format!(
            "link `{target}` — directory {} doesn't exist. \
             Run `mars link --unlink {target}` to remove stale entry.",
            target_dir.display()
        ));
        return;
    }

    for subdir in ["agents", "skills"] {
        let link_path = target_dir.join(subdir);
        let expected = ctx.managed_root.join(subdir);

        // Check if symlink exists
        if link_path.symlink_metadata().is_err() {
            issues.push(format!(
                "link `{target}` — missing {target}/{subdir} symlink. \
                 Run `mars link {target}` to fix."
            ));
            continue;
        }

        // Check if it's a symlink (not a real dir)
        match link_path.read_link() {
            Ok(actual_target) => {
                // Resolve and compare
                let resolved = target_dir.join(&actual_target);
                let resolved_canon = resolved.canonicalize().ok();
                let expected_canon = expected.canonicalize().ok();

                if resolved_canon != expected_canon {
                    issues.push(format!(
                        "link `{target}` — {target}/{subdir} points to {} (expected {})",
                        actual_target.display(),
                        expected.display()
                    ));
                } else if !link_path.exists() {
                    // Symlink exists but target is broken
                    issues.push(format!(
                        "link `{target}` — {target}/{subdir} is a broken symlink"
                    ));
                }
            }
            Err(_) => {
                // Real directory, not a symlink
                issues.push(format!(
                    "link `{target}` — {target}/{subdir} is a real directory, not a symlink. \
                     Run `mars link {target}` to merge and link."
                ));
            }
        }
    }
}
```

## Dependencies

- **Requires**: Phase 2 (MarsContext)
- **Independent of**: Phases 3-5 (doctor reads config, doesn't mutate)

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] `cargo test` passes
- [ ] Doctor with healthy links → no issues
- [ ] Doctor with missing target dir → warning with unlink hint
- [ ] Doctor with missing symlink → warning with link hint
- [ ] Doctor with foreign symlink → warning with actual vs expected paths
- [ ] Doctor with real directory instead of symlink → warning with merge hint
- [ ] Doctor with broken symlink → warning

## Agent Staffing

**Risk**: Low — straightforward validation logic, no mutations.
- **Coder**: Standard model
- **Reviewer**: 1 — quick pass
- **Verifier**: Yes
