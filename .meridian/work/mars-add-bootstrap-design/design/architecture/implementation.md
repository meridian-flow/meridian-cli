# Architecture: mars add Bootstrap

## Target Repository

`mars-agents` — all changes land in the mars CLI. No meridian changes required unless doc updates reference the new behavior.

## Design Decision: Centralized Auto-Bootstrap

### Rejected: Per-command bootstrap

Each command that requires context (`add`, `sync`, `upgrade`, etc.) could independently check for missing config and bootstrap. This leads to duplication and inconsistent behavior across commands.

### Chosen: Bootstrap in `find_agents_root`

The `find_agents_root` function (in `src/cli/mod.rs`) is the single entry point for context-requiring commands. Bootstrap logic belongs here.

**Tradeoff**: This couples bootstrap to root discovery. If a command wants to require explicit init (e.g., a hypothetical `mars check-config`), it would need a different code path. Acceptable for now; extract if needed.

## Implementation Shape

### Modified: `find_agents_root` (src/cli/mod.rs)

Current flow:
1. If `--root` provided, validate `mars.toml` exists there → error if missing
2. Else walk up from cwd to `.git` boundary looking for `mars.toml`
3. Error if not found

New flow:
1. If `--root` provided:
   - If `mars.toml` exists, use it
   - Else bootstrap at `--root` (create `mars.toml` + `.agents/`)
2. Else walk up from cwd:
   - If `mars.toml` found, use it
   - Else if `.git` found (git root located), bootstrap there
   - Else error (no git repo)
3. Return `MarsContext` with optional `bootstrapped: bool` flag (for messaging)

### New: `bootstrap_project` helper

```rust
fn bootstrap_project(project_root: &Path) -> Result<(), MarsError> {
    let config_path = project_root.join("mars.toml");
    crate::fs::atomic_write(&config_path, b"[dependencies]\n")?;
    let managed_root = project_root.join(".agents");
    std::fs::create_dir_all(&managed_root)?;
    std::fs::create_dir_all(project_root.join(".mars"))?;
    Ok(())
}
```

This is factored out from `init.rs:ensure_consumer_config` to share logic.

### Modified: Command output

Commands that trigger bootstrap should print the init message before their normal output. This requires threading the `bootstrapped` signal from `find_agents_root` to the command handler.

Options:
1. **Return tuple** — `find_agents_root` returns `(MarsContext, bool)` where bool is `bootstrapped`
2. **Context field** — Add `MarsContext::bootstrapped: bool` field
3. **Environment side-effect** — Print from `find_agents_root`, no return value change

Recommendation: **Option 2** — `MarsContext::bootstrapped` field. Commands can check it to emit the init message. Keeps the API clean and testable.

## File Changes

| File | Change |
|------|--------|
| `src/cli/mod.rs` | Add bootstrap logic to `find_agents_root`, add `bootstrapped` to `MarsContext` |
| `src/cli/add.rs` | Check `ctx.bootstrapped` and print init message if true |
| `src/cli/sync.rs` | (Optional) Same bootstrap message handling |
| `src/types.rs` | Add `bootstrapped: bool` to `MarsContext` struct |

## Edge Cases

### Nested git repos (submodules)

The current `find_agents_root_from` stops at the first `.git` encountered (line 337). This is correct — submodules have `.git` (file or directory) at their root. Bootstrap will target the innermost git boundary.

### Permission errors

If `mars.toml` cannot be written (permissions, read-only filesystem), the error surfaces naturally from `atomic_write`. No special handling needed.

### Race with concurrent `mars add`

Two `mars add` commands running simultaneously in the same uninitialized repo:
- Both detect missing `mars.toml`
- Both attempt `atomic_write`
- First one wins (atomic rename)
- Second one reads the just-created file

This is correct. `atomic_write` uses tmp+rename, and the add logic is idempotent.

### Existing `.agents/` directory without `mars.toml`

If `.agents/` exists but `mars.toml` does not, bootstrap creates `mars.toml` and leaves `.agents/` as-is. This covers repos that have manually created `.agents/` or migrated from legacy systems.

## Testing Strategy

### Unit tests (src/cli/mod.rs)

1. `bootstrap_on_missing_config_in_git_repo` — walk-up finds `.git`, no `mars.toml`, bootstrap succeeds
2. `bootstrap_on_explicit_root_without_config` — `--root /path` with no `mars.toml`, bootstrap succeeds
3. `no_bootstrap_outside_git` — no `.git` found, error returned
4. `existing_config_not_overwritten` — `mars.toml` exists, `bootstrapped` is false, content unchanged
5. `submodule_boundary_respected` — inner `.git` file present, bootstrap at submodule root

### Smoke tests

1. Fresh git repo → `mars add owner/repo` → creates `mars.toml`, adds dependency, syncs
2. Fresh git repo → `mars add owner/repo --root .` → same behavior
3. Non-git directory → `mars add owner/repo` → error with hint
4. Already-initialized project → `mars add another/dep` → no init message, dependency added

## Migration / Compatibility

### Behavioral change

Previously: `mars add` in uninitialized project → error
Now: `mars add` in uninitialized project → auto-init + add

This is additive, not breaking. No existing workflows depend on the error.

### Documentation updates

| Doc | Change |
|-----|--------|
| `mars-agents/docs/troubleshooting.md` | Update "no mars.toml found" section to note auto-bootstrap |
| `meridian-cli/docs/getting-started.md` | Simplify first-use flow — `mars add` works directly |
| `meridian-cli/docs/commands.md` | Note that `mars add` bootstraps if needed |

## Alternatives Considered

### Require `--init` flag for bootstrap

Adds explicit control but defeats the purpose of reducing friction. If the user wanted explicit init, they would run `mars init`. Rejected.

### Prompt before bootstrap

Adds ceremony that slows down scripts and spawns. The safety rules (git boundary, explicit --root) are strict enough to prevent accidents. Rejected.

### Bootstrap at cwd outside git

Would allow `mars add` to work in any directory. Too dangerous — creates config in arbitrary locations. The git boundary is a reasonable safety bar.
