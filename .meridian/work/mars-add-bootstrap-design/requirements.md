# Requirements: Walk-Up Add, Explicit Init

## Problem

`mars add <source>` fails when `mars.toml` does not already exist with a message directing users to run `mars init`. This is correct behavior. The current design proposal (cwd-first auto-init) diverges from mainstream tooling semantics and creates surprising nested-project behavior.

## User Intent

When a user runs `mars add` in a repository:
- If a `mars.toml` exists in the current directory or any ancestor, the system should use that project
- If no `mars.toml` exists anywhere up to filesystem root, the system should fail and direct the user to `mars init`

When a user runs `mars init`:
- The system should create a project at cwd (or `--root` if specified)
- The system should NOT search for or adopt ancestor projects

## Design Direction

**Walk-up for add, explicit init for create**: This matches `uv add`, `cargo add`, and npm local project resolution semantics.

**Walk-up for reads and add**: Commands that operate on an existing project (`add`, `sync`, `list`, etc.) walk up from cwd to find the nearest `mars.toml`.

**Target-based for init**: `mars init` creates at cwd or `--root`. It does not walk up.

This separation ensures:
- Adding dependencies works from any subdirectory of a project (common workflow)
- Creating nested projects requires explicit `mars init` (intentional action)
- No surprising auto-creation of config files

## Scope

### In scope: Walk-up add and explicit init

- Define walk-up behavior for `mars add` (find nearest `mars.toml`)
- Define error messaging when `add` finds no project
- Define explicit init behavior (cwd or `--root`, no walk-up)
- Define context discovery for all commands: walk-up to filesystem root, no git boundary
- Specify cross-platform behavior (Windows, macOS, Linux)
- Specify `--root` flag behavior for both add and init

### Out of scope: Separate follow-on tracks

1. **Remove accidental git assumptions**
   - Audit and remove git-coupled behaviors beyond walk-up boundary
   - Separate pass after bootstrap semantics are settled

2. **Repo-wide Windows compatibility**
   - Full Windows compatibility audit across all mars commands
   - Separate design track with its own scope

## Constraints

- Default landing zone is `mars-agents`, not `meridian`, unless the design proves otherwise.
- `mars add` must NOT auto-create `mars.toml`. That is `init`'s job.
- `mars add` must NOT create nested projects implicitly.
- Follow progressive-disclosure UX: simple first-use path, explicit controls for edge cases.
- Keep the design compatible with direct `mars` usage, not just `meridian mars` passthrough.
- **Windows compatibility is mandatory** for walk-up and init. Platform-specific path concerns must be explicitly validated.

## Success Criteria

A converged design package should answer:

1. **Add behavior**: How does `mars add` find the project? (Answer: walk-up to nearest `mars.toml`)
2. **Add failure**: What happens when no project exists? (Answer: error with "run `mars init`")
3. **Init behavior**: Where does `mars init` create config? (Answer: cwd or `--root`, no walk-up)
4. **Walk-up boundary**: Where does walk-up stop? (Answer: filesystem root, not git)
5. **--root semantics**: How does `--root` work for add vs init? (Answer: sets search start for add, sets target for init)
6. **Windows paths**: How does walk-up terminate at drive roots? How are UNC paths handled?
7. **Migration**: What existing behaviors change? How are users affected?

## Observed Current Behavior

- `meridian mars` is a thin passthrough over the bundled `mars` executable.
- `mars add` fails if no `mars.toml` exists, with "no mars.toml found ... Run `mars init` first."
- `mars init` defaults to git root if inside a git repo (via `default_project_root()`).
- Walk-up stops at `.git` boundary.
- No auto-init behavior exists on any command.

## Change Summary

The main change from current behavior:
- **add**: Walk-up to find existing project (instead of checking cwd only)
- **init**: Use cwd directly (instead of walking up to git root)

## Tier

small
