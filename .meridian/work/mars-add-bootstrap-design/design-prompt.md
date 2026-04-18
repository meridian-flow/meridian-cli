Design the first-use bootstrap behavior for `mars add`.

Primary target: `mars-agents`.
Secondary target: only note any `meridian` follow-through needed if the underlying mars behavior changes.

Produce a design package under the work item using the standard design artifact layout.

Key design question:
- When `mars add` runs in a repo with no `mars.toml`, should it auto-create `mars.toml` and continue?

You should explore and decide:
- auto-init default vs prompt vs explicit flag
- repo root and cwd semantics
- interactive vs non-interactive behavior
- unsafe/ambiguous cases that must still error
- whether `--root` should change the bootstrap story
- migration/docs/help implications

Ground the design in the current behavior of:
- ../mars-agents/src/cli/mod.rs
- ../mars-agents/src/cli/add.rs
- ../mars-agents/docs/troubleshooting.md
- docs/getting-started.md
- docs/commands.md

The user preference is that this should probably land in `mars-agents`, and that `mars add` should create `mars.toml` when clearly needed. Treat that as a strong direction, but still surface tradeoffs and safety constraints explicitly.
