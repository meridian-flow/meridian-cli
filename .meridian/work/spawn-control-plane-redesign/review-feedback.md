# Review Feedback — Spawn Control Plane Redesign (v1 → v2)

Four parallel reviewers (opus design-alignment, gpt-5.4 adversarial,
gpt-5.2 security, refactor-reviewer structural) returned **request changes**
on the v1 design. Full review reports live at:

- `.meridian/spawns/p1789/report.md` — design alignment vs requirements.md
- `.meridian/spawns/p1790/report.md` — adversarial correctness / races
- `.meridian/spawns/p1791/report.md` — authorization / security
- `.meridian/spawns/p1792/report.md` — structural / refactor

v1 artifacts (rejected) are preserved in git history at commit `943ae7d`.
Overwrite `design/` and `decisions.md` cleanly for v2; do not version
rejected drafts alongside approved ones.

## Blockers That Must Be Resolved in v2

### BL-1 — Pick a single cancel mechanism (converged: opus + gpt-5.4 + refactor)

v1 claims "one SignalCanceller pipeline for CLI/HTTP/timeout" but D-03 +
liveness_contract.md route app-managed cancel through HTTP →
`manager.stop_spawn(...)` in the FastAPI worker, bypassing SIGTERM. That is
two pipelines hidden behind one name, and it leaves the "cancel semantics
consistent across CLI, HTTP, and timeout kill" success criterion unmet.

**Direction to evaluate (not prescribe):** either

- (a) Unify on SIGTERM by making app-launched spawns have their own
  addressable runner process (per-spawn worker or cooperatively-signalable
  thread) so one SIGTERM targets one spawn — then CLI, HTTP, and timeout
  all go through `SignalCanceller.cancel(spawn_id)` end to end; or
- (b) Explicitly adopt a two-lane contract (lifecycle-for-CLI via signals,
  lifecycle-for-app via HTTP) and rewrite spec/overview + architecture to
  stop claiming unification. Document why the two lanes cannot converge.

Option (a) is strongly preferred if feasible. If v2 picks (b), the decision
log must explain why (a) was rejected with concrete probe evidence.

### BL-2 — Add a launch-mode / owner discriminator to `spawn_store` schema

v1 assumes CLI cancel can dispatch on `record.launch_mode == "app"` but
the persisted schema only has `background|foreground`, and the app server
currently records app-launched spawns as `foreground`
(`src/meridian/lib/app/server.py:163`, `src/meridian/lib/state/spawn_store.py:54`).
Without a durable owner field, the dispatcher has nothing to branch on,
and the SIGTERM fallback would target the FastAPI worker (killing
siblings).

v2 must introduce the owner/launch-mode discriminator as its own refactor
item, sequenced **before** any refactor that relies on the dispatch.

### BL-3 — HTTP caller identity over TCP loopback is undeliverable

v1 `authorization_guard.md:124-131` proposes reading the connecting
process's env via its PID to identify the caller for HTTP requests. That
is not portable on TCP loopback — no reliable peer-PID.

v2 must pick one of:

- Move the app server to an **AF_UNIX socket** and use `SO_PEERCRED` to
  extract peer creds; read `/proc/<pid>/environ` for caller identity.
- Adopt **per-spawn/per-session tokens** issued by the parent and verified
  by the guard.

AF_UNIX is the preferred direction — it keeps the honest-actors threat
model and avoids introducing a token-rotation surface. If tokens are
chosen, the decision log must justify the added surface.

### BL-4 — `finalizing`-status SIGKILL race can lose authoritative finalize

v1 `cancel_pipeline.md:39,129` escalates SIGTERM → SIGKILL after grace
without a `finalizing`-status gate, contradicting spec `CAN-008`. Runner
only masks **SIGTERM** (not SIGKILL) across `mark_finalizing` →
`finalize_spawn`. A SIGKILL landing in that window loses the runner's
authoritative terminal row and replaces it with `origin="cancel"`.

v2 `SignalCanceller` pseudocode must treat `status == "finalizing"` as a
hard no-escalation branch: poll for terminal-row emission until timeout,
then return `503`, never SIGKILL.

### BL-5 — No lifecycle authorization enforced on any surface today

Current code has zero authorization on any surface:

- `src/meridian/lib/ops/spawn/api.py:466` — SIGTERM + finalize unconditional
- `src/meridian/lib/streaming/control_socket.py:86-90` — control socket accepts cancel/interrupt without check
- `src/meridian/lib/app/server.py:315` — REST cancel
- `src/meridian/lib/app/ws_endpoint.py:205-216` — WS cancel + interrupt
- `src/meridian/lib/ops/manifest.py:378` — MCP tool surface exposes cancel

