---
name: smoke-test
description: End-to-end smoke testing methodology — testing from the user's perspective. CLI invocations, HTTP requests, end-to-end flows, race probes, and interruption recovery. Use when you need to verify that user-facing behavior actually works, not just that tests pass.
---
# Smoke Testing

You test the system from the outside — as a user would, not as a developer. Your perspective is valuable precisely because you're not looking at internals. A passing test suite means nothing if the CLI crashes on launch.

## Before You Test

Every project is different. Before writing a single test, understand what's testable:

1. **Read setup docs.** README, CLAUDE.md, Makefile, package.json, pyproject.toml. Look for how to run the project, CLI entry points, dev server commands.
2. **Check for project-specific smoke testing skills.** Some projects have dedicated smoke-testing skills with knowledge about what to test and how. These save you from rediscovering patterns that are already documented.
3. **Look at existing smoke tests.** `tests/smoke/`, `tests/integration/`, `tests/e2e/` — existing tests show what the project cares about and what patterns to follow.

Only after you understand the landscape do you start testing.

## How to Test

Start with the happy path — does the basic thing work? Then go adversarial:

- **Bad input.** Empty strings, missing files, invalid flags, unicode, unexpected types.
- **Concurrent access.** Run the same operation twice simultaneously. Does it corrupt state?
- **Interruption.** Kill a process mid-operation. Is state recoverable?
- **Boundary conditions.** Empty databases, missing environment variables, first-run experience.
- **Sequencing.** Does the order of operations matter? What if a user skips a step?

Focus on what the user actually experiences — error messages, exit codes, output format, side effects on disk. Internals are someone else's job.

## Reporting

Structure your report so the orchestrator can act quickly:

- **What passed** — briefly, so they know what's covered
- **What failed** — with reproduction steps (the exact commands you ran and what happened)
- **What was surprising** — even if it didn't technically break, the orchestrator decides if it matters
