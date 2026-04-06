# launch/ — Spawn Lifecycle Overview

## What This Is

`src/meridian/lib/launch/` owns the full lifecycle from "resolved spawn request" to "harness process exits and artifacts are persisted." It bridges the policy layer (ops/spawn/) and the mechanism layer (harness adapters, state stores).

## Lifecycle Phases

```
1. resolve_primary_launch_plan()     [plan.py]
   - Merge RuntimeOverrides layers (CLI > env > agent profile > config)
   - Resolve agent profile, skills, model, harness
   - Build command via adapter.build_command()
   - Result: ResolvedPrimaryLaunchPlan

2. run_harness_process()             [process.py]
   - Allocate session (session_store)
   - Register spawn as queued → started (spawn_store)
   - Write PID file, attach to work item
   - For primary CLI: spawn_and_stream() via PTY or pipe
   - For subagent spawns: spawn_and_stream() async [runner.py]
   - Heartbeat loop active throughout execution
   - On exit: enrich_finalize() extracts report, usage, session ID
   - Finalize spawn state (succeeded / failed / cancelled)

3. enrich_finalize()                 [extract.py]
   - adapter.extract_usage() → TokenUsage
   - adapter.extract_session_id() → harness session ID
   - extract_or_fallback_report() [report.py] → report text
   - Persist report.md atomically
```

## Entry Point

`launch_primary()` in `__init__.py`:
```python
def launch_primary(*, repo_root, request, harness_registry) -> LaunchResult
```

Resolves work-item attachment at the policy level (before entering `process.py`), then delegates to `run_harness_process()`. Returns `LaunchResult{command, exit_code, continue_ref, warning}`.

## Key Types

```python
LaunchRequest     — what to launch: model, agent, prompt, session mode, work_id, ...
ResolvedPolicies  — resolved agent profile, model, harness, adapter, skills, overrides
ResolvedPrimaryLaunchPlan — command tuple, run_params, state paths, session metadata
ProcessOutcome    — exit_code, chat_id, primary_spawn_id, resolved_harness_session_id
LaunchResult      — command, exit_code, continue_ref, warning (returned to CLI)
```

## Module Map

```
launch/
  __init__.py        — launch_primary() public entry point
  plan.py            — resolve_primary_launch_plan(); ResolvedPrimaryLaunchPlan
  resolve.py         — resolve_policies(); resolve_harness(); two-pass override merge
  process.py         — run_harness_process(); PTY/pipe copy; session/spawn lifecycle
  runner.py          — spawn_and_stream() async subprocess execution
  prompt.py          — compose_run_prompt(); skill injection; report instruction
  reference.py       — ReferenceFile loading; template variable resolution
  report.py          — extract_or_fallback_report(); report.md preference
  extract.py         — enrich_finalize() pipeline: usage + session + report
  signals.py         — SignalForwarder, SignalCoordinator; SIGINT/SIGTERM forwarding
  timeout.py         — wait_for_process_exit(); terminate_process() SIGTERM→SIGKILL
  heartbeat.py       — threaded/async heartbeat writer (30s interval, atomic writes)
  command.py         — build_launch_env(); normalize_system_prompt_passthrough_args()
  env.py             — build_harness_child_env() (env sanitization for child processes)
  default_agent_policy.py — fallback chain when no agent profile requested
  errors.py          — ErrorCategory; classify_error(); should_retry()
  types.py           — LaunchRequest, LaunchResult, SessionMode, SessionIntent, ...
```

## Design Notes

**Policy vs mechanism split**: `launch_primary()` resolves work-item attachment and policy. `process.py` is pure mechanism — it manages subprocesses, state writes, and artifact persistence without caring about work items or overrides.

**Two-pass policy resolution**: `resolve_policies()` runs a pre-profile merge first to select the agent profile, then re-merges with the profile's overrides. Required because the profile may specify a model/harness that needs to win over config defaults, but profile selection itself may depend on the pre-profile resolved agent name.

**Crash tolerance**: PID files + heartbeats mean a crashed meridian parent doesn't orphan state permanently. The reaper (`state/reaper.py`) detects stale spawns on read paths using PID liveness, heartbeat age, and durable report presence.

## Related Docs

- `launch/process.md` — subprocess management, signals, timeouts, heartbeat
- `launch/prompt.md` — prompt assembly, skill injection, template variables
- `launch/reports.md` — report extraction, fallback chain, auto-extracted reports
- `state/spawns.md` — spawn store, event model, terminal merging
- `catalog/agents-and-skills.md` — profile and skill loading
