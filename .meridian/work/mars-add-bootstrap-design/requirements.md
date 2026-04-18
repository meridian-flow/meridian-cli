# Requirements: mars add bootstrap behavior

## Problem
`meridian mars add <source>` currently fails when `mars.toml` does not already exist, because the underlying `mars add` command requires an initialized mars project. This creates first-use friction for a command that already carries clear mutation intent.

## User Intent
When a user runs `mars add` or `meridian mars add` in a repository that does not yet have `mars.toml`, the system should do the right thing by default instead of forcing a separate explicit init step.

## Scope
In scope:
- Design first-use bootstrap behavior for `mars add` in `mars-agents`.
- Define when `mars add` should auto-create `mars.toml` and continue.
- Define safety rules for project-root detection and ambiguous locations.
- Define non-interactive and interactive behavior.
- Define error/help messaging when auto-bootstrap is unsafe.
- Identify any required follow-through in `meridian` docs/help text after a `mars-agents` change.

Out of scope:
- Implementing the behavior in this phase.
- Broad redesign of `mars init` or `meridian init` beyond what is needed for `mars add` first-use UX.
- Changing unrelated mars package-management flows.

## Constraints
- Default landing zone should be `mars-agents`, not `meridian`, unless the design proves otherwise.
- Preserve explicit project-boundary safety; do not silently create config in the wrong repo.
- Follow progressive-disclosure UX: simple first-use path, explicit controls for edge cases.
- Respect existing repo-boundary discovery semantics unless the design intentionally changes them.
- Keep the design compatible with direct `mars` usage, not just `meridian mars` passthrough.

## Success Criteria
A converged design package should answer:
- Should `mars add` auto-init by default, prompt, or require a new flag?
- Where should `mars.toml` be created when cwd is inside a repo but not at root?
- What should happen when no repo root is found, or root detection is ambiguous?
- What exact CLI behavior should differ between interactive and non-interactive modes?
- What docs/help updates are required in `mars-agents` and, if needed, `meridian`?
- Why this design is better than keeping explicit `mars init` as a hard prerequisite.

## Observed Current Behavior
- `meridian mars` is a thin passthrough over the bundled `mars` executable.
- The exact failure comes from `mars-agents` root discovery when no `mars.toml` exists.
- `meridian init --link` already provides a convenience bootstrap path, but plain `meridian mars add` does not.

## Tier
small
