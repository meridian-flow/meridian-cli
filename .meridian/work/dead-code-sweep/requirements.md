# Dead Code Sweep + Auth Removal + Post-Impl Cleanup

Post-cycle cleanup after the spawn-control-plane redesign shipped. Scope
combines three threads that turn out to be the same story: incomplete
removal of old paths left shadows live, and one feature (authorization)
turned out not worth having at all.

## Background

The spawn-control-plane redesign (`.meridian/work-archive/spawn-control-plane-redesign/`)
shipped across commits `c533d47..64ce2f9`. All 693 unit/integration tests
pass, but:

- Smoke testing (`p1821`, `p1822`) found 7 end-to-end blockers where
  shipped code did not actually match the design.
- Dead-code sweep (`p1819`, `p1820`, `p1818`) enumerated ~12 safe-delete
  items plus fence markers.
- Root-cause overlap: several smoke failures are caused by the same
  dead-code shadows the sweep identified (e.g. control-socket `cancel`
  type still handled, `--cancel` CLI flag still present, ws_endpoint
  `caller_from_env` fallback contradicting peercred-deny).
- User decision: the authorization feature is not worth maintaining.
  The threat model was "honest actors, solo dev" — the mitigation
  ("don't expose lifecycle in MCP") is cheaper than a guard that
  protects against a problem we don't have.

## Scope

### Part A — Delete the authorization feature

Remove `AuthorizationGuard` and all caller-identity plumbing:

- `AuthorizationGuard` module and all `authorize()` call sites
- SO_PEERCRED / peer-cred extraction plumbing
- `/proc/<pid>/environ` caller-environment reader
- `caller_from_env` / `_caller_from_http` / `_caller_from_socket_peer` helpers
- `MERIDIAN_SPAWN_ID` caller-identity read path (env var itself stays for
  parent-tracking and other legitimate uses; only the auth-specific reads go)
- `AUTH-*` EARS leaves, `spec/authorization.md`, `architecture/authorization_guard.md`
- Corresponding test files

**Keep:** AF_UNIX transport. It earned its keep separately (no TCP
exposure, no `--host 0.0.0.0` footgun). Authorization was never the
reason for AF_UNIX; the reason was binding discipline.

**Replace with:** remove lifecycle ops (cancel, interrupt) from the MCP
agent-tool surface entirely. An LLM subagent should not have a `spawn
cancel` tool exposed via `@manifest.py`. Inject stays (cooperative
text-send is a feature).