v2 must sequence `AuthorizationGuard` (R-08) **before** any refactor that
exposes new lifecycle surfaces (R-05, R-09). Phases that expose surfaces
without the guard must not be marked independently shippable.

### BL-6 — "Loopback-only by construction" is not actually enforced

`src/meridian/cli/app_cmd.py:14` accepts `--host`, so `--host 0.0.0.0`
exposes the app server on the network. v1 relies on "loopback-only" as
a threat-model precondition (`spec/authorization.md:20-22`) but never
enforces it.

v2 must either enforce loopback binding in code, or explicitly acknowledge
the non-loopback threat model and provide token-based auth for it. (Moving
to AF_UNIX per BL-3 resolves this automatically.)

### BL-7 — Terminal-cancel HTTP contract contradicts itself

Spec `CAN-004/CAN-007` + `HTTP-004` say terminal-at-request-time cancel
returns `409`; architecture `http_endpoints.md:85` says `200` with
`already_terminal=true`. Clients can't implement both.

v2 pick one and make spec + architecture agree.

## Majors That Should Be Resolved in v2

- **Feasibility gaps still OPEN.** P7 (`MERIDIAN_SPAWN_ID` inheritance) and
  P10 (per-harness interrupt semantics) are marked OPEN in v1 feasibility.md,
  but LIV-006, AUTH-001, and interrupt_pipeline.md treat them as settled.
  v2 must close or re-probe these before any leaf depends on them.
- **"Missing env ⇒ trusted operator" is fail-open inside `MERIDIAN_DEPTH>0`.**
  Env-drop bugs auto-promote subagents to operators. v2 `authorize()` should
  treat `depth>0 ∧ caller missing` as deny-by-default, with an explicit
  operator-override flag for the CLI entry point.
- **PID-reuse guard missing in `SignalCanceller`.** The reaper was hardened
  to pass `created_after_epoch=started_epoch` to `is_process_alive`
  (`src/meridian/lib/state/reaper.py:121`, `liveness.py:6`). The cancel
  resolver must use the same guard; otherwise `spawn cancel` can SIGTERM a
  reused PID.
- **Inject FIFO lock must also serialize ack emission** (or the INJ-002
  contract must be redefined around `inbound_seq` rather than ack arrival
  order). v1 lock wraps `record_inbound + send_*` but not the reply write
  in `control_socket.py`.
- **"Runner = whoever owns HarnessConnection" is still terminological.**
  v1 cancel_pipeline.md:84 preserves a FastAPI background finalizer
  writing `origin="launcher"` on top of the worker's finalize. Dual
  finalize ownership must go away, or the reframe is not real.
- **Refactor agenda mis-sequenced.** R-05 / R-09 expose `/cancel` + the
  app dispatcher before R-08 lands the guard. Resequence so no lifecycle
  surface is exposed ungated.
- **Verification plan incomplete.** `requirements.md:37` asks for unit,
  smoke, **and fault-injection** coverage. v1 has no fault-injection plan
  for the cancel/finalize race paths. v2 must name the fault-injection
  probes explicitly (SIGKILL-during-finalize, concurrent inject ordering,
  PID-reuse, env-drop) per spec leaf.

## Minor Notes (Fold in as Convenient)

- `inject_serialization.md` reasons from a stale `SpawnManager` object
  model (per-spawn) but the live type is a multi-spawn registry with
  shared session maps. Lock design still works; rationale should be updated.
- CORS/origin checks aren't an authorization boundary for non-browser
  clients; don't cite them as mitigations.

## What to Preserve From v1

These were good calls and should survive into v2:

- **D-04** (`turn/completed` never spawn-terminal) — preserved.
- **D-05** (per-spawn `asyncio.Lock` for inject) — preserved; extend scope
  to cover ack emission per major above.
- **D-07** (inject stays ungated) — preserved.
- **D-08** (delete `SpawnManager.cancel` outright; no shim) — preserved.
- **D-09** (reject cancel-via-control-socket `type="cancel_graceful"`) — preserved.
- **D-02** (heartbeat ownership moves to `SpawnManager`) — preserved, but
  the "runner = HarnessConnection owner" reframe needs to actually land
  structurally, not just terminologically.

## Out of Scope for v2

- Do not rework the reaper authority model. The `AUTHORITATIVE_ORIGINS`
  rule and depth-gated reaping stay as-is.
- Do not remove the app server. Web GUI is a supported surface.
