## Verdict
regressions-found

## Harness coverage
- claude: exercised
- codex: exercised
- opencode: exercised

## Scenarios passed
- Setup: created seed spawn `p1` on Codex and recorded harness session `019d9649-f546-75b0-87b8-b5fdd5f011c9`
- `FORK-2b` extra probe: `uv run meridian --json --fork c1 --dry-run` succeeded when using the actual session ID from `sessions.jsonl`
- `FORK-3b` extra probe: `uv run meridian --json spawn --fork c1 -p "Branch from actual source session."` succeeded when using the actual session ID from `sessions.jsonl`
- `FORK-4` `--fork` and `--from` are mutually exclusive
- `FORK-5` root `--fork` and `--continue` are mutually exclusive
- `FORK-6` model override on fork is honored in dry-run
- `FORK-7` agent override on fork is honored in dry-run
- `FORK-8` fork works with `--yolo` in dry-run
- `FORK-9` fork can target a different work item (`work_id: "fork-smoke-alt-work"` on `p3`)
- `FORK-10` Claude seed+fork captured distinct harness sessions (`p8` -> `p9`)
- `FORK-10` Codex seed+fork captured distinct harness sessions (`p10` -> `p11`)
- `FORK-11` source spawn metadata stayed unchanged
- `FORK-12` nonexistent fork ref fails cleanly
- `FORK-14` `--fork` + `--dry-run` previews without executing
- `FORK-16` spawn without harness session ID fails cleanly
- `FORK-17` legacy `--continue ... --fork` syntax gets helpful error
- Extra probe: chained fork `uv run meridian --json spawn --fork p2 -p "Fork from a fork."` launched `p14`

## Scenarios failed
- **Scenario:** Setup contract drift before numbered cases
- **Command:** `uv run meridian --json spawn -a reviewer -p "Seed session for fork smoke tests."`
- **Actual output:** `/tmp/meridian-fork-source-create.json` contained two JSON lines, not one document: `{"spawn_id":"p1","status":"running"}` and `{"duration_secs":58.68,"exit_code":0,"spawn_id":"p1","status":"succeeded"}`
- **Expected behavior:** `tests/smoke/fork.md` assumes a single JSON document; current CLI emits NDJSON-style status events

- **Scenario:** `FORK-1` `spawn --fork <spawn_id> -p` creates a new spawn and chat
- **Command:** `uv run meridian --json spawn --fork p1 -p "Branch from source spawn."`
- **Actual output:** command succeeded and produced `p2`, but persisted state is inconsistent: `spawns.jsonl` start row for `p2` kept `chat_id:"c0"` while `sessions.jsonl` created `c2`; `uv run meridian spawn children p1 --format text` returned `(no spawns)`
- **Expected behavior:** forked child should have a distinct Meridian chat ID and be discoverable as a child of the parent spawn

- **Scenario:** `FORK-2` root `--fork <session_id>` dry-run using the source row's session ref
- **Command:** `uv run meridian --json --fork c0 --dry-run`
- **Actual output:** `error: Session 'c0' not recognized by any harness. Use --harness to specify which harness owns this session.`
- **Expected behavior:** dry-run JSON contract like `{"message":"Fork dry-run.","forked_from":"<session-id>",...}`; the same command works with actual session `c1`, so the broken part is the stored source ref

- **Scenario:** `FORK-3` `spawn --fork <session_id> -p` using the source row's session ref
- **Command:** `uv run meridian --json spawn --fork c0 -p "Branch from source session."`
- **Actual output:** `error: Codex session 'c0' not found in threads table.`
- **Expected behavior:** child spawn should launch from the parent session ref; the same flow works with actual session `c1`

- **Scenario:** `FORK-10` OpenCode harness matrix fork
- **Command:** `MERIDIAN_DEFAULT_HARNESS=opencode uv run meridian --json spawn --fork p12 -p "Fork on opencode."`
- **Actual output:** `/tmp/meridian-fork-10-opencode-fork.json` ended with `{"duration_secs":122.5,"exit_code":2,"forked_from":"c0","spawn_id":"p13","status":"failed"}` after repeated warnings `OpenCode session endpoint did not become ready within 30.0s`
- **Expected behavior:** forked OpenCode child should complete with a distinct harness session like the Claude and Codex matrix cases

