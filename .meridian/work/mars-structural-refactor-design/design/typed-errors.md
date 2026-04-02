# F17: Typed Error for Unmanaged Collisions

## Problem

`src/sync/target.rs:372-378` formats a string into `MarsError::Source`:
```rust
return Err(MarsError::Source {
    source_name: target_item.source_name.to_string(),
    message: format!(
        "refusing to overwrite unmanaged path `{}`",
        target_item.dest_path.display()
    ),
});
```

`src/cli/repair.rs:99-107` parses that string back:
```rust
fn extract_unmanaged_collision_path(err: &MarsError) -> Option<&Path> {
    let MarsError::Source { message, .. } = err else { return None; };
    let prefix = "refusing to overwrite unmanaged path `";
    let suffix = "`";
    let trimmed = message.strip_prefix(prefix)?.strip_suffix(suffix)?;
    Some(Path::new(trimmed))
}
```

If anyone changes the wording in target.rs, repair.rs silently stops recovering from unmanaged collisions. No compiler catches this.

## Design

### New Error Variant

Add to `MarsError` in `src/error.rs`:

```rust
/// Sync refused to overwrite a file/directory not tracked in mars.lock.
#[error("source error: {source_name}: refusing to overwrite unmanaged path `{}`", path.display())]
UnmanagedCollision {
    source_name: String,
    path: PathBuf,
},
```

**Exit code:** 3 (same as `MarsError::Source`). Add to the `exit_code()` match arm alongside `Source`.

**Display format:** Identical to current string — `"source error: {source_name}: refusing to overwrite unmanaged path \`{path}\`"` — so CLI output doesn't change.

### Call Sites

1. **`src/sync/target.rs` `check_unmanaged_collisions()`** — construct `MarsError::UnmanagedCollision` instead of `MarsError::Source`.

2. **`src/cli/repair.rs` `extract_unmanaged_collision_path()`** — match on the typed variant:
   ```rust
   fn extract_unmanaged_collision_path(err: &MarsError) -> Option<&Path> {
       match err {
           MarsError::UnmanagedCollision { path, .. } => Some(path.as_path()),
           _ => None,
       }
   }
   ```

### Audit: Other String-Encoded Semantics

Searched all `MarsError::Source` construction sites for cases where the message encodes structured data that's later parsed:

| Location | Message pattern | Parsed elsewhere? |
|---|---|---|
| `src/sync/target.rs:372` | `"refusing to overwrite unmanaged path \`{}\`"` | **Yes** — repair.rs. **FIX THIS.** |
| `src/source/*.rs` | Various fetch/git errors | No — displayed to user only |

No other string-encoded semantic patterns found. `MarsError::Source` is otherwise used correctly as a display-only error bag for source fetch failures.
