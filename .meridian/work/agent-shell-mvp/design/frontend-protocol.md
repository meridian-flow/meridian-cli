# Frontend Protocol — WebSocket Contract

> **Status update (2026-04-08, p1135).** Two corrections from
> [`findings-harness-protocols.md`](../findings-harness-protocols.md):
>
> 1. `INJECT_USER_MESSAGE` is a **first-class V0 client→server command**,
>    not a V1 placeholder. Mid-turn steering is tier-1 across all three
>    primary harnesses.
> 2. The `mid_turn_injection` capability flag is a **semantic enum**
>    (`queue` / `interrupt_restart` / `http_post` / `none`), not a boolean.
>    The composer is enabled mid-turn whenever the value is anything other
>    than `none`, and the per-mode value drives a per-harness hint string.
>
> §2.2 SESSION_HELLO, §8 capability negotiation, and §10 edge cases are
> updated against the new shape.

> The wire contract between **frontend-v2** (React 19, in `frontend/`) and the
> **agent-shell FastAPI backend**. This is the joint protocol both sides
> implement; neither side owns it unilaterally.

## 1. Framing

The frontend is a **protocol client**, not a UI on top of a generic API. Its
activity-stream reducer (`src/features/activity-stream/streaming/reducer.ts`)
already consumes a fixed event vocabulary inherited from the biomedical-mvp
pivot. **The reducer is the contract.** Whatever the backend emits must reduce
into the existing `ActivityBlockData` shape, or the reducer must change in
lockstep.

Three consequences fall out of this framing:

1. **No "server dictates protocol".** Any change to the wire format is a joint
   PR: server emit code + reducer case + the type union in
   `src/features/activity-stream/types.ts`. Treat the contract like a shared
   header file.
2. **Adoption over reinvention.** The biomedical-mvp pivot already iterated
   this contract to a stable shape (`TOOL_OUTPUT`, `DISPLAY_RESULT`,
   `TOOL_CALL_RESULT` lifecycle). V0 adopts that shape verbatim except where
   gaps in the reducer force new events.
3. **Forward compatibility is a first-class requirement.** The reducer must
   tolerate unknown event types without crashing, so V1 features (permission
   gating, mid-turn injection acks) can land on the server before the reducer
   knows about them.

The rest of this doc enumerates the connection lifecycle, the envelope,
server→client and client→server vocabularies, the evolution from biomedical-
mvp, capability negotiation, error handling, edge cases, and the hand-
maintained type boundary for V0. The canonical normalized schema lives in
[harness-abstraction.md](./harness-abstraction.md); this wire doc is the thin
frontend-facing rename layer on top of it.

## 2. Connection lifecycle

### 2.1 Opening the WebSocket

The frontend connects to a single WebSocket endpoint per backend process:

```
ws://localhost:<port>/ws?work_item=<work_item_id>
```

V0 has no auth. The backend binds to `127.0.0.1` only, so the loopback
constraint substitutes for an authentication boundary. `work_item` is a query
param so the backend can resolve the active session before the first frame.

The frontend uses the existing `WsClient` wrapper at
`src/lib/ws/ws-client.ts` — native browser `WebSocket`, no socket.io, no SSE.
The client already provides reconnect with exponential backoff and jitter, a
`disconnected → connecting → connected → reconnecting` state machine, and
ping/pong via the `protocol.ts` envelope. The backend MUST honor that
machinery; do not invent a parallel control plane.

### 2.2 Server-initiated `SESSION_HELLO`

Immediately after the upgrade completes, the server pushes a `SESSION_HELLO`
control frame **before any other traffic**. The frontend treats it as a
`SessionInfo` payload, not per-turn state, and stashes it outside
`StreamState`.

```json
{
  "kind": "control",
  "op": "session_hello",
  "subId": "session",
  "seq": 0,
  "payload": {
    "sessionId": "sess_01HZX...",
    "workItemId": "agent-shell-mvp",
    "harness": "claude-code",
    "harnessVersion": "1.0.123",
    "agentProfile": "data-analyst",
    "capabilities": {
      "mid_turn_injection": "queue",
      "supports_tool_approval_gating": false,
      "supports_session_persistence": false,
      "supports_session_resume": false,
      "supports_session_fork": false,
      "supports_interactive_tools": true,
      "supports_binary_mesh_frames": true
    },
    "resumed": false,
    "serverProtocolVersion": "1.0.0",
    "minClientProtocolVersion": "1.0.0"
  }
}
```

`resumed` is `true` if this `SESSION_HELLO` is the result of a reconnect
that landed inside the in-memory replay window (V0) or rehydrated a
durably persisted session (V1). It is `false` for fresh sessions and for
reconnects that arrived after the replay window expired (in which case
the client should treat the prior session as cancelled — see §9.3 and
§10).

The frontend MUST receive `SESSION_HELLO` before sending any client→server
command. If the first inbound frame is anything else, the client logs a
protocol error, drops the connection, and reconnects. This guarantees
capability flags are known before the UI exposes affordances.

### 2.3 Heartbeat

`WsClient` already pings on a 25-second interval and treats two missed pongs
as a dead connection (see `src/lib/ws/ws-client.ts`). The backend MUST respond
to `kind: "control", op: "ping"` with `kind: "control", op: "pong"`. No
Meridian-specific heartbeat layered on top.

