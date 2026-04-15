# Explorer pre-pass: map meridian-channel harness code for AG-UI + streaming refactor

## Context

The agent-shell-mvp work item has been reframed (see `reframe.md` and
decisions D34–D40 at `$MERIDIAN_WORK_DIR/decisions.md`). It is NOT a new
product. It is a **meridian-channel refactor** that adds:

1. **AG-UI event emission** in harness adapters (Claude stream-json,
   Codex JSON-RPC `item/*`, OpenCode HTTP session events → canonical
   AG-UI event taxonomy). Per-tool behavior config (bash collapsed,
   Python stdout inline, etc.) is attached at `TOOL_CALL_START`.
2. **Streaming spawn mode** with stdin control protocol. New
   invocation shape — e.g. `meridian spawn --stream -a ...` — that
   emits AG-UI JSONL to stdout and accepts control frames
   (`user_message`, `interrupt`, `cancel`) on stdin.
3. **`meridian spawn inject <spawn_id> "message"` CLI primitive** that
   writes a `user_message` control frame into a running streaming spawn.

The external contract (AG-UI event taxonomy, 3-WS topology, per-tool
behavior config) is defined in meridian-flow, not here. Do not try to
redesign it — just understand what meridian-channel must emit.

External references (READ-ONLY, do not edit):
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md`
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`

Read at least the top of each so you understand what AG-UI events meridian-channel
must ultimately emit.

## Your task

Produce `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — a single
focused design document that maps the current meridian-channel source tree
and identifies every file that must change (or be newly introduced) for the
refactor above.

This is a **read-and-report** job, not a code edit. You do not modify source.
You produce one markdown file.

### Required coverage

For **every file under**:

- `src/meridian/lib/harness/` — adapter.py, claude.py, codex.py, opencode.py,
  common.py, transcript.py, launch_types.py, registry.py, direct.py,
  session_detection.py (and __init__.py if it matters)
- `src/meridian/lib/state/` — spawn_store.py, session_store.py, event_store.py,
  artifact_store.py, paths.py, reaper.py, reaper_config.py, atomic.py
- `src/meridian/cli/` — spawn.py, main.py, report_cmd.py (and the rest only
  if they're load-bearing for spawn/streaming)

Document, for each file you consider load-bearing:

1. **Current role** — one or two sentences on what this file does today.
2. **Refactor impact** — must change / may change / new sibling / unchanged,
   and why. Be specific: what new method, what new arg, what new return shape.
3. **Consumers** — who else imports or calls it? Will the refactor leak into
   those consumers? (grep `from meridian.lib.harness...` style imports.)
4. **Risk** — is there a test coupling, a CLI surface coupling, or a
   dogfood-workflow coupling that could break? (e.g. does dev-workflow
   orchestrator rely on a specific output shape?)

Files that are completely untouched by the refactor — say so explicitly in
a short "unchanged" list at the end with a one-line justification each.

### Structural analysis

After the per-file table, add a **Structural analysis** section that answers:

- Where should the **AG-UI event emitter** live? (new `ag_ui_events.py` under
  `harness/`? extended `transcript.py`? a new module?)
- Where should the **stdin control reader** live? (per-adapter? shared in
  `common.py`? a new `control_channel.py`?)
- Where should the **streaming launch type** live? (extend `launch_types.py`?
  new subtype?)
- How does `meridian spawn inject <spawn_id>` find the target spawn's stdin?
  (does it go via `.meridian/spawns/<id>/` artifact dir? Through
  `spawn_store.py`? Through a new control FIFO?)
- What does the current dogfood workflow need from spawn output (report.md,
  events, stdout) that could regress? This is the "don't break prod" risk list.

Cite specific file:line references wherever possible (e.g.
`src/meridian/lib/harness/claude.py:145`).

### Output tests and smoke surface

Also enumerate:

- Which existing **tests** (`tests/`, `tests/smoke/`) exercise harness output
  format, transcript building, or spawn lifecycle. For each, note whether the
  refactor would regress it as-is.
- Which **smoke tests** (the markdown guides) cover spawn behavior, CLI
  invocation shape, or output format.

### Format

Plain markdown. Headings, tables, code fences. No decorative prose. Target
length: dense and navigable, probably 400–700 lines depending on how many
load-bearing files exist.

Start with a 10-line "how to read this doc" preamble so the downstream
@architects know where to look for what.

### What you should NOT do

- Do not edit any source file.
- Do not edit any design doc.
- Do not design the new interface. That's the @architects' job — you're
  feeding them the map, not the solution.
- Do not speculate about AG-UI event semantics — the meridian-flow docs
  are the authority on those. Point to them, don't rewrite them.
- Do not touch `.agents/` or `.claude/agents/` — those are generated/
  owned by other agents right now.

### Deliverable path

Write the single file `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md`.

Report back with a short summary:
- Total load-bearing files identified
- Top 3 highest-risk touchpoints
- Any surprises or structural concerns the @architects should know up front
