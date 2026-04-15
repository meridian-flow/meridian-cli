# Edge Cases and Failure Modes

This document enumerates failure modes, boundary conditions, and error propagation behavior across all three phases. Every case must have a defined behavior — "undefined" is not acceptable even when the behavior is "degrade gracefully."

## Harness Subprocess Dies Mid-Turn

**Scenario**: The Claude/Codex/OpenCode subprocess crashes, is OOM-killed, or exits unexpectedly while the user is watching the activity stream.

**Phase 1 behavior**:
1. The transport (WebSocket or HTTP) raises a connection-closed exception
2. `HarnessConnection.events()` iterator yields a final `HarnessEvent(event_type="error", payload={"message": "harness process exited unexpectedly", "exit_code": N})`
3. The iterator completes (StopAsyncIteration)
4. `SpawnManager` marks the spawn as `failed` in `spawn_store.finalize_spawn()`
5. Control socket server for this spawn is shut down
6. Heartbeat file stops being touched

**Phase 2 behavior**:
1. The outbound task sees the error event from Phase 1
2. Sends `RunErrorEvent(message="harness process exited unexpectedly (exit code N)")` to the WebSocket client
3. Sends WebSocket close frame
4. Does NOT send `RUN_FINISHED` — the error event is the terminal event

**Phase 3 behavior**:
1. The `RUN_ERROR` event dispatches through the reducer: `isStreaming = false`, `error = "harness process exited..."`, `isCancelled = false`
2. UI shows an error banner with the message
3. Send button is disabled (spawn is dead)
4. User can start a new spawn

## Client Disconnects Mid-Stream

**Scenario**: The user closes the browser tab, navigates away, or the WebSocket connection drops while the harness is actively working.

**Behavior**: The spawn **continues running**. The harness subprocess is not killed on client disconnect.

**Rationale**: The spawn may be doing useful work (writing files, running tests). Killing it because the viewer disconnected would lose that work. The spawn will finish naturally, and `meridian spawn show` / `meridian spawn log` will show the results.

**Phase 1 behavior**: The durable drain task continues reading `connection.events()` and persisting to `output.jsonl` regardless of UI client state. The drain task is owned by `SpawnManager`, not by any UI client.

**Phase 2 behavior**:
1. The `inbound` task gets a `WebSocketDisconnect` exception
2. The `outbound` task gets a `WebSocketDisconnect` when it next tries to send
3. Both tasks end; `finally` block calls `manager.unsubscribe(spawn_id)` to remove the subscriber queue
4. The drain task in `SpawnManager` continues draining events to `output.jsonl` — it does not depend on any subscriber existing
5. When the harness finishes, the spawn is finalized normally

**Reconnect**: Not supported in MVP. If the user opens a new browser tab to `meridian app`, they can see active spawns in the spawn list and reconnect by clicking one. The reconnected WebSocket subscribes to the drain's fan-out for new events — it does NOT replay events from before the disconnect. Lost events are available in `meridian spawn log <spawn_id>`.

## Inbound Message During Mid-Tool-Execution

**Scenario**: User sends `user_message` while the harness is executing a tool (e.g., running a bash command).

**Per-harness behavior**:

| Harness | What happens |
|---|---|
| Claude (queue) | Message is delivered via WS. Claude queues it and processes it after the current tool completes and the current turn ends. Effectively a no-op until the next turn boundary. |
| Codex (steer) | If in-flight turn is active, `turn/steer` appends the message to the in-flight turn. The agent sees it as additional context within the current turn. If between turns, `turn/start` begins a new turn. |
| OpenCode (http_post) | `POST /session/:id/message` is accepted. OpenCode queues it for when the current processing completes. |

**None of these reject the message.** The adapter always accepts the delivery — the harness handles queuing/timing internally.

**Phase 2 behavior**: `inject()` returns `InjectResult(success=True)` regardless of whether the harness is mid-tool. The user sees no error. The UI may optionally show a "message queued" indicator based on capabilities.

## Adapter Starts But Harness Refuses to Produce RUN_STARTED

**Scenario**: The harness subprocess starts but doesn't connect (Claude never connects to our WS server) or doesn't respond (Codex never sends `initialize` response).

**Behavior**: Connection timeout.

**Phase 1**:
1. `HarnessConnection.start()` has a configurable timeout (default: 30 seconds)
2. If the harness doesn't establish the bidirectional channel within the timeout, `start()` raises `ConnectionTimeout`
3. `SpawnManager` marks the spawn as `failed` with reason "harness did not connect within timeout"
4. The harness subprocess is killed

**Phase 2**: The WebSocket endpoint reports the failure:
```json
{"type": "RUN_ERROR", "message": "harness did not connect within 30s"}
```

**Phase 3**: Error banner shown. User can retry.

## Two Processes Attempt to Control the Same Spawn

**Scenario**: Both `meridian app` (via WebSocket) and `meridian spawn inject` (via control socket) send a message to the same spawn at the same time.

**MVP behavior**: Last-writer-wins at the transport level. Both messages are delivered to the harness in whatever order they arrive. The harness processes them sequentially.

