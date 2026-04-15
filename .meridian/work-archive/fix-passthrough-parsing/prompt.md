# Fix: cyclopts `--` passthrough args consumed by named parameters

## The Bug

Cyclopts does not properly isolate tokens after `--` from named parameter assignment. When a user runs:

```
meridian spawn --prompt-file plan.md -- --add-dir /foo
```

Cyclopts assigns `--add-dir` to the unfilled `--prompt` parameter (treating it as a positional) and only `/foo` reaches `*passthrough`. This is confirmed — the bug is in cyclopts' positional resolution, not in our code.

Repro:
```python
from typing import Annotated
from cyclopts import App, Parameter

app = App()

@app.default
def main(
    prompt: Annotated[str | None, Parameter(name=['--prompt', '-p'])] = None,
    prompt_file: Annotated[str | None, Parameter(name='--prompt-file', allow_leading_hyphen=True)] = None,
    *passthrough: str,
):
    print(f'prompt={prompt!r}, prompt_file={prompt_file!r}, passthrough={passthrough!r}')

app(['--prompt-file', 'plan.md', '--', '--add-dir', '/foo'])
# ACTUAL:   prompt='--add-dir', prompt_file='plan.md', passthrough=('/foo',)
# EXPECTED: prompt=None,        prompt_file='plan.md', passthrough=('--add-dir', '/foo')
```

## The Fix (Approach A — pre-split before cyclopts)

Extract passthrough args (`--` separator and everything after it) from the cleaned argv **before** cyclopts sees them. Stash them on `GlobalOptions`, and have `_spawn_create` read from there instead of from a `*passthrough` cyclopts parameter.

### Step 1: Add `passthrough_args` to `GlobalOptions`

In `src/meridian/cli/main.py`, add a `passthrough_args: tuple[str, ...] = ()` field to the `GlobalOptions` model. Read the file to find the exact type — it may be a pydantic BaseModel or a dataclass.

### Step 2: Split on `--` in `main()` before calling `app()`

In the `main()` function, after `_extract_global_options(args)` returns `cleaned_args`, split `cleaned_args` on `--`:

```python
# Extract passthrough args before cyclopts sees them
if '--' in cleaned_args:
    sep_idx = cleaned_args.index('--')
    passthrough_args = tuple(cleaned_args[sep_idx + 1:])
    cleaned_args = cleaned_args[:sep_idx]
else:
    passthrough_args = ()
```

Store `passthrough_args` on the `GlobalOptions` instance (the same one set via `_GLOBAL_OPTIONS.set(options)`).

### Step 3: Update `_spawn_create` in `src/meridian/cli/spawn.py`

1. **Remove** the `*passthrough` parameter from the function signature entirely.
2. **Read** passthrough args from global options:
   ```python
   passthrough = get_global_options().passthrough_args
   ```
3. The three places that use `passthrough_args=passthrough` (lines ~337, ~364, ~392) stay the same — they just read from a different source now.

### Step 4: Verify `_spawn_continue` also works

`_spawn_create` handles both create and continue flows. Both pass `passthrough_args=passthrough`. After the change, both should work since they read from the same global options.

## What NOT to change

- Don't change `allow_leading_hyphen=True` on `--prompt-file` — it's needed for `--prompt-file -` (stdin).
- Don't change the `SpawnCreateInput` or `SpawnContinueInput` models — they already accept `passthrough_args: tuple[str, ...]`.
- Don't change harness adapter code — `--add-dir` injection in `runner.py` is separate from CLI passthrough and works correctly.

## Test expectations

After the fix, these should all work:
1. `meridian spawn -p "hello" -- --add-dir /foo` → prompt="hello", passthrough=("--add-dir", "/foo")
2. `meridian spawn --prompt-file plan.md -- --add-dir /foo` → prompt_file reads plan.md, passthrough=("--add-dir", "/foo")
3. `meridian spawn -p "hello"` (no --) → prompt="hello", passthrough=()
4. `meridian spawn -p "hello" --` (-- but nothing after) → prompt="hello", passthrough=()

Write a pytest unit test in the appropriate test file that covers these cases by calling the arg-splitting logic directly (not the full CLI). Put tests in `tests/unit/` — look at existing test files there for conventions.
