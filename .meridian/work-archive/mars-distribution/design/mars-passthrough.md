# Design: `meridian mars` Passthrough Subcommand

## Problem

Users need `meridian mars <args>` to transparently forward to the `mars` binary on PATH. If mars isn't installed, they need clear install instructions. This must work without cyclopts intercepting flags like `-h` or `--version` that belong to mars.

## Approach: Pre-dispatch Interception in `main()`

**Why not a normal cyclopts command?** Cyclopts intercepts `--help`/`-h` and `--version` before the command handler runs. A `@app.command(name="mars")` handler would never see `meridian mars -h` — cyclopts would print meridian's help for the mars subcommand instead of forwarding to mars. The `*passthrough` pattern used by harness shortcuts has the same problem.

**Solution:** Intercept `mars` in `main()` before cyclopts dispatches, forward all remaining args via `subprocess.run`, and register a no-op cyclopts command so `meridian -h` still lists mars.

### Decision: `subprocess.run` vs `os.execvp`

`subprocess.run` over `os.execvp` because:
- Returns exit code to the caller (important for `meridian mars sync && git add .`)
- Works on all platforms without edge cases
- Allows future error handling if needed
- `execvp` replaces the process, preventing cleanup in `main()`

### Decision: Interception point

Insert the mars check in `main()` after logging setup but before `_extract_global_options`. This means global flags like `--json` are NOT consumed — everything after `mars` goes verbatim to the binary. This is correct: `meridian --json mars sync` is not a valid use case; the user wants `meridian mars sync`.

The check uses `_first_positional_token()` which already exists and correctly skips global flags. So `meridian --format text mars sync` would still route to mars (though nobody would write this). More importantly, plain `meridian mars -h` routes correctly.

## Implementation

Two changes, both in `src/meridian/cli/main.py`. ~40 lines total.

### 1. Mars passthrough function

```python
def _try_mars_passthrough(argv: list[str]) -> bool:
    """If first positional is 'mars', exec the mars binary with remaining args.

    Returns True if handled (caller should exit), False if not a mars command.
    """
    # Find where 'mars' appears in argv
    for i, arg in enumerate(argv):
        if arg == "--":
            return False
        if arg.startswith("-"):
            continue
        if arg != "mars":
            return False
        # Everything after 'mars' is forwarded
        mars_args = argv[i + 1:]
        _exec_mars(mars_args)
        return True
    return False


def _exec_mars(args: list[str]) -> None:
    """Find mars on PATH and run it, or print install instructions."""
    import shutil
    import subprocess

    mars_path = shutil.which("mars")
    if mars_path is None:
        print(
            "mars is not installed.\n"
            "\n"
            "Install via npm (recommended):\n"
            "  npm i -g @mars-agents/cli\n"
            "\n"
            "Or build from source:\n"
            "  cargo install --git https://github.com/haowjy/mars-agents\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    result = subprocess.run([mars_path, *args])
    raise SystemExit(result.returncode)
```

### 2. Insert interception in `main()`

After logging setup (line ~992), before `_extract_global_options`:

```python
    # Mars passthrough — before cyclopts touches the args
    if _try_mars_passthrough(args):
        return
```

### 3. Register no-op command for help listing

In the command registration section (~line 460):

```python
@app.command(name="mars")
def mars_noop() -> None:
    """Agent package manager (mars-agents). Forwards to mars binary on PATH."""
    # Unreachable — main() intercepts before cyclopts dispatch.
    # Exists so 'meridian -h' lists mars as a subcommand.
    _exec_mars([])
```

The docstring becomes the help text in `meridian -h`. The body calls `_exec_mars([])` as a safety net — if someone bypasses `main()` and calls `app()` directly, it still works (just without `-h` forwarding).

### 4. Update `_AGENT_ROOT_HELP`

Add mars to the commands list:

```
  mars     Agent package manager (forwards to mars binary)
```

## Behavior Matrix

| Command | Result |
|---|---|
| `meridian mars sync` | Runs `mars sync` |
| `meridian mars -h` | Runs `mars -h` (mars's help) |
| `meridian mars --version` | Runs `mars --version` |
| `meridian mars` | Runs `mars` (mars's default behavior) |
| `meridian -h` | Lists mars as a subcommand |
| `meridian mars` (mars not installed) | Prints install instructions, exits 1 |

## Files to Modify

- `src/meridian/cli/main.py` — all changes in one file (~40 lines added)

## Verification

- [ ] `meridian -h` lists mars
- [ ] `meridian mars --version` shows mars version (when installed)
- [ ] `meridian mars -h` shows mars help (when installed)
- [ ] `meridian mars` without mars installed prints install instructions to stderr, exits 1
- [ ] `uv run ruff check src/meridian/cli/main.py` passes
- [ ] `uv run pyright` passes
