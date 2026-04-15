# Investigation Lane B: Finalize-Path Bug Family

**Investigator**: p-investigator  
**Scope**: Read-only diagnosis of B-01, B-02, B-03, B-04  
**Hypothesis under test**: The finalizer reads the wrong source of truth for exit classification — harness subprocess exit / connection-close rather than stream cancel/exit events.

## Verdict Summary

| Bug | Root Cause | Same Family? | Confidence |
|-----|-----------|--------------|------------|
| B-01 | Drain loop never terminates for persistent-session harnesses (Codex) | **Yes** — drain loop is the source of truth, and it never produces a DrainOutcome | High |
| B-02 | Drain loop resolves DrainOutcome *before* `stop_spawn()` can set the cancelled status | **Yes** — drain loop's default "clean exit = succeeded" wins the race | High |
| B-03 | Same as B-01/B-02 — drain loop sees clean connection close after SIGKILL, reports succeeded | **Yes** — SIGKILL kills worker, WS closes cleanly, drain loop → succeeded | High |
| B-04 | Pydantic `model_validator` ValueError intercept downgrades 422 → 400 | **No** — unrelated, app server validation handler bug | High |

**The hypothesis is confirmed with refinement**: B-01, B-02, B-03 are one bug family. The root cause is not simply "reads the wrong source" — it's that **the drain loop in SpawnManager is the sole authority for DrainOutcome, and its `finally` block has no awareness of cancel events, idle state, or abnormal termination**. It classifies every clean connection close as `succeeded/0`.

---

## B-01: Idle → finalized never fires

### Observed behavior
Agent completes work (Codex emits `turn/completed` + `thread/status/changed idle`), but spawn stays `running` indefinitely.

### Root cause chain

1. **`_terminal_event_outcome()` explicitly ignores Codex `turn/completed`**  
   `streaming_runner.py:246-248`:
   ```python
   if event.harness_id == HarnessId.CODEX.value and event.event_type == "turn/completed":
       # Codex turn completion is per-turn state, not spawn/session terminal state.
       return None
   ```
   This is correct per the Codex protocol — turns can repeat. But nothing else detects idle.

2. **No handler for `thread/status/changed idle`**  
   `_terminal_event_outcome()` has no case for `thread/status/changed` at all. It only recognizes:
   - Claude: `result` (line 250)
   - OpenCode: `session.idle`, `session.error` (lines 276-290)
   - Codex: nothing — `turn/completed` is explicitly skipped, and no other Codex event is terminal.

3. **Codex WS connection stays open after idle**  
   Unlike Claude (subprocess exits after `result`, closing stdout, ending `events()` generator at `claude_ws.py:221-230`), Codex keeps its WebSocket alive after `turn/completed`. The `_read_messages_loop()` at `codex_ws.py:470-545` blocks on `async for raw_message in ws:` indefinitely.

4. **Drain loop blocks forever**  
   `spawn_manager.py:267`: `async for event in receiver.events()` never exits because the Codex connection's `events()` queue never gets the `None` sentinel (`codex_ws.py:545` only runs in `finally` when the reader task ends).

5. **`completion_future` never resolves**  
   The drain loop's `finally` block (`spawn_manager.py:326-354`) is the only place that calls `_resolve_completion_future()`. Since drain never exits, the future never resolves.

6. **`_background_finalize()` blocks forever**  
   `server.py:199-211`: `outcome = await spawn_manager.wait_for_completion(spawn_id)` waits on the completion_future, which is stuck.

7. **Heartbeat keeps ticking**  
   The heartbeat task (started at `server.py:340`) keeps touching the heartbeat file every 30s, so the reaper sees `recent_activity` and returns `Skip(reason="recent_activity")` at `reaper.py:168-169` or `reaper.py:151-152`.

### Why the reaper can't save this
The reaper checks `runner_pid_alive` at `reaper.py:167`. For app spawns, `runner_pid` is the FastAPI server process (`server.py:232`: `runner_pid=os.getpid()`), which is alive. The heartbeat keeps updating. So the reaper correctly skips it — but that means nothing ever finalizes the spawn.

### Concrete fix target
`_terminal_event_outcome()` at `streaming_runner.py:245-292` needs a Codex idle-detection case. The event `thread/status/changed` with payload `{"status": "idle"}` (or equivalent) should map to `_TerminalEventOutcome(status="succeeded", exit_code=0)`. Alternatively, the drain loop or a side task needs a Codex-specific idle timeout that calls `manager.stop_spawn()`.

---

## B-02: Cancel origin mis-tagged

