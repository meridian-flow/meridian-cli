# Init Command Redesign

## Current Problems

1. **Dot-prefix heuristic**: `path_str.starts_with('.')` misclassifies `./my-project` (relative path) and `.hidden-project/` (project root).
2. **Path vs name ambiguity**: The positional arg accepts both paths and directory names, requiring heuristic disambiguation.
3. **No link integration**: Users must run `mars init` then `mars link` separately.

## Redesigned Interface

```
mars init [TARGET] [--link DIR...] [--root DIR]
```

- **TARGET** — Simple directory name (default: `.agents`). NOT a path. No `/` allowed. Creates `<cwd>/TARGET/agents.toml`.
- **--link DIR** — After init, immediately link these directories. Repeatable.
- **--root DIR** — Global flag. When used with init, initializes at `--root` directly (TARGET is ignored).

### Examples

```bash
mars init                           # creates .agents/agents.toml
mars init .claude                   # creates .claude/agents.toml
mars init --link .claude            # creates .agents/ + links .claude/
mars init .claude --link .cursor    # creates .claude/ + links .cursor/
mars init --root /path/to/.agents   # init at explicit path
```

## Args Struct

```rust
#[derive(Debug, clap::Args)]
pub struct InitArgs {
    /// Directory name to create (default: .agents). Simple name, not a path.
    pub target: Option<String>,

    /// Directories to link after initialization. Repeatable.
    #[arg(long, value_name = "DIR")]
    pub link: Vec<String>,
}
```

TARGET changes from `Option<PathBuf>` to `Option<String>`. The type change enforces that it's a name, not a path.

## Validation

```rust
fn validate_target(target: &str) -> Result<(), MarsError> {
    if target.contains('/') || target.contains('\\') {
        return Err(MarsError::Config(ConfigError::Invalid {
            message: format!(
                "`{target}` looks like a path — TARGET should be a directory name like `.agents` or `.claude`. \
                 Use `--root` to specify an explicit path."
            ),
        }));
    }
    if target == "." || target == ".." || target.is_empty() {
        return Err(MarsError::Config(ConfigError::Invalid {
            message: format!(
                "`{target}` is not a valid target name — use a directory name like `.agents` or `.claude`."
            ),
        }));
    }
    Ok(())
}
```

## Run Logic

```rust
pub fn run(args: &InitArgs, explicit_root: Option<&Path>, json: bool) -> Result<i32, MarsError> {
    // 1. Determine the managed root
    let managed_root = if let Some(root) = explicit_root {
        // --root flag: use directly
        root.to_path_buf()
    } else {
        let target = args.target.as_deref().unwrap_or(".agents");
        validate_target(target)?;
        std::env::current_dir()?.join(target)
    };

    // 2. Idempotency check
    let config_path = managed_root.join("agents.toml");
    if config_path.exists() {
        // Already initialized — reconcile required structure
        // (.mars/ may have been deleted, .gitignore may be missing)
        std::fs::create_dir_all(managed_root.join(".mars"))?;
        add_to_gitignore(&managed_root)?;

        if !json {
            output::print_info(&format!(
                "{} already initialized",
                managed_root.display()
            ));
        }
        // Still proceed with --link flags (idempotent linking)
    } else {
        // 3. Create structure
        std::fs::create_dir_all(&managed_root)?;
        std::fs::create_dir_all(managed_root.join(".mars"))?;

        let config = Config {
            sources: IndexMap::new(),
            settings: Settings::default(),
        };
        crate::config::save(&managed_root, &config)?;
        add_to_gitignore(&managed_root)?;

        if !json {
            output::print_success(&format!(
                "initialized {} with agents.toml",
                managed_root.display()
            ));
        }
    }

    // 4. Process --link flags
    for link_target in &args.link {
        let link_args = LinkArgs {
            target: link_target.clone(),
            unlink: false,
            force: false,
        };
        let ctx = MarsContext::new(managed_root.clone())?;
        link::run(&link_args, &ctx, json)?;
    }

    if json && !config_path.exists() {
        // Only print init JSON if we didn't print above
    }

    Ok(0)
}
```

## Key Behavior Changes

| Behavior | Before | After |
|---|---|---|
| `mars init ./foo` | Heuristic: is it a path or name? | Error: "looks like a path" |
| `mars init .claude` | Heuristic: dot-prefix → target dir | Always: creates `.claude/agents.toml` |
| `mars init` when already initialized | Error | Info message + proceed with `--link` |
| `mars init --link .claude` | N/A | Init + link in one command |

## Idempotency

Running `mars init` when `.agents/agents.toml` already exists is a no-op for init but still processes `--link` flags. This is important because:
- `mars init --link .claude` should work even if `.agents/` already exists
- Re-running init after adding a new tool should just link the new tool
- Users shouldn't need to remember whether they've already initialized

## Interaction with --root

When `--root` is provided, TARGET is ignored (--root takes precedence). This matches the existing behavior where `--root` is the explicit override for auto-detection. The managed root is whatever `--root` points to — it doesn't need to be a well-known name.