Revert `decisions.md`: mark D-06, D-14, D-19 as reverted with a
D-25 entry explaining why (threat model doesn't justify the surface).

Update `requirements.md` success criterion #5: restate as "LLM agent-tool
surface does not expose cancel or interrupt."

### Part B — Dead code deletion

Safe-delete items from the three-reviewer sweep, in rough dependency
order (smallest blast radius first):

1. `streaming/types.py:22,28` — `CancelControl` class + `ControlMessage`
   cancel arm
2. `streaming/control_socket.py:134` — `message_type == "cancel"`
   migration shim (fixes smoke blocker #2)
3. `cli/spawn_inject.py` — remaining `--cancel` flag / `action="cancel"`
   inbound-record code (fixes smoke blocker #2 complement)
4. `app/server.py:501,516` — `legacy_delete_spawn()` + `DELETE /api/spawns/{id}` route
5. `streaming/signal_canceller.py:270` — `_read_background_pid()` (no writer anywhere)
6. `state/spawn_store.py:104` — `wrapper_pid` field (write-only)
7. `state/spawn_store.py:67,503` — `LEGACY_RECONCILER_ERRORS` +
   `resolve_finalize_origin()` shims
8. `harness/connections/__init__.py:11` — `register_connection()` retired shim
9. `launch/claude_preflight.py` — backcompat re-export wrapper
10. `state/event_store.py:63` — `append_event(store_name=...)` ignored param
11. `core/context.py:16,52` — `parent_spawn_id`, `child_context()`,
    `MERIDIAN_PARENT_SPAWN_ID` (env drift, never actually set)
12. `state/paths.py:155,167` — `resolve_work_items_dir`,
    `resolve_work_archive_scratch_dir` export-only leftovers
13. `harness/launch_spec.py:37,38` — `_SPEC_HANDLED_FIELDS`, `_REGISTRY`
    test scaffolding

**Fence markers to investigate before deciding:**

- `reaper.py:157` — `missing_worker_pid` error label is semantically
  stale but path is live. Rename to `missing_runner_pid` (matches the
  new "runner = whoever owns HarnessConnection" reframe).
- `ws_endpoint.py:266` — `caller_from_env` fallback. Dies naturally when
  Part A deletes the auth guard.

**Explorer-flagged orphaned modules** — verify zero inbound imports
before deletion:

- `__main__.py`, `dev/pytests.py`, `lib/app/agui_types.py`,
  `lib/launch/claude_preflight.py`, `stream_capture.py`, `terminal.py`,
  `timeout.py`, `lib/ops/spawn/context_ref.py`, `execute.py`,
  `prepare.py`, `lib/state/reaper_config.py`

Some of these (e.g. `__main__.py`, `pytests.py`) are legitimate entry
points and the import-graph scan missed their invocation path — do not
delete blindly.

### Part C — Smoke retest

After Parts A and B land, re-run both smoke lanes (same scenarios as
`p1821` cancel/interrupt and `p1822` AF_UNIX/liveness) to see which
bugs survive deletion.

Expected: several smoke blockers fold away when their root-cause dead
code is deleted. In particular, #2 (control-socket cancel live) is
directly caused by the `control_socket.py:134` cancel shim, and #3/#4
(auth enforcement) go away entirely with Part A.

Remaining blockers after deletion become the scope for a follow-up
bug-fix cycle — out of scope for this work item.

### Part D — Distribution

Global `meridian` binary (`~/.local/bin/meridian`) is stale — still
exposes `--host/--port` and cannot run current app-server code. After
all other parts converge:

- `uv tool install --reinstall .` to refresh the installed binary.
- Verify `meridian --version` matches `src/meridian/__init__.py`
  `__version__`.

## Sequencing

Part A unblocks the smoke-4 class of failures and kills ~1000 lines
before anything else. Part B's items 1-3 fold directly into Part A's
cleanup; items 4-13 are independent and can parallelize.

Part C needs investigation before execution — spawn `@investigator`
per sub-bug to find root cause; don't send coders at symptoms.

Part D is mechanical, runs last.

Recommended phases:

1. Delete auth (Part A) — single coder, single commit.
2. Dead code safe-delete (Part B items 1-13) — one coder, scoped
   commits per logical group.
3. Fence-marker rename (`missing_worker_pid` → `missing_runner_pid`).
4. Reinstall binary (Part D) — needed before smoke retest so the tests
   run against current code.
5. Smoke retest — same scenarios as `p1821` + `p1822`. Document which
   blockers folded away and which survive. Surviving blockers become
   the scope for a follow-up bug-fix work item.

## Success criteria

- `AuthorizationGuard` and all caller-identity plumbing deleted.
- LLM agent-tool surface does not expose cancel or interrupt.
- All safe-delete items in Part B removed.
- `uv run pytest-llm`, `uv run ruff check .`, `uv run pyright` all
  clean after deletions.
- Global `meridian` binary refreshed.
- Smoke lanes re-run; report written documenting which smoke blockers
  folded away (expected: #2, #3, #4) and which survive (scope for
  follow-up work item).

## Out of scope

- Tokens / cryptographic auth / multi-user — explicitly not needed.
- Changes to the reaper authority model or AF_UNIX transport.
- Redesigning any part of the shipped control plane.

## Artifacts to read

- `.meridian/spawns/p1821/report.md` — cancel/interrupt smoke report
- `.meridian/spawns/p1822/report.md` — AF_UNIX/auth/liveness smoke report
- `.meridian/spawns/p1819/report.md` — structural dead-code sweep
- `.meridian/spawns/p1820/report.md` — adversarial dead-code hunt
- `.meridian/spawns/p1818/report.md` — pattern-level scan
- `.meridian/work-archive/spawn-control-plane-redesign/design/` — original design, authoritative for non-auth decisions that still apply