### Observed behavior
HTTP and CLI cancel both finalize spawns as `{status: succeeded, exit_code: 0}` despite the stream having emitted `cancelled`/`143`.

### Root cause chain

1. **Cancel calls `stop_spawn()` correctly**  
   `signal_canceller.py:122-127` (app cancel):
   ```python
   await self._manager.stop_spawn(
       spawn_id,
       status="cancelled",
       exit_code=143,
       error="cancelled",
   )
   ```
   This is correct — it passes `status="cancelled"`.

2. **`stop_spawn()` tries to resolve completion_future with cancelled status**  
   `spawn_manager.py:547-555`:
   ```python
   outcome = self._resolve_completion_future(
       session,
       DrainOutcome(status="cancelled", exit_code=143, error="cancelled", ...),
   )
   ```

3. **BUT: `_resolve_completion_future()` is first-writer-wins**  
   `spawn_manager.py:695-705`:
   ```python
   def _resolve_completion_future(self, session, outcome):
       if not session.completion_future.done():
           with suppress(asyncio.InvalidStateError):
               session.completion_future.set_result(outcome)
       if session.completion_future.done() and not session.completion_future.cancelled():
           return session.completion_future.result()
       return outcome
   ```
   If the future is **already resolved**, the passed-in outcome is ignored.

4. **The race: drain loop finalizes FIRST**  
   When `stop_spawn()` is called:
   - It calls `session.connection.send_cancel()` (`spawn_manager.py:537`)
   - It calls `session.connection.stop()` (`spawn_manager.py:561`)
   - It cancels `drain_task` (`spawn_manager.py:563`)
   
   The `connection.stop()` closes the WebSocket/process. This causes the drain loop's `async for event in receiver.events()` to exit naturally (not via CancelledError). The drain loop's `finally` block (`spawn_manager.py:326-354`) then runs:
   
   ```python
   # Line 343-348: No cancel, no error → succeeded
   else:
       outcome = DrainOutcome(
           status="succeeded",
           exit_code=0,
           ...
       )
   self._resolve_completion_future(session, outcome)  # First writer wins!
   ```
   
   The drain loop writes `succeeded/0` to the future **before** `stop_spawn()`'s `_resolve_completion_future()` call at line 547.

5. **`_background_finalize()` reads the already-resolved future**  
   `server.py:200-211`: Gets `DrainOutcome(status="succeeded", exit_code=0)`, writes it as `origin="runner"`.

6. **The `cancelled` terminal event is emitted but never consumed**  
   `stop_spawn()` at `spawn_manager.py:538-544` does emit a cancelled event to `output.jsonl` via `_emit_cancelled_terminal_event()`, but by this point the drain loop has already exited and the subscriber has been fanned out `None`. The terminal event is persisted to disk but is never read by the finalizer.

### Why the streaming runner's terminal event detection doesn't help for app spawns
For CLI spawns using `execute_with_streaming()`, the `_consume_subscriber_events()` task watches the subscriber queue and feeds `terminal_event_future`. But `_background_finalize()` in the app server doesn't use terminal event detection at all — it relies solely on `DrainOutcome` from the completion future.

### Concrete fix target
Two options:
1. **`stop_spawn()` should set the completion future BEFORE stopping the connection**, not after. Move the `_resolve_completion_future()` call at line 547 to before line 537 (`send_cancel`).
2. **Drain loop's `finally` should check `session.cancel_sent`** and produce `cancelled` status instead of `succeeded` when a cancel was requested.

Option 2 is more robust — it ensures the drain loop itself knows about the cancel, regardless of timing.

---

## B-03: SIGKILL classified as succeeded

### Observed behavior
Worker SIGKILL on an app-run spawn finalizes as `{status: succeeded, duration_secs: 9.6}` with only in-progress `sleep 120` + `error/connectionClosed` in `output.jsonl`.

### Root cause chain

This is B-02 with a different trigger:

1. **SIGKILL kills the Codex worker process**  
   The Codex subprocess is killed, which closes its WebSocket connection.

2. **Codex `_read_messages_loop()` catches the connection close**  
   `codex_ws.py:532-541`: The exception from the closed WebSocket is caught, an `error/connectionClosed` event is emitted to the queue, and the `finally` block at line 543-545 puts `None` sentinel.

3. **Drain loop receives `error/connectionClosed` then `None`**  
   The drain loop at `spawn_manager.py:267` processes the error event, then gets `None` and exits the `async for`. Since the loop exits normally (no `CancelledError`, no exception), the `finally` block classifies this as:
   ```python
   # spawn_manager.py:343-348
   else:  # no drain_cancelled, no drain_error
       outcome = DrainOutcome(status="succeeded", exit_code=0, ...)
   ```

