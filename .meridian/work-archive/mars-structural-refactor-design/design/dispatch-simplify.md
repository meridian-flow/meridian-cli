# F21: Simplify CLI Dispatch

## Problem

`src/cli/mod.rs:152-209` has 13 near-identical stanzas:
```rust
Command::Add(args) => {
    let ctx = find_agents_root(cli.root.as_deref())?;
    add::run(args, &ctx, cli.json)
}
```

Every new command requires copy-pasting the same 3 lines. It also obscures which commands need a root and which don't.

## Design

Split into root-free and root-required paths:

```rust
fn dispatch_result(cli: Cli) -> Result<i32, MarsError> {
    match &cli.command {
        // Root-free commands
        Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
        Command::Check(args) => check::run(args, cli.json),
        // All other commands require a managed root
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
        // Init and Check handled in dispatch_result — unreachable here
        Command::Init(_) | Command::Check(_) => unreachable!(),
    }
}
```

**Benefits:**
- Root requirement is explicit in code structure (root-free vs root-required)
- `find_agents_root()` called once instead of 13 times
- Adding a new root-required command: add one match arm, not three lines
- The unreachable arms serve as documentation and catch refactoring errors
