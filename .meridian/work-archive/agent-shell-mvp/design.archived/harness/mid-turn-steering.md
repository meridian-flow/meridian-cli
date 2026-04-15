# Mid-Turn Steering: The FIFO Control Protocol

> What this is: the differentiating-feature design — the FIFO control
> protocol, the per-harness injection mechanics, the `meridian spawn
> inject` CLI primitive, and how all of that lives next to the
> existing meridian-channel spawn lifecycle without breaking it.
>
> What this is not: the AG-UI event taxonomy (lives in events/), or
> the per-harness wire format (lives in [`adapters.md`](adapters.md)).

Up: [`overview.md`](overview.md).

## Mid-Turn Steering Is Tier-1, Not A Footnote

Per [`../../findings-harness-protocols.md`](../../findings-harness-protocols.md)
**§ "Mid-Turn Steering is Tier-1, Not Optional"**, mid-turn injection
is **the differentiating feature of the platform** and the harness
abstraction must be shaped around it from day one. The findings doc is
explicit about why this isn't a "nice-to-have we might add in V1" —
retrofitting steering into a Claude-only abstraction means rebuilding
the interface, and the platform's value proposition collapses to "yet
another chat UI over Claude Code" without it.

The user-visible motivation: today's typical agent loop is **prompt →
wait minutes/hours → read report → respawn with corrections**. That's
slow and lossy. The platform we're refactoring meridian-channel to
support collapses the loop by making **every spawn in the tree
steerable mid-execution** — a user (or a parent orchestrator) can say
"wait, reconsider X" mid-run and the running agent absorbs the
correction without being killed and respawned. The
[findings doc](../../findings-harness-protocols.md) is the authoritative
statement; this design implements it.

Two consequences for the design pass:

1. **Capability is a semantic enum, not a boolean.** The three
   harnesses really do behave differently mid-turn. Claude queues to
   the next safe boundary; Codex interrupts the current turn and
   restarts; OpenCode POSTs to a live session. Capability honesty is
   the principle — see [`abstraction.md`](abstraction.md).
2. **The control surface lives at every layer.** Adapter method,
   normalized control frame on the wire, CLI command, AG-UI capability
   event so the consumer can render the right affordance.

## Control Frame Model

Three frame types ride on the per-spawn control FIFO as **JSONL**.
Frames live in the new `harness/control_channel.py` sibling module;
each is a Pydantic model with a discriminated `type` field and a
`version` field for additive evolution.

```jsonl
{"version": "0.1", "type": "user_message", "id": "uuid", "text": "wait, reconsider X"}
{"version": "0.1", "type": "interrupt",    "id": "uuid"}
{"version": "0.1", "type": "cancel",       "id": "uuid"}
```

| Field | Required | Notes |
|---|---|---|
| `version` | yes | `"0.1"` for V0. Adapters reject frames with an unknown major version. |
| `type` | yes | One of `user_message`, `interrupt`, `cancel`. |
| `id` | yes | Caller-generated identifier. Echoed in `control.log` lines so the spawn-side audit trail can correlate frames with adapter outcomes. |
| `text` | `user_message` only | The mid-turn message body. UTF-8. |

`version` ships from day one (per D37 open question #2 — recommendation
adopted). It's cheaper to require a field that adapters mostly ignore
than to retrofit one when v0.2 needs to add an attachment field or a
streaming-text frame.

**Maximum frame size**: each JSONL frame must serialize to **less than
`PIPE_BUF` bytes** — 4096 on Linux, 512 on the strict POSIX baseline
(meridian-channel targets the Linux value). Frames smaller than
`PIPE_BUF` are atomic on FIFO writes (POSIX guarantee), so concurrent
injectors cannot interleave bytes within a single frame. The CLI writer
rejects frames larger than 3500 bytes (a safety margin under the Linux
`PIPE_BUF`) with a clear error so callers cannot accidentally hit the
interleave hazard. For `user_message` frames that need to carry more
content, the design choice is "split into multiple frames" or "use a
sidecar artifact path that the frame references" — V0 picks the simpler
"reject and force the caller to split."

### Frame Semantics Across All Adapters

