# Task: Re-verify docs/ Fix Addressed Prior Findings

Spawn p1776 flagged accuracy issues in docs/. Spawn p1778 applied fixes. Verify each was addressed.

## Prior findings (see `.meridian/spawns/p1776/report.md` for full detail)

1. `docs/commands.md` and `docs/mcp-tools.md` — `finalizing` description corrected: NOT "draining output"; instead "post-exit work complete, committing terminal state" (or equivalent). Drain/extract happens while still `running`.
2. `docs/troubleshooting.md` — 120s window should cover any of `heartbeat`, `output.jsonl`, `stderr.log`, `report.md` (not heartbeat alone).
3. `docs/troubleshooting.md` — `orphan_run` vs `orphan_finalization` described in terms of status at reap time, not before/after harness exit.
4. `docs/_internal/ARCHITECTURE.md:~271` — `start` event example uses `"status":"queued"` (not `"running"`).
5. `docs/_internal/ARCHITECTURE.md:~276, ~385, ~397` — sequence corrected to "extract results → mark finalizing → finalize".

## Output
For each: FIXED / NOT FIXED / REGRESSED with quotes. Flag new issues. If clean, say "converged".
