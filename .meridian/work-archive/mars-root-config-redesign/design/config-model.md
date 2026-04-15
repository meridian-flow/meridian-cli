# Config Model

## Consumer Detection

**Decision: `[dependencies]` key is the sole consumer marker.**

The `INIT_MARKER` comment (`# created by mars init`) is dead on arrival — it doesn't survive `config::save()` because serde doesn't preserve TOML comments. Any `load → mutate → save` cycle (which `mars add`, `mars link`, etc. all do) silently strips it. Two detection paths (marker OR `[dependencies]` in `is_consumer_config`, marker AND `[dependencies]` in `ensure_consumer_config`) already diverge.

Replace with: a `mars.toml` is a consumer config if and only if it contains a `[dependencies]` table (empty or populated). `mars init` creates `[dependencies] = {}` — that IS the initialization marker, and it survives serialization.

### Changes

- **Delete `INIT_MARKER` constant** from `cli/mod.rs`
- **Simplify `is_consumer_config`**: parse TOML, check `table.contains_key("dependencies")`. No comment scanning.
- **Simplify `ensure_consumer_config`**: if file doesn't exist, write `[dependencies]\n`. If file exists with `[dependencies]`, return `Ok(true)`. If file exists WITHOUT `[dependencies]`, check for `[package]` — see next section.

## Package Manifest Protection

**Decision: `mars init` refuses to silently mutate package-only manifests.**

Running `mars init` in a package repo with only `[package]` currently injects `[dependencies]` via lossy TOML roundtrip (strips comments, reorders keys). This is surprising and destructive.

New behavior:
- If `mars.toml` exists with `[package]` but no `[dependencies]`: **error** with message:
  ```
  mars.toml contains [package] but no [dependencies]. To use this as both a package
  and a consumer, add [dependencies] manually. Running `mars init` won't modify an
  existing package manifest.
  ```
- If `mars.toml` exists with `[dependencies]` (with or without `[package]`): already initialized, return `Ok(true)`.
- If `mars.toml` doesn't exist: create with `[dependencies]\n`, return `Ok(false)`.

This means a project that wants BOTH `[package]` and `[dependencies]` must add `[dependencies]` intentionally — either by hand or by starting with `mars init` first, then adding `[package]` later. This is the right UX because the dual-role config is an advanced use case.

## Settings: Managed Root Persistence

**Decision: Add `managed_root` to `[settings]`.**

```toml
[settings]
managed_root = ".claude"  # optional, default: ".agents"
links = [".cursor"]
```

The `Settings` struct gains:

```rust
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct Settings {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub managed_root: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub links: Vec<String>,
}
```

### How It's Used

1. `mars init <target>` writes `settings.managed_root = "<target>"` when target ≠ `.agents` (the default is omitted for cleanliness).
2. `MarsContext::new()` reads `settings.managed_root` from `mars.toml` before calling `detect_managed_root()`. If set, it's authoritative — no heuristic scanning needed.
3. `detect_managed_root()` becomes the fallback only when `settings.managed_root` is `None` (backwards compat for projects that didn't set it).

### Why Not Drop Custom Target Support?

Custom targets matter for tool-specific directories (`.claude/`, `.cursor/`) where the harness reads from a non-`.agents` path. Dropping support would force users into a symlink workflow for something that should just work.

## `[dependencies]` vs `[dependencies]` — Kept Separate

**Decision: `[dependencies]` and `[dependencies]` remain distinct sections.**

- `[dependencies]` = package manifest concern. "This package depends on these other packages for resolution." Used by the resolver when this package is consumed by others. Think `Cargo.toml [dependencies]`.
- `[dependencies]` = consumer concern. "Install these packages into my managed directory." Used by `mars sync` to materialize files. Think `package.json dependencies` in an app (not a library).

A project can have both when it's a package that also consumes packages (e.g., meridian-channel has `[package]` defining its own agents AND `[dependencies]` pulling in external agents).

Unifying them would conflate "what I export" with "what I install locally" — these are different things with different semantics (version constraints vs concrete sources, transitive resolution vs flat installation).
