---
description: General smoke-test methodology for the meridian CLI. Use this after
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

### Coverage Map

| Source area            | Smoke test files                                  |
|------------------------|---------------------------------------------------|
| cli/                   | quick-sanity.md, output-formats.md, agent-mode.md |
| lib/harness/           | spawn/dry-run.md, spawn/lifecycle.md              |
| lib/launch/            | spawn/lifecycle.md, spawn/error-paths.md          |
| lib/state/             | state-integrity.md                                |
| lib/sync/              | sync/install-cycle.md                             |
| config changes         | config/init-show-set.md                           |

## General Patterns

For CLI smoke tests, cover the following basics:

- Test both `--json` and text output modes.
- Exercise at least one error path. Bad input should produce a clean failure, never a traceback.
- Check agent-mode behavior with `MERIDIAN_DEPTH=1`.
- Inspect the resulting `.meridian/` state after mutating operations.
- For spawn work, prefer `--dry-run` first when you only need to verify command construction.

When a command changes files or state, verify both the visible output and the on-disk result.

## Two Testing Scenarios

Set `REPO_ROOT` to the meridian-channel checkout root before starting (`git rev-parse --show-toplevel`). Many smoke test scripts reference this variable.

### 1. Testing Against This Repo

When the command should operate on the current `meridian-channel` repo, the simple path is usually enough:

```bash
uv run meridian --help
uv run meridian --json doctor
uv run meridian spawn list
```

This is the default path for quick validation after normal CLI edits.
Note: `uv run meridian spawn list` now defaults to the active view (queued + running). Use `--all` or `--view completed` when your smoke test needs succeeded history.

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
uv run meridian spawn list --all
MERIDIAN_DEPTH=1 uv run meridian --help
```

Use these as the first pass, then move to the focused doc in `tests/smoke/` that matches the area you changed.

### Test Ordering

After `quick-sanity.md` passes, run the focused file matching your change area next (use the coverage map above). For cross-cutting changes that span multiple source areas, also run `output-formats.md` and `state-integrity.md` to catch ripple effects.

## Feature-Specific Notes

Keep the main smoke-test pass generic. When a change targets one command area, read the focused smoke doc for that feature and any matching reference in `resources/`.

- For spawn lifecycle and harness testing, see [`resources/spawn-lifecycle.md`](resources/spawn-lifecycle.md).
- For `meridian sync`, use `tests/smoke/sync/install-cycle.md` and [`resources/sync.md`](resources/sync.md).
- For Codex-specific notes about sandboxed `uv run` usage, cache location, scratch-repo hygiene, and **profile sandbox mapping** (including the sandbox nesting trap), see [`resources/testing-with-codex.md`](resources/testing-with-codex.md).

## Self-Healing This Skill

When you discover a new smoke-test workaround, gotcha, or pattern during testing, update this skill rather than keeping the knowledge in your head:

1. If it's a general pattern (like the env-var trap or CWD warning), add it to the relevant section above.
2. If it's feature-specific, add or update the matching file under `resources/`. Create a new resource file if no existing one fits.
3. If a resource link is broken or a section is outdated, fix it now — don't leave it for later.
4. Add a link from Feature-Specific Notes to any new resource file you create.

The goal is that any agent picking up this skill cold gets the same workarounds you had to discover the hard way.
