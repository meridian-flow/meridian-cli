---
description: General smoke-testing methodology for the meridian CLI. Use this after
  implementing or modifying any CLI command, after refactors touching state,
  launch, or ops layers, before calling a feature done, and when debugging
  user-reported issues. Covers how smoke tests are organized, core CLI testing
  patterns, the env-var trap for scratch repos, and a compact command cheat
  sheet.
name: _meridian-dev-smoke-test
---

# Smoke-Testing the Meridian CLI

Use `uv run meridian` to test the CLI in its current state. Prefer smoke tests over unit tests for CLI work: this tool is built for agents, so you should exercise the real commands yourself.

## When to Smoke Test

Smoke test whenever you:

- implement or modify any CLI command
- refactor code that touches state, launch, or ops layers
- think a feature is "done"
- debug a user-reported issue

If you changed behavior, prove the real CLI still works before you stop.

## How Smoke Tests Are Organized

Smoke test guides live in [`tests/smoke/`](tests/smoke/) as markdown files.

- Each file is short, focused, and self-contained.
- Pick the file or files that match the area you changed.
- `tests/smoke/quick-sanity.md` is the minimum bar. Always run it.
- `tests/smoke/adversarial.md` is for deeper coverage when you expect edge cases or regressions.

Read only the specific smoke docs you need. Do not rewrite them unless that is the task.

## General Patterns

For CLI smoke tests, cover the following basics:

- Test both `--json` and text output modes.
- Exercise at least one error path. Bad input should produce a clean failure, never a traceback.
- Check agent-mode behavior with `MERIDIAN_DEPTH=1`.
- Inspect the resulting `.meridian/` state after mutating operations.
- For spawn work, prefer `--dry-run` first when you only need to verify command construction.

When a command changes files or state, verify both the visible output and the on-disk result.

## Two Testing Scenarios

### 1. Testing Against This Repo

When the command should operate on the current `meridian-channel` repo, the simple path is usually enough:

```bash
uv run meridian --help
uv run meridian --json doctor
uv run meridian spawn list
```

This is the default path for quick validation after normal CLI edits.

### 2. Testing Against a Scratch Repo

When you need isolation, use a scratch repo under `/tmp` and override the repo and state roots together. This matters for install, spawn, sync, and any operation that writes state.

## The Env-Var Trap

You are usually running inside an active meridian session. Child processes inherit:

```text
MERIDIAN_REPO_ROOT
MERIDIAN_STATE_ROOT
```

`MERIDIAN_STATE_ROOT` wins for state resolution. If you override only `MERIDIAN_REPO_ROOT`, you can end up splitting writes across two repos:

- repo files go to the scratch repo
- `.meridian/` state leaks into the real project

This mismatch is specific to the "test another repo from inside an active session" case.

Always override both:

```bash
export MERIDIAN_REPO_ROOT=/tmp/test-repo
export MERIDIAN_STATE_ROOT=/tmp/test-repo/.meridian
```

## uv run Resets CWD

`uv run` executes from the project root where `pyproject.toml` lives. So this pattern is misleading:

```bash
cd /tmp/test-repo
uv run meridian ...
```

The command still resolves relative to the source checkout, not the scratch repo.

Rules:

- Use absolute paths.
- Set both env vars for scratch-repo tests.
- Do not rely on `cd` surviving across separate shell-tool calls.

## Pollution Check

After your first scratch-repo run, verify you did not write into the real repo's `.meridian/`.

Typical checks:

```bash
git status --short
find .meridian -maxdepth 2 -type f | sort
```

If a test unexpectedly touched real state, stop and inspect before continuing.

## Quick Reference

Minimum common smoke-test commands:

```bash
uv run meridian --help
uv run meridian --json doctor
uv run meridian --json spawn create --dry-run -p "test"
uv run meridian --json models list
uv run meridian --json config show
uv run meridian spawn list
MERIDIAN_DEPTH=1 uv run meridian --help
```

Use these as the first pass, then move to the focused doc in `tests/smoke/` that matches the area you changed.
