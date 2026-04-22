# Meridian Smoke Tests

Smoke tests are short, LLM-executed manual checks for the `meridian` CLI. They validate the command surface, state files under `.meridian/`, and harness integration without turning the suite into a large unit-test matrix.

## How to run

1. Pick one file under `tests/smoke/`.
2. Run each bash block exactly as written.
3. Treat any `FAIL` line, traceback, or hang as a test failure.

Every markdown file here is independent. You can hand a single file to an agent and expect it to work without opening the rest of the smoke suite.

## Command surface

Always invoke the CLI through the checked-out source tree:

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
cd "$REPO_ROOT"
uv run meridian --help >/dev/null && echo "PASS: meridian CLI is runnable" || echo "FAIL: meridian CLI is not runnable"
```

## Scratch repo setup

When a smoke test needs isolated state, override both environment variables below. This matters because `MERIDIAN_RUNTIME_DIR` wins over repo-root discovery, and `uv run` resets the working directory back to the source checkout.

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-smoke.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_PROJECT_DIR="$SMOKE_REPO"
export MERIDIAN_RUNTIME_DIR="$SMOKE_REPO/.meridian"
test "$MERIDIAN_RUNTIME_DIR" = "$SMOKE_REPO/.meridian" && echo "PASS: scratch repo env is isolated" || echo "FAIL: scratch repo env is wrong"
```

## Conventions

- Priorities use `[CRITICAL]`, `[IMPORTANT]`, and `[NICE-TO-HAVE]`.
- Every bash block is copy-pasteable and should end with `PASS` or `FAIL`.
- Prefer absolute paths in setup blocks.
- Keep `.meridian/` writes inside the scratch repo unless the file explicitly says otherwise.
- Spawn lifecycle smoke tests require a working harness in the current session.
- Use `timeout` when probing risky or adversarial behavior.
