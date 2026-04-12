# launch/process — Subprocess Management

## run_harness_process()

`run_harness_process(plan, harness_registry)` in `process.py` is the synchronous entry point for primary (CLI) launches. It owns the full lifecycle: session allocation → subprocess execution → state finalization.

### Execution Path

```
1. _resolve_command_and_session(plan)
   - For FORK mode + Codex: materializes the fork by calling adapter.fork_session()
   - Returns (command, resolved_harness_session_id, run_params)

2. start_session() [session_store]
   - Allocates chat_id (c1, c2, ...)
   - Acquires session lock + lease file

3. spawn_store.start_spawn() → registers spawn as queued
   - runner_pid=os.getpid() recorded in start event

4. update_session_work_id() if work_id set

5. _run_primary_process_with_capture()
   - PTY mode (if stdin is a tty): pty.fork() + _copy_primary_pty_output()
   - Pipe mode (non-interactive): subprocess.Popen (no runner.py involved)

5.5. spawn_store.record_spawn_exited() — exited event written immediately after process exits
   - Wrapped in suppress(Exception) so disk errors don't block finalization
   - Carries raw exit code and timestamp; spawn status stays "running" until finalize

6. Finalization (inline, no enrich_finalize)
   - has_durable_report_completion() checks if report.md exists with completion marker
   - resolve_execution_terminal_state() maps exit code + report presence → status
   - extract_latest_session_id() discovers harness session post-launch
   - spawn_store.finalize_spawn() → terminal state

7. stop_session() [session_store]
```

## Primary PTY Mode

When running with a real terminal (`os.isatty(stdin)`), `process.py` spawns the harness in a PTY. `_copy_primary_pty_output()` runs a select loop forwarding:
- PTY master → stdout + `output.jsonl` log
- stdin → PTY master

Window resize signals (`SIGWINCH`) are forwarded via `_install_winsize_forwarding()`.  
The parent stdin is set to raw mode for the duration.  
Output is written to `.meridian/spawns/<id>/output.jsonl`.

**Note:** The primary path does NOT call `enrich_finalize()`. That pipeline (usage extraction, session ID extraction, report fallback) is exclusive to the spawn/subagent path in `runner.py`. The primary path finalizes from exit code + durable report checks directly in `process.py`.

## Async Subprocess Execution (runner.py)

`spawn_and_stream()` in `runner.py` is the async subprocess runner for subagent spawns (non-primary). Key behaviors:

- Captures stdout → `output.jsonl`, stderr → `stderr.log`
- Feeds stdin from `run_params.stdin_prompt` if set (for stdin-based prompt delivery)
- Runs a report watchdog: if `report.md` appears during execution, can consider spawn done
- Maps raw return codes to meridian exit codes via `map_process_exit_code()`
- After `spawn_and_stream` returns, `execute_with_finalization()` writes the `exited` event inline (via `record_spawn_exited`), then calls `enrich_finalize()` to extract and persist artifacts

## Signal Handling

`SignalForwarder` and `SignalCoordinator` in `signals.py`:

- `SignalCoordinator` is a process-global singleton managing SIGINT/SIGTERM handlers
- `SignalForwarder` registers with the coordinator for the duration of a subprocess run
- On first SIGINT/SIGTERM: forwarded to child process group via `os.killpg(pgid, signum)`
- On second signal: escalates to SIGKILL immediately
- When no forwarders are registered, previous signal handlers are restored

`SignalCoordinator.mask_sigterm()` context manager suppresses SIGTERM during critical sections (e.g., final state writes).

## Timeout Handling

`timeout.py` provides:

```python
terminate_process(process, grace_seconds=DEFAULT_KILL_GRACE_SECONDS)
  # Sends SIGTERM, waits grace_seconds, then SIGKILL

wait_for_process_exit(process, timeout_seconds)
  # Returns exit code or raises SpawnTimeoutError

wait_for_process_returncode(process, timeout_seconds)
  # Non-raising variant; returns None on timeout
```

Default kill grace is `config.kill_grace_minutes * 60` (default: 2 seconds).  
Guardrail timeout: `config.guardrail_timeout_minutes * 60` (default: 30 seconds) — used by the safety guardrails layer.

## Artifact Outputs

Each spawn writes to `.meridian/spawns/<id>/`:
- `output.jsonl` — harness stdout (JSONL stream events or raw text)
- `stderr.log` — harness stderr
- `tokens.json` — token usage (extracted from output stream)
- `report.md` — extracted report (written by `enrich_finalize()`)

Spawn directories contain only durable artifacts. Runtime coordination (PIDs, exit status, timestamps) lives exclusively in the `spawns.jsonl` event stream. No PID files, heartbeat files, or marker files are written to disk.

## Error Classification

`errors.py` classifies subprocess failures:

- `ErrorCategory.INFRA` — meridian-level error (process didn't start, OOM, etc.)
- `ErrorCategory.HARNESS` — harness exited non-zero
- `should_retry(exit_code, category)` — whether to attempt retry

Retries are controlled by `config.max_retries` and `config.retry_backoff_seconds`.
