# Auto-extracted Report

Here is the full review report — `meridian report create` is unavailable, so providing as the final output per fallback instructions.

---

# Review: mars root config migration (mars-root-config-diff.patch)

## Overall Assessment

This is a well-conceived architectural refactor. Moving `mars.toml`/`mars.lock` to the project root (like `Cargo.toml`/`Cargo.lock`) is the right design, and the implementation is internally thorough — every call site is consistently updated, `is_consumer_config()` is clean, and the `.git`-boundary walk-up stop is an improvement over the old "walk to /" behavior.

**But this is an unannounced hard break for existing users with zero migration support.** Someone who ran `mars init` last week and has `.agents/mars.toml` will hit a cryptic error on upgrade with no automated recovery path and no error message that explains what happened. That needs resolution before shipping.

---

## Critical (Blocking)

### 1. No migration path for existing `.agents/mars.toml` users

**What happens:** The old `find_agents_root` walked *subdirectories* (`WELL_KNOWN + TOOL_DIRS`) at each level, checking `.agents/mars.toml` and `.claude/mars.toml`. The new `find_agents_root` walks *up* checking `dir/mars.toml` directly. It **never checks subdirectories**. So any existing user's `.agents/mars.toml` is invisible after upgrading. They get:

```
no consumer mars.toml found from <cwd> up to repository root. Run `mars init` first.
```

If they follow that advice, `mars init` creates a **fresh** `mars.toml` at the project root with empty `[sources]`, silently abandoning all configured sources. The old `.agents/mars.toml` is left as dead weight with no notice.

**Fix:** In `find_agents_root`, before the walk-up loop fails, check for `.agents/mars.toml` and `.claude/mars.toml` and emit a specific error:

```
Found legacy config at .agents/mars.toml.
Config files have moved to the project root — run `mars migrate` to relocate.
```

Ideally add `mars migrate` that moves `.agents/mars.toml` → `./mars.toml` and `.agents/mars.lock` → `./mars.lock`.

---

### 2. `mars.lock` orphaned — first sync after upgrade breaks existing installs

**What happens:** The lock file moves from `.agents/mars.lock` to `mars.lock`. After upgrading (assuming the user also migrates `mars.toml`), the first `mars sync` calls `crate::lock::load(&ctx.project_root)`. That file doesn't exist, so `load()` returns an empty `LockFile`.

With an empty old lock, `check_unmanaged_collisions` treats every existing managed file (`.agents/agents/coder.md`, etc.) as unmanaged. Depending on implementation, this either errors on every file with collision warnings, or silently clobbers them. Either outcome is wrong — the user's existing installation is in an unrecoverable state.

**Fix:** During migration (or at startup), detect `.agents/mars.lock` when `project_root/mars.lock` is absent and either copy it automatically or direct the user to `mars migrate`.

---

### 3. `--root` flag semantics changed without compatibility layer

**Old behavior:** `--root .agents` → managed directory containing `mars.toml`.  
**New behavior:** `--root .` → project root containing `mars.toml`.

Any CI script, Makefile, or wrapper passing `--root .agents` now gets:

```
.agents does not contain a consumer mars.toml config.
A file with only [package] is a package manifest; run `mars init` to add [sources].
```

This is actively misleading — `.agents` typically has *no* `mars.toml` now, not a manifest-only one. **Meridian's `meridian mars` invocations are likely affected** if any of them pass an explicit `--root .agents`.

**Fix:** Detect when `--root <path>` has no `mars.toml` at the path but *does* have a `mars.toml` one level up, and emit: "Did you mean `--root <parent>`? The `--root` flag now takes the project root, not the managed directory."

---

## High

### 4. `mars.local.toml` also moved — dev overrides silently abandoned

`load_local` now reads from `project_root` instead of `managed_root`. Existing dev override files at `.agents/mars.local.toml` are silently ignored after upgrade with no error or warning. Since `mars.local.toml` is gitignored by convention, this can't be detected from the repo — each developer would independently notice their overrides stopped working.

---

### 5. `mars.local.toml` not gitignored at project root

`mars init` calls `add_to_gitignore(&managed_root)`, which only writes `.mars/` into `.agents/.gitignore`. The `mars.local.toml` now lives at the **project root** and needs an entry in the project root's `.gitignore`. Nothing in the new `init` flow adds it.

Consequence: a developer runs `mars override base /local/path`, `mars.local.toml` gets written at the project root, `git status` shows it untracked, and it gets accidentally committed — exposing local filesystem paths.

**Fix:** In `ensure_consumer_config` or `run`, append `mars.local.toml` to the project root's `.gitignore` (create or append, same pattern as `add_to_gitignore`).

---

### 6. Walk-up behavior completely untested

`find_root_walks_up` was deleted and not replaced. The new walk-up logic (which is the default code path for *every command* that doesn't pass `--root`) has zero test coverage:

- Walking 2 levels up to find `mars.toml` — untested
- Stopping at a `.git` boundary — untested
- Skipping a non-consumer (package-only) `mars.toml` mid-walk — untested
- Walking up from inside a subdirectory — untested

The only tests exercise the `explicit` root path and `MarsContext::new`. This is a significant regression in test coverage for the most common usage pattern.

---

## Medium

### 7. `ensure_consumer_config` strips TOML comments

When upgrading a `[package]`-only `mars.toml` (adding `[sources]`), the code round-trips through `toml::Value` + `toml::to_string_pretty`. TOML's Rust implementation doesn't preserve comments. A user who had a carefully-commented `mars.toml` would silently lose all comments on the first `mars init`. Low blast radius today (the `[package]`-only format is new), but establishes a bad precedent for future upgrades.

---

### 8. `detect_managed_root` path comparison is unresolved

`project_root.join(subdir)` produces an unresolved path. `read_dir` entries are also unresolved paths. The equality check `marked_roots.iter().any(|p| p == &candidate)` works for simple cases but can fail when `.claude` is a relative symlink or when `project_root` itself wasn't canonicalized. The managed root detection already has a known fragility here; it's worth adding a comment at minimum.

---

## Verdict: Request Changes

The architecture is sound and the implementation is internally consistent. Before shipping, three things are blocking:

1. **Detect legacy `.agents/mars.toml`** and emit a clear migration error (or auto-migrate via `mars migrate`)
2. **Handle the lock file relocation** — detect `.agents/mars.lock` when project `mars.lock` is absent
3. **Clarify `--root` semantics** in the error path for users passing the old managed-dir form

Also fix in the same PR: `mars.local.toml` gitignore gap (#5, one-liner) and walk-up test coverage (#6, required for confidence in the core discovery path).
