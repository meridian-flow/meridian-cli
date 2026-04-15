# HTTP Surface — CLI / HTTP Parity

The HTTP surface mirrors the CLI's spawn control vocabulary one-for-one.
The app server binds to an AF_UNIX socket (D-11), not TCP. Shapes are
split by **kind of operation**, not by transport:

| Operation | HTTP endpoint | CLI command | Kind |
|---|---|---|---|
| Send text | `POST /api/spawns/{id}/inject` | `spawn inject <id> '<text>'` | Cooperative |
| Interrupt turn | `POST /api/spawns/{id}/inject` (`interrupt: true`) | `spawn inject <id> --interrupt` | Cooperative |
| Cancel spawn | `POST /api/spawns/{id}/cancel` | `spawn cancel <id>` | Lifecycle |

## EARS Statements

### HTTP-001 — `/inject` accepts text or interrupt

Defined in INJ-005 and INT-005. Cross-referenced here.

### HTTP-002 — `/cancel` is a dedicated lifecycle endpoint

Defined in CAN-004. HTTP cancel MUST NOT route through `/inject`.

### HTTP-003 — `DELETE /api/spawns/{id}` is removed

Defined in CAN-005.

### HTTP-004 — All endpoints return structured errors

**When** any spawn-control HTTP endpoint rejects a request,
**the response shall** include a `detail` field and a status code from:

| Code | Meaning | Applies to |
|---|---|---|
| 400 | Semantic validation (text + interrupt both set, neither set) | inject (D-17) |
| 403 | Authorization denied or caller identity unavailable (D-19) | cancel, interrupt |
| 404 | Spawn id does not exist | all |
| 405 | Removed legacy method (CAN-005) | DELETE |
| 409 | Spawn already terminal at request time | cancel (CAN-007, D-16) |
| 410 | Spawn already terminal at request time | inject, interrupt (INJ-004) |
| 422 | Schema validation (missing fields, wrong types) | inject (D-17) |
| 503 | Spawn is `finalizing`; retry after backoff | cancel (CAN-008) |

**v2 resolution of BL-7.** Cancel against already-terminal spawns returns
`409` (not `200 with already_terminal=true`). Spec and architecture agree
on this (D-16).

**v2r2 terminal status code split.** Cancel uses `409 Conflict` (the
requested state transition conflicts with current state). Inject uses
`410 Gone` (the resource the client wants to interact with no longer
exists in active form). All error responses use the `detail` field
convention.

**v2r2 validation split (D-17).** Schema errors → 422 (FastAPI default
pydantic handler). Semantic errors → 400 (custom exception handler
remaps `ValueError` from `model_validator`).

### HTTP-005 — Inject and cancel are the only spawn-control endpoints

**When** a request arrives at any `/api/spawns/{id}/...` path other than
the listed endpoints,
**the app shall** respond `404 Not Found`.

**Observable.** OpenAPI lists exactly: `GET /api/spawns`,
`GET /api/spawns/{id}`, `POST /api/spawns`, `POST .../inject`,
`POST .../cancel`.

### HTTP-006 — App server binds AF_UNIX, not TCP (v2 new)

**When** the app server starts,
**the server shall** bind to an AF_UNIX socket at
`.meridian/app.sock` (or `--uds <path>` override). The `--host` and
`--port` flags are removed from the primary `app` command. A `--proxy`
subcommand starts a TCP-to-UDS proxy for browser access.

**Observable.** `lsof` shows the server listening on a Unix socket.
No TCP port is opened by default. `--host 0.0.0.0` is no longer
accepted.

## Verification plan

### Smoke tests
- Scenario 9a: `POST /inject` with text via AF_UNIX.
- Scenario 9b: `POST /inject` with interrupt via AF_UNIX.
- Scenario 9c: `POST /inject` with both → 400.
- Scenario 14: `POST /cancel` end-to-end.
- Scenario 15: `DELETE /api/spawns/{id}` → 405.
- Scenario 19 (v2 new): app server starts on AF_UNIX, not TCP.
