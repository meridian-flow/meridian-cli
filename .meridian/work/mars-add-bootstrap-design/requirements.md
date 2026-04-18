# Requirements: Init-Centric Bootstrap

## Problem

`meridian mars add <source>` currently fails when `mars.toml` does not already exist, because the underlying `mars add` command requires an initialized mars project. This creates first-use friction for a command that already carries clear mutation intent.

## User Intent

When a user runs `mars add` or `meridian mars add` in a repository that does not yet have `mars.toml`, the system should do the right thing by default instead of forcing a separate explicit init step.

## Design Direction

**Init-centric model**: `mars init` is the canonical bootstrap primitive. Commands with clear project-setup intent may auto-initialize by invoking init semantics internally.

This replaces the previous `add`-specific bootstrap framing with a generalized model that can be extended to other commands if needed.

## Scope

### In scope: Bootstrap semantics

- Make `mars init` the canonical bootstrap path with cwd as default root.
- Define an explicit auto-init allowlist (initially: `init`, `add`).
- Make `add` invoke init semantics when config is missing.
- Define root selection: cwd unless `--root` specified.
- Define walk-up behavior: filesystem root, no git boundary.
- Define error messaging for init-required commands.
- Specify cross-platform behavior (Windows, macOS, Linux).
- Specify idempotency guarantees for init and auto-init.

### Out of scope: Separate follow-on tracks

1. **Remove accidental git assumptions**
   - Audit and remove git-coupled behaviors beyond walk-up boundary
   - Separate pass after bootstrap semantics are settled

2. **Repo-wide Windows compatibility**
   - Full Windows compatibility audit across all mars commands
   - Separate design track with its own scope

## Constraints

- Default landing zone is `mars-agents`, not `meridian`, unless the design proves otherwise.
- Preserve explicit project-boundary safety; do not silently create config in the wrong repo.
- Follow progressive-disclosure UX: simple first-use path, explicit controls for edge cases.
- Keep the design compatible with direct `mars` usage, not just `meridian mars` passthrough.
- **Windows compatibility is mandatory** for bootstrap and root-discovery. Platform-specific path concerns must be explicitly validated.

## Success Criteria

A converged design package should answer:

1. **Init semantics**: What does `mars init` do by default? Where does it create config?
2. **Auto-init allowlist**: Which commands may auto-initialize? How is the list defined?
3. **Walk-up behavior**: How does walk-up find existing config? What are the boundaries?
4. **Error handling**: What error do init-required commands produce when config is missing?
5. **Idempotency**: What happens if init or auto-init runs twice? Or concurrently?
6. **Windows paths**: How does walk-up terminate at drive roots? How are UNC paths handled?
7. **Migration**: What existing behaviors change? How are users affected?

## Observed Current Behavior

- `meridian mars` is a thin passthrough over the bundled `mars` executable.
- `mars add` fails if no `mars.toml` exists, with "no mars.toml found ... Run `mars init` first."
- `mars init` defaults to git root if inside a git repo (via `default_project_root()`).
- Walk-up stops at `.git` boundary.
- No auto-init behavior exists on any command.

## Tier

small
