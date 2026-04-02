# Error Model

## Problem

All error paths in `link.rs` use `MarsError::Source { source_name: "link".to_string(), ... }`. The `Source` variant semantically means "error related to a package source" — link operations are not source operations.

## New MarsError Variant

```rust
pub enum MarsError {
    // ... existing variants ...

    /// Link operation error — conflict, missing target, bad symlink.
    #[error("link error: {target}: {message}")]
    Link {
        target: String,
        message: String,
    },
}
```

### Exit Code

Link errors map to exit code 2 (same category as config/validation errors — user-actionable).

```rust
impl MarsError {
    pub fn exit_code(&self) -> i32 {
        match self {
            MarsError::Link { .. } => 2,
            // ... existing arms ...
        }
    }
}
```

### Conflict Error

For the specific case of conflicts preventing linking, a richer error is useful:

```rust
/// All conflicts found during link scan, with details.
pub struct LinkConflicts {
    pub target: String,
    pub conflicts: Vec<ConflictInfo>,
}

pub struct ConflictInfo {
    pub relative_path: String,
    pub target_hash: String,
    pub managed_hash: String,
}

impl std::fmt::Display for LinkConflicts {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "cannot link {} — {} conflict(s) found:", self.target, self.conflicts.len())?;
        for c in &self.conflicts {
            writeln!(f, "  {}", c.relative_path)?;
        }
        Ok(())
    }
}
```

This struct is used internally by the link command for detailed error output. The `MarsError::Link` variant carries the summary; the structured conflict data is printed to stderr before the error propagates.

## Init Errors

Init also stops misusing `MarsError::Source`:

```rust
// Before
Err(MarsError::Source {
    source_name: "init".to_string(),
    message: "already exists".to_string(),
})

// After — use Config variant (init is about config/setup)
Err(MarsError::Config(ConfigError::Invalid {
    message: "already exists".to_string(),
}))
```

For init, `ConfigError::Invalid` is the right semantic — init failures are config/setup problems. No new variant needed.

## Root Detection Errors

Root detection currently uses `MarsError::Source { source_name: "root" }`. This should also use `ConfigError`:

```rust
// Before
Err(MarsError::Source {
    source_name: "root".to_string(),
    message: "no agents.toml found...".to_string(),
})

// After
Err(MarsError::Config(ConfigError::Invalid {
    message: "no agents.toml found from...".to_string(),
}))
```

## Summary of Error Variant Usage

| Command | Error variant | When |
|---|---|---|
| link (conflicts) | `MarsError::Link` | Conflicts detected, foreign symlinks |
| link (IO) | `MarsError::Io` | Filesystem operations fail |
| init (setup) | `MarsError::Config(ConfigError::Invalid)` | Invalid target, already exists |
| root detection | `MarsError::Config(ConfigError::Invalid)` | No root found |
| config save | `MarsError::Config(ConfigError::Io)` | Write failures |
