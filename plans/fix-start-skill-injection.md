# Fix: `meridian start` Missing Skill Injection

**Status:** implemented

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

### 2. Sync missing default skills in agent profiles

After checking the repo, two profiles already had defaults (`reviewer: reviewing`, `orchestrator: orchestrate/run-agent/plan-task`). Only `coder` and `researcher` were still empty.

Update both `.agents/agents/` AND `.claude/agents/` (must stay in sync):

| Profile | Skills |
|---------|--------|
| `coder.md` | `skills: [scratchpad]` |
| `reviewer.md` | `skills: [reviewing]` |
| `researcher.md` | `skills: [researching]` |
| `orchestrator.md` | unchanged (already non-empty, intentionally broader) |

### 3. Update existing tests (instead of adding a new file)

- `tests/test_default_agent_profiles.py`
  - flip expectation to include `--append-system-prompt` when profile skills resolve
  - add guard test: omit flag when profile has no skills
- `tests/test_space_launch_sliceb.py`
  - flip `start`/`dry-run` command assertions to include `--append-system-prompt`

## Verification

1. `meridian start --dry-run` path includes `--append-system-prompt` whenever resolved skill content is non-empty
2. `meridian start --dry-run` path omits the flag when the chosen profile has no skills
3. Targeted tests pass:
   - `tests/test_default_agent_profiles.py`
   - `tests/test_space_launch_sliceb.py`

## Files Changed

- `src/meridian/lib/space/launch.py` — add 1 import + 3 lines for skill injection
- `.agents/agents/coder.md` — `skills: [scratchpad]`
- `.agents/agents/researcher.md` — `skills: [researching]`
- `.claude/agents/coder.md` — mirror of .agents
- `.claude/agents/researcher.md` — mirror of .agents
- `tests/test_default_agent_profiles.py` — update expectations, add no-skills guard
- `tests/test_space_launch_sliceb.py` — update expectations for start/dry-run

## Context for Engineer

- The workaround pattern already exists in `_run_prepare.py:348-354` — copy the same approach.
- `compose_skill_injections()` is in `src/meridian/lib/prompt/compose.py:50-65`. It takes `Sequence[SkillContent]`, returns `str | None`. Returns `None` when no skills (caller omits the flag).
- `resolved_skills.loaded_skills` is already available in `_build_interactive_command()` at line 175-186.
- The broader unification (eliminating the duplication entirely) is tracked in `plans/unify-harness-launch.md`. This fix is the immediate patch.
