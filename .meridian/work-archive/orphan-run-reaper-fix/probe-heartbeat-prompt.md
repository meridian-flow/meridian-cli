# Explorer probe: harness output cadence in `running`

## Why this matters

Round 1 review (p1731 finding 3 — F4) flagged that the 120s heartbeat window is only justified for `finalizing` (bounded post-exit work). For `running`, the design currently **relies on `output.jsonl` / `stderr.log` mtimes moving** to signal liveness, which assumes every supported harness emits output within 120s during normal execution. That assumption is unproven.

We need either:
- **Evidence** that every supported harness emits at least one output-jsonl line within, say, 60s during any realistic `running` state (including long model-thinking gaps, tool-use-pending states, and approval waits); OR
- A recommendation to introduce a **runner-owned periodic heartbeat** that touches a `heartbeat` artifact every N seconds from the runner's own event loop, decoupled from harness output.

## What to probe

For each harness adapter in `src/meridian/lib/harness/` (at minimum claude, codex, opencode if present), answer:

1. What is the longest realistic gap between successive lines written to `output.jsonl` during normal `running`?
2. Are there harness states (approval prompts, long model thinking, tool execution) where output.jsonl *provably* does not get written for >60s?
3. Does the stream-capture pipeline (`src/meridian/lib/launch/stream_capture.py`) itself add any buffering that would further delay mtime updates?

## How to probe

1. **Past-run empirical evidence.** Walk `.meridian/spawns/*/output.jsonl` on this repo. For a sample of recent long spawns (look at any spawn older than, say, p1500 with substantial duration), compute the largest inter-line gap by `mtime` or by timestamp inside the JSON if available. Report per-harness worst gaps across the sample.
2. **Code inspection.** Read `src/meridian/lib/launch/stream_capture.py` to understand when output.jsonl mtime advances — per harness line, per flush, per interval?
3. **Harness-specific docs/behavior.** Check `src/meridian/lib/harness/claude/*.py`, `codex/*.py`, `opencode/*.py` for any "keepalive" or periodic-emit behavior. Report whether each harness can sit silent for >60s without crashing.

## Expected output

Write findings to `$MERIDIAN_WORK_DIR/probe-heartbeat.md`. Structure:

### Empirical gap distribution

| harness | sample size | p50 inter-line gap | p95 inter-line gap | max inter-line gap | spawn IDs checked |
|---|---|---|---|---|---|

### Harness-specific silence scenarios

For each harness, list scenarios where silence >60s is plausible even during healthy execution (e.g. Claude waiting for user approval, Codex running a long shell command, Opus thinking).

### Recommendation

One of:
- **No runner heartbeat needed.** Every harness emits within Ns; 120s window on output.jsonl is safe for `running`. Cite evidence.
- **Runner heartbeat needed.** Name the silence scenarios that force the decision. Propose tick interval (30s seems right if threshold is 120s — 4× safety factor).
- **Per-state thresholds.** If `running` needs a different threshold from `finalizing`, quantify both and justify.

Keep this to one page. Data over speculation. It's OK to say "sample too small to conclude" if that's the truth — that's also evidence for picking the runner-heartbeat path.

## Reference

- `.meridian/work/orphan-run-reaper-fix/plan/preservation-hint.md`
- `.meridian/spawns/p1731/report.md` finding 3 (the flag)
- `.meridian/work/orphan-run-reaper-fix/design/feasibility.md` (Round 1 unprobed assumption at line 75)

## Scope discipline

Read-only. Do not edit any source. Do not propose an implementation — only evidence + recommendation. The design memo will incorporate your finding.