| Frame | What it means | What the adapter is required to do |
|---|---|---|
| `user_message` | "Deliver this user input to the running spawn." | Translate to the harness-native injection mechanism using the `mid_turn_injection` mode this adapter declares. Write a structured success/failure entry to `control.log` (see "Control errors and `control.log`" below). |
| `interrupt` | "Stop the current turn but keep the spawn alive." | If the adapter has a clean interrupt primitive (Codex `turn/interrupt`, OpenCode session-cancel where supported), signal the harness to stop the in-flight turn and emit a `RUN_FINISHED`-equivalent step boundary. If not (Claude in queue mode), write a "interrupt not supported" entry to `control.log` and leave the in-flight turn running. |
| `cancel` | "Tear the whole spawn down." | Emit a final `RUN_FINISHED`, signal the harness subprocess (`SIGTERM` with timeout, then `SIGKILL`), close stdout, exit. Required of all adapters as part of the lifecycle contract — there is no `supports_cancel` flag because cancellation is not a capability, it is a precondition. |

`interrupt` is intentionally distinct from `cancel`. A consumer that
wants "stop generating but let me reframe" sends `interrupt` and
follows up with `user_message`. A consumer that wants "kill this
spawn" sends `cancel`.

### Control errors and `control.log`

There is no `CONTROL_RECEIVED` or `CONTROL_ERROR` AG-UI event. Both
were rejected during review because meridian-flow owns the AG-UI
taxonomy (D36) and meridian-channel cannot unilaterally mint new
events. Control-frame outcomes are recorded out-of-band on two
surfaces:

1. **Synchronous CLI return code.** `meridian spawn inject` performs a
   non-blocking write to the FIFO and returns a clear exit code:
   - `0` — frame written successfully (the FIFO accepted the bytes)
   - non-zero with stderr message — see "Failure modes" in the inject
     CLI section below

   The CLI writer has full information about whether the bytes hit the
   FIFO. There is no need for an asynchronous "frame received"
   acknowledgement — POSIX FIFO write semantics guarantee delivery
   once `write(2)` returns success for a sub-`PIPE_BUF` frame.

