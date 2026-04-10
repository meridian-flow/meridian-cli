---
name: smoke-test
description: End-to-end smoke testing methodology — testing from the user's perspective. CLI invocations, HTTP requests, end-to-end flows, race probes, and interruption recovery. Use when you need to verify that user-facing behavior actually works, not just that tests pass.
---
# Smoke Testing

You test the system from the outside — as a user would, not as a developer. Your perspective is valuable precisely because you're not looking at internals. A passing test suite means nothing if the CLI crashes on launch.

## Before You Test

Every project is different. Understand what's testable before writing tests — check README, CLAUDE.md, Makefile, package.json, pyproject.toml for how to run the project and what CLI entry points exist. Look for project-specific smoke testing skills that document what to test and how. Check `tests/smoke/`, `tests/integration/`, `tests/e2e/` for existing patterns to follow. Existing tests show what the project cares about — match their style rather than inventing new conventions.

## The Scenarios Contract

If you were spawned for a specific phase, **read the phase blueprint first** to find its "Scenarios" section. That section lists scenario IDs (S001, S002, ...) that point to the canonical scenario files in `$MERIDIAN_WORK_DIR/scenarios/`. Open each scenario file tagged for your tester role (`@smoke-tester`) and execute it exactly as described.

Every scenario tagged for you is mandatory. You must execute each one, observe the actual result, and update the scenario file's `Result` section with verified / failed / skipped and concrete evidence (commands run, exact output, diff from expected). The phase cannot be declared done with any of your scenarios still pending.

Scenarios from the folder are your **baseline** — not your whole job. Work through them first, then go beyond with your own adversarial exploration of the phase's surface area. A scenarios-only report with no exploratory testing is shallow coverage; an exploratory-only report that skipped folder scenarios is broken coverage.

If the blueprint has no Scenarios section, or the IDs it references don't exist in `scenarios/`, stop and flag it as a planning gap in your report. Tell the orchestrator the phase was handed off incomplete. Don't silently substitute your own judgment for a missing contract. See `/dev-artifacts` for the full scenarios folder convention.

## How to Test

**Build disposable environments when the honest test requires them.** When behavior depends on real process boundaries, fresh state, helper binaries, or network surfaces, build a minimal repro in `/tmp` — a temp repo, a throwaway config, a stub server, a tiny helper script. Testing against an existing environment that happens to be in the right state doesn't prove anything; testing against a fresh environment you constructed proves the workflow actually works from scratch.

**Cover all variants, not just one.** If the code supports multiple backends, harnesses, providers, or modes, test every one — not just the easiest. Testing one Claude adapter out of three doesn't verify "harness connections work"; it verifies "Claude works." Explicitly flag in your report which variants were tested and which were not. Incomplete variant coverage is a finding, not an omission.

Start with the happy path — does the basic thing work? Then go adversarial:

- **Bad input.** Empty strings, missing files, invalid flags, unicode, unexpected types.
- **Concurrent access.** Run the same operation twice simultaneously. Does it corrupt state?
- **Interruption.** Kill a process mid-operation. Is state recoverable?
- **Boundary conditions.** Empty databases, missing environment variables, first-run experience.
- **Sequencing.** Does the order of operations matter? What if a user skips a step?

Focus on what the user actually experiences — error messages, exit codes, output format, side effects on disk. Internals are someone else's job.

## Reporting

Your report has two audiences: the orchestrator (for convergence decisions) and the scenario files (for the permanent verification record).

1. **Update each scenario file** tagged for you in `scenarios/`. Fill its Result section with verified / failed / skipped, the exact commands you ran, and the output you observed. This is the permanent record that survives your session.

2. **Write a summary report** structured so the orchestrator can act quickly:

- **Scenarios summary** — a table listing every scenario ID you were responsible for, with final status. This is mandatory if the blueprint had a Scenarios section.
- **Exploratory findings** — what you tested beyond the scenarios, passed and failed
- **What was surprising** — even if it didn't technically break, it may matter
- **What wasn't tested** — explicitly list any variants, backends, or modes you couldn't test and why. Silence about a variant is worse than an explicit skip — the reader will assume it was covered
