# Local Package Sync (R3)

## Problem

A project like meridian-channel is both a **package** (has `agents/`, `skills/` at repo root) and a **consumer** (pulls external packages via `[dependencies]`). The harness only reads from `.agents/`, so the project's own agents/skills are invisible unless manually copied.

Goal: `mars sync` should make local package items visible in `.agents/` via symlinks, so edits to the source files are immediately reflected without re-syncing.

## Design: Synthetic `_self` Source

**Decision: Local package items are injected as a synthetic source during sync, not stored in `[dependencies]`.**

### Why Not a User-Visible Source?

Considered: add `[dependencies._self]` or `[sources.self] path = "."` to `mars.toml`. Rejected because:

1. **Circular reference** — the project's `mars.toml` would reference itself as a source. The resolver would try to read the manifest of "." and find... the same `mars.toml`, creating a confusing loop.
2. **User confusion** — users would see `_self` in `mars list` alongside real sources, wonder what it is, and potentially try to remove/modify it.
3. **Not really a "source"** — external sources are fetched, cached, version-locked. Local items are just... already here. Different lifecycle entirely.

### Reserved Name

`_self` is reserved — validate in `config::merge()` that no user source is named `_self`. Error:
```
source name `_self` is reserved for local package items
```

## How It Works

### Discovery

`discover_local_items(project_root: &Path) -> Result<Vec<LocalItem>>`

Scans:
- `project_root/agents/*.md` → agent items
- `project_root/skills/*/` (directories containing `SKILL.md`) → skill items

Returns `LocalItem` structs (not `TargetItem` — these bypass the normal pipeline):

```rust
struct LocalItem {
    kind: ItemKind,
    name: ItemName,
    /// Absolute path to the source — for agents, the .md file; for skills, the directory.
    source_path: PathBuf,
    /// Relative destination under managed root — e.g., "agents/my-agent.md" or "skills/my-skill"
    dest_rel: DestPath,
    /// Content hash of source (agents: file hash; skills: hash of SKILL.md)
    source_hash: ContentHash,
}
```

### Symlink Granularity

**Agents: file-level symlinks.** `.agents/agents/my-agent.md → ../../agents/my-agent.md`

**Skills: directory-level symlinks.** `.agents/skills/my-skill/ → ../../skills/my-skill/`

Skills are directories, not single files — they can contain `SKILL.md` plus `resources/` subdirectories with additional files. File-level symlinks would miss `resources/`. Directory-level symlinks capture everything and remain live.

### Pipeline: Bypass Diff/Plan, Direct to Apply

**Decision: `_self` items bypass the diff engine and plan entirely.** They are injected as `PlannedAction::Symlink` directly into the plan after the normal plan is built.

Why bypass:
- The diff engine compares source hashes against lock hashes to detect changes. For symlinks, the content is always live — there's no meaningful "has this changed since install?" question. The symlink either exists and points to the right place, or it needs to be (re)created.
- Routing through the diff engine would require special-casing `_self` in `diff::compute`, `plan::create`, and `target::build_with_collisions` — three touch points instead of one.

### Pipeline Integration (in `sync::execute`)

After step 13 (create plan) and before step 14 (frozen gate):

```rust
// Step 13b: Inject local package symlinks into plan
if config.package.is_some() {
    let self_items = discover_local_items(&ctx.project_root)?;
    let managed = &ctx.managed_root;
    for item in &self_items {
        let dest = managed.join(&item.dest_rel);
        let needs_update = match dest.symlink_metadata() {
            Ok(meta) if meta.file_type().is_symlink() => {
                // Check if symlink points to the right place
                let current_target = std::fs::read_link(&dest).ok();
                let expected = relative_symlink_path(&dest, &item.source_path);
                current_target.as_deref() != Some(expected.as_path())
            }
            Ok(_) => true,   // exists but is not a symlink — replace
            Err(_) => true,  // doesn't exist — create
        };
        if needs_update {
            plan.actions.push(PlannedAction::Symlink {
                source_abs: item.source_path.clone(),
                dest_rel: item.dest_rel.clone(),
                kind: item.kind,
                name: item.name.clone(),
            });
        }
    }
}
```

