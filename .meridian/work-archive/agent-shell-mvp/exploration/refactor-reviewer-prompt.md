# Refactor-reviewer: structural review on agent-shell-mvp rewritten design tree

## Context

The `agent-shell-mvp` work item in meridian-channel was reframed per D34–D40. The rewritten design tree describes a refactor of meridian-channel's harness layer: each adapter (`claude.py`, `codex.py`, `opencode.py`) will emit AG-UI events, accept a stdin control protocol, and report capabilities via a semantic enum. A new sibling module `harness/ag_ui_events.py` will own the AG-UI event types and per-tool config. A new sibling module `harness/control_channel.py` will own the control-frame reader. A per-spawn FIFO at `.meridian/spawns/<id>/control.fifo` will let `meridian spawn inject` target a running streaming spawn.

Your job is to evaluate the **proposed structure** of this refactor — the module boundaries, the new files, the relationships between them, and whether the shape will age well. This is a design-time structural review, before any code is written.

## What to read

1. `$MERIDIAN_WORK_DIR/reframe.md` — context
2. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 — basis
3. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness authority
4. `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — **read this carefully**. It maps 37 load-bearing files across harness/, state/, cli/, launch/, and ops/. Structural analysis there is where the new sibling modules (`ag_ui_events.py`, `control_channel.py`) were originally proposed.
5. The rewritten design tree:
   - `$MERIDIAN_WORK_DIR/design/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
   - `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
   - `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
   - `$MERIDIAN_WORK_DIR/design/events/overview.md`
   - `$MERIDIAN_WORK_DIR/design/events/flow.md`
   - `$MERIDIAN_WORK_DIR/design/events/harness-translation.md`

You may want to also look at the current meridian-channel source to ground your review:
- `src/meridian/lib/harness/adapter.py` (current adapter protocol)
- `src/meridian/lib/harness/common.py` (current shared parsing helpers)
- `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` (current adapters)
- `src/meridian/lib/harness/transcript.py` (post-hoc text normalization, NOT where AG-UI goes)
- `src/meridian/lib/launch/process.py` (the stdin-to-PTY path that collides with streaming stdin)
- `src/meridian/lib/launch/stream_capture.py` (the bridge from subprocess pipe to observer callback)
- `src/meridian/lib/state/spawn_store.py` / `paths.py` / `reaper.py` (per-spawn state)

## Focus: structural health

Per `/dev-principles`, structural issues are highest-leverage to catch at design time — the shape shipped here becomes the shape every downstream phase builds on. Apply the signals from that skill:

### 1. Module boundaries and responsibilities

For each proposed new file and each modified existing file, ask:
- Is there a clear single responsibility, or is it a dumping ground?
- Does it fit the existing layering (mechanism in `lib/harness/`, policy in `cli/`, state in `lib/state/`)?
- Do the new modules (`ag_ui_events.py`, `control_channel.py`) have a clean reason to be siblings of the three adapter files rather than living inside `common.py`, `transcript.py`, or `launch/stream_capture.py`? The design argues they do — validate or push back.

### 2. Coupling and fan-out

- Does any adapter file take on knowledge that belongs in `ag_ui_events.py`? (If so, the abstraction is leaking.)
- Does `ag_ui_events.py` take on knowledge that belongs in a specific adapter? (If so, the shared module is overgeneralized.)
- How many files need to change to add a new harness? The answer should be roughly 1 (a new adapter file + registration) — flag if the design implies more.
- How many files need to change to add a new AG-UI event type? Ideally 1 (ag_ui_events.py) plus per-adapter emission. Flag if the design scatters this across the three adapters without a central contract.

### 3. Naming and greppability

- Are the new module names (`ag_ui_events.py`, `control_channel.py`) self-explanatory?
- Are the proposed control-frame kinds (`user_message`, `interrupt`, `cancel`) discoverable by grep?
- Does `HarnessCapabilities.mid_turn_injection` survive a grep across the codebase without being confused with something else?

### 4. Mixed concerns

The explorer pre-pass flagged that `transcript.py` is post-hoc text normalization for session log replay — putting AG-UI emission there would be a mixed concern. `common.py` is the shared parsing helper home and already at risk of becoming a dumping ground. Validate that the rewritten design keeps these files in their current roles and doesn't silently re-expand them.

### 5. Regression risks to existing interfaces

The refactor must not break:
- `report.md`, `output.jsonl`, `stderr.log` artifact contracts
- `meridian spawn show / log / wait / files / stats`
- `--from` and `--fork` invocation shapes
- `state/reaper.py` liveness detection (which currently keys off `report.md`)
- `launch/process.py` primary-launch stdin-to-PTY copy (which collides with a naïve "streaming owns stdin" approach)

Evaluate whether the rewritten design clearly preserves each of these. Flag any spot where the design implies a regression or is unclear about preservation.

### 6. Structural signals from `/dev-principles`

Check the design against these triggers:
- A single file proposed to exceed 500 lines or hold more than three responsibilities
- A new abstraction that accumulates conditionals to fit three different harnesses (bad sign — abstraction may be wrong-shaped)
- An import list whose growth signals rising coupling
- Dynamic dispatch or computed names that drop greppability (a concern for capability enum handling)

### 7. Refactoring opportunities surfaced by the design

The design may have implicitly identified existing structural debt that should be cleaned up in the same refactor. Flag candidates:
- Duplicated parsing helpers across the three adapters that should consolidate
- A `HarnessCapabilities` surface that currently uses booleans but should move to the semantic-enum pattern per `findings-harness-protocols.md`
- A `SpawnParams` / `SpawnResult` surface that needs extension for streaming and may have accumulated optional fields to prune first

### 8. Abstraction judgment (per `/dev-principles`)

Does the design propose abstractions at three or more genuine instances? Or at two instances that look similar on the surface but aren't semantically the same (bad — leave duplicated)?

## Anti-patterns to avoid in your review

- Don't propose a rewrite of the harness layer; the refactor is scoped to the three D36/D37 deliverables
- Don't redo the structural analysis already in `refactor-touchpoints.md` — build on it
- Don't flag style preferences (docstring phrasing, type-hint style) unless they cross the threshold into a structural signal

## Report format

Structured report with findings ranked by severity:

- **Blocker** — a structural choice will visibly degrade the codebase or lock in a wrong abstraction
- **Concern** — a structural risk or unclear boundary that should be resolved before implementation
- **Opportunity** — an unrelated structural cleanup the design surfaces that would be cheap to include in the same refactor
- **Nit** — naming/greppability nits

For each finding: cite the file + section, state the structural concern, and propose a concrete shape fix (module split, responsibility move, rename, etc.) if obvious.
