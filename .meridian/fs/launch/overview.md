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

2a. run_harness_process()            [process.py] — PRIMARY PATH
   - Allocate session (session_store)
   - Register spawn as queued → started (spawn_store)
     runner_pid=os.getpid() recorded in start event
   - Attach to work item
   - _run_primary_process_with_capture() via PTY or subprocess.Popen
   - record_spawn_exited() written immediately after harness process exits
   - On exit: resolve_execution_terminal_state() from exit code +
     has_durable_report_completion() check (no enrich_finalize)
     Special case: exit codes 143/-15 (SIGTERM) with a durable report →
     terminated_after_completion=True → resolved as succeeded
   - Finalize spawn state (succeeded / failed / cancelled)
   - extract_latest_session_id() for harness session persistence

2b. spawn_and_stream()               [runner.py] — SPAWN/SUBAGENT PATH
   - Async subprocess execution with stdout/stderr capture
   - Heartbeat task started when worker PID is known; touches heartbeat artifact every 30s
   - Report watchdog, stdin feeding
   - record_spawn_exited() written immediately after process exits, before enrich_finalize
   - On exit: enrich_finalize() extracts report, usage, session ID
   - Retry handling (guardrails, retry backoff)
   - mark_finalizing() CAS: transitions running → finalizing under flock, in finalization
     finally block, after drain/report work and retry handling, immediately before finalize_spawn
   - finalize_spawn(origin="runner") — terminal state
   - Heartbeat task cancelled in outer finally (after finalize_spawn returns or raises)

3. enrich_finalize()                 [extract.py] — SPAWN PATH ONLY
   - adapter.extract_usage() → TokenUsage
   - adapter.extract_session_id() → harness session ID
   - extract_or_fallback_report() [report.py] → report text
   - Persist report.md atomically
   - NOT used on the primary launch path
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
  command.py         — build_launch_env(); normalize_system_prompt_passthrough_args()
  env.py             — build_harness_child_env() (env sanitization for child processes)
  default_agent_policy.py — fallback chain when no agent profile requested
  errors.py          — ErrorCategory; classify_error(); should_retry()
  types.py           — LaunchRequest, LaunchResult, SessionMode, SessionIntent, ...
```

## Design Notes

**Policy vs mechanism split**: `launch_primary()` resolves work-item attachment and policy. `process.py` is pure mechanism — it manages subprocesses, state writes, and artifact persistence without caring about work items or overrides.

**Two-pass policy resolution**: `resolve_policies()` runs a pre-profile merge first to select the agent profile, then re-merges with the profile's overrides. Required because the profile may specify a model/harness that needs to win over config defaults, but profile selection itself may depend on the pre-profile resolved agent name.

**Crash tolerance**: The runner writes a `heartbeat` artifact every 30s for the full active window (`running` + `finalizing`). The reaper uses heartbeat recency as its primary liveness signal; psutil `runner_pid` liveness is a secondary check (skipped entirely for `finalizing` rows). A `mark_finalizing` CAS after drain/report work (immediately before `finalize_spawn`) lets the reaper distinguish `orphan_finalization` (runner entered controlled drain but crashed before writing terminal state) from `orphan_run` (crashed during execution) — the distinction is a lifecycle fact, not an `exited_at` heuristic. If the runner reports a terminal state after the reaper has already stamped an orphan, the runner's `origin="runner"` finalize supersedes the reconciler stamp via the projection authority rule. See `state/spawns.md` for full projection and reaper logic.

## Related Docs

- `launch/process.md` — subprocess management, signals, timeouts, exited event recording
- `launch/prompt.md` — prompt assembly, skill injection, template variables
- `launch/reports.md` — report extraction, fallback chain, auto-extracted reports
- `state/spawns.md` — spawn store, event model, terminal merging
- `catalog/agents-and-skills.md` — profile and skill loading
