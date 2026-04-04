---
name: smoke-test
description: End-to-end smoke testing methodology — testing from the user's perspective. CLI invocations, HTTP requests, end-to-end flows, race probes, and interruption recovery. Use when you need to verify that user-facing behavior actually works, not just that tests pass.
---
# Smoke Testing

You test the system from the outside — as a user would, not as a developer. Your perspective is valuable precisely because you're not looking at internals. A passing test suite means nothing if the CLI crashes on launch.

## Before You Test

Every project is different. Understand what's testable before writing tests — check README, CLAUDE.md, Makefile, package.json, pyproject.toml for how to run the project and what CLI entry points exist. Look for project-specific smoke testing skills that document what to test and how. Check `tests/smoke/`, `tests/integration/`, `tests/e2e/` for existing patterns to follow. Existing tests show what the project cares about — match their style rather than inventing new conventions.

## How to Test

**Build disposable environments when the honest test requires them.** When behavior depends on real process boundaries, fresh state, helper binaries, or network surfaces, build a minimal repro in `/tmp` — a temp repo, a throwaway config, a stub server, a tiny helper script. Testing against an existing environment that happens to be in the right state doesn't prove anything; testing against a fresh environment you constructed proves the workflow actually works from scratch.

Start with the happy path — does the basic thing work? Then go adversarial:

- **Bad input.** Empty strings, missing files, invalid flags, unicode, unexpected types.
- **Concurrent access.** Run the same operation twice simultaneously. Does it corrupt state?
- **Interruption.** Kill a process mid-operation. Is state recoverable?
- **Boundary conditions.** Empty databases, missing environment variables, first-run experience.
- **Sequencing.** Does the order of operations matter? What if a user skips a step?

Focus on what the user actually experiences — error messages, exit codes, output format, side effects on disk. Internals are someone else's job.

## Reporting

Structure your report so the reader can act quickly:

- **What passed** — briefly, so they know what's covered
- **What failed** — with reproduction steps (the exact commands you ran and what happened)
- **What was surprising** — even if it didn't technically break, it may matter
