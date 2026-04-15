# Phase 0: Crate Scaffold + CI

## Scope

Create the `mars-agents` Rust project from scratch: Cargo.toml with all dependencies, module stubs with `mod.rs` files, `main.rs` + `lib.rs` entry points, and a GitHub Actions CI workflow. The goal is a crate that compiles, has the right dependency tree, and establishes the module layout that all subsequent phases fill in.

## Why First

Everything depends on this. No coder can start without a compiling crate and module structure. This is also where dependency version choices are validated — if `threeway-merge` or `git2` has build issues, we find out here.

## Files to Create

```
mars-agents/
  Cargo.toml
  .gitignore
  .github/workflows/ci.yml
  src/
    main.rs
    lib.rs
    error.rs              # MarsError enum with all variants (empty bodies ok)
    cli/mod.rs            # Cli struct with clap derive, subcommand stubs
    config/mod.rs         # Config, SourceEntry, EffectiveConfig structs (empty impls)
    manifest/mod.rs       # Manifest, PackageInfo, DepSpec structs
    lock/mod.rs           # LockFile, LockedSource, LockedItem, ItemId, ItemKind
    source/mod.rs         # SourceFetcher trait, ResolvedRef
    resolve/mod.rs        # ResolvedGraph, ResolvedNode stubs
    sync/mod.rs           # SyncContext, SyncOptions, SyncReport stubs
    sync/target.rs        # TargetState, TargetItem stubs
    sync/diff.rs          # SyncDiff, DiffEntry stubs
    sync/plan.rs          # SyncPlan, PlannedAction stubs
    sync/apply.rs         # ApplyResult, ActionOutcome stubs
    merge/mod.rs          # MergeResult, MergeLabels stubs
    hash/mod.rs           # compute_hash stub
    discover/mod.rs       # DiscoveredItem, discover_source stub
    validate/mod.rs       # ValidationWarning, check_deps stub
    fs/mod.rs             # atomic_write, FileLock stubs
  tests/
    integration/mod.rs    # empty integration test module
```

## Cargo.toml

Use the exact dependency versions from the architecture doc:

```toml
[package]
name = "mars-agents"
version = "0.1.0"
edition = "2024"

[[bin]]
name = "mars"
path = "src/main.rs"

[dependencies]
clap = { version = "4", features = ["derive"] }
serde = { version = "1", features = ["derive"] }
toml = "0.8"
serde_yaml = "0.9"
git2 = "0.19"
sha2 = "0.10"
threeway-merge = "0.2"
semver = { version = "1", features = ["serde"] }
indexmap = { version = "2", features = ["serde"] }
thiserror = "2"
tempfile = "3"
termcolor = "1"

[dev-dependencies]
assert_fs = "1"
predicates = "3"
assert_cmd = "2"
```

**Important**: Validate that `threeway-merge = "0.2"` actually exists on crates.io. If not, find the correct crate name/version for three-way merge with git conflict markers. Alternatives to check: `diffy`, `similar`, or use `git2::merge_file` directly (git2 already has three-way merge built in). The design doc mentions both `threeway_merge` crate and `git2::merge_file()` — verify which is the right choice and document the decision.

## CI Workflow

GitHub Actions with:
- `cargo build` (compile check)
- `cargo test` (unit tests)
- `cargo clippy -- -D warnings` (lint)
- `cargo fmt --check` (formatting)
- Matrix: stable Rust, latest Rust
- Cache: `~/.cargo/registry`, `target/`

## Module Stubs

Each `mod.rs` should:
1. Define the public types from the architecture doc (structs, enums, traits)
2. Have `todo!()` or `unimplemented!()` in function bodies
3. Include `#[allow(dead_code)]` where needed to compile cleanly
4. Re-export public types in `lib.rs`

The stubs establish the interface contracts. Subsequent phases fill in implementations without changing signatures.

## `main.rs`

```rust
fn main() {
    let cli = mars_agents::cli::Cli::parse();
    let result = mars_agents::cli::dispatch(cli);
    match result {
        Ok(code) => std::process::exit(code),
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(3);
        }
    }
}
```

## Verification Criteria

- [ ] `cargo build` succeeds with no errors
- [ ] `cargo test` runs (tests may be trivial/empty but must pass)
- [ ] `cargo clippy -- -D warnings` passes
- [ ] `cargo fmt --check` passes
- [ ] All 11 modules (`cli`, `config`, `manifest`, `lock`, `source`, `resolve`, `sync`, `merge`, `hash`, `discover`, `validate`, `fs`, `error`) are declared and importable from `lib.rs`
- [ ] `cargo run -- --help` shows the CLI help text with subcommand stubs
- [ ] CI workflow file exists and would pass (verify locally with `act` if available, or just ensure the YAML is valid)

## Patterns to Follow

This is a new project — no existing patterns to match. Establish:
- `pub mod X;` declarations in `lib.rs` for each module
- `#[derive(Debug, Clone, Serialize, Deserialize)]` on all data structs
- `thiserror::Error` derive on all error enums
- `clap::Parser` derive on CLI structs

## Dependencies

- Requires: nothing (first phase)
- Produces: compiling crate with all module stubs, interface contracts for every subsequent phase

## Constraints

- Do NOT implement any business logic. Stubs only.
- Do NOT add dependencies beyond what's listed. If `threeway-merge` doesn't exist, use `git2::merge_file` and document the change.
- Rust edition 2024 (latest stable).