4. **`_background_finalize()` writes `succeeded/0`**

### Why `error/connectionClosed` doesn't trigger failure
`_terminal_event_outcome()` at `streaming_runner.py:245-292` has **no case for `error/connectionClosed`**. It only matches:
- Claude: `result`
- Codex: `turn/completed` (ignored)
- OpenCode: `session.idle`, `session.error`

The `error/connectionClosed` event is Codex-specific and falls through to `return None` at line 292.

### Why the drain loop doesn't see this as an error
The `error/connectionClosed` event is emitted by the Codex connection as a regular `HarnessEvent` and placed in the `_event_queue`. From the drain loop's perspective, it's just another event to persist and fan out. The drain loop only sets `drain_error` if an **exception is raised** during `async for event in receiver.events()` (`spawn_manager.py:323-324`), which doesn't happen here — the connection gracefully queues the error event then queues `None`.

### Why the reaper doesn't catch it
Same as B-01: the heartbeat was recently touched (within the last 30s), and `_has_recent_activity()` returns `True` at `reaper.py:172`. Even after the heartbeat goes stale (120s window), the runner process (FastAPI server) is still alive, so `runner_pid_alive` is `True` at `reaper.py:167`, leading to `Skip(reason="runner_alive")` at `reaper.py:170`.

Wait — actually, by the time the reaper runs (120s later), the `_background_finalize()` has already written `succeeded/0`. So the spawn is already terminal. The reaper never gets a chance.

### Concrete fix target
Same fix family as B-02. The drain loop's `finally` block needs to distinguish "connection closed cleanly after successful work" from "connection closed unexpectedly". Options:
1. Check if the last event was `error/connectionClosed` and classify as `failed`.
2. Track whether a terminal event was ever received; if not, and the connection closed, classify as `failed`.
3. The consumer/streaming_runner should recognize `error/connectionClosed` as a terminal failure event.

Option 3 is the cleanest: add `error/connectionClosed` to `_terminal_event_outcome()` as a `failed` outcome.

---

## B-04: `/inject` missing-field returns 400 instead of 422

### Observed behavior
`POST /api/spawns/{id}/inject` with missing required field returns `400 Bad Request` instead of `422 Unprocessable Entity`.

### Root cause

This is completely unrelated to B-01/B-02/B-03. It's a validation handler bug.

1. **Pydantic model with `model_validator`**  
   `server.py:99-112`:
   ```python
   class InjectRequest(BaseModel):
       text: str | None = None
       interrupt: bool = False
   
       @model_validator(mode="after")
       def _exactly_one(self) -> InjectRequest:
           text_set = self.text is not None and self.text.strip() != ""
           if text_set and self.interrupt:
               raise ValueError("text and interrupt are mutually exclusive")
           if not text_set and not self.interrupt:
               raise ValueError("provide text or interrupt: true")
           return self
   ```
   
   Both fields are optional with defaults (`text: str | None = None`, `interrupt: bool = False`). An empty body `{}` passes schema validation (no missing required fields), then hits the `model_validator` which raises `ValueError("provide text or interrupt: true")`.

2. **Custom validation error handler intercepts the ValueError**  
   `server.py:168-191`:
   ```python
   async def _validation_error_handler(request, exc):
       error_factory = getattr(exc, "errors", None)
       if callable(error_factory):
           error_items = cast("list[object]", error_factory())
           for error_item in error_items:
               ...
               underlying_error = context.get("error")
               if isinstance(underlying_error, ValueError):
                   return json_response_cls(
                       status_code=400,
                       content={"detail": str(underlying_error)},
                   )
       return await request_validation_exception_handler(request, exc)
   ```
   
   This handler is registered for **all** `RequestValidationError` exceptions (`server.py:191`). It checks if any error item wraps a `ValueError` and, if so, returns 400 instead of letting FastAPI's default handler return 422.

3. **The design intent is clear but the implementation is wrong**  
   The handler was meant to separate semantic errors (ValueError from `model_validator`) from schema errors (missing/wrong-type fields). But because `text` and `interrupt` both have defaults, the "missing field" case is **never** a schema error — it always passes schema validation and becomes a semantic `ValueError`. The handler then converts it to 400.

### Why no field is ever truly "missing"
The `InjectRequest` model defines `text: str | None = None` and `interrupt: bool = False`. Sending `{}` is valid according to the schema — both fields get their defaults. The emptiness check happens in the `model_validator`, which raises `ValueError`, which the custom handler catches and returns as 400.

