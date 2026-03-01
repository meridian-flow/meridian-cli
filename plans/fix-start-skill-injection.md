# Fix: `meridian start` Missing Skill Injection

**Status:** draft

## Problem

`meridian start` launches the primary agent via Claude Code but **never injects skills** via `--append-system-prompt`. Skills listed in agent profiles are resolved and materialized but silently dropped from the command.

This is because Claude Code `--agent` does not preload skills from frontmatter for the primary agent (issue #29902). A workaround exists in the `run spawn` path (`_run_prepare.py`) but was never added to the `start` path (`launch.py`).

## Root Cause

Two separate code paths build the harness command independently:

| Path | File | Skill injection |
|------|------|----------------|
| `run spawn` | `src/meridian/lib/ops/_run_prepare.py:348-354` | ✅ `compose_skill_injections()` → `--append-system-prompt` |
| `start` | `src/meridian/lib/space/launch.py:198-234` | ❌ **missing** |

In `launch.py:_build_interactive_command()`, skills are resolved (line 175) and materialized (line 189), but the command is built manually without the injection:

```python
command: list[str] = ["claude"]
if materialized.agent_name:
    command.extend(["--agent", materialized.agent_name])
command.extend(["--model", str(model)])
command.extend(resolver.resolve_flags(harness))
command.extend(passthrough_args)
# ← no --append-system-prompt here
```

## Fix

### 1. Add skill injection to `launch.py` (3-line fix)

**File:** `src/meridian/lib/space/launch.py`

Add import at top of file:
```python
from meridian.lib.prompt.compose import compose_skill_injections
```

After line 233 (`command.extend(resolver.resolve_flags(harness))`), before `command.extend(passthrough_args)`, add:
```python
# Workaround: Claude Code --agent does not preload skills (issue #29902).
appended = compose_skill_injections(resolved_skills.loaded_skills)
if appended:
    command.extend(["--append-system-prompt", appended])
```

### 2. Add default skills to agent profiles

All profiles currently have `skills: []`. Update both `.agents/agents/` AND `.claude/agents/` (must stay in sync):

| Profile | Skills |
|---------|--------|
| `coder.md` | `skills: [scratchpad]` |
| `reviewer.md` | `skills: [reviewing]` |
| `researcher.md` | `skills: [researching]` |
| `orchestrator.md` | `skills: [orchestrate]` |

### 3. Add test

**File:** `tests/test_start_skill_injection.py`

```python
"""Verify meridian start injects skills via --append-system-prompt."""

from pathlib import Path
import pytest
from meridian.lib.space.launch import _build_interactive_command, SpaceLaunchRequest
from meridian.lib.types import SpaceId


def test_start_dry_run_includes_append_system_prompt(tmp_path: Path) -> None:
    """When agent profile has skills, the command should include --append-system-prompt."""
    # Setup: create minimal .meridian structure
    # Use an agent profile with at least one skill
    # Call _build_interactive_command with dry_run request
    # Assert "--append-system-prompt" in resulting command tuple
    ...
```

The exact test setup depends on how agent profile discovery works with `tmp_path`. A simpler smoke test:

```bash
MERIDIAN_SPACE_ID=test uv run meridian start --dry-run --agent coder -m claude-sonnet-4-6 2>&1 | grep append-system-prompt
```

Should show `--append-system-prompt` in the dry-run command output.

## Verification

1. `MERIDIAN_SPACE_ID=test uv run meridian start --dry-run --agent coder -m claude-sonnet-4-6` → command includes `--append-system-prompt` with scratchpad skill content
2. `uv run pytest -x -q` → all tests pass
3. `uv run pytest tests/test_space_threading.py tests/test_cli_smoke.py -xvs` → pass

## Files Changed

- `src/meridian/lib/space/launch.py` — add 1 import + 3 lines for skill injection
- `.agents/agents/coder.md` — `skills: [scratchpad]`
- `.agents/agents/reviewer.md` — `skills: [reviewing]`
- `.agents/agents/researcher.md` — `skills: [researching]`
- `.agents/agents/orchestrator.md` — `skills: [orchestrate]`
- `.claude/agents/coder.md` — mirror of .agents
- `.claude/agents/reviewer.md` — mirror of .agents
- `.claude/agents/researcher.md` — mirror of .agents
- `.claude/agents/orchestrator.md` — mirror of .agents
- `tests/test_start_skill_injection.py` — new test

## Context for Engineer

- The workaround pattern already exists in `_run_prepare.py:348-354` — copy the same approach.
- `compose_skill_injections()` is in `src/meridian/lib/prompt/compose.py:50-65`. It takes `Sequence[SkillContent]`, returns `str | None`. Returns `None` when no skills (caller omits the flag).
- `resolved_skills.loaded_skills` is already available in `_build_interactive_command()` at line 175-186.
- The broader unification (eliminating the duplication entirely) is tracked in `plans/unify-harness-launch.md`. This fix is the immediate patch.
