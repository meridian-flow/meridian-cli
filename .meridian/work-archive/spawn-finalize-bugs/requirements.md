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

### B-05: Report source-of-truth duplication + cross-scope clobber

`meridian spawn report create --stdin` exists as an explicit write path for
`.meridian/spawns/<id>/report.md`, separate from the "auto-extracted report"
that `meridian spawn show` derives from the agent's final message. Two
issues compound:

1. **Duplicate source of truth.** The final message is the report.
   Having a second way to produce one creates drift, wastes tokens
   (agents re-write content they already emitted), and obscures which
   is canonical.

2. **Cross-scope clobber.** When called from inside a spawn, the tool
   resolves SPAWN_ID from the wrong scope and writes to the parent's
   `report.md` path. Observed this session: investigators p1835 and
   p1837 both clobbered `.meridian/spawns/p1713/report.md` (the parent
   dev-orch session's report), not their own.

This is the reporting-side counterpart to B-01..B-03 (the finalize-state
side). Same surface: "authoritative source of truth for spawn lifecycle
output." Preferred shape: delete `meridian spawn report create`, make the
auto-extracted final message canonical, treat `report.md` as derived cache
rather than primary state.

## Working hypothesis

B-01, B-02, B-03, B-05 form one conceptual family: **source-of-truth
confusion in the spawn lifecycle surface.**

- B-01/02/03 are the **state side**: drain loop vs stream terminal events
  disagree on what "done" means.
- B-05 is the **content side**: final message vs `report create --stdin`
  both claim to be the report.

B-04 is adjacent (HTTP validation), not part of the family.

Investigation confirmed by p1837 (gpt-5.4) + p1838 (opus): drain loop is
the sole authority for DrainOutcome; its `finally` block classifies every
clean connection close as `succeeded/0` regardless of cancel intent, idle,
or abnormal close. See `investigation-lane-{a,b}.md`.

## Design decisions (settled by research)

Research spawns p1843 (Codex idle semantics) and p1844 (report CLI blast
radius) settled the two open design questions:

- **B-01 approach:** treat Codex `turn/completed` for the tracked `turnId`
  as terminal (one-shot completion). No declared-spawn-shape API needed.
  See `research-codex-idle-semantics.md`.
- **B-05 approach:** delete `meridian spawn report create` + MCP
  `report_create`; rely on `spawn show` auto-extracted report from final
  message. 0 actual usages in corpus; blast radius is prompt/doc cleanup
  only. See `research-report-cli-surface.md`.

## Fix sites (concrete)

| Bug | File(s) |
|---|---|
| B-01 | `streaming_runner.py:245` `_terminal_event_outcome()` — add Codex `turn/completed` terminal case. `spawn_manager.py:267,326-354` drain loop. |
| B-02 | `spawn_manager.py:326-354` drain `finally` — consult `session.cancel_sent`. |
| B-03 | `streaming_runner.py:245` `_terminal_event_outcome()` — add `error/connectionClosed` → `failed`. |
| B-04 | `server.py:168-191` `_validation_error_handler` — scope 400 to "mutually exclusive" messages only. |
| B-05 | CLI surface (`spawn report create`), MCP tool (`report_create`), `docs/commands.md`, `docs/mcp-tools.md`, `.agents/` launch prompt + `meridian-spawn` skill references. |

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
