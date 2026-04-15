# Mars Root Config Redesign

## Background

Mars is a package manager for `.agents/` directories — it manages AI agent profiles and skills (markdown files with YAML frontmatter). Think npm/cargo but for agent configurations.

Mars was just released (v0.0.3, no real users yet). A coder moved consumer config (`mars.toml`, `mars.lock`) from inside `.agents/` to the repo root (like Cargo.toml). The structural direction is right but 4 reviewers found issues. We're taking this opportunity to also add missing functionality before anyone adopts it.

## Current State

The coder's diff is applied but uncommitted at `/home/jimyao/gitrepos/mars-agents/`. Key files:
- `src/cli/mod.rs` — root discovery, MarsContext
- `src/cli/init.rs` — initialization  
- `src/config/mod.rs` — config loading/saving (now includes merged manifest)
- `src/sync/mod.rs` — sync pipeline
- `src/lock/mod.rs` — lock file
- `src/resolve/mod.rs` — dependency resolution
- `tests/integration/mod.rs` — integration tests

## Requirements

### R1: Fix reviewer blocking findings

1. **Kill the init marker.** The `# created by mars init` TOML comment is fragile — doesn't survive serialization, creates confusing dual-detection logic. Consumer config = `[sources]` key exists. `mars init` creates empty `[sources]` table. That IS the marker.

2. **Gitignore `mars.local.toml` at project root.** `mars init` must add it to project root `.gitignore`, not just `.agents/.gitignore`.

3. **Canonicalize `project_root` in `MarsContext::from_roots()`.** Currently only `managed_root` is canonicalized, so `starts_with()` fails with relative paths.

4. **Don't silently mutate package manifests.** Running `mars init` in a package repo with only `[package]` should warn/refuse, not silently inject `[sources]`.

5. **Pass `&MarsContext` to sync/repair/link instead of two bare `&Path` args.** Prevents argument-ordering bugs.

### R2: Persist managed root name

`mars init custom-dir` works but the name isn't persisted. After deleting the managed dir, discovery falls back to `.agents`. Either:
- Persist managed dir name in `[settings]` in mars.toml
- Or drop custom target support entirely (just always use `.agents/`)

### R3: Local package items synced into managed dir

When a project has BOTH `[package]` (it IS a package with `agents/`, `skills/` at root) AND `[sources]` (it consumes other packages), `mars sync` should:
- **Symlink** the local package's own `agents/*.md` and `skills/*/SKILL.md` into `.agents/agents/` and `.agents/skills/`
- **Copy** dependency items from `[sources]` into `.agents/` as before
- Symlinks mean live edits — no need to re-sync when developing your own agents/skills
- The harness only reads `.agents/`, so this makes everything visible in one place

### R4: Test coverage for git boundary

The walk-up root discovery has zero tests for:
- Stopping at `.git` boundary
- Not crossing into parent repos / submodules
- Skipping package-only `mars.toml` mid-walk
- Walking up from subdirectory

## Constraints

- Breaking changes are fine — no real users yet (v0.0.3)
- The coder's existing diff is the starting point — improve it, don't start over
- Must pass `cargo test`, `cargo fmt`, `cargo clippy`
- Keep `.mars/` metadata under managed root (not project root)

## Success Criteria

- `mars init` in a fresh project creates root `mars.toml` with `[sources]`, `.agents/` dir, gitignores `mars.local.toml`
- `mars init` in a package repo with `[package]` warns instead of silently mutating
- `mars sync` in a package-that-also-consumes symlinks local items + copies dependency items into `.agents/`
- Root discovery stops at `.git`, never treats package-only manifest as consumer config
- No init marker comment anywhere
- `sync::execute` takes `&MarsContext` not two paths
