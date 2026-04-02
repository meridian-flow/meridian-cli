# Phase 5: Simplify CLI Dispatch (F21)

## Scope
Collapse 13 identical `find_agents_root()` stanzas into one call site.

## Files to Modify
- `src/cli/mod.rs` — refactor `dispatch_result()`, add `dispatch_with_root()`

## Dependencies
- Independent of all other phases

## Implementation Notes

Replace `dispatch_result()` with:
```rust
fn dispatch_result(cli: Cli) -> Result<i32, MarsError> {
    match &cli.command {
        Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
        Command::Check(args) => check::run(args, cli.json),
        cmd => {
            let ctx = find_agents_root(cli.root.as_deref())?;
            dispatch_with_root(cmd, &ctx, cli.json)
        }
    }
}

fn dispatch_with_root(cmd: &Command, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
    match cmd {
        Command::Add(args) => add::run(args, ctx, json),
        Command::Remove(args) => remove::run(args, ctx, json),
        Command::Sync(args) => sync::run(args, ctx, json),
        Command::Upgrade(args) => upgrade::run(args, ctx, json),
        Command::Outdated(args) => outdated::run(args, ctx, json),
        Command::List(args) => list::run(args, ctx, json),
        Command::Why(args) => why::run(args, ctx, json),
        Command::Rename(args) => rename::run(args, ctx, json),
        Command::Resolve(args) => resolve_cmd::run(args, ctx, json),
        Command::Override(args) => override_cmd::run(args, ctx, json),
        Command::Link(args) => link::run(args, ctx, json),
        Command::Doctor(args) => doctor::run(args, ctx, json),
        Command::Repair(args) => repair::run(args, ctx, json),
        Command::Init(_) | Command::Check(_) => unreachable!(),
    }
}
```

No test changes needed — existing integration tests exercise the same paths.

## Verification Criteria
- [ ] `cargo test` passes
- [ ] `cargo clippy --all-targets --all-features` clean
- [ ] `find_agents_root()` called exactly once in dispatch (in the `cmd =>` arm)
