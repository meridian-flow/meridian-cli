## Verdict
regressions-found

## Harness coverage
- claude: exercised
- codex: exercised
- opencode: exercised

## Scenarios passed
- `tests/smoke/quick-sanity.md`: QS-1 through QS-8 all passed in `/tmp/meridian-quick.vYK6gG`.
- Codex background lifecycle: `spawn --background` returned `{"spawn_id":"p1","status":"running"}`, `spawn wait` reached `succeeded (exit 0)`, `spawn show` and `spawn report show` both returned the final report, and `spawn stats` reflected the run in `/tmp/meridian-life-codex.US2BaA`.
- Claude background lifecycle: create/wait/show/report succeeded in `/tmp/meridian-life-claude.7Y1mct`.
- OpenCode background lifecycle: create/wait/show succeeded in `/tmp/meridian-life-opencode.8HSNrX`.
- Codex cancel flow: background spawn stayed `running`, `spawn cancel` terminated it, and `spawn wait`/`spawn show` converged to `cancelled (exit 143)` in `/tmp/meridian-cancel.xgJTol`.
- `tests/smoke/spawn/lifecycle.md` LIFE-6 passed: nested read with `MERIDIAN_DEPTH=1` did not stamp `orphan_run`.
- `tests/smoke/spawn/lifecycle.md` LIFE-8 passed: late metadata update did not downgrade a terminal `succeeded` row.
- State files stayed well-formed JSONL in the exercised repos; I saw expected persistent `.flock` sidecars but no truncation.

## Scenarios failed
- **Scenario:** Foreground/background dry-run UX parity check from lane prompt.
- **Command:** `MERIDIAN_REPO_ROOT=/tmp/meridian-fg-bg-text.yBJDKa MERIDIAN_STATE_ROOT=/tmp/meridian-fg-bg-text.yBJDKa/.meridian uv run meridian spawn -a coder -p "echo ok" --dry-run --background`
- **Actual output:** `Dry run complete.` then `codex exec --json -` and `spawn list` remained `(no spawns)`. JSON mode was also just `{"agent":"coder",...,"status":"dry-run"}` with no spawn id.
- **Expected behavior:** Background dry-run should return immediately with a spawn id so `spawn show` can report the terminal dry-run state, while foreground dry-run blocks to terminal.

- **Scenario:** OpenCode report extraction on successful run.
- **Command:** `MERIDIAN_REPO_ROOT=/tmp/meridian-life-opencode.8HSNrX MERIDIAN_STATE_ROOT=/tmp/meridian-life-opencode.8HSNrX/.meridian uv run meridian spawn report show p1`
- **Actual output:** `# Auto-extracted Report` followed by `{"event_type":"session.idle","harness_id":"opencode","payload":{"properties":{"sessionID":"ses_269b4ee21ffeUW9O8WwgnfsOVR"},"type":"session.idle"}}`
- **Expected behavior:** `report.md` should contain the spawned agent's final assistant message, not an OpenCode transport/session event envelope.

- **Scenario:** `tests/smoke/spawn/lifecycle.md` LIFE-7 finalizing filter.
- **Command:** `MERIDIAN_REPO_ROOT=/tmp/meridian-life-invariants.iGZ86q MERIDIAN_STATE_ROOT=/tmp/meridian-life-invariants.iGZ86q/.meridian uv run meridian --json spawn list --status finalizing --limit 20`
- **Actual output:** `{"spawns": [], "truncated": false}` even though `spawns.jsonl` contained a seeded `start` row with `"id":"p-finalizing-filter-smoke","status":"finalizing"`. The read path then reconciled it to `{"event":"finalize","error":"orphan_finalization","status":"failed"}`.
- **Expected behavior:** The seeded `finalizing` row should be returned by the filter, matching the smoke doc's assertion.

## Foreground/background UX check
`spawn --background` on live runs still behaves correctly: Codex, Claude, and OpenCode each returned a spawn id immediately, and `spawn show`/`spawn wait` resolved to terminal states. The regression is specific to `--dry-run --background`: it behaves exactly like foreground dry-run and produces no spawn row or spawn id, so the flipped default in `cli/main.py` is not observable on that path.

## Surprises
- The work item has no current phase blueprint or `Claimed EARS statements` artifact under `.meridian/work/workspace-config-design/plan/`; per-ID EARS verification is blocked by planning state, so this lane is best-effort runtime coverage rather than contract-complete coverage.
- `spawn show` exposed `running` and terminal states correctly in live runs; `finalizing` was visible in `spawns.jsonl` on all successful/cancelled runs but too brief to catch reliably via `spawn show`.
- `spawn cancel` printed `Spawn did not terminate within grace; reaper will reconcile.` and exited non-zero before the subsequent `spawn wait` showed the run as cleanly `cancelled (exit 143)`. That looks acceptable but is worth keeping in mind when reading cancel automation output.
