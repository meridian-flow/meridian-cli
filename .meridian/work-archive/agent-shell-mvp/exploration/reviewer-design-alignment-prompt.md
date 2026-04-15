# Reviewer: design alignment on agent-shell-mvp rewritten design tree

## Context

The `agent-shell-mvp` work item in meridian-channel was **reframed** per decisions D34–D40 at `$MERIDIAN_WORK_DIR/decisions.md`. Pre-reframe subtrees (`strategy/`, `extensions/`, `packaging/`, `frontend/`, `execution/`) were deleted. Two architects just rewrote the remaining scope:

- **Architect A** (p1161): `design/overview.md` + `design/harness/{overview,abstraction,adapters,mid-turn-steering}.md`
- **Architect B** (p1162): `design/events/{overview,flow,harness-translation}.md` (replacing the old `normalized-schema.md`)

## What to read

Read these in order:

1. `$MERIDIAN_WORK_DIR/reframe.md` — the architectural correction
2. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 (bottom of file) — the basis decisions
3. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness protocol authority (all three harnesses tier-1, mid-turn steering is V0, capability is a semantic enum)
4. `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — the 37-file impact map from explorer p1160
5. The rewritten design tree:
   - `$MERIDIAN_WORK_DIR/design/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
   - `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
   - `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
   - `$MERIDIAN_WORK_DIR/design/events/overview.md`
   - `$MERIDIAN_WORK_DIR/design/events/flow.md`
   - `$MERIDIAN_WORK_DIR/design/events/harness-translation.md`

## Focus: design alignment

Your job is to verify the rewritten design tree **hangs together as a coherent whole** and **stays inside the corrected D34–D40 scope**. You're NOT here to redesign or re-litigate decisions; you're here to catch drift, gaps, and contradictions.

Check in particular:

### 1. Scope discipline (D38)

- Does any doc reintroduce pre-reframe framing (strategy, extensions, packaging, frontend redesign, local deployment packaging, meridian-llm-go providers)?
- Does any doc talk about agent-shell-mvp as a "new product" rather than a meridian-channel refactor?
- Does any doc mention `providers/claude-code/` or similar harness-shim providers in meridian-llm-go? (D40 explicitly rejects this.)
- Does any doc propose Go rewrites of meridian-channel? (D35 says stays Python.)

### 2. Decision traceability (D34–D40)

Every design claim should trace back to at least one of D34–D40. Flag claims that don't — either they need a citation or they're out of scope.

### 3. External contract fidelity (shallow check)

The AG-UI event taxonomy and 3-WS topology live in `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/`. The rewritten tree should **reference** those files and **not redefine** anything. Flag any place where the rewritten docs restate the schema rather than link to it. (A separate reviewer is doing a deeper external-contract fidelity review, so you can stay at the "does it duplicate or does it link?" level.)

### 4. Internal consistency across the 8 docs

- Does `design/overview.md` promise deliverables that the harness + events docs actually cover?
- Do the harness docs and the events docs agree on where translation lives (`harness/ag_ui_events.py` sibling module)?
- Do the harness docs and the events docs agree on the control-frame model (`user_message`, `interrupt`, `cancel`)?
- Do the harness docs and the events docs agree on the capability semantic enum (`queue` | `interrupt_restart` | `http_post` | `none`)?
- Does anything contradict `findings-harness-protocols.md`? (The findings doc is authoritative for wire formats, mid-turn semantics, and capability reporting.)
- Does any doc reference a file that doesn't exist in the rewritten tree?
- Does the refactor-touchpoints map agree with the harness docs on which files must change and their current roles?

### 5. D37 open questions

The four D37 open questions (stdin ownership, frame versioning, error reporting, integration with existing spawn commands) should be **resolved** in `harness/mid-turn-steering.md`. Flag any that are left open, answered incompletely, or where the resolution contradicts findings-harness-protocols.md.

### 6. Dogfood workflow preservation

The explorer pre-pass flagged that `report.md`, `output.jsonl`, `stderr.log`, `spawn show/log/wait/files/stats`, `--from`, `--fork`, and `reaper.py` are load-bearing for existing dev-workflow orchestrators. The AG-UI streaming surface must be **additive**, not a replacement. Flag any place where the rewritten design implies replacement or unclear regression risk.

### 7. Edge cases and failure modes

The design should enumerate failure modes and edge cases explicitly — this is mandatory per /dev-principles. Flag missing coverage of:
- What happens when the harness subprocess dies mid-stream
- What happens when control-frame delivery fails
- What happens when a control frame arrives during `--fork` or `--from`
- What happens when the AG-UI stream consumer disconnects but the harness is still running
- What happens when two `meridian spawn inject` commands race against the same target spawn

## Anti-patterns to avoid in your review

- Don't propose alternative architectures; the architects already made the structural calls and the orchestrator ratified them
- Don't re-litigate D34–D40; they're the basis
- Don't demand exhaustive implementation detail; this is a design tree, not a phase blueprint
- Don't flag missing coverage for things that are explicitly out-of-scope per D38/D39/D40

## Report format

Structured report with findings ranked by severity:

- **Blocker** — the design contradicts itself, contradicts findings-harness-protocols.md, or reintroduces out-of-scope framing. Must be fixed before handoff.
- **Concern** — a real gap or unclear claim that a future implementer will trip on. Should be fixed.
- **Nit** — wording or navigation improvement; optional.

For each finding: cite the file + section, state the problem, and propose a concrete fix if obvious.