### Lock File Tracking

Local items ARE tracked in `mars.lock` under source name `_self`. This is needed for:
1. **Pruning**: when `[package]` is removed or items are deleted, lock entries with `source = "_self"` that aren't in the new `self_items` list become orphans → `PlannedAction::Remove`
2. **`mars list` / `mars why`**: provenance display for local items

Lock entries use the **actual content hash** (computed by `discover_local_items`):
- Agents: `hash::compute_hash(agent_file_path)`
- Skills: `hash::compute_hash(skill_dir/SKILL.md)` (SKILL.md is the canonical content)

After apply, update the lock file with `_self` entries. The `lock::build` function needs a post-loop step: after building sources from `graph.nodes`, insert a synthetic `LockedSource { path: Some("."), version: None, commit: None }` for `_self` if any `_self` items exist, and add the corresponding `LockedItem` entries.

### Apply: `PlannedAction::Symlink`

```rust
PlannedAction::Symlink {
    source_abs: PathBuf,  // absolute path to source file/dir
    dest_rel: DestPath,   // relative path under managed root
    kind: ItemKind,
    name: ItemName,
}
```

`apply::execute_action` for `Symlink`:
1. `dest = managed_root.join(&dest_rel)`
2. Create parent dirs: `std::fs::create_dir_all(dest.parent())`
3. Remove existing at dest (file, dir, or symlink): `if dest.exists() || is_symlink(&dest) { remove(dest) }`
4. Compute relative symlink: `relative_symlink_path(&dest, &source_abs)`
5. `std::os::unix::fs::symlink(relative, &dest)`

For `--dry-run`: report as `ActionTaken::Symlinked` (new variant) without touching disk.
For `--frozen`: `PlannedAction::Symlink` entries count as changes → frozen violation. This is correct — if the managed dir was wiped, `--frozen` should fail.

### Collision Handling

`_self` items are injected AFTER `build_with_collisions` returns — `build_with_collisions` signature doesn't change. Collision check happens during symlink injection:

```rust
for item in &self_items {
    if target_state.items.contains_key(&item.dest_rel) {
        let existing = &target_state.items[&item.dest_rel];
        eprintln!("warning: local {} `{}` shadows source `{}` {} `{}`",
            item.kind, item.name, existing.source_name, existing.kind, existing.name);
        // Remove the external item from target state — local wins
        target_state.items.remove(&item.dest_rel);
    }
}
```

### Symlink Path Computation

Use **relative symlinks**:

```rust
fn relative_symlink_path(symlink_location: &Path, target: &Path) -> PathBuf {
    // symlink_location = /repo/.agents/agents/my-agent.md
    // target = /repo/agents/my-agent.md
    // result = ../../agents/my-agent.md
    let from_dir = symlink_location.parent().unwrap();
    pathdiff::diff_paths(target, from_dir).unwrap()
}
```

Add `pathdiff` to `Cargo.toml` dependencies, or inline the ~10-line implementation.

### Example

```
# Project structure
mars.toml          # has [package] + [dependencies]
agents/
  my-agent.md
skills/
  my-skill/
    SKILL.md
    resources/
      advanced.md
.agents/            # after mars sync
  agents/
    my-agent.md    → ../../agents/my-agent.md  (file symlink)
    coder.md       (copied from source "base")
  skills/
    my-skill/      → ../../skills/my-skill/     (directory symlink)
    review/
      SKILL.md     (copied from source "base")
```

### Cleanup

When `[package]` is removed from `mars.toml`, `discover_local_items` returns empty. Lock entries with `source = "_self"` become orphans → `PlannedAction::Remove` prunes the symlinks. Clean lifecycle.
