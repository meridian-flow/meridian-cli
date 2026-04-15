# Events Overview

> **What this subtree describes**: how meridian-channel's harness adapters
> translate each harness's native event stream — Claude stream-json NDJSON,
> Codex JSON-RPC `item/*` notifications, OpenCode HTTP session events — into
> the canonical **AG-UI event taxonomy** consumed by meridian-flow's frontend
> reducer.
>
> **What this subtree does NOT do**: define the AG-UI taxonomy. The taxonomy
> lives in meridian-flow. This subtree is the *translation* story, not the
> *schema* story.

Up to [../overview.md](../overview.md). Sibling subtree: [`../harness/`](../harness/overview.md).

## Where the Taxonomy Lives

The canonical AG-UI event taxonomy is defined and owned by meridian-flow's
biomedical-mvp design tree. meridian-channel does not redefine, version, or
fork it — it emits events in the shape meridian-flow's reducer already expects.

| Canonical source | What it defines |
|---|---|
| [`meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md) | End-to-end AG-UI event sequence during a turn, with traces |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md) | 3-WS topology, Agent WS role, streaming reducer contract |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md#per-tool-display-config`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md#per-tool-display-config) | Canonical `ToolDisplayConfig` contract and `toolDisplayConfigs` registry (`toolName`-keyed, frontend-resident) |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md) | Per-tool render config example: python (stdout visible inline) |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md) | Per-tool render config example: bash (everything collapsed) |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md) | DISPLAY_RESULT and TOOL_OUTPUT payload contracts |

When this subtree references an event by name (`TOOL_CALL_START`, `DISPLAY_RESULT`,
etc.) it always means the meridian-flow definition. When it talks about per-tool
display behavior, it means meridian-flow's frontend `ToolDisplayConfig` fields
(`inputCollapsed`, `stdoutCollapsed`, `stderrMode`) resolved from
`toolDisplayConfigs` by `toolName`. Read those docs first if any name is
unfamiliar — this subtree is deliberately a thin layer on top of them.

## Why AG-UI Is Canonical (D36)

[D36](../../decisions.md)
makes AG-UI the single canonical schema for meridian-channel's streaming
output. The pre-reframe `events/normalized-schema.md` proposed a parallel
"meridian-channel normalized schema" with its own event names and lifecycle
rules. **D36 rejects that.** A parallel schema would mean two wire contracts
for the same conceptual events, two reducers to maintain, and a translation
layer between them — for no benefit, because meridian-flow already has a
working frontend that consumes AG-UI events.

The corrected framing from [`../../reframe.md`](../../reframe.md) is that
agent-shell-mvp is a **local deployment shape** of meridian-flow's frontend —
not a new product. The frontend reducer, the per-tool render defaults, and
the activity-stream item kinds already exist. meridian-channel's job is to
*emit events that fit* — not to invent its own dialect.

## Where Translation Happens

Translation lives at the **adapter boundary** — inside each harness adapter
(`src/meridian/lib/harness/{claude,codex,opencode}.py`), not in a post-hoc
normalization layer.

Per the structural analysis in
[`../refactor-touchpoints.md` §Structural Analysis](../refactor-touchpoints.md#structural-analysis),
the canonical home for the AG-UI event model types and shared serialization
helpers is a **new sibling module** `src/meridian/lib/harness/ag_ui_events.py`:

- **Not in `transcript.py`** — that file is post-hoc text normalization for
  session log replay; AG-UI emission is a wire-format concern.
- **Not in `common.py`** — `common.py` already collects shared parsing
  helpers; piling AG-UI taxonomy on top makes it a dumping ground for
  adapter-specific rules.
- **Not in `launch/stream_capture.py`** — that file is the bridge that
  ferries parsed events from the subprocess pipe to the observer callback.
  It's the right plumbing, but the taxonomy belongs one layer up in the
  adapter, not in generic stream capture.

Each adapter owns its harness's wire-format → AG-UI translation. Shared
event constructors and serialization helpers live in `ag_ui_events.py` so the
three adapters don't diverge on what an `AGUIToolCallStart` payload looks like.
The adapter layer does **not** own per-tool display config tables; that remains
frontend-resident in meridian-flow's `toolDisplayConfigs` registry (see
[`frontend/component-architecture.md` §Per-Tool Display Config](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md#per-tool-display-config)).
The adapter contract — i.e., the *interface* the rest of meridian-channel sees —
lives in [`../harness/abstraction.md`](../harness/abstraction.md). This subtree
covers the *event-level* view; the harness subtree covers the *adapter contract*
view. They reference each other and don't duplicate.

## Navigation

| Doc | Purpose |
|---|---|
| [flow.md](flow.md) | The AG-UI event sequence during a streaming spawn, from `RUN_STARTED` to `RUN_FINISHED`, with example traces (simple text turn, tool-call turn) |
| [harness-translation.md](harness-translation.md) | Per-harness mapping tables: native wire format → AG-UI events, plus tool naming coordination (no wire config) and known gaps |

For the *adapter contract* view (protocol interface, lifecycle methods,
mid-turn steering semantics), see [`../harness/`](../harness/overview.md).