### Concrete fix target
Either:
1. Make `text` required (remove `= None` default) so missing `text` triggers a true schema 422 before the validator runs. This changes the API contract.
2. Remove the `not text_set and not self.interrupt` case from the `model_validator` and handle it in the endpoint function, returning 422 explicitly.
3. The custom `_validation_error_handler` should only convert to 400 for the "mutually exclusive" case, not the "missing" case. Check the error message string.

Option 3 is simplest and most targeted.

---

## Unified Diagnosis: The Drain Loop Source-of-Truth Problem

B-01, B-02, and B-03 all converge on one structural issue: **the drain loop in `SpawnManager._drain_loop()` is the sole producer of `DrainOutcome`, and its classification logic in the `finally` block (`spawn_manager.py:326-354`) is too simplistic**.

The drain loop's classification decision tree:

```python
if drain_cancelled:          # asyncio.CancelledError caught
    outcome = DrainOutcome(status="cancelled", ...)
elif drain_error is not None: # Python exception caught
    outcome = DrainOutcome(status="failed", ...)
else:                         # Clean exit from async for
    outcome = DrainOutcome(status="succeeded", ...)
```

This means:
- **B-01**: Codex connection never closes → drain never reaches `finally` → no outcome ever
- **B-02**: Cancel closes connection gracefully → drain exits normally → `succeeded/0` written before cancel outcome can win
- **B-03**: SIGKILL closes connection → drain exits normally → `succeeded/0`

The `else` branch is the problem. A "clean" exit from the drain loop (no Python exception, no CancelledError) does NOT imply successful agent completion. It only means the connection closed without a crash. The drain loop needs additional signal to distinguish "agent completed work" from "connection closed for external reasons".

### What the drain loop should check in `finally`

The drain loop should consult `session.cancel_sent` and/or track whether a genuine terminal event was observed during the event stream. A minimal fix:

```python
# In the finally block of _drain_loop:
if drain_cancelled:
    outcome = DrainOutcome(status="cancelled", ...)
elif drain_error is not None:
    outcome = DrainOutcome(status="failed", ...)
elif session.cancel_sent:
    outcome = DrainOutcome(status="cancelled", exit_code=143, error="cancelled", ...)
else:
    outcome = DrainOutcome(status="succeeded", exit_code=0, ...)
```

This alone fixes B-02. For B-03, the drain loop needs to know whether an `error/connectionClosed` was the last meaningful event, or `_terminal_event_outcome()` needs to recognize it. For B-01, the terminal event detector needs a Codex idle case.

---

## Files Referenced

| File | Lines | Relevance |
|------|-------|-----------|
| `src/meridian/lib/streaming/spawn_manager.py` | 250-354 | Drain loop and DrainOutcome classification (root cause for B-01/02/03) |
| `src/meridian/lib/streaming/spawn_manager.py` | 518-575 | `stop_spawn()` — cancel path that races with drain loop |
| `src/meridian/lib/streaming/spawn_manager.py` | 695-705 | `_resolve_completion_future()` — first-writer-wins semantics |
| `src/meridian/lib/launch/streaming_runner.py` | 245-292 | `_terminal_event_outcome()` — missing Codex idle and error/connectionClosed |
| `src/meridian/lib/launch/streaming_runner.py` | 1186-1236 | `execute_with_streaming()` finally block — runner finalization |
| `src/meridian/lib/app/server.py` | 199-211 | `_background_finalize()` — blindly trusts DrainOutcome |
| `src/meridian/lib/app/server.py` | 99-112 | `InjectRequest` model — B-04 root cause |
| `src/meridian/lib/app/server.py` | 168-191 | `_validation_error_handler` — B-04 400/422 confusion |
| `src/meridian/lib/streaming/signal_canceller.py` | 114-138 | `_cancel_app_spawn()` — correct cancel intent, loses to drain race |
| `src/meridian/lib/state/reaper.py` | 145-179 | `decide_reconciliation()` — correctly skips, can't save B-01/02/03 |
| `src/meridian/lib/harness/connections/codex_ws.py` | 373-378 | `events()` — blocks on queue, never exits for idle Codex |
| `src/meridian/lib/harness/connections/codex_ws.py` | 470-545 | `_read_messages_loop()` — clean exit after connection close |
| `src/meridian/lib/harness/connections/claude_ws.py` | 197-261 | `events()` — exits on subprocess EOF (why Claude doesn't have B-01) |
| `src/meridian/lib/core/spawn_lifecycle.py` | 68-85 | `resolve_execution_terminal_state()` — CLI path, works correctly |
