# Authorization — Lifecycle Operations Are Gated

Cancel and interrupt are **lifecycle and turn-control** operations. An
arbitrary subagent should not be able to terminate sibling spawns, kill its
parent's session, or wedge an unrelated user's spawn. The model is
**capability-by-ancestry**: a process may operate on the spawn it owns or
on its descendants. Inject (cooperative text) is **not** gated; it is a
data-plane operation and stays open.

## Threat model

- A spawned subagent (`MERIDIAN_SPAWN_ID=<my_id>`) shells out
  `meridian spawn cancel <other_id>`. If `<other_id>` is not in the agent's
  own ancestry, the cancel must be denied.
- A spawned subagent issues `POST /api/spawns/<other_id>/cancel` against the
  local FastAPI app. Same rule.
- Local human user runs `meridian spawn cancel <id>` from an interactive
  shell with no `MERIDIAN_SPAWN_ID` in the environment. This is the trusted
  operator surface and is always allowed (no parent context to check).
- A remote attacker reaching the FastAPI app over the network. Out of scope
  here — the app server is loopback-only by construction; network exposure
  is a separate hardening problem.

## EARS Statements

### AUTH-001 — Cancel and interrupt require ancestry authorization

**When** any caller invokes a lifecycle operation (cancel, interrupt) for a
spawn `<target>` and the caller process has `MERIDIAN_SPAWN_ID=<caller>`
populated in its environment,
**the surface shall** authorize the call only when `<caller> == <target>` or
`<caller>` is an ancestor of `<target>` per the `parent_id` chain in
`spawns.jsonl`.

**Observable.** Authorization decision is logged with
`reason in {"ancestor", "self"}` on accept and
`reason in {"not_in_ancestry", "missing_target"}` on deny.

### AUTH-002 — Operator surface is unauthenticated by inheritance

**When** a caller invokes a lifecycle operation and the caller process has
`MERIDIAN_SPAWN_ID` unset (or equal to the empty string),
**the surface shall** treat the caller as the trusted operator and allow the
operation.

**Observable.** `meridian spawn cancel <id>` from a human shell continues to
work without ceremony. Logs record `auth_mode="operator"`.

### AUTH-003 — Denials surface a clear error

**When** authorization denies a lifecycle operation,
**the surface shall** respond with the appropriate transport error and **shall
not** dispatch the operation:

| Surface | Response |
|---|---|
| CLI | exit 2; stderr `Error: caller <caller> is not authorized to cancel <target>` |
| HTTP | `403 Forbidden` with `{"detail": "caller is not authorized for this spawn"}` |
| Control socket | `{"ok": false, "error": "interrupt requires caller authorization"}` (interrupt only; inject is unaffected) |

**Observable.** Denial events do not produce SIGTERM, do not append finalize
events, and do not enter `inbound.jsonl`.

### AUTH-004 — Authorization is enforced at the surface, not in `SpawnManager`

**When** the lifecycle pipeline executes,
**the authorization check shall** happen at the surface (CLI ops module,
HTTP endpoint, control socket interrupt handler) **before** any side-effect
(SIGTERM, `send_interrupt`, `inbound.jsonl` append).

**Observable.** `SpawnManager` and `spawn_cancel_sync` remain unaware of
authorization; the surface module composes them. Unit tests for
`AuthorizationGuard` are surface-scoped.

### AUTH-005 — Ancestry walk is read-only and bounded

**When** the authorization guard walks the `parent_id` chain,
**the walk shall** stop at the first match, at a `parent_id is None` row, or
after `_AUTH_ANCESTRY_MAX_DEPTH` (default 32) hops, whichever comes first.

**Observable.** The walk reads `spawns.jsonl` once via the existing
projection and does not mutate state. Pathological cycles (which should not
exist in practice) terminate within the depth bound.

### AUTH-006 — Agent-tool surface defers to the same guard

**When** an agent runtime exposes `meridian spawn cancel` /
`meridian spawn inject --interrupt` as MCP tools or similar callables,
**the agent runtime shall** invoke the existing CLI / Python entrypoint and
**shall not** bypass `AuthorizationGuard`. Agent profiles that need to
disable lifecycle control entirely should remove the corresponding tool
from the profile allowlist instead of bypassing the guard.

**Observable.** No new agent-side authorization codepath. Agent profiles
that include `spawn-cancel` / `spawn-interrupt` in their tool allowlist are
governed by AUTH-001.
