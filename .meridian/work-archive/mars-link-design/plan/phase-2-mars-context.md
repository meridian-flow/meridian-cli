# Phase 2: MarsContext Struct & Command Migration

**Design refs**: [root-context.md](../design/root-context.md)

## Scope

Introduce `MarsContext` struct and migrate all commands from `root: &Path` to `ctx: &MarsContext`. This is a mechanical refactor — no behavior changes, just replacing the parameter type and adjusting field access.

## Files to Modify

- `src/cli/mod.rs` — Define `MarsContext`, update `find_agents_root` return type, update `dispatch_result`
- `src/cli/link.rs` — `run()` signature: `root: &Path` → `ctx: &MarsContext`
- `src/cli/init.rs` — No change to run signature (init constructs its own context)
- `src/cli/add.rs` — `run()` signature change
- `src/cli/remove.rs` — `run()` signature change
- `src/cli/sync.rs` — `run()` signature change
- `src/cli/upgrade.rs` — `run()` signature change
- `src/cli/outdated.rs` — `run()` signature change
- `src/cli/list.rs` — `run()` signature change
- `src/cli/why.rs` — `run()` signature change
- `src/cli/rename.rs` — `run()` signature change
- `src/cli/resolve_cmd.rs` — `run()` signature change
- `src/cli/override_cmd.rs` — `run()` signature change
- `src/cli/doctor.rs` — `run()` signature change
- `src/cli/repair.rs` — `run()` signature change

## Interface Contract

```rust
// src/cli/mod.rs
pub struct MarsContext {
    pub managed_root: PathBuf,
    pub project_root: PathBuf,
}

impl MarsContext {
    pub fn new(managed_root: PathBuf) -> Result<Self, MarsError> {
        let project_root = managed_root.parent()
            .ok_or_else(|| MarsError::Config(ConfigError::Invalid {
                message: format!(
                    "managed root {} has no parent directory",
                    managed_root.display()
                ),
            }))?
            .to_path_buf();
        Ok(MarsContext { managed_root, project_root })
    }
}

// find_agents_root now returns MarsContext
pub fn find_agents_root(explicit: Option<&Path>) -> Result<MarsContext, MarsError> { ... }
```

## Migration Pattern

For most commands, the change is mechanical:

```rust
// Before:
pub fn run(args: &AddArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    // uses `root` for config loading, sync execution, etc.
}

// After:
pub fn run(args: &AddArgs, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    // replace `root` with `ctx.managed_root` everywhere
    // replace `root.parent().unwrap_or(root)` with `ctx.project_root` (if present)
}
```

In `dispatch_result`:
```rust
// Before:
Command::Add(args) => {
    let root = find_agents_root(cli.root.as_deref())?;
    add::run(args, &root, cli.json)
}

// After:
Command::Add(args) => {
    let ctx = find_agents_root(cli.root.as_deref())?;
    add::run(args, &ctx, cli.json)
}
```

### Special Case: sync/mod.rs

`sync::execute` uses `root.parent().unwrap_or(root)` at line 128. This stays as-is for now — the sync module takes `&Path` (the managed root), not `MarsContext`. The caller already passes `ctx.managed_root`. Pushing `MarsContext` into the sync module is a larger refactor and not in scope.

## Dependencies

- **Requires**: Phase 1 (uses `MarsError::Config` for the new error case)
- **Produces**: `MarsContext` struct — consumed by phases 3-5
- **Independent of**: Phases 3-5 (they can start after this completes)

## Verification Criteria

- [ ] `cargo build` succeeds with no warnings
- [ ] `cargo test` passes (all existing tests unbroken)
- [ ] Every command still works (all use `ctx.managed_root` where they used `root`)
- [ ] `sync/mod.rs:128` (`project_root` derivation) is unchanged (documented as future cleanup)
- [ ] New test: `MarsContext::new` errors on root path like `/`

## Constraints

- Do NOT change any command behavior — only parameter types
- Do NOT push MarsContext into sync module or config module (those take &Path)
- Keep all `root` → `ctx.managed_root` replacements mechanical
