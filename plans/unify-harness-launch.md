# Unify Harness Launch Pipeline

**Status:** in-progress (partially implemented)

## Current Implementation Snapshot (2026-03-03)

- Skill injection gap is fixed in `meridian start` (`launch.py` now appends `--append-system-prompt`).
- Shared launch resolution helpers exist in `lib/launch_resolve.py` and are used by both launch paths.
- Remaining work is structural: command assembly and session metadata resolution are still duplicated between `launch.py` and `_spawn_prepare.py`.

## Problem

`meridian start` (`launch.py`) and `meridian run spawn` (`_spawn_prepare.py`) duplicate the same "resolve agent -> resolve skills -> resolve permissions -> build harness command" pipeline. This duplication previously caused a concrete bug: the skill injection workaround (`--append-system-prompt` for Claude Code issue #29902) was added to `_spawn_prepare.py` but not to `launch.py`.

The previous plan (`unified-launch-refactor.md`) completed Steps 0-1 (remove `--skills`, add shared flags) but Steps 2-4 were never done.

### Duplicated pipeline (current state)

Both paths independently:
1. Load agent profile (`load_agent_profile_with_fallback`)
2. Resolve run defaults (`resolve_run_defaults`)
3. Route model → harness
4. Resolve skills (`resolve_skills_from_profile`)
5. Resolve permission tier from profile
6. Build permission config + resolver
7. Build harness command with permission flags

`_run_prepare.py` additionally:
- Composes prompt with skills/agent body/references/template vars
- Handles continuation (session resume/fork)
- Injects skills via `--append-system-prompt` (workaround)
- Builds command via `harness.build_command(RunParams)`

`launch.py` additionally:
- Materializes agent/skill files for harness directories
- Handles `MERIDIAN_HARNESS_COMMAND` override
- Handles passthrough args for interactive mode
- Builds command manually: `["claude", "--agent", ..., "--model", ...]`
- **Missing**: skill injection via `--append-system-prompt`

### Why `launch.py` can't just use `harness.build_command()`

`harness.build_command()` uses `PromptMode.FLAG` for Claude (`claude -p "prompt"`). But `meridian start` is interactive — there's no `-p` flag. The prompt is injected via `MERIDIAN_SPACE_PROMPT` env var or the user types it. So we can't just swap in `build_command()` directly.

## Design

Extract a `ResolvedHarnessLaunch` dataclass from `launch_resolve.py` that captures the fully-resolved state. Both paths call `resolve_harness_launch()` and then do their own command assembly from the resolved config.

```python
@dataclass(frozen=True, slots=True)
class ResolvedHarnessLaunch:
    """Fully-resolved harness launch configuration."""
    model: str
    harness_id: str
    agent_name: str | None
    resolved_skills: ResolvedSkills
    permission_config: PermissionConfig
    permission_resolver: PermissionResolver
    skill_injection: str | None        # --append-system-prompt content
    materialization: MaterializeResult | None
    warning: str | None
```

```python
def resolve_harness_launch(
    *,
    repo_root: Path,
    config: MeridianConfig,
    requested_model: str,
    requested_agent: str | None,
    default_agent: str,
    fallback_agent: str,
    permission_tier_override: str | None,
    default_permission_tier: str,
    agent_explicitly_requested: bool,
    materialize: bool,
    materialize_chat_id: str,
    dry_run: bool,
) -> ResolvedHarnessLaunch:
    ...
```

## Step 0: Quick fix — inject skills in launch.py (immediate)

Before the refactor, patch `launch.py:_build_interactive_command()` to add the missing `--append-system-prompt`. This is a 3-line fix that unblocks `meridian start` with skills.

Also: add default skills to agent profiles (they're all `skills: []` currently).

### Files to change

#### `src/meridian/lib/space/launch.py`
- After `command.extend(resolver.resolve_flags(harness))` (line 233), add:
  ```python
  appended = compose_skill_injections(resolved_skills.loaded_skills)
  if appended:
      command.extend(["--append-system-prompt", appended])
  ```
- Add import: `from meridian.lib.prompt.compose import compose_skill_injections`

#### Agent profiles (`.agents/agents/` AND `.claude/agents/`)
- `coder.md`: `skills: [scratchpad]`
- `reviewer.md`: `skills: [reviewing]`
- `researcher.md`: `skills: [researching]`
- `orchestrator.md`: `skills: [orchestrate]`

### Tests
- `meridian start --dry-run --agent coder -m claude-sonnet-4-6` should show `--append-system-prompt` in output
- Full suite passes

## Step 1: Extract `resolve_harness_launch()` into `launch_resolve.py`

Move the shared resolve pipeline from both `_run_prepare.py` and `launch.py` into `launch_resolve.py`. The function resolves: profile, defaults, model→harness, skills, permissions, materialization, skill injection.

### Files to change

#### `src/meridian/lib/launch_resolve.py`
- Add `ResolvedHarnessLaunch` dataclass
- Add `resolve_harness_launch()` function that encapsulates:
  1. `load_agent_profile_with_fallback`
  2. `resolve_run_defaults`
  3. Model → harness routing
  4. `resolve_skills_from_profile`
  5. `resolve_permission_tier_from_profile` + `build_permission_config` + `build_permission_resolver`
  6. `compose_skill_injections` (workaround for issue #29902)
  7. `materialize_for_harness` (optional, only when `materialize=True`)
  8. Warning aggregation

#### `src/meridian/lib/ops/_run_prepare.py`
- Replace the duplicated pipeline (lines 227-354) with a call to `resolve_harness_launch()`
- Keep `_run_prepare`-specific logic: prompt composition, references, template vars, continuation handling
- `_PreparedCreate` still exists but is populated from `ResolvedHarnessLaunch` + prepare-specific fields

#### `src/meridian/lib/space/launch.py`
- Replace the duplicated pipeline in `_build_interactive_command()` (lines 159-233) with `resolve_harness_launch()`
- Keep launch-specific logic: `MERIDIAN_HARNESS_COMMAND` override, interactive command assembly, passthrough args
- Also update `_resolve_primary_session_metadata()` to use `resolve_harness_launch()` (it duplicates the same pipeline a THIRD time for session metadata)

### Tests
- Add unit tests for `resolve_harness_launch()` in isolation
- Existing tests continue to pass (behavioral equivalence)
- Dry-run both paths and verify identical harness flags

## Step 2: Eliminate `_resolve_primary_session_metadata()` duplication

`_resolve_primary_session_metadata()` in `launch.py` is a THIRD copy of the same pipeline, used only to extract metadata for session records. After Step 1, it should derive from the same `ResolvedHarnessLaunch` that `_build_interactive_command()` uses.

### Files to change
- `src/meridian/lib/space/launch.py`: Remove `_resolve_primary_session_metadata()`, derive session metadata from the `ResolvedHarnessLaunch` already computed in `launch_primary()`

## Implementation Order

| Step | Risk | Scope | Priority |
|------|------|-------|----------|
| 0: Quick fix skills in launch.py | Low | 3-line patch + profiles | P0 — unblocks `meridian start` |
| 1: Extract `resolve_harness_launch()` | Medium | Refactor | P1 — eliminates root cause |
| 2: Eliminate session metadata dup | Low | Cleanup | P2 — nice to have |

**Recommend:** Step 0 now (immediate fix). Step 1 as the real fix. Step 2 as cleanup.
