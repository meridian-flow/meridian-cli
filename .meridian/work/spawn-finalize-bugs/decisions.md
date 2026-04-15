# Decisions: spawn-finalize-bugs

## D-01: B-01 approach — turn/completed as terminal
Treat Codex `turn/completed` for tracked turnId as terminal in `_terminal_event_outcome()`. No declared-spawn-shape API needed. Research (p1843) confirmed turn lifecycle is the correct one-shot completion signal for Codex app-server. Alternatives rejected: idle timeout (fragile, unnecessary), declared spawn shape API (over-engineered for the current need).

## D-02: B-02 approach — drain finally consults cancel_sent
Add `session.cancel_sent` check in drain loop `finally` block before the `succeeded` default. This is more robust than moving `_resolve_completion_future` before `send_cancel` in `stop_spawn` — the drain loop itself should know about cancel state regardless of timing.

## D-03: B-03 approach — error/connectionClosed → failed
Add `error/connectionClosed` → `failed` in `_terminal_event_outcome()`. Connection closed without a prior terminal event is abnormal termination.

## D-04: B-04 approach — scope validation handler
Scope `_validation_error_handler` to "mutually exclusive" messages only. Let other ValidationErrors flow through as default 422. Simplest and most targeted fix.

## D-05: B-05 approach — delete report create
Delete `meridian spawn report create` + MCP `report_create` tool. Auto-extracted report from final message is canonical. 0 actual usages in corpus. Keep `report.show` and `report.search`. Update `prompt.py` to tell agents to emit report as final message instead of calling the CLI.

## D-06: Cycle 2 — skip formal planner, direct implementation
Three well-scoped items with clear root causes and fix shapes from prior investigation. Two phases: (1) drain-loop fix + SIGKILL cleanup in spawn_manager.py, (2) one-way executor deletion in runner.py/execute.py. Phases can parallelize since they touch different files. Formal planner adds overhead without value here.

## D-07: _terminal_event_outcome extraction approach
Move `_terminal_event_outcome` and `_TerminalEventOutcome` from streaming_runner.py (private) to a shared location importable by both streaming_runner.py and spawn_manager.py. Options: (a) new file in streaming/, (b) make them public in streaming_runner.py and import. Going with (b) — rename to public, import in spawn_manager. Simpler than a new file for two symbols. The function is already well-isolated.

## D-08: Drain loop terminal event precedence
In finally block: drain_cancelled > drain_error > cancel_sent > recorded_terminal_outcome > default succeeded/0. Terminal outcome from events overrides the blind succeeded default but yields to explicit cancel/error signals.

## D-09: Drain loop must break on terminal event, not just record
Smoke falsified B-01/B-03. Root cause: drain loop records terminal outcome but doesn't exit the `async for`. For Codex, WS stays open after turn/completed → loop never reaches `finally`. For Claude on app path, subprocess exits and closes stdout → loop exits naturally → but the recorded outcome approach works for Claude already. Codex and any persistent-connection harness needs the loop to `break` when a terminal event is detected.

Fix: after recording `recorded_terminal_outcome`, break out of the loop. `_cleanup_completed_session` handles connection cleanup. This mirrors what CLI path does: `_consume_subscriber_events` sets terminal_event_future, then `execute_with_streaming` calls `stop_spawn()`.

## D-10: Default to failed when no terminal event observed
When the drain loop exits its `async for` without recording a terminal outcome and without cancel, default to `failed` instead of `succeeded`. Rationale: a normal completion ALWAYS emits a terminal event (Claude `result`, Codex `turn/completed`, OpenCode `session.idle`). If the connection closed without one, something went wrong (SIGKILL, crash, protocol error). Defaulting to `succeeded` is the root of B-03 on Claude (where the `error` event from subprocess exit is not recognized as terminal, but the `async for` exits because stdout EOF). This is a safer default — false `failed` is detectable and recoverable, false `succeeded` silently loses the failure signal.