### 2.4 Reconnect

On reconnect the client re-opens the same URL and waits for a fresh
`SESSION_HELLO`. V0 has one session per backend process and one work item per
process. Reconnect within the server's 30-second in-memory replay window uses
the same `sessionId`, sets `SESSION_HELLO.resumed = true`, and replays
buffered events from the client's last seen `seq`. After that window, the
server emits `SESSION_HELLO` with `resumed = false` followed by
`SESSION_RESYNC`, and the client dispatches `RESET`.

```json
{
  "kind": "control",
  "op": "session_resync",
  "payload": {
    "sessionId": "sess_01HZX...",
    "abandonedTurnId": "turn_42",
    "stateDigest": {
      "activeTurnId": null,
      "lastSeqByTurn": {}
    }
  }
}
```

**V0 SESSION_RESYNC semantics: the active turn is abandoned, not rehydrated.**
The in-memory replay buffer is the only source of truth for streamed
text/tool/output content; once it's gone, the client cannot reconstruct
the partial turn from a digest. The `abandonedTurnId` field tells the
client which turn to mark `cancelled` in its local activity stream so
the user can re-send. This is intentional and acceptable for V0 — the
work-item file layout still records any tool side effects, so the user
hasn't lost work, only the conversation transcript for that one turn.

V1 with durable session persistence may rehydrate the active turn instead
of abandoning it. That path uses the same `SESSION_RESYNC` envelope but
populates `stateDigest.lastSeqByTurn` with the resume cursor and omits
`abandonedTurnId`; the client backfills via `subscribe_turn` rather than
resetting. The wire shape accommodates both paths so V1 doesn't need a
new event type.

The reconnect requirement that matters now is simple: the client always
includes its last seen `seq`, and the server either replays buffered events
(within the 30s window, `resumed=true`), or emits `SESSION_RESYNC` with
`abandonedTurnId` (after the window, `resumed=false`).

## 3. Message envelope

All JSON frames use the existing frontend-v2 envelope from
`src/lib/ws/protocol.ts`:

| Field      | Type                  | Required | Notes                                                                 |
|------------|-----------------------|----------|-----------------------------------------------------------------------|
| `kind`     | `"control" \| "stream" \| "notify" \| "error"` | yes | Lane discriminator.                                                   |
| `op`       | string                | yes      | Operation name within the lane (lowercase snake_case).                |
| `resource` | string                | no       | Optional logical scope (`turn`, `session`, `document`).               |
| `subId`    | string                | yes      | Subscription id; for turn streams, this is the turn id.               |
| `seq`      | int (uint64)          | yes      | Per-`subId` monotonic sequence; the gap detector keys on this.        |
| `epoch`    | int                   | no       | Bumped when the server intentionally restarts a stream (e.g. branch). |
| `payload`  | object                | yes      | Lane-specific payload; see vocabularies below.                        |

The agent-shell backend uses exactly four lanes:

- `control` — session lifecycle, ping/pong, command acks.
- `stream` — AG-UI activity events for a specific turn (`subId = turnId`).
- `notify` — invalidations to refetch (e.g. work-item file changes); sparse in
  V0, the backend instead inlines what the UI needs.
- `error` — protocol errors and recoverable run errors.

### 3.1 Stream events vs. AG-UI payloads

Activity-stream events ride the `stream` lane. The AG-UI event type lives
inside `payload.type` (uppercase `SNAKE_CASE`), matching the existing reducer.
This nesting is intentional: it lets the gap detector inspect `seq`/`epoch`
without parsing the AG-UI payload.

```json
{
  "kind": "stream",
  "op": "event",
  "resource": "turn",
  "subId": "turn_42",
  "seq": 17,
  "payload": {
    "type": "TEXT_MESSAGE_CONTENT",
    "messageId": "msg_8a",
    "delta": "Loading the femur DICOM stack..."
  }
}
```

### 3.2 Binary frames (mesh data)

Mesh payloads ride the same WebSocket as binary frames. The framing is the
biomedical-mvp shape, kept verbatim:

```
[subId UTF-8] 0x00 [meshId UTF-8] 0x00 [binary payload]
```