- **Scenario:** `FORK-13` unsupported harness path fails clearly
- **Command:** `MERIDIAN_DEFAULT_HARNESS=definitely-not-a-harness uv run meridian spawn --fork p1 -p "bad harness smoke"`
- **Actual output:** no validation error; it launched real spawn `p4` on Codex and had to be interrupted. Captured output: `{"spawn_id":"p4","status":"running"}` then `Spawn completed. Spawn id: p4 Forked from: c0 Exit code: 130`
- **Expected behavior:** immediate error mentioning unsupported/unknown harness, with no child spawn launched

- **Scenario:** `FORK-15` cross-harness fork is rejected
- **Command:** `MERIDIAN_DEFAULT_HARNESS=claude uv run meridian spawn --fork p1 -p "cross harness fork"`
- **Actual output:** command succeeded: `{"spawn_id":"p5","status":"running"}` then `Spawn completed. Spawn id: p5 Forked from: c0 Exit code: 0`; `spawns.jsonl` shows `p5` still ran on `harness:"codex"`
- **Expected behavior:** explicit rejection such as `Cannot fork across harnesses`; at minimum the harness override must not be silently ignored

- **Scenario:** `FORK-18` raw harness session ID forks with no Meridian lineage
- **Command:** `MERIDIAN_DEFAULT_HARNESS=codex uv run meridian --json spawn --fork 019d9649-f546-75b0-87b8-b5fdd5f011c9 -p "Raw harness fork."`
- **Actual output:** `/tmp/meridian-fork-18.json` reported `{"duration_secs":59.22,"exit_code":0,"forked_from":"c1","spawn_id":"p7","status":"succeeded"}` and `sessions.jsonl` recorded `c6` with `forked_from_chat_id:"c1"`
- **Expected behavior:** `forked_from` should be the raw harness session ID, with no Meridian chat lineage recorded

- **Scenario:** `FORK-19` fork prompt guidance is used
- **Command:** `uv run meridian --json spawn --fork p1 -p "Check fork guidance text." --dry-run`
- **Actual output:** `/tmp/meridian-fork-19.json` `composed_prompt` contained only the agent profile/report text plus `Check fork guidance text.`; it did not contain `You are working in a forked Meridian session`
- **Expected behavior:** fork dry-run prompt should include fork guidance and omit continuation guidance

## Fork coverage matrix
| Fork type | claude | codex | opencode |
|---|---|---|---|
| `spawn --fork <spawn_id>` | fail | fail | fail |
| `spawn --fork <session_id>` | unavailable | pass | unavailable |
| `root --fork <session_id> --dry-run` | unavailable | pass | unavailable |
| fork a fork (`spawn --fork p2`) | unavailable | fail | unavailable |
| raw harness session ID | unavailable | fail | unavailable |
| cross-harness rejection | fail | unavailable | unavailable |
| `--continue-fork` flag | unavailable | unavailable | unavailable |
| `--fork-from` flag | unavailable | unavailable | unavailable |

## Surprises
- No lane-local `Claimed EARS statements` list was present in the available phase artifacts, so traceability here is scenario-based rather than per-statement.
- The core regression is lineage split-brain: `spawns.jsonl` keeps `chat_id:"c0"` on every forked spawn, while `sessions.jsonl` creates new sessions (`c2`, `c3`, `c8`, `c10`, `c12`). That breaks `spawn children`, poisons follow-on `--fork <session_id>` when callers trust the spawn row, and makes reports disagree with persisted spawn rows.
- `spawns.jsonl` start rows for forked spawns already contain the child `harness_session_id`, unlike non-fork starts that get session IDs later via `update`. That suggests the row-before-fork ordering invariant is at least questionable in the new path.
- `MERIDIAN_DEFAULT_HARNESS` appears to be ignored for fork launches in at least two paths (`FORK-13`, `FORK-15`), which points at precedence/dispatch breakage in the refactored fork materialization path.
- Codex root dry-run from the real session ID `c1` worked, but it emitted a warning to stderr about dropped `--allowedTools` resolver flags before printing the JSON result.
