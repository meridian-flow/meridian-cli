# Harness Domain Overview

## What It Is

The harness layer is the mechanism side of the policy/mechanism split. It translates a `SpawnParams` struct into an executable subprocess (or in-process API call) and extracts results back from the output. The CLI and ops layer are policy — they decide what to run. Harness adapters are mechanism — they know how to run it.

Source: `src/meridian/lib/harness/`

## Adapter Protocol

Two protocols, defined in `adapter.py`:

**`SubprocessHarness`** — subprocess-launching adapters (Claude, Codex, OpenCode). Key methods:
- `build_command(run, perms)` → `list[str]` — full argv including model, session flags, permissions
- `env_overrides(config)` → `dict[str, str]` — harness-specific env vars to set
- `blocked_child_env_vars()` → `frozenset[str]` — env vars to suppress in child process
- `extract_usage(artifacts, spawn_id)` → `TokenUsage`
- `extract_session_id(artifacts, spawn_id)` → `str | None`
- `extract_report(artifacts, spawn_id)` → `str | None`
- `detect_primary_session_id(project_root, started_at_epoch, ...)` → `str | None` — post-launch scan for primary harness session
- `seed_session(is_resume, harness_session_id, passthrough_args)` → `SessionSeed`
- `filter_launch_content(prompt, skill_injection, is_resume, ...)` → `PromptPolicy`
- `owns_untracked_session(project_root, session_ref)` → `bool`

**`InProcessHarness`** — in-process execution (Direct adapter only). Single method: `execute(prompt, model, **kwargs)` → `SpawnResult`.

`BaseSubprocessHarness` provides no-op defaults for all optional methods, so adapters only implement what they support.

## HarnessCapabilities

Each adapter declares its feature flags via `HarnessCapabilities`:

| Flag | Claude | Codex | OpenCode | Direct |
|------|--------|-------|----------|--------|
| `supports_stream_events` | ✓ | ✓ | ✓ | ✗ |
| `supports_stdin_prompt` | ✓ | ✓ | ✓ | — |
| `supports_session_resume` | ✓ | ✓ | ✓ | ✗ |
| `supports_session_fork` | ✓ | ✓ | ✓ | ✗ |
| `supports_native_skills` | ✓ | ✓ | ✓ | ✗ |
| `supports_native_agents` | ✓ | ✗ | ✗ | ✗ |
| `supports_programmatic_tools` | ✗ | ✗ | ✗ | ✓ |
| `supports_primary_launch` | ✓ | ✓ | ✓ | ✗ |
| `reference_input_mode` | paths | paths | paths | — |

## Command Assembly (`common.py`)

`build_harness_command()` is the shared strategy-driven command builder. Each adapter declares a `STRATEGIES: StrategyMap` dict mapping `SpawnParams` field names to `FlagStrategy` rules.

**`FlagStrategy.effect` options:**
- `CLI_FLAG` — append `[flag, value]` to args
- `TRANSFORM` — call a custom function to modify the args list
- `DROP` — silently skip this field

**Invariant:** Every `SpawnParams` field must be either in `STRATEGIES` or in the `_SKIP_FIELDS` set (`prompt`, `extra_args`, `project_root`, `mcp_tools`, `adhoc_agent_payload`, `interactive`, `report_output_path`). Missing mappings raise `ValueError` at build time — this prevents adapter drift when `SpawnParams` gains new fields.

**`PromptMode`:**
- `FLAG` — prompt passed via `-p "..."` flag (Claude uses `--prompt` via stdin + `-p`)
- `POSITIONAL` — prompt as positional argument (OpenCode, Codex)

## SpawnParams

The canonical input to every harness command build:
- `prompt`, `model`, `effort`, `skills`, `agent`
- `adhoc_agent_payload` — pre-built native agent JSON (Claude only)
- `extra_args` — passthrough CLI args
- `project_root`, `mcp_tools`, `interactive`
- `continue_harness_session_id`, `continue_fork` — session continuity
- `appended_system_prompt` — launch-layer injected startup context for Claude (skills plus primary-session `Meridian Agents` inventory)
- `report_output_path` — for harnesses supporting `-o` style report output (Codex)

## Registry

`HarnessRegistry` (`registry.py`) maps `HarnessId` to adapter instances. The default registry registers Claude, Codex, OpenCode, and Direct. Adding a harness = one adapter file + one `register()` call in `with_defaults()`.

The global singleton is created lazily via `get_default_harness_registry()`.

## Stream Events

Subprocess harnesses produce JSON stream output. `parse_json_stream_event()` in `common.py` parses each line into a `StreamEvent`. Lines that aren't valid JSON are wrapped as `event_type="line"`. Meridian protocol events (`spawn.*` or `meridian.spawn.*`) are categorized as `"sub-run"` and get synthesized text summaries.

## Why This Design

Adding a harness shouldn't touch any shared code — only the adapter and the registry registration. The `StrategyMap` invariant enforces that new `SpawnParams` fields are consciously handled (or explicitly dropped) in every adapter. The capability flags let the launch layer make harness-sensitive decisions without adapter-specific conditionals.

Primary launch inventory is one example of that harness-sensitive split:
- Claude receives the installed agent catalog through `appended_system_prompt`
- Codex and OpenCode receive the same agent catalog inline in the primary prompt text