The first NUL terminates `subId` (the turn id). The second NUL terminates
`meshId`. Everything after is the raw binary mesh blob (typed-array stream:
positions, indices, normals, colors — format negotiated through the prior
`DISPLAY_RESULT` event's `data.format` field).

`WsClient` already handles this framing in `ws-client.ts:115`. The agent-shell
backend MUST emit binary frames AFTER the `DISPLAY_RESULT` event that
references `meshId`, never before — the reducer needs the descriptor to know
what to do with the bytes.

## 4. Server → client event vocabulary

The full event surface. Every event payload is JSON nested under
`envelope.payload` with `type` set to the SNAKE_CASE name. Field types use
TypeScript syntax for clarity; see §11 for the formal schema.

### 4.1 Run lifecycle

| Event         | When emitted                                              | Reducer effect |
|---------------|-----------------------------------------------------------|----------------|
| `RUN_STARTED` | Backend received `SEND_USER_MESSAGE` and started a turn.  | Creates a fresh `ActivityBlockData`, clears any pending state. |
| `RUN_FINISHED`| Harness reported turn complete.                           | Marks `isStreaming = false`. |
| `RUN_ERROR`   | Harness reported a fatal turn error (model 5xx, etc.).    | Sets `error`; UI shows `TurnStatusBanner`. |

```json
{ "type": "RUN_STARTED", "turnId": "turn_42", "userMessageId": "msg_user_7" }
```

```json
{ "type": "RUN_FINISHED", "turnId": "turn_42", "stopReason": "end_turn", "usage": { "inputTokens": 1234, "outputTokens": 567 } }
```

```json
{ "type": "RUN_ERROR", "turnId": "turn_42", "error": { "code": "harness_died", "message": "Claude Code subprocess exited with code 1", "retryable": true } }
```

### 4.2 Text streaming

| Event                  | Payload fields                                | Reducer effect |
|------------------------|-----------------------------------------------|----------------|
| `TEXT_MESSAGE_START`   | `messageId`                                   | Creates a new `content` item. |
| `TEXT_MESSAGE_CONTENT` | `messageId`, `delta`                          | Appends `delta` to the active content item AND `pendingText`. |
| `TEXT_MESSAGE_END`     | `messageId`                                   | Closes the content item. |

```json
{ "type": "TEXT_MESSAGE_CONTENT", "messageId": "msg_8a", "delta": "Now segmenting the femur via watershed..." }
```

### 4.3 Thinking (extended thinking blocks)

| Event                            | Payload fields           | Reducer effect |
|----------------------------------|--------------------------|----------------|
| `THINKING_START`                 | `thinkingId`             | Creates a `thinking` item. |
| `THINKING_TEXT_MESSAGE_START`    | `thinkingId`             | Lifecycle marker. |
| `THINKING_TEXT_MESSAGE_CONTENT`  | `thinkingId`, `delta`    | Appends to thinking item. |
| `THINKING_TEXT_MESSAGE_END`      | `thinkingId`             | Lifecycle marker. |

These exist as four events instead of three because Claude Code emits
extended-thinking blocks with their own start/end framing distinct from the
inner streaming text. The reducer already handles all four; the backend MUST
emit them in order.

### 4.4 Tool call lifecycle

| Event              | Payload fields                                                          | Reducer effect |
|--------------------|-------------------------------------------------------------------------|----------------|
| `TOOL_CALL_START`  | `messageId`, `toolCallId`, `toolName`                                   | Creates a `ToolItem` with `status: "preparing"`. |
| `TOOL_CALL_ARGS`   | `messageId`, `toolCallId`, `delta`                                      | Concatenates into `toolArgsBuffers[toolCallId]`; partial-parses to `inputPreview`. |
| `TOOL_CALL_END`    | `messageId`, `toolCallId`                                               | Final parse of args; flips `status` to `executing`. |
| `TOOL_OUTPUT`      | `messageId`, `toolCallId`, `stream` (`stdout \| stderr`), `text`, `sequence` | Appended to `ToolItem.stdout` or `.stderr` (gap-aware via `sequence`). |
| `DISPLAY_RESULT`   | `messageId`, `toolCallId`, `displayId`, `resultKind`, `data`            | Creates a `DisplayResultItem` keyed off `displayId`. |
| `TOOL_CALL_RESULT` | `messageId`, `toolCallId`, `status` (`done \| error \| cancelled \| timeout`), `result` | Flips tool status to terminal state; may attach text result. |

`displayId` is new in agent-shell — biomedical-mvp keyed display results by
`toolCallId`, but the interactive-tool flow needs **two** `DISPLAY_RESULT`
events for the same tool call (pending → done) and a single key collides.
`displayId` is unique per `DISPLAY_RESULT` emission; the second one for the
same `toolCallId` REPLACES the first if they share `displayId`, otherwise
appends.

The canonical lifecycle is exactly:

```
TOOL_CALL_START
  → TOOL_CALL_ARGS (1..N)
  → TOOL_CALL_END
  → TOOL_OUTPUT (0..N)        # streamed during execution
  → DISPLAY_RESULT (0..N)     # post-execution result capture
  → TOOL_CALL_RESULT          # terminal
```

`TOOL_CALL_RESULT` is always last. The reducer treats it as the "settle this
tool" signal and the UI swaps the spinner for a final state.

```json
{ "type": "TOOL_CALL_START", "messageId": "msg_8a", "toolCallId": "tool_3", "toolName": "python" }
```

```json
{ "type": "TOOL_CALL_ARGS", "messageId": "msg_8a", "toolCallId": "tool_3", "delta": "{\"code\":\"import SimpleITK as si" }
```

```json
{ "type": "TOOL_OUTPUT", "messageId": "msg_8a", "toolCallId": "tool_3", "stream": "stdout", "text": "Loaded 412 slices\n", "sequence": 0 }
```

```json
{
  "type": "DISPLAY_RESULT",
  "messageId": "msg_8a",
  "toolCallId": "tool_3",
  "displayId": "disp_12",
  "resultKind": "plotly",
  "data": { "spec": { "data": [...], "layout": {...} } }
}
```

```json
{ "type": "TOOL_CALL_RESULT", "messageId": "msg_8a", "toolCallId": "tool_3", "status": "done", "result": "Segmentation complete (4 labels)" }
```

#### `resultKind` values

The reducer stores `DisplayResultItem` opaquely; `resultKind` is the
discriminator the renderer dispatches on. V0 vocabulary:

| `resultKind`            | `data` shape                                                     | Renderer |
|-------------------------|------------------------------------------------------------------|----------|
| `plotly`                | `{ spec: PlotlyFigure }`                                         | Plotly inline. |
| `matplotlib`            | `{ pngBase64: string, width: int, height: int }`                 | `<img>`. |
| `dataframe`             | `{ columns: string[], rows: any[][], dtypes: string[] }`         | Table. |
| `mesh`                  | `{ meshId: string, format: "draco" \| "stl-bin" \| "ply", bbox?: number[6], stats?: object }` | 3D viewer; binary frame follows. |
| `image`                 | `{ pngBase64?: string, url?: string, width?: int, height?: int, caption?: string }` | `<img>`. |
| `text`                  | `{ text: string, language?: string }`                            | Code block / pre. |
| `interactive_pending`   | `{ tool: string, prompt: string, args: object }`                 | "Window open on your desktop" placeholder. |
| `interactive_done`      | `{ tool: string, output: object, durationMs: int }`              | Completion summary. |
| `unknown`               | arbitrary                                                         | Generic JSON viewer. |

Renderers SHOULD treat unknown `resultKind` as `unknown` rather than
crashing — see §10 forward-compat.

### 4.5 Capability and command-related events

| Event                  | Purpose                                                       |
|------------------------|---------------------------------------------------------------|
| `SESSION_HELLO`        | Connection bootstrap (see §2.2). Always `seq: 0`.             |
| `SESSION_RESYNC`       | Replay window expired; client must reset to the server's current state digest. |
| `INTERRUPT_ACK`        | Server acknowledged a `CANCEL_TURN` command. Carries `turnId`, `acceptedAt`, and `effective` (`true` if cancellation will land, `false` if turn already finished). |
| `PERMISSION_REQUESTED` | (V1) Server asks the user to approve a tool call. Carries `requestId`, `toolCallId`, `toolName`, `args`, `risk` (`low \| med \| high`), `expiresAt`. |
| `PERMISSION_RESOLVED`  | (V1) Final state after user approves/denies; carries `requestId`, `decision`. |

```json
{ "type": "INTERRUPT_ACK", "turnId": "turn_42", "acceptedAt": "2026-04-08T17:31:04Z", "effective": true }
```

```json
{
  "type": "PERMISSION_REQUESTED",
  "requestId": "perm_55",
  "toolCallId": "tool_3",
  "toolName": "bash",
  "args": { "command": "rm -rf $MERIDIAN_WORK_DIR/results/run_07" },
  "risk": "high",
  "expiresAt": "2026-04-08T17:32:00Z"
}
```

V0 reducer ignores `PERMISSION_REQUESTED` and `PERMISSION_RESOLVED` (forward
compat path); the V1 reducer adds explicit cases.

## 5. Client → server command vocabulary

All client commands ride the `control` lane. The server replies on the same
`subId` with either an ack frame or an error frame. Five commands in V0+V1:

| `op`                 | Purpose                                                       | Ack             | V0?  |
|----------------------|---------------------------------------------------------------|-----------------|------|
| `send_user_message`  | Start a new turn with a user message.                         | `RUN_STARTED`   | yes  |
| `cancel_turn`        | Interrupt the active turn.                                    | `INTERRUPT_ACK` | yes  |
| `reset_session`      | Hard reset; drop all in-flight state, restart subprocess.     | `SESSION_HELLO` | yes  |
| `approve_tool`       | (V1) Approve a pending permission request.                    | `PERMISSION_RESOLVED` | V1 |
| `deny_tool`          | (V1) Deny a pending permission request.                       | `PERMISSION_RESOLVED` | V1 |

### 5.1 `send_user_message`

```json
{
  "kind": "control",
  "op": "send_user_message",
  "subId": "session",
  "seq": 1,
  "payload": {
    "messageId": "msg_user_7",
    "content": [
      { "type": "text", "text": "Run preprocessing on the femur DICOM stack I just uploaded." }
    ],
    "turnHints": { "previousTurnId": "turn_41" }
  }
}
```

`content` is an array because the user composer can attach images or
references (existing frontend-v2 `UserBubble` already handles
`text | image | reference` blocks). The backend MUST preserve the array shape
and forward to the harness.

### 5.2 `cancel_turn`

```json
{
  "kind": "control",
  "op": "cancel_turn",
  "subId": "turn_42",
  "seq": 1,
  "payload": { "turnId": "turn_42" }
}
```

The backend immediately acks with `INTERRUPT_ACK`, then proceeds to actually
interrupt the harness (Claude Code: stream-json `interrupt` message; opencode:
HTTP DELETE on the run). If the turn already finished before cancel arrives,
`INTERRUPT_ACK.effective = false`.

### 5.3 `reset_session`

```json
{ "kind": "control", "op": "reset_session", "subId": "session", "seq": 1, "payload": {} }
```

Drops all in-flight state, kills and restarts the harness subprocess, emits a
fresh `SESSION_HELLO` with a new `sessionId`. Reducer dispatches `RESET`.

### 5.4 `approve_tool` / `deny_tool` (V1)

```json
{
  "kind": "control",
  "op": "approve_tool",
  "subId": "session",
  "seq": 7,
  "payload": { "requestId": "perm_55", "scope": "once" }
}
```

`scope` is `once | session | always`. V1 only — V0 server rejects with
`error.code = "capability_disabled"` because `supports_tool_approval_gating` is
false.

## 6. Protocol evolution from biomedical-mvp

This section is the "what we kept and why we changed" log. Adopt-as-is is the
default; every divergence is justified.

### 6.1 Adopted verbatim

- The seven-step tool lifecycle (`TOOL_CALL_START → ARGS → END → OUTPUT →
  DISPLAY_RESULT → TOOL_CALL_RESULT`) — see biomedical-mvp `display-results.md`
  L9, L181, L329.
- The mesh binary frame format `[subId]\0[meshId]\0[payload]` — already
  implemented in `ws-client.ts` L115.
- File-based capture handshake (helpers write `.meridian/result.json`, backend
  reads and emits `DISPLAY_RESULT`) — agent-shell's `local-execution.md`
  inherits this verbatim.
- The persisted block forms `tool_output` and `display_result` for
  conversation history.
- Run lifecycle events (`RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`) and their
  reducer semantics.

### 6.2 Evolved with rationale

| Change                                           | Rationale |
|--------------------------------------------------|-----------|
| **Add `SESSION_HELLO` with capability flags.**   | Biomedical-mvp had no equivalent because it spoke to a single fixed Go backend. agent-shell intentionally supports multiple harnesses with different capability sets (Claude Code vs opencode), and the frontend must gate UI affordances on what the active adapter can actually do. Without this, mid-turn-injection UI either appears broken (Claude Code, hard) or hidden (opencode, easy) — capability negotiation is the only honest answer. |
| **Add `SESSION_RESYNC`.**                        | V0 uses a 30-second in-memory replay window on disconnect. When that window expires, the frontend needs an explicit "drop reducer state and trust the server's current digest" signal instead of pretending full replay exists. |
| **Add `displayId` to `DISPLAY_RESULT`.**         | Biomedical-mvp keyed displays by `toolCallId`. Interactive tools need two display events for one tool call (`interactive_pending` then `interactive_done`); a single key collides. `displayId` is the stable identity, with replace semantics on collision. |
| **Add `interactive_pending` / `interactive_done` `resultKind` values.** | The interactive-tool protocol (PyVista point picker, etc.) needs a "window is open on your desktop" placeholder UI that resolves to a final result. Not part of biomedical-mvp's vocabulary because it predates the co-pilot Path B model from Decision 10. |
| **Add `INTERRUPT_ACK`.**                         | Biomedical-mvp ran turns to completion; cancellation was best-effort. agent-shell explicitly supports `cancel_turn` from V0 (Dad needs to stop a long segmentation that's clearly going wrong), so the ack channel must exist. |
| **Reserve `PERMISSION_REQUESTED` / `PERMISSION_RESOLVED`.**  | V1 feature, but the event names are reserved now so V0 reducer code accommodates them as unknown-event no-ops without crashing. |
| **`TOOL_OUTPUT.sequence` is mandatory.**         | Biomedical-mvp had `sequence` as optional. agent-shell makes it mandatory because gap detection on the `subId` envelope is too coarse for streaming stdout — a `python` tool can emit hundreds of `TOOL_OUTPUT` events per `seq` of higher-level events. |
| **Reducer must tolerate unknown `type` values.** | Biomedical-mvp could afford to crash on unknown events (single fixed server). agent-shell explicitly cannot — V1 server features need to land before V0 reducer code is updated. New requirement, see §10. |

### 6.3 Reducer gap to fill

The current frontend-v2 reducer (`reducer.ts:101`) handles:
`RUN_STARTED, RUN_FINISHED, RUN_ERROR, TEXT_MESSAGE_START/CONTENT/END,
THINKING_START, THINKING_TEXT_MESSAGE_START/CONTENT/END, TOOL_CALL_START,
TOOL_CALL_ARGS, TOOL_CALL_END, TOOL_CALL_RESULT, RESET`.

It does **not** yet handle `TOOL_OUTPUT` or `DISPLAY_RESULT`. These were added
by the biomedical-mvp pivot but never landed in the reducer file copied into
frontend-v2 main. agent-shell V0 must:

1. Add `TOOL_OUTPUT` reducer case → append to `ToolItem.stdout` / `.stderr`.
2. Add `DISPLAY_RESULT` reducer case → push a `DisplayResultItem` keyed by
   `displayId` (replace if same `displayId`, append if new).
3. Add `SESSION_HELLO` handling at the `WsClient`/provider layer (out of band
   from `StreamState`).
4. Add a default `_unknown` branch that logs and returns state unchanged.
5. **Mid-turn composer state.** Add reducer cases for:
   - dispatching `INJECT_USER_MESSAGE` (composer enters "injecting" state),
   - `MESSAGE_QUEUED` (composer shows the pending pill — "queued for next
     turn"),
   - `INTERRUPT_ACK` (clear any in-flight inject UI when the harness
     confirms an interrupt landed).
   These are necessary because mid-turn injection is now V0 tier-1 (every
   adapter ships with a non-`none` `mid_turn_injection` mode); see
   `event-flow.md` §6 for the wire flow.

This is a small, well-scoped change to `reducer.ts` and `types.ts`. It is the
ONLY mandatory frontend-v2 reducer change for V0.

## 7. Interactive tool events on the wire

The general contract: the agent calls **any** registered interactive tool with
JSON args; the backend emits a `DISPLAY_RESULT` of `resultKind:
"interactive_pending"` while the tool window is open on the user's desktop;
when the tool returns, the backend emits a second `DISPLAY_RESULT` with the
SAME `displayId` and `resultKind: "interactive_done"`. The reducer's replace-
on-same-`displayId` rule means the placeholder seamlessly upgrades to the
final result without flicker.

Concrete example, the PyVista point-picker flow:

```json
{ "type": "TOOL_CALL_START", "messageId": "msg_8a", "toolCallId": "tool_5", "toolName": "pick_points_on_mesh" }
```

```json
{ "type": "TOOL_CALL_ARGS", "messageId": "msg_8a", "toolCallId": "tool_5", "delta": "{\"mesh_id\":\"femur_seg_v1\",\"n\":4}" }
```

```json
{ "type": "TOOL_CALL_END", "messageId": "msg_8a", "toolCallId": "tool_5" }
```

```json
{
  "type": "DISPLAY_RESULT",
  "messageId": "msg_8a",
  "toolCallId": "tool_5",
  "displayId": "disp_18",
  "resultKind": "interactive_pending",
  "data": {
    "tool": "pick_points_on_mesh",
    "prompt": "Click 4 anatomical landmarks on the femur model in the open window.",
    "args": { "mesh_id": "femur_seg_v1", "n": 4 }
  }
}
```

User clicks landmarks, window closes, tool serializes its result. Backend
emits:

```json
{
  "type": "DISPLAY_RESULT",
  "messageId": "msg_8a",
  "toolCallId": "tool_5",
  "displayId": "disp_18",
  "resultKind": "interactive_done",
  "data": {
    "tool": "pick_points_on_mesh",
    "output": { "points": [[12.3, 4.5, 6.7], [13.0, 4.6, 6.9], [11.8, 5.0, 6.4], [12.5, 4.4, 6.5]] },
    "durationMs": 14820
  }
}
```

Then the normal terminal:

```json
{ "type": "TOOL_CALL_RESULT", "messageId": "msg_8a", "toolCallId": "tool_5", "status": "done", "result": "{\"points\": [...]}" }
```

The shell does not know what PyVista is. The renderer for
`interactive_pending` is a generic "Window open on your desktop, waiting for
your input — `{tool}`" card with a spinner. The renderer for
`interactive_done` is a generic "Completed in {durationMs}ms" card with a
collapsible JSON view of `output`. **No PyVista-specific code on the frontend.**
Domain-specific renderers are an opt-in extension; the default generic
renderers always work.

## 8. Capability negotiation

Capability flags in `SESSION_HELLO.payload.capabilities` gate UI affordances.
The frontend `SessionContext` exposes them via a hook
(`useSessionCapabilities()`) and components render conditionally:

| Flag                            | Affordance gated                                          |
|---------------------------------|-----------------------------------------------------------|
| `mid_turn_injection`            | **Semantic enum** (`queue` / `interrupt_restart` / `http_post` / `none`). For any value other than `none`, the composer accepts input while a turn is running and sends as `inject_user_message`. The mode also controls a per-mode hint near the composer (queue → "queued for next turn", interrupt_restart → "this will interrupt the current turn", http_post → no hint). When `none`, composer is disabled mid-turn. |
| `supports_tool_approval_gating` | Permission approval banner UI. When false, never shown.   |
| `supports_session_persistence`  | Banner on reconnect: "Resumed previous session" vs "Fresh session". When false, always-fresh. |
| `supports_session_resume`       | Resume affordance after restart (V1 only).                |
| `supports_session_fork`         | Fork-session affordance (V1 only).                        |
| `supports_interactive_tools`    | Whether to render `interactive_pending` placeholders specially. When false, all tools render as plain. |
| `supports_binary_mesh_frames`   | Whether to expect mesh binary frames. When false, mesh `DISPLAY_RESULT` falls back to embedded base64 in `data.payloadBase64`. |

The point of this design is **the transition from one harness to another
does not require frontend code changes**. The mid-turn composer is enabled
on every adapter from V0 (Claude Code is `queue`); when Codex or OpenCode
land in V1 the only thing that changes is the per-mode hint string.

#### Layering note: shell-level vs adapter-level capabilities

`supports_interactive_tools` and `supports_binary_mesh_frames` are
**shell-level** capabilities, not properties of any particular `HarnessAdapter`
— they describe what the meridian shell + gateway can do, not what the
underlying harness supports. They are therefore **not** fields on
`HarnessCapabilities` (`harness-abstraction.md` §3.2). The gateway merges
shell-level flags onto the adapter-level flags before emitting
`SESSION_HELLO`. The merged blob is what the frontend sees.

Claude Code adapter capabilities for V0:

```json
{
  "mid_turn_injection": "queue",
  "supports_tool_approval_gating": false,
  "supports_session_persistence": false,
  "supports_session_resume": false,
  "supports_session_fork": false,
  "supports_interactive_tools": true,
  "supports_binary_mesh_frames": true
}
```

Codex adapter capabilities for V1 (sketch):

```json
{
  "mid_turn_injection": "interrupt_restart",
  "supports_tool_approval_gating": true,
  "supports_session_persistence": true,
  "supports_session_resume": true,
  "supports_session_fork": false,
  "supports_interactive_tools": true,
  "supports_binary_mesh_frames": true
}
```

OpenCode adapter capabilities for V1 (sketch):

```json
{
  "mid_turn_injection": "http_post",
  "supports_tool_approval_gating": true,
  "supports_session_persistence": true,
  "supports_session_resume": true,
  "supports_session_fork": true,
  "supports_interactive_tools": true,
  "supports_binary_mesh_frames": true
}
```

## 9. Error handling

Two error layers:

### 9.1 Run errors (`RUN_ERROR` event)

A run error means the harness or a tool failed in a way that ends the turn.
The turn closes, the UI shows a banner, the user can retry or send a new
message.

```json
{
  "type": "RUN_ERROR",
  "turnId": "turn_42",
  "error": {
    "code": "harness_died",
    "message": "Claude Code subprocess exited with code 1: stream-json parse error",
    "retryable": true,
    "details": { "stderrTail": "..." }
  }
}
```

`code` enumeration:

| code                    | meaning                                                |
|-------------------------|--------------------------------------------------------|
| `harness_died`          | Subprocess crashed.                                    |
| `harness_unreachable`   | Adapter cannot reach the harness (e.g. opencode HTTP). |
| `tool_execution_failed` | A tool call raised; turn aborted.                      |
| `kernel_crashed`        | Persistent Python kernel died; needs reset.            |
| `model_error`           | Upstream model returned 5xx.                           |
| `rate_limited`          | Upstream rate limit; `details.retryAfterSec`.          |
| `cancelled`             | Turn was cancelled by user (paired with `INTERRUPT_ACK`). |
| `internal`              | Unclassified backend error.                            |

### 9.2 Protocol errors (`error` lane)

A protocol error means the request was malformed or the connection state is
inconsistent. The connection MAY survive (backend sends `error` and continues)
or MAY drop (backend sends `error` then closes).

```json
{
  "kind": "error",
  "op": "protocol_error",
  "subId": "session",
  "seq": 0,
  "payload": {
    "code": "envelope_invalid",
    "message": "Missing required field: seq",
    "fatal": false,
    "originSeq": null
  }
}
```

`code` enumeration:

| code                  | meaning                                                |
|-----------------------|--------------------------------------------------------|
| `envelope_invalid`    | Frame did not parse as the envelope.                   |
| `unknown_op`          | `op` not recognized for the given `kind`.              |
| `capability_disabled` | Client invoked a command requiring a capability the adapter does not support. |
| `out_of_order`        | `seq` regressed unexpectedly.                          |
| `unknown_subscription`| `subId` does not exist on this session.                |
| `binary_frame_orphan` | Binary frame arrived for an unknown `meshId`.          |

`fatal: true` means the backend closes the connection after sending. The
client reconnects.

### 9.3 Reconnect-with-error recovery

If the WebSocket closes mid-turn for any reason, `WsClient` reconnects, the
backend emits a fresh `SESSION_HELLO`, and the client checks `resumed`:

- `resumed = false` → reducer dispatches `RESET`. Any in-flight turn shows as
  `cancelled` in the previous activity block (frozen state, no further events
  expected). User starts over.
- `resumed = true` (V1) → reducer compares `lastSeqByTurn` against its own
  per-turn `seq` cursor. If the server is ahead, it requests a backfill via
  `subscribe_turn` (existing `streaming-channel-client.ts` pattern). If the
  client is ahead, that's a bug.

## 10. Edge cases

| Case                                                              | Behavior |
|-------------------------------------------------------------------|----------|
| Client sends `inject_user_message` while a turn is running. | Backend dispatches to `HarnessSender.inject_user_message()`. If `capabilities.mid_turn_injection == "none"` (no live adapter ships in this mode), backend rejects with `RUN_ERROR{code:"agent_busy"}`. Otherwise the adapter handles it per its mode (`queue`, `interrupt_restart`, or `http_post`). The composer's enabled state already gates this on the client side, but the server enforces. |
| Client disconnects mid-turn, reconnects.                          | V0: replay buffered events if reconnect happens within 30 seconds; otherwise send `SESSION_RESYNC` and reset to the server's current digest. V1: durable replay replaces the in-memory window. |
| Out-of-order messages on the same `subId`.                        | `seq` is monotonic per `subId`. If client sees `seq` regress, it logs `out_of_order`, ignores the frame, and continues. If client sees a gap (`seq` jumps by more than 1), it requests a backfill once; if the gap persists, it falls back to a full re-subscribe (existing `handleGap` logic in `streaming-channel-client.ts:400`). |
| Binary frame arrives for an unknown `meshId`.                     | Client logs `binary_frame_orphan`, drops the frame. This can happen if a `DISPLAY_RESULT` was lost in a gap; the next backfill brings the descriptor and the server retransmits. |
| Very large `TOOL_OUTPUT` chunks.                                  | Backend chunks `text` to ≤ 64 KiB per event. If a single line exceeds 64 KiB, it splits mid-line and the renderer concatenates by `(toolCallId, sequence)`. |
| Reducer encounters unknown event `type`.                          | Default `_unknown` branch logs `console.warn` once per unique type, returns state unchanged. NEVER throws. This is the forward-compat invariant. |
| Server emits `TOOL_CALL_RESULT` without a preceding `TOOL_CALL_END`. | Reducer treats it as an implicit `TOOL_CALL_END` followed by the result (lenient parser). Backend SHOULD NOT do this but the client tolerates. |
| User sends `cancel_turn` after the turn already finished.         | `INTERRUPT_ACK.effective = false`. UI shows nothing; the turn is already in its terminal state. |
| `DISPLAY_RESULT` for `mesh` arrives but binary frame never does.  | After 10s, renderer falls back to "mesh data unavailable" placeholder. The tool result is still recorded; only the 3D viewer is degraded. |
| User uploads a dataset from the drag-drop zone.                   | V0 uses a simple multipart `POST /api/datasets/<name>` backend endpoint that writes directly into `<work-item>/data/raw/<dataset_name>/`. No presign, no finalize, no manifest dance. |
| Composer attaches an image larger than 8 MiB.                     | V0: rejected by composer with toast. Inline multimodal attachments stay small; large datasets go through the drag-drop dataset endpoint above. |

## 11. Typed schema

Both sides MUST be type-safe. V0 keeps the types **hand-maintained** on both
sides and uses tests, not code generation, to keep them aligned.

### 11.1 Backend and frontend sources

- Backend wire models live in `src/meridian/shell/schemas/wire.py`.
- Frontend wire types live in `frontend/src/lib/wire-types.ts`.
- Both reference the canonical normalized schema in
  [harness-abstraction.md](./harness-abstraction.md).

```python
# src/meridian/shell/schemas/wire.py

class RunStarted(BaseModel):
    type: Literal["RUN_STARTED"] = "RUN_STARTED"
    turnId: str
    userMessageId: str

class DisplayResult(BaseModel):
    type: Literal["DISPLAY_RESULT"] = "DISPLAY_RESULT"
    messageId: str
    toolCallId: str
    displayId: str
    resultKind: str
    data: dict[str, Any]
```

```ts
// frontend/src/lib/wire-types.ts
export interface RunStarted {
  type: "RUN_STARTED";
  turnId: string;
  userMessageId: string;
}

export interface DisplayResult {
  type: "DISPLAY_RESULT";
  messageId: string;
  toolCallId: string;
  displayId: string;
  resultKind: string;
  data: Record<string, unknown>;
}
```

### 11.2 Parity check

V0 adds a backend test that asserts the hand-maintained frontend type surface
matches the backend wire schema for the load-bearing fields:

- event `type` discriminators
- required field names
- `resultKind` / capability flag spellings
- command payload shapes

If the two drift, the test fails. That is enough for V0 without introducing a
codegen pipeline into the critical path.

### 11.3 Why not codegen in V0

- **It is overkill for the MVP.** The wire surface is small and changing
  quickly.
- **Generated files would still need review.** Drift bugs move from "bad hand
  edit" to "bad generator invocation."
- **The real source of truth is the normalized schema.** The wire layer is
  intentionally a rename/wrap surface, so full codegen buys less than it would
  in an API-first system.

### 11.4 Versioning

`SESSION_HELLO.payload.serverProtocolVersion` is semver. Major bumps mean the
client must update. Minor bumps add events; the unknown-event branch handles
those without a client update. Patch bumps are bug fixes with no schema
change.

`minClientProtocolVersion` lets the server reject ancient clients with a
clear `error.code = "client_too_old"` instead of mysterious behavior.

## 12. Open questions for review

These are intentionally left for review fan-out, not silently decided:

1. **Should `SESSION_HELLO` carry the full agent profile (skills list,
   model, tool surface) or just the name?** Frontend may want to show "Active
   agent: data-analyst, 4 skills loaded" in a header. Loading the full profile
   bloats the hello frame; loading just the name forces a follow-up REST call.
   Suggested: name + summary fields, full detail via REST.
2. **Is `displayId` always server-assigned, or can the agent's `show_*`
   helpers propose one?** Server-assigned is simpler and avoids conflicts
   across helpers. Recommended.
3. **Should `TOOL_OUTPUT.sequence` reset per `toolCallId` or be globally
   monotonic per turn?** Reset per `toolCallId` matches biomedical-mvp and
   makes the reducer simpler. Recommended.
4. **Do we need a `STREAM_HEARTBEAT` event for long tool runs with no
   output?** The connection ping/pong handles dead-connection detection, but
   the user might want a "still working..." UI cue after 30s of silence.
   Suggested: V1, derived from absence-of-events on the client side, no new
   server event needed.
5. **Reset semantics on `reset_session` — does it clear the work-item
   directory?** No. Files-as-authority means the work-item is the audit
   trail; resetting the session must not delete files. Reset only clears
   in-memory state (kernel, harness subprocess, conversation history).
