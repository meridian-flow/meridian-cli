## Verdict
regressions-found

## Harness coverage
- claude: exercised
- codex: exercised
- opencode: exercised

## Scenarios passed
Adversarial basics:
- Huge dry-run prompt with long repeated content plus shell-sensitive characters stayed stable and produced no traceback.
- Concurrent read-heavy commands (`models list`, `skills list`, `spawn list`) completed in parallel without tracebacks or malformed JSON output.
- Dry-run permission-boundary probe (`touch /root/forbidden`) completed cleanly.
- Mixed `--json --format json` on `models list` returned valid JSON.

Bad-input handling:
- Missing reference file via `-f /tmp/no-such-ref-file.md` failed cleanly with `error: Reference file not found`.
- Broken-symlink reference file failed cleanly with `error: Reference file not found`.
- `--from p99999` failed cleanly with `error: Spawn 'p99999' not found`.
- `spawn cancel p99999` returned a structured JSON error and exit code 1.
- `spawn cancel p1` on an already-succeeded spawn returned success without corrupting state.
- Repeated `spawn wait p1` calls were stable and returned the same terminal result both times.

Concurrency:
- Cross-harness background spawns on Claude, Codex, and OpenCode all launched successfully in the same scratch repo.
- Three concurrent background spawns (`p5`/`p6`/`p7`) all created rows cleanly; final `spawns.jsonl` remained valid JSONL.

Recovery via supported CLI:
- After the dead-runner probe left `p8` stuck as `running`, `uv run meridian spawn cancel p8` repaired the row and stamped a terminal `cancelled` finalize event with `origin: "cancel"`.

## Scenarios failed / regressions found
- **Scenario:** `meridian doctor` did not reconcile a force-killed background spawn even after both recorded PIDs were dead.
- **Command:**
```bash
env MERIDIAN_REPO_ROOT=/tmp/meridian-adversarial.IVaghN \
  MERIDIAN_STATE_ROOT=/tmp/meridian-adversarial.IVaghN/.meridian \
  uv run meridian --json spawn -a reviewer -m gpt-5.4-mini \
  -p "Before answering, wait 60 seconds and then say killed" --background

kill -9 2581073
kill -9 2581060

env MERIDIAN_REPO_ROOT=/tmp/meridian-adversarial.IVaghN \
  MERIDIAN_STATE_ROOT=/tmp/meridian-adversarial.IVaghN/.meridian \
  uv run meridian doctor

env MERIDIAN_REPO_ROOT=/tmp/meridian-adversarial.IVaghN \
  MERIDIAN_STATE_ROOT=/tmp/meridian-adversarial.IVaghN/.meridian \
  uv run meridian spawn show p8
```
- **Actual output:**
```text
{"spawn_id": "p8", "status": "running"}

ok: WARNINGS
repo_root: /tmp/meridian-adversarial.IVaghN
runs_checked: 8
agents_dir: /tmp/meridian-adversarial.IVaghN/.agents/agents
skills_dir: /tmp/meridian-adversarial.IVaghN/.agents/skills
repaired: stale_session_locks
warning: missing_skills_directories: No configured skills directories were found.
warning: active_spawns_present: Active spawns still present: p8

Spawn: p8
Status: running
Model: gpt-5.4-mini (codex)
Parent: p1927
Log: /tmp/meridian-adversarial.IVaghN/.meridian/spawns/p8/stderr.log
Hint: tail -f /tmp/meridian-adversarial.IVaghN/.meridian/spawns/p8/stderr.log
```
- **Expected behavior:** After both the worker PID (`2581073`) and runner PID (`2581060`) were gone, `meridian doctor` should have reconciled `p8` out of `running` and stamped an orphan/failure terminal state instead of leaving a ghost active spawn.
- **Severity:** silent-wrong

- **Scenario:** Passive state-integrity check found stale `.flock` sidecars left in `.meridian/` after the lane completed.
- **Command:**
```bash
find /tmp/meridian-adversarial.IVaghN/.meridian -name '*.flock' -print | sort
```
- **Actual output:**
```text
/tmp/meridian-adversarial.IVaghN/.meridian/session-id-counter.flock
/tmp/meridian-adversarial.IVaghN/.meridian/sessions.jsonl.flock
/tmp/meridian-adversarial.IVaghN/.meridian/spawns.jsonl.flock
```
- **Expected behavior:** `tests/smoke/state-integrity.md` STATE-5 expects no stale `.flock` sidecars to remain after setup/use.
- **Severity:** cosmetic

## State integrity findings
- `spawns.jsonl` stayed parseable after all adversarial runs: 70 non-empty JSON lines, each a valid object with an id field.
- `sessions.jsonl` stayed parseable after all runs: 23 non-empty JSON lines, all valid JSON objects.
- Top-level lock files were absent by the end of the lane; no unusable lock file remained.
- `meridian doctor` finished cleanly at the end of the lane once `p8` was manually cancelled; final warning surface was only `missing_skills_directories`.
- `.flock` sidecars remained present, so passive state hygiene is not fully clean.
- I did not run `tests/smoke/adversarial.md` ADV-3 or `tests/smoke/state-integrity.md` STATE-6..10 verbatim because this lane’s prompt explicitly forbids manually modifying `.meridian/` files. Coverage here stayed on real CLI/process behavior plus passive integrity inspection.

## Creative scenarios you invented
- Real cross-harness baseline runs on Codex (`p1`/`p4`), Claude (`p2`/`p5`), and OpenCode (`p3`) in one scratch repo.
- Concurrent background spawn fire (`p5`/`p6`/`p7`) to probe `spawns.jsonl` race behavior.
- Force-kill of a live background spawn’s worker and runner PIDs, followed by `doctor`, `spawn show`, and supported recovery via `spawn cancel`.
- `spawn cancel` on a nonexistent id and on an already-succeeded id.
- Broken-symlink reference file via `-f`.
- Directory passed to `--prompt-file`.
- Repeated `spawn wait` on the same terminal spawn.
- `--from` pointing at a nonexistent spawn.

## Surprises
- `uv run meridian spawn -a reviewer --prompt-file /tmp` returns a structured error, but the message is raw Python text: `{"error":"[Errno 21] Is a directory: '/tmp'","exit_code":1,"type":"error"}`. No traceback, but the UX is rough.
- `MERIDIAN_HARNESS_COMMAND=/dev/null uv run meridian --json spawn ...` still produced a normal successful Codex run (`p4`) instead of an obvious harness-override failure. I did not treat this as a regression because I did not verify the intended semantics first, but it is worth clarifying.
