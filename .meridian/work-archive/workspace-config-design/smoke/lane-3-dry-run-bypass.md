## Verdict
regressions-found

Claimed EARS statements were not listed in the lane prompt or nearby `workspace-config-design` plan files, so this report is scenario-based rather than per-ID.

## Harness coverage
- claude: exercised
- codex: exercised
- opencode: exercised

## Scenarios passed
- `tests/smoke/spawn/dry-run.md` passed end to end in a throwaway repo rooted at `/tmp/meridian-lane3.UUzHv0`:
  `DRY-1` basic dry-run, `DRY-2` model override, `DRY-3` template vars, `DRY-4` reference files, `DRY-5` empty prompt failed cleanly.
- Primary dry-run honored the bypass:
  `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --format text --dry-run --agent coder`
  rendered `/bin/echo`.
- Real primary launch honored the bypass and exited cleanly:
  `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --format text --agent coder`
  returned `Session finished.` and recorded spawn `p1` as `succeeded (exit 0)`.
- App-server spawns did not inherit the bypass:
  with `MERIDIAN_HARNESS_COMMAND=/bin/echo`, `POST /api/spawns` over the Unix socket returned `HTTP/1.1 200 OK` with `{"spawn_id":"p2","harness":"codex","state":"connected",...}` instead of a bypass-related `400`.
- App-server baseline without the env override also returned `HTTP/1.1 200 OK` with `{"spawn_id":"p4","harness":"codex","state":"connected",...}`.
- Real background worker spawn did not inherit the bypass:
  `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --json spawn --background -a coder -p 'test'`
  created `p3`; two seconds later `spawn show p3` still reported `Status: running`, and `/tmp/meridian-lane3.UUzHv0/.meridian/spawns/p3/stderr.log` began with:
  `codex app-server (WebSockets)`
  `listening on: ws://127.0.0.1:36969`
  That confirms worker execution stayed on Codex rather than `/bin/echo`.
- Per-harness dry-run probes all worked:
  `uv run meridian --json --harness claude spawn -m sonnet -p 'harness probe' --dry-run`
  `uv run meridian --json --harness codex spawn -m codex -p 'harness probe' --dry-run`
  `uv run meridian --json --harness opencode spawn -m gemini -p 'harness probe' --dry-run`

## Scenarios failed
- **Scenario:** Worker foreground dry-run should honor bypass-substituted command preview
- **Command / env:** `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --format text spawn --dry-run -a coder -p 'test'`
- **Actual output:** `Dry run complete.` then `codex exec --json --model gpt-5.3-codex -c 'model_reasoning_effort="high"' --sandbox danger-full-access -`
- **Expected behavior:** per the lane contract, dry-run preview should have rendered `/bin/echo` as the resolved command.

- **Scenario:** Worker background dry-run should honor bypass-substituted command preview
- **Command / env:** `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --format text spawn --dry-run --background -a coder -p 'test'`
- **Actual output:** `Dry run complete.` then `codex exec --json --model gpt-5.3-codex -c 'model_reasoning_effort="high"' --sandbox danger-full-access -`
- **Expected behavior:** per the lane contract, background dry-run preview should also have rendered `/bin/echo`.

- **Scenario:** `spawn show` should reflect the bypassed command for a real bypass-substituted spawn
- **Command / env:** real spawn:
  `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian MERIDIAN_HARNESS_COMMAND=/bin/echo uv run meridian --format text --agent coder`
  then inspect:
  `env -u MERIDIAN_CHAT_ID MERIDIAN_REPO_ROOT=/tmp/meridian-lane3.UUzHv0 MERIDIAN_STATE_ROOT=/tmp/meridian-lane3.UUzHv0/.meridian uv run meridian --format text spawn show @latest --no-report`
- **Actual output:** 
  `Spawn: p1`
  `Status: succeeded (exit 0)`
  `Exited at: 2026-04-16T12:37:43Z`
  `Process exit code: 0`
  `Model: gpt-5.3-codex (codex)`
  `Duration: 0.0s`
- **Expected behavior:** the inspection surface should expose the bypassed `/bin/echo` command or equivalent evidence of the substituted launch command.

## Bypass scoping matrix
| Path | Without bypass | With bypass |
| --- | --- | --- |
| primary launch | `uv run meridian --format text --dry-run --agent coder` showed native Codex launch command: `codex --model gpt-5.3-codex ...` | `uv run meridian --format text --dry-run --agent coder` with `MERIDIAN_HARNESS_COMMAND=/bin/echo` showed `/bin/echo` and real launch succeeded immediately |
| worker spawn | `uv run meridian --format text spawn --dry-run -a coder -p 'test'` showed native worker preview: `codex exec --json ...` | dry-run still showed native `codex exec --json ...` instead of `/bin/echo` (regression vs lane expectation); real `spawn --background` stayed on Codex and did not leak the bypass |
| app server | `POST /api/spawns` returned `200 connected` on `/tmp/meridian-lane3.UUzHv0/app-no-bypass.sock` | `POST /api/spawns` also returned `200 connected` on `/tmp/meridian-lane3.UUzHv0/app.sock`; no bypass-related `400`, so the env override did not leak into app spawns |

## Surprises
- No separate CLI harness-command override flag was surfaced by `uv run meridian -h`, `uv run meridian spawn -h`, or `uv run meridian app -h`; only `MERIDIAN_HARNESS_COMMAND` exists in the current surface.
- The lane prompt expects `spawn --dry-run` to honor the bypass, but the current implementation wires `MERIDIAN_HARNESS_COMMAND` only into primary-launch code paths. The failing dry-run behavior is therefore either a real regression against intended behavior or a design/prompt mismatch that needs explicit resolution.
- `spawn show` has no command field at all, so even when a real primary bypass launch succeeds there is no built-in inspection surface that proves which command actually ran.
- Temp repo agent copies were missing skill files, so `coder` dry-runs emitted a warning about unavailable `dev-principles` and `shared-workspace`. That warning did not block any tested path.
