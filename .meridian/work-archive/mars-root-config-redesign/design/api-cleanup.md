# API Cleanup

## Pass `&MarsContext` to Sync/Repair/Link

**Decision: Replace `(project_root: &Path, managed_root: &Path)` pairs with `&MarsContext`.**

The two-bare-`Path` pattern is error-prone — swapping argument order compiles fine but produces subtle bugs. `MarsContext` already exists and encapsulates both paths.

### Changes

1. **`sync::execute`**: `(project_root: &Path, managed_root: &Path, request)` → `(ctx: &MarsContext, request)`
   - Internal references change: `project_root` → `ctx.project_root`, `managed_root` → `ctx.managed_root`

2. **`cli::repair::execute_repair_with_collision_cleanup`**: same pattern

3. **`cli::link::mutate_link_config`**: same pattern (if it takes both paths)

4. **All call sites**: already have a `MarsContext` in scope — pass `&ctx` instead of `&ctx.project_root, &ctx.managed_root`

5. **Test helpers**: create `MarsContext` from temp dirs. Add a test helper:
   ```rust
   #[cfg(test)]
   impl MarsContext {
       pub fn for_test(project_root: PathBuf, managed_root: PathBuf) -> Self {
           MarsContext { project_root, managed_root }
       }
   }
   ```

### Scope

Only change the public API signatures that currently take two paths. Internal functions that only need one path (e.g., `config::load(root)`) keep their signatures — they don't have the ordering ambiguity.

## Gitignore `mars.local.toml` at Project Root

### New Function

```rust
fn ensure_local_gitignored(project_root: &Path) -> Result<(), MarsError> {
    let gitignore_path = project_root.join(".gitignore");
    let entry = "mars.local.toml";
    // Same append-or-create logic as existing add_to_gitignore
}
```

Called from `init::run()` after `ensure_consumer_config()`.

### Why Not Reuse `add_to_gitignore`?

The existing function takes a managed dir and writes `.mars/`. The new function targets a different directory (project root) with a different entry. Rather than parameterize one function awkwardly, add a focused helper. The duplication is ~15 lines of straightforward file I/O — not worth abstracting.

(Alternatively, extract a generic `ensure_gitignore_entry(dir: &Path, entry: &str)` and call it from both. Either approach is fine — the coder can choose.)

## `mars link` Lock Directory

**`mars link` must create `.mars/` before acquiring the sync lock.**

Currently `link.rs` acquires `.mars/sync.lock` without ensuring `.mars/` exists. Under the new model where `.agents/` is "purely generated output" that users may delete, this fails.

Fix: `std::fs::create_dir_all(ctx.managed_root.join(".mars"))` before lock acquisition, matching what `sync::execute` already does.