2. **Asynchronous `control.log` for adapter-side outcomes.** A new
   per-spawn artifact, `.meridian/spawns/<spawn_id>/control.log`,
   captures one structured JSONL line per control frame the adapter
   processes. Format:

   ```jsonl
   {"ts": "...", "frame_id": "uuid", "type": "user_message", "outcome": "delivered", "harness_action": "stream-json frame written to claude stdin"}
   {"ts": "...", "frame_id": "uuid", "type": "interrupt",    "outcome": "rejected", "reason": "claude adapter has no interrupt primitive in queue mode"}
   {"ts": "...", "frame_id": "uuid", "type": "user_message", "outcome": "error",    "reason": "harness subprocess exited before frame could be delivered"}
   ```

   `control.log` lives next to `output.jsonl` and `stderr.log` in the
   spawn artifact directory. It is a sibling to those files — read
   it the way you'd read `stderr.log` for diagnostics. A consumer
   that wants live visibility into control outcomes (the Go backend,
   a debugging CLI, the dev-orchestrator's own observation loop)
   tails `control.log` the way they would tail any other per-spawn
   artifact.

This is the resolution to **D37 open question #3** (error reporting).
Synchronous failures from `meridian spawn inject` for delivery errors
(the frame couldn't be handed to the spawn). Out-of-band `control.log`
entries for adapter-level outcomes (the frame was delivered but the
harness can't honor it right now). Two surfaces, one for each consumer
class.

## Per-Harness Injection Mechanics

The adapter hides the wire mechanic; the consumer always sends the
same `user_message` frame. What happens inside:

### Claude Code — `mid_turn_injection = "queue"`

The adapter writes a stream-json `user` message frame to the harness
subprocess's stdin (the **harness's** stdin, not meridian's). Claude
queues the message and delivers it at the next safe turn boundary —
typically right after the current tool call settles or the current
text message ends.

User-visible semantics: **"Message will be applied at the next turn
boundary."** The frontend (or CLI) shows a queued indicator until the
adapter emits the corresponding `STEP_STARTED` for the new turn.

Claude is the lowest-friction case because the harness's own input
format is what the adapter writes, just at a different time than the
initial prompt.

### Codex (`codex app-server`) — `mid_turn_injection = "interrupt_restart"`

The adapter calls JSON-RPC `turn/interrupt` to stop the current turn,
then `turn/start` with the injected `user_message.text` as the new
turn's initial prompt. Per the
[findings doc](../../findings-harness-protocols.md), this is the
documented stable mechanism — `turn/interrupt` is part of Codex's
core stable protocol over stdio.

User-visible semantics: **"This will interrupt the current turn."**
The frontend shows the interrupt warning before the injection actually
happens. The previous turn's `RUN_FINISHED` arrives before the new
turn's `STEP_STARTED`.

This is the case where **honesty** matters most — pretending Codex's
interrupt-restart is the same as Claude's queue-and-deliver would mean
silently destroying the current turn without telling the user. The
capability enum is what makes the difference visible.

### OpenCode — `mid_turn_injection = "http_post"`

The adapter holds a session URL (resolved at launch) and POSTs the
injected `user_message.text` to the live session's message endpoint.
The OpenCode session emits the resulting events on its own event
stream, which the adapter is already tailing for the AG-UI translation
path.

User-visible semantics: **normal send button**. POSTing to a live
session is conceptually the same as a fresh user message; OpenCode
handles the multi-turn-during-streaming case at the session layer.

Per the findings doc, this is the "cleanest of the three" because the
HTTP session API was explicitly designed for external drivers.

## Capability Reporting Via `params.json`

Capabilities are written to the per-spawn `params.json` artifact at
spawn-launch time, **not** as an on-wire AG-UI event. meridian-flow
owns the AG-UI taxonomy (D36); meridian-channel cannot unilaterally
mint a new event type. Capabilities live on the out-of-band artifact
that every existing dry-run / `spawn show` / debugging surface already
reads (per [`../refactor-touchpoints.md`](../refactor-touchpoints.md)).

The capability bundle uses the canonical flat shape from
[`abstraction.md`](abstraction.md) — no `supports_` prefix, no boolean
gate where the truth is a semantic enum:

```json
{
  "spawn_id": "...",
  "agent": "...",
  "harness": "claude",
  "control_protocol_version": "0.1",
  "capabilities": {
    "mid_turn_injection": "queue",
    "runtime_model_switch": false,
    "runtime_permission_switch": false,
    "structured_reasoning_stream": true,
    "cost_tracking": true
  }
}
```

The frontend uses `mid_turn_injection` to render the right affordance:

- `queue` → composer stays enabled mid-turn, with a "queued for next
  turn" hint
- `interrupt_restart` → composer stays enabled, with a "this will
  interrupt the current turn" warning before send
- `http_post` → composer stays enabled, normal send button
- `none` → composer disabled while a turn is in flight

A consumer that needs the capability bundle (the Go backend rendering
an affordance, the dev-workflow orchestrator deciding whether to show
"queued for next turn") reads `params.json` once at spawn-attach time.
The live AG-UI event stream stays pure: it carries only events from
meridian-flow's canonical taxonomy.

`control_protocol_version` lets the consumer reject a streaming spawn
whose protocol it does not understand, the same way version-skewed
clients reject old REST APIs.

> **Future migration.** If meridian-flow later blesses a canonical
> `CAPABILITY` event in its AG-UI taxonomy, meridian-channel can start
> emitting it on the wire as the first event after `RUN_STARTED`. The
> event payload would be the same `capabilities` object that lives in
> `params.json` today. Until that conversation has happened, the bundle
> lives in `params.json` only.

## FIFO Is The Single Control Ingress

**Open question D37 #1.** Does the streaming spawn own its own stdin
exclusively, or sit behind a per-spawn control FIFO?

**Recommendation: per-spawn FIFO is the single authoritative control
ingress. The streaming spawn does NOT use stdin as a control channel.**

The previous draft proposed a "tee both stdin and FIFO into the same
queue" model and was rejected during review. Two ingresses means two
ordering domains and an implicit merge rule the protocol does not
specify, which is exactly the kind of ambiguity that turns "the
differentiating feature" into a debugging nightmare. One ingress, one
ordering domain, one source of truth.

The collision risk is also real: per [`../refactor-touchpoints.md`](../refactor-touchpoints.md)
and direct inspection of `src/meridian/lib/launch/process.py:116-149`,
the **primary launch path already copies parent stdin straight into
the child PTY**. A naïve "streaming spawn owns its stdin and reads
control frames from it" approach would either break interactive
`meridian` sessions or accidentally feed PTY input to the harness as
if it were a control frame.

The resolution:

1. **Streaming-mode launch is a non-PTY launch flavor.** The streaming
   launch type in `harness/launch_types.py` declares "no PTY relay, no
   parent-stdin copy." `launch/process.py` learns one new branch: when
   streaming mode is requested, do not enter the PTY/stdin-relay path.
   Streaming spawns are designed for non-interactive callers (a Go
   backend, an orchestrator, an SDK client) — there is no terminal to
   relay.

2. **The streaming spawn's stdin is reserved for the harness
   subprocess only.** The meridian-channel process's stdin is **not**
   read as a control channel. For Claude specifically, the adapter
   writes stream-json frames to **the harness subprocess's** stdin (a
   private pipe between the adapter and the Claude subprocess); the
   meridian-channel process's own stdin is closed or ignored in
   streaming mode.

3. **`meridian spawn inject` writes to a per-spawn control FIFO.** The
   FIFO is the only place control frames enter the spawn:

   ```
   .meridian/spawns/<spawn_id>/control.fifo
   ```

   This is the only authoritative per-spawn anchor today (per the
   touchpoints map's structural analysis). The streaming spawn opens
   the FIFO read-only on launch (`O_NONBLOCK | O_RDONLY`) and the FIFO
   reader plumbing in `lib/launch/control_fifo.py` tails it for JSONL
   frames, parses each frame via `harness/control_channel.py`, and
   dispatches to the adapter's `ControlDispatcher`.

4. **A parent process that wants to inject from its own stdin must do
   so through `meridian spawn inject`.** A Go backend that holds a
   JSONL control stream from its own caller writes those frames to the
   FIFO via the same CLI primitive (or directly via
   `os.open(fifo_path, ...)` against the well-known per-spawn path).
   There is no special "stdin shortcut" for the spawning process.

This single-ingress model has the practical benefits the
two-ingress draft was trying to capture, without the ordering hazard:

- **Decouples injector from spawner.** Anyone who knows the spawn id
  can write to the FIFO. The dev-workflow orchestrator injects against
  spawned `coder` agents the same way the Go backend does — by writing
  JSONL frames to `.meridian/spawns/<id>/control.fifo`.
- **Survives crash-only discipline.** The FIFO path is recorded in
  `spawn_store.py` before the streaming spawn opens it; after a crash,
  the orphan reaper detects a dangling FIFO the same way it detects
  dangling pid files today.
- **Atomic concurrent writes.** Sub-`PIPE_BUF` JSONL frames are atomic
  on POSIX FIFO writes, so two concurrent injectors cannot interleave
  bytes within a frame (see "Maximum frame size" above and the racing
  injectors entry in "Failure modes and edge cases" below).

The cost is one filesystem primitive (a named pipe), which is cheap on
Linux/macOS and well-supported by Python's `os.mkfifo`.

### What Has To Change In State

`spawn_store.py` and `paths.py` learn one new piece of metadata: the
control surface descriptor for a streaming spawn. From the touchpoints
map: `state/spawn_store.py` has no live-control metadata today, and
`state/paths.py` has the per-spawn directory but no FIFO knowledge.

```python
# state/paths.py
def resolve_spawn_control_fifo(repo_root: Path, spawn_id: SpawnId) -> Path:
    return resolve_spawn_log_dir(repo_root, spawn_id) / "control.fifo"

def resolve_spawn_control_log(repo_root: Path, spawn_id: SpawnId) -> Path:
    return resolve_spawn_log_dir(repo_root, spawn_id) / "control.log"

# state/spawn_store.py  (new field on SpawnRecord)
control_protocol: Literal["none", "fifo"] = "none"
```

`control_protocol_version` is a top-level field in each spawn's
`params.json`, not a `SpawnRecord` field.

`reaper.py` learns to clean up dangling FIFOs (and the
`control.log` artifact) the same way it cleans up dangling pid files.
Per the touchpoints map, the reaper is sensitive — it treats
`report.md` as a completion signal — so the streaming-mode
finalization path must continue producing `report.md` exactly when it
does today.

## `meridian spawn inject <spawn_id> "message"`

A new top-level CLI command in `cli/spawn.py`. Shape:

```bash
meridian spawn inject <spawn_id> "wait, reconsider X"
meridian spawn inject <spawn_id> --interrupt
meridian spawn inject <spawn_id> --cancel
meridian spawn inject <spawn_id> --frame-file frame.json
```

### Resolution

1. Resolve `<spawn_id>` against `state/spawn_store.py` (full id or
   prefix, the way `spawn show` already resolves).
2. Read the spawn record. Verify `control_protocol == "fifo"`
   (i.e. it was launched in streaming mode).
3. Resolve the FIFO path via `paths.resolve_spawn_control_fifo(...)`.

### Writing The Frame

4. Build a `ControlFrame` Pydantic model with a fresh `id`, the
   `version` from top-level `params.json.control_protocol_version`,
   and the requested type.
5. Serialize to JSONL. **Reject** the frame synchronously if it
   serializes to more than 3500 bytes (see "Maximum frame size"
   above) — the caller should split the message.
6. `open(fifo_path, 'wb')` with a configurable timeout (default 5s).
   The writer blocks on `open` if no reader is attached; if the
   timeout elapses without a reader, surface "spawn is not reading
   control frames" rather than blocking forever.
7. Write the frame in a single `write(2)` call (atomic for
   sub-`PIPE_BUF` payloads). Close the FIFO. Return exit code `0` —
   the bytes are guaranteed delivered to the FIFO buffer.

### Failure Modes

The CLI has one synchronous failure surface (delivery to the FIFO)
and one asynchronous out-of-band surface (adapter-side outcomes
written to `control.log`). See "Control errors and `control.log`"
above for the broader picture.

| Failure | Detection | UX |
|---|---|---|
| `<spawn_id>` not found | `spawn_store.py` lookup | Synchronous error, exit non-zero: "no such spawn" |
| Spawn not in streaming mode | `control_protocol == "none"` | Synchronous error: "spawn was not launched with --ag-ui-stream; injection is unavailable" |
| FIFO does not exist | `paths.resolve_spawn_control_fifo` + `os.path.exists` | Synchronous error: "control fifo missing — spawn may have crashed" |
| FIFO open blocks (no reader) | configurable timeout, default 5s | Synchronous error: "spawn is not reading control frames — may have exited" |
| Frame too large for atomic write | serialize size check | Synchronous error: "frame exceeds 3500 bytes; split into smaller messages" |
| Frame written, harness rejects it mid-turn | adapter writes `outcome: rejected` to `control.log` | **Asynchronous** — the inject CLI succeeded; the operator/consumer reads `control.log` for the adapter-side outcome |

This is the resolution to **D37 open question #3**: hybrid error
reporting. Synchronous CLI exit codes for **delivery** errors (the
frame couldn't reach the FIFO). Asynchronous `control.log` entries
for **adapter-level** outcomes (the frame was delivered but the
harness can't honor it right now). The two surfaces line up with the
two consumers: the CLI caller wants exit codes, the operator wants a
tail-able log.

The recommendation: **error if not in streaming mode**, do not
fall back. Falling back to "open a one-shot subprocess and try to
inject" would silently violate the user's mental model — they ran
`spawn inject` against a non-streaming spawn and got something
unexpected. A clear error message tells them to relaunch with
`--ag-ui-stream`.

## Failure Modes And Edge Cases

The control protocol's worst behaviors aren't on the happy path. The
following table is the explicit closure for the load-bearing lifecycle
boundaries the previous draft only sketched.

| Scenario | What happens | Why |
|---|---|---|
| **Harness dies mid-stream** | The streaming-mode reader sees EOF on `output.jsonl` (or the harness pipe). The runner emits a `RUN_FINISHED` AG-UI event with the harness's exit code, writes the existing `report.md` artifact, and tears down the FIFO reader. Any in-flight `spawn inject` calls get "spawn is not reading control frames" on their next attempt. Pending frames already buffered in the FIFO are dropped (the OS frees the FIFO buffer when the reader closes). | The streaming spawn does not "leak" past harness death. The artifact contract — `report.md`, `output.jsonl`, `stderr.log`, `control.log` — captures everything that happened up to the death. Recovery is the same as for non-streaming spawns: read the artifact directory. |
| **AG-UI consumer disconnects, harness keeps running** | The streaming-mode runner detects the closed AG-UI sink (stdout EPIPE in `--ag-ui-stream` mode, file write OK in artifact mode). In stdout mode, the runner logs the disconnect to `stderr.log`, switches the sink to the per-spawn artifact file, and continues. The harness keeps running; the spawn lifecycle is decoupled from any single consumer. | A streaming consumer is a tail, not the source of truth. Killing the spawn just because the AG-UI reader disconnected would defeat the "long-running steerable agent" model. The artifact file lets a reconnecting consumer replay. |
| **Two `spawn inject` calls race** | Both writers `open(fifo_path, 'wb')` and call `write(2)` independently. Each frame is a single sub-`PIPE_BUF` JSONL line, so POSIX guarantees the bytes do not interleave within a frame. The reader sees the frames in arrival order with no torn lines. Frame `id`s are caller-generated UUIDs, so the adapter and `control.log` correlate them unambiguously. | This is exactly what `PIPE_BUF` atomicity is for. The 3500-byte rejection on the writer side is the safety belt that keeps frames inside the atomic-write window. |
| **Control frame arrives during `--from` / `--fork` startup** | The streaming spawn does not open the FIFO for reading until it has finished resuming from the parent session and emitted `RUN_STARTED`. A writer that arrives early blocks on `open(fifo_path, 'wb')` (no reader) until startup completes — bounded by the writer's 5-second timeout. If startup takes longer than 5s, the writer fails fast with "spawn is not reading control frames"; the caller can retry. The startup contract is "FIFO opens before `RUN_STARTED`" so any writer that sees the spawn state as "running" can write. | Resume/fork is part of the adapter's startup phase, not part of the streaming protocol. Pinning the FIFO open to before `RUN_STARTED` gives consumers a clear "you may inject now" signal. |
| **FIFO does not exist when injector tries to write** | The CLI synchronously fails with "control fifo missing — spawn may have crashed" before attempting `open`. This is the recovery case for "the spawn record exists in `spawn_store.py` but the artifact directory was wiped, or the spawn never finished launching." | Distinguishes "FIFO truly absent" from "FIFO exists but no reader." Operators can correlate with `stderr.log` for the launch failure. |
| **FIFO exists but has no reader** | The streaming spawn always opens the FIFO with `O_NONBLOCK | O_RDONLY` on launch and holds the read fd for the duration of the spawn. So "FIFO exists but no reader" implies the spawn is not running — either it hasn't launched yet (the 5s `open` timeout on the writer side handles this) or it has exited and the reaper has not yet cleaned up. The injector sees the timeout error and the operator cross-references `spawn show <id>`. | `O_NONBLOCK` on the reader side guarantees the spawn never blocks on open; it can poll the FIFO without ever wedging the launch path. |
| **Reader is alive but adapter is mid-tool-call when frame arrives** | The FIFO reader keeps reading frames into an internal queue regardless of what the harness is currently doing; the adapter drains the queue at safe boundaries (Claude: stream-json frame goes to harness stdin immediately, Claude queues internally; Codex: `turn/interrupt` then `turn/start`; OpenCode: HTTP POST returns immediately). No frame is dropped — but adapter-side rejection (e.g. interrupt during a Claude queue-mode turn) is recorded in `control.log` with `outcome: rejected`. | Buffering on the meridian-channel side decouples FIFO write latency from harness latency. The harness's own injection mechanic decides what "deliver" actually means. |

These cases are deliberately enumerated rather than left to "the
adapter handles it" because the lifecycle boundary is exactly where
streaming-mode bugs become unrecoverable in production.

## Integration With Existing `spawn` Subcommands

**D37 open question #4.** Does streaming mode change `spawn wait`,
`spawn show`, `spawn log`?

**Recommendation: streaming is a parallel invocation shape, existing
inspection commands keep working unchanged.**

| Command | Behavior in streaming mode |
|---|---|
| `spawn create` | Gains a `--ag-ui-stream` flag. Default behavior unchanged. (The existing hidden `--stream` flag at `cli/spawn.py:211` — "Stream raw harness output to terminal (debug only)" — is renamed in this refactor to avoid collision; see the planner pass for the exact rename.) |
| `spawn show <id>` | Unchanged. Reads `state/spawn_store.py` and the per-spawn artifact dir. Streaming spawns get an extra row showing `control_protocol` and the FIFO path. |
| `spawn log <id>` | Unchanged. Continues to read from `output.jsonl` and the assistant tail. The streaming AG-UI events are written to a sibling sink so the existing transcript display path is undisturbed. |
| `spawn wait <id>` | Unchanged. Waits on the same lifecycle signals (terminal status in `spawn_store.py`, `report.md` durability). Streaming spawns reach the same terminal states. |
| `spawn files <id>` | Unchanged. Lists `control.fifo` and `control.log` alongside the usual artifacts. |
| `spawn stats` | Unchanged. |
| `spawn cancel <id>` | Existing path stays. For streaming spawns, this is equivalent to `spawn inject <id> --cancel` from the user's perspective; under the hood it can flow through the same control frame path or hit the existing kill plumbing — implementation discretion. |
| `spawn inject <id>` | **New.** Only valid when `control_protocol == "fifo"`. |

The principle: **streaming mode is a launch-time choice that
publishes a richer event stream and a control surface, but the
artifact contracts stay the same.** Every existing
inspection/recovery path keeps working because the artifact
directory is still where the truth lives.

## Capability Honesty Restated

The three injection modes are honestly different. The abstraction
unifies the **capability** ("send a `user_message` frame") and surfaces
the **semantics** (`queue` vs `interrupt_restart` vs `http_post`) so
the caller can render the right affordance and the user is not lied to
about wire-level behavior.

This is restated here because it's the principle that decides every
trade-off in the streaming control protocol. When in doubt, **expose
the difference, do not paper over it**.

## Open Questions Still Requiring User Input

The four D37 open questions are resolved above with explicit
recommendations. The remaining items the architect cannot resolve
unilaterally are:

1. **Exact CLI flag/subcommand name for streaming launch.** This doc
   uses `--ag-ui-stream` to avoid collision with the existing hidden
   `--stream` flag at `cli/spawn.py:211` ("Stream raw harness output
   to terminal (debug only)"). The planner pass should pick the final
   spelling once the planner has the broader CLI ergonomics in view.
   Candidates: `meridian spawn create --ag-ui-stream`, `meridian spawn
   stream`, `meridian spawn open`. Recommendation: `--ag-ui-stream`
   for clarity over the existing debug flag.
2. **Whether `spawn cancel <id>` should route through the control
   frame path for streaming spawns.** Tradeoff: routing through the
   control frame path is more uniform; keeping the existing kill
   plumbing is lower risk for the touchpoints map. Recommendation:
   keep existing kill plumbing for V0; revisit if user-visible cancel
   semantics drift.
3. **Whether `meridian spawn inject` should support a `--frame-file`
   path mode for batch injection or streaming control input.** Useful
   for orchestrators that already have a JSONL control stream;
   incremental cost is small. Recommendation: include from V0 — same
   command, two input modes (`--text` vs `--frame-file`), with
   `--text` as the default positional shorthand.
4. **What `interrupt` should look like on harnesses that don't have a
   native interrupt primitive.** Resolved in the frame semantics
   table above: `interrupt` is a frame, not a capability flag. For
   Codex, the adapter calls `turn/interrupt`. For OpenCode, if the
   session API exposes a cancel endpoint the adapter calls it; if
   not, the adapter writes a `rejected` entry to `control.log`. For
   Claude in queue mode, the adapter writes a `rejected` entry to
   `control.log` and the in-flight turn keeps running. There is no
   `supports_interrupt` capability field — interrupt fold into the
   `mid_turn_injection` semantics, and adapter-side rejection is
   surfaced through `control.log` rather than through a boolean gate.

## Read Next

- [`abstraction.md`](abstraction.md) — the adapter interface that
  hosts the new methods
- [`adapters.md`](adapters.md) — per-harness wire format and
  the coordination checklist for tool naming
- [`../events/flow.md`](../events/flow.md) — the AG-UI event sequence
  the streaming spawn produces (canonical taxonomy only — capability
  bundle lives in `params.json`, control outcomes in `control.log`)
- [`../refactor-touchpoints.md`](../refactor-touchpoints.md) — the
  per-file map of what changes to enable this protocol
