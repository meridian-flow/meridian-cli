# Redesign Feedback: Full Parity With Existing Tooling

The cwd-first `mars add` design is no longer the preferred direction.

## New Direction

Align `mars add` with mainstream project tools like `uv add`, `cargo add`, and local npm command resolution:

- `mars add` should search for the nearest existing project by walking up
- if a parent project exists, use it
- if no project exists anywhere, fail and tell the user to run `mars init`

## Required Rules

1. `mars add` must walk up to the nearest ancestor `mars.toml`
2. `mars add` must not auto-create a nested project at cwd when an ancestor project exists
3. `mars add` must not auto-init at cwd when no project exists
4. `mars init` remains the explicit create/bootstrap command
5. Nested mars projects should be created explicitly with `mars init`, not implicitly via `mars add`

## Why

- This matches the behavior users already know from `uv add`, `cargo add`, and npm's local project resolution.
- It avoids surprising divergence from common CLI semantics.
- It cleanly separates:
  - "use the current/nearest existing project" commands
  - "create a new project here" commands

## Expected Revision

Revise the design so that:

1. `mars add` walks up to find the nearest existing `mars.toml`
2. `mars add` errors if no `mars.toml` is found anywhere up to filesystem root
3. The error should direct the user to run `mars init`
4. `mars init` stays cwd- or `--root`-targeted and explicit
5. Any nested-project creation via `add` is removed from the design

## Scope Note

Keep the previously established constraints:

- filesystem root, not git, is the walk-up boundary
- Windows/macOS/Linux must all work
- `--root` semantics still need to be defined clearly
- do not broaden this into the full repo-wide de-git or Windows audit
