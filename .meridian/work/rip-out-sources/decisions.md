# Decisions — rip-out-sources

## mars-agents dependency commented out (not added to pyproject.toml)

**What**: `mars-agents>=0.1.0` is listed as a comment in pyproject.toml instead of an active dependency.

**Why**: mars-agents is not yet published to PyPI. Adding it as a real dependency breaks `uv sync` and all `uv run` commands, making the project unbuildable.

**Alternatives considered**: 
- Path dependency (`mars-agents @ file:///...`) — works locally but breaks for all other users
- Optional dependency group — contradicts the design principle that mars is required, not optional
- Just skip it entirely — loses the intent documentation

**Action needed**: Uncomment the dependency line once mars-agents is published to PyPI.

## agents.toml/agents.lock added to deprecated gitignore lines

**What**: Added `!agents.toml` and `!agents.lock` to `_DEPRECATED_GITIGNORE_LINES` so `ensure_gitignore()` actively strips them from existing `.gitignore` files.

**Why**: The `_merge_required_gitignore_lines` function appends any lines from `_REQUIRED_GITIGNORE_LINES` that aren't present in the file. Even after removing agents.toml/agents.lock from the required list, existing gitignore files retained the old lines. The deprecated list actively removes stale entries. This was discovered during implementation when spawns kept re-adding the lines via `ensure_gitignore()` calls triggered by `uv run meridian`.

**Alternatives considered**: Only cleaning the on-disk file manually — insufficient because any `meridian` CLI invocation could re-trigger `ensure_gitignore()`.
