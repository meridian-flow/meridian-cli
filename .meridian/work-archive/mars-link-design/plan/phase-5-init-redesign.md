# Phase 5: Init Redesign

**Design refs**: [init.md](../design/init.md)

## Scope

Rewrite `init.rs` to use simple name-based TARGET, add `--link` flag, add idempotency. Uses MarsContext from phase 2 and link::run from phase 4.

## Files to Modify

- `src/cli/init.rs` — Rewrite `InitArgs`, `run()`, validation logic
- `src/cli/mod.rs` — Update `Command::Init` dispatch (init still gets `explicit_root` separately since it doesn't use `find_agents_root`)

## Interface Contract

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

## Changes

### init.rs

1. Change `InitArgs.path: Option<PathBuf>` to `InitArgs.target: Option<String>`

2. Add `validate_target()`:
   ```rust
   fn validate_target(target: &str) -> Result<(), MarsError> {
       if target.contains('/') || target.contains('\\') {
           return Err(MarsError::Config(ConfigError::Invalid {
               message: format!(
                   "`{target}` looks like a path — TARGET should be a directory name \
                    like `.agents` or `.claude`. Use `--root` to specify an explicit path."
               ),
           }));
       }
       Ok(())
   }
   ```

3. Rewrite `run()`:
   ```rust
   pub fn run(args: &InitArgs, explicit_root: Option<&Path>, json: bool) -> Result<i32, MarsError> {
       let managed_root = if let Some(root) = explicit_root {
           root.to_path_buf()
       } else {
           let target = args.target.as_deref().unwrap_or(".agents");
           validate_target(target)?;
           std::env::current_dir()?.join(target)
       };

       let config_path = managed_root.join("agents.toml");
       let already_initialized = config_path.exists();

       if !already_initialized {
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
       } else if !json {
           output::print_info(&format!(
               "{} already initialized",
               managed_root.display()
           ));
       }

       // Process --link flags
       if !args.link.is_empty() {
           let ctx = MarsContext::new(managed_root.clone())?;
           for link_target in &args.link {
               let link_args = super::link::LinkArgs {
                   target: link_target.clone(),
                   unlink: false,
                   force: false,
               };
               super::link::run(&link_args, &ctx, json)?;
           }
       }

       if json {
           output::print_json(&serde_json::json!({
               "ok": true,
               "path": managed_root.to_string_lossy(),
               "already_initialized": already_initialized,
               "links": args.link,
           }));
       }

       Ok(0)
   }
   ```

4. Remove `resolve_base()` function (no longer needed — we join cwd + target name directly)

5. Remove the dot-prefix heuristic logic entirely

### cli/mod.rs

The init dispatch stays the same shape — init gets `cli.root.as_deref()` instead of `MarsContext`:

```rust
Command::Init(args) => init::run(args, cli.root.as_deref(), cli.json),
```

This is correct because init creates the root rather than finding it.

## Dependencies

- **Requires**: Phase 2 (MarsContext), Phase 4 (link::run for --link integration)
- **Produces**: Complete init redesign
- **Independent of**: Phase 6 (doctor)

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] `cargo test` passes
- [ ] `mars init` creates `.agents/agents.toml`
- [ ] `mars init .claude` creates `.claude/agents.toml`
- [ ] `mars init ./foo` errors ("looks like a path")
- [ ] `mars init` when already initialized → info message, not error
- [ ] `mars init --link .claude` creates `.agents/` + links `.claude/`
- [ ] `mars init --link .claude --link .cursor` links both
- [ ] `mars init .claude --link .cursor` creates `.claude/` + links `.cursor/`
- [ ] `mars init --root /path/.agents` uses explicit path, ignores TARGET
- [ ] JSON output includes `already_initialized` field

## Agent Staffing

**Risk**: Medium — clear requirements, builds on phase 4's link implementation.
- **Coder**: Standard model
- **Reviewer**: 1 — correctness focus
- **Verifier**: Yes
