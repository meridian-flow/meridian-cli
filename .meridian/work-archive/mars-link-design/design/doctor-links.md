# Doctor Link Validation

## Current State

`doctor.rs` checks config validity, lock file integrity, and file checksums. It has no awareness of links.

## New Checks

Add a link validation section after the existing checks:

```rust
// Check link health
if let Ok(config) = crate::config::load(root) {
    for link_target in &config.settings.links {
        check_link_health(root, &ctx, link_target, &mut issues);
    }
}
```

### check_link_health

For each entry in `settings.links`:

```rust
fn check_link_health(
    root: &Path,
    ctx: &MarsContext,
    target: &str,
    issues: &mut Vec<DoctorIssue>,
) {
    let target_dir = ctx.project_root.join(target);

    // 1. Target directory exists?
    if !target_dir.exists() {
        issues.push(DoctorIssue::Warning(format!(
            "link target `{target}` — directory {} doesn't exist",
            target_dir.display()
        )));
        return;
    }

    // 2. Check each expected symlink
    for subdir in ["agents", "skills"] {
        let link_path = target_dir.join(subdir);
        let expected_target = ctx.managed_root.join(subdir);

        if !link_path.exists() && link_path.symlink_metadata().is_err() {
            // Symlink doesn't exist at all
            issues.push(DoctorIssue::Warning(format!(
                "link `{target}` — missing {target}/{subdir} symlink. Run `mars link {target}` to fix."
            )));
            continue;
        }

        match link_path.read_link() {
            Ok(actual_target) => {
                // Resolve to absolute for comparison
                let resolved = target_dir.join(&actual_target);
                if resolved.canonicalize().ok() != expected_target.canonicalize().ok() {
                    issues.push(DoctorIssue::Warning(format!(
                        "link `{target}` — {target}/{subdir} points to {} (expected {})",
                        actual_target.display(),
                        expected_target.display()
                    )));
                }
                // Also check that the symlink target actually exists (not broken)
                if !link_path.exists() {
                    issues.push(DoctorIssue::Warning(format!(
                        "link `{target}` — {target}/{subdir} is a broken symlink",
                    )));
                }
            }
            Err(_) => {
                // Not a symlink — it's a real directory
                issues.push(DoctorIssue::Warning(format!(
                    "link `{target}` — {target}/{subdir} is a real directory, not a symlink. \
                     Run `mars link {target}` to merge and link."
                )));
            }
        }
    }
}
```

### Stale Link Detection

A link entry in `settings.links` is stale when:
- The target directory doesn't exist
- Neither `agents/` nor `skills/` symlinks exist in the target dir
- The symlinks point to a different mars root

Doctor reports these as warnings with actionable hints:

```
⚠ link `.claude` — .claude/agents points to ../.other-agents/agents (expected ../.agents/agents)
⚠ link `.cursor` — directory /project/.cursor doesn't exist
  hint: run `mars link --unlink .cursor` to remove stale entry

✓ all 2 links healthy
```

### DoctorIssue Enum

Upgrade from `Vec<String>` to structured issues:

```rust
enum DoctorIssue {
    Error(String),   // exit code 2
    Warning(String), // exit code 1 (new)
    Info(String),    // exit code 0
}
```

This is a nice-to-have refinement. For v1, appending strings to the existing `Vec<String>` is fine — the structured enum can come later.

## JSON Output

```json
{
    "ok": false,
    "issues": [...],
    "links": [
        {
            "target": ".claude",
            "status": "healthy",
            "agents_symlink": "../.agents/agents",
            "skills_symlink": "../.agents/skills"
        },
        {
            "target": ".cursor",
            "status": "stale",
            "message": "directory doesn't exist"
        }
    ]
}
```