**Why this is acceptable**: MVP is single-user, localhost. The user is either using the UI or the CLI, not both simultaneously in a race-critical way. If they do use both, both messages arrive — there's no data corruption, just potentially surprising ordering.

**Post-MVP**: If this becomes a real problem, add a simple sequence counter to the control protocol so the adapter can detect and warn about concurrent controllers.

## WebSocket Reconnect After Process Restart

**Scenario**: The `meridian app` process crashes and the user restarts it. Active spawns from the previous process are orphaned.

**Phase 1 behavior**: Orphaned spawns are detected by `meridian doctor` (existing behavior — heartbeat stops, orphan reconciliation kicks in). The new `meridian app` process starts fresh — it does not attempt to reattach to orphaned harness subprocesses.

**Phase 3 behavior**: The UI shows no active spawns on fresh start. The user starts a new spawn. Orphaned spawns appear in `meridian spawn list` with appropriate status.

**Post-MVP**: Session persistence and spawn reattachment are tracked in `post-mvp-cleanup`.

## Harness Output Exceeds Memory

**Scenario**: A harness produces an enormous amount of output (e.g., a bash tool that `cat`s a large file, or a tool that generates a large image as base64).

**Phase 1 behavior**: Events are streamed, not accumulated. `HarnessConnection.events()` yields one event at a time — backpressure is handled by asyncio's flow control on the WebSocket/HTTP transport.

**Phase 2 behavior**: Each AG-UI event is sent as a separate WebSocket frame. No accumulation of the full output.

**Phase 3 behavior**: The reducer accumulates `TextMessageContent` deltas in memory (in the `items[]` array). For extremely large text blocks, this could cause browser memory pressure. **Mitigation**: tool output that exceeds a threshold (e.g., 100KB) is truncated in the UI with a "show full output" link that reads from `output.jsonl`.

## Malformed Harness Events

**Scenario**: The harness sends a wire event that doesn't parse as valid JSON, or parses but has unexpected structure.

**Phase 1 behavior**: The adapter logs the malformed event and skips it. The `events()` iterator does not yield a `HarnessEvent` for unparseable input. The raw text is logged to `stderr.log` for debugging.

**Phase 2 behavior**: Mapper's `translate()` returns an empty list for events it can't map. No AG-UI event is sent to the client.

**Phase 3 behavior**: UI doesn't see the event — no impact.

## Control Socket Left Behind After Crash

**Scenario**: The `meridian app` process is killed with SIGKILL (or crashes hard) and the control socket file at `.meridian/spawns/<spawn_id>/control.sock` is not cleaned up.

**Behavior**: The next process that tries to create a control socket at the same path calls `socket_path.unlink(missing_ok=True)` before `start_unix_server()`. Stale socket files are harmlessly cleaned up.

Additionally, `meridian spawn inject` connecting to a stale socket will get `ConnectionRefusedError` and report "spawn not found or not running."

## Concurrent WebSocket Clients for the Same Spawn

**Scenario**: Two browser tabs connect to `/ws/spawn/{spawn_id}` simultaneously.

**MVP behavior**: One UI client per spawn. The second connection is rejected with a clear error:
```json
{"type": "RUN_ERROR", "message": "another client is already connected to this spawn"}
```

The first client holds the subscription. The drain task feeds events to exactly one subscriber queue.

**Why not multi-client fan-out for MVP**: The drain architecture supports fan-out (multiple queues fed by the drain task), but the MVP is single-user localhost. Adding multi-subscriber bookkeeping, per-subscriber backpressure, and subscriber lifecycle management is complexity without a user need. The subscriber set in `SpawnManager` is designed to extend to `dict[SpawnId, list[Queue]]` post-MVP when the use case materializes.

**Post-MVP**: Extend `subscribe()` to support multiple concurrent subscribers per spawn. Each gets an independent `asyncio.Queue` fed by the drain task.

## Port Conflicts

**Scenario**: The auto-assigned port for the WS server (Claude) or the Codex app-server conflicts with an existing service.

**Behavior**: Port 0 (auto-assign) makes this nearly impossible for the Meridian-side server. For Codex, if its `--listen` port conflicts, Codex will fail to start and the adapter will surface the error via `ConnectionTimeout` or a more specific error from Codex's stderr.

## Agent Profile Loading

**Scenario**: The user selects an agent profile in the UI, but `.agents/` is out of sync or the profile doesn't exist.

**Phase 2 behavior**: The `POST /api/spawn` endpoint validates the agent profile exists before launching. Returns 400 with a clear error if not found.

**Phase 3 behavior**: The spawn selector grays out unavailable profiles or shows a warning.

## Large Initial Prompt

**Scenario**: The user pastes a very large initial prompt (e.g., 100KB of text).

**Behavior**: The prompt is delivered to the harness as-is. Claude and OpenCode handle large prompts natively. Codex has a prompt-from-stdin mode for `codex exec` but the app-server's `turn/start` sends the prompt as a JSON field — extremely large prompts may hit JSON-RPC message size limits. **Mitigation**: the adapter truncates the `turn/start` prompt and logs a warning if it exceeds 50KB, advising the user to use file references instead.
