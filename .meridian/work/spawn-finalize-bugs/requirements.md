# Spawn Finalize-Path Bugs

Follow-up to `dead-code-sweep` (archived). After auth deletion + dead-code
cleanup, smoke retest showed three lifecycle/finalize bugs survive and one
minor spec bug. These are the scope.

## Background

The spawn-control-plane redesign shipped heartbeat-based liveness,
`finalizing` status gate, and origin-tagged finalize rows. Unit/integration
tests pass. Smoke (`p1821`, `p1822`) found finalize misbehavior; dead-code
sweep deleted ~1000 lines of auth + dead shadows; retest smoke (`p1830`,
`p1835`) confirmed most blockers folded away but the finalize-path bugs are
live logic, not dead shadows.

## Surviving bugs (from `p1835`)

### B-01: Idle → finalized never fires

Graceful agent completion (harness emits `turn/completed` + `thread/status/changed idle`)
does not flip spawn status from `running` to finalized. Observed in smoke
(p1/p4 stuck `running` after final answer) AND in this dev-orch session
(`p1835` itself stuck `running` at time of write, ~20 minutes after its
agent went idle).

### B-02: Cancel origin mis-tagged

HTTP and CLI cancel both finalize spawns as `{status: succeeded, exit_code: 0}`
despite the stream having emitted `cancelled` / `143`. The finalizer is
ignoring the cancel event and picking up the "successful subprocess exit"
path instead.

### B-03: SIGKILL classified as succeeded

Worker `SIGKILL` on an app-run spawn finalizes as `{status: succeeded,
duration_secs: 9.6}` with only in-progress `sleep 120` + `error/connectionClosed`
in `output.jsonl`. Reaper authority model should tag this as
`origin=reaper, status=failed`.

### B-04: `/inject` missing-field returns 400 instead of 422

Minor spec drift. Documented contract is `422 unprocessable entity` for
missing required field. Live behavior is `400 bad request`. Likely one-line
fix. Separate from B-01..B-03.

## Working hypothesis

B-01, B-02, B-03 look like one bug family: **the finalizer reads the wrong
source of truth for exit classification.** Probable: it reads the harness
subprocess exit code or final-agent-message, not the stream's
cancel/exit/connection-closed events. Authoritative-origins model
(`{runner, launcher, launch_failure, cancel}`) may not be wiring cancel +
reaper events into the finalize row correctly.

Investigators should falsify or confirm this hypothesis, not assume it.

## Scope

- Root-cause each surviving bug with evidence pointers.
- Produce diagnosis reports (read-only).
- B-01/B-02/B-03 likely converge on one fix family; B-04 is standalone.
- No fixes yet — fix cycle follows investigation.

## Out of scope

- Re-opening deleted auth feature.
- Any redesign of the control plane.
- `docs/mcp-tools.md` stale entry (doc-only, deferred).

## Success criteria

- Each of B-01..B-04 has a diagnosis report with file:line pointers.
- Investigators converge or diverge clearly on the "wrong source of truth"
  hypothesis.
- Enough detail that the next coder phase can execute without re-investigating.

## Artifacts to read

- `.meridian/spawns/p1822/report.md` — original AF_UNIX smoke report
- `.meridian/spawns/p1830/report.md` — retest cancel/interrupt lane (all PASS)
- `.meridian/spawns/p1835/report.md` — retest AF_UNIX/liveness lane (surviving bugs)
- `.meridian/work-archive/dead-code-sweep/` — what was deleted
- `.meridian/work-archive/spawn-control-plane-redesign/design/` — authoritative design for reaper authority + finalize origin tagging
- `src/meridian/lib/state/` — spawn store + reaper logic
- `src/meridian/lib/streaming/` — stream events + cancel path
