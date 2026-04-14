# HTTP Surface — CLI / HTTP Parity

The HTTP surface mirrors the CLI's spawn control vocabulary one-for-one. The
shapes are split by **kind of operation**, not by transport:

| Operation | HTTP endpoint | CLI command | Surface kind |
|---|---|---|---|
| Send text into active spawn | `POST /api/spawns/{id}/inject` | `meridian spawn inject <id> '<text>'` | Cooperative |
| Interrupt current turn | `POST /api/spawns/{id}/inject` (`interrupt: true`) | `meridian spawn inject <id> --interrupt` | Cooperative |
| Cancel spawn (lifecycle) | `POST /api/spawns/{id}/cancel` | `meridian spawn cancel <id>` | Lifecycle |

## EARS Statements

### HTTP-001 — `/inject` accepts text or interrupt

Defined in INJ-005 and INT-005. Cross-referenced here for navigation; HTTP
inject parity is owned by the inject and interrupt subsystems.

### HTTP-002 — `/cancel` is a dedicated lifecycle endpoint

Defined in CAN-004. The HTTP surface MUST NOT route cancel through `/inject`.

### HTTP-003 — `DELETE /api/spawns/{id}` is removed

Defined in CAN-005.

### HTTP-004 — All endpoints return structured errors

**When** any spawn-control HTTP endpoint rejects a request,
**the response shall** include a `detail` field matching the reason and a
status code from `{400, 404, 405, 409, 410, 422, 503}` per the table below:

| Code | Meaning |
|---|---|
| 400 | Malformed request body (e.g., text and interrupt both set) |
| 404 | Spawn id does not exist |
| 405 | Removed legacy method (CAN-005) |
| 409 | Spawn already terminal at request time |
| 410 | Inject rejected because spawn moved to terminal status |
| 422 | Schema validation failure |
| 503 | Spawn is in `finalizing`; retry after backoff (CAN-008) |

### HTTP-005 — Inject and cancel are the only spawn-control endpoints

**When** a request arrives at any `/api/spawns/{id}/...` path other than
`GET`, `POST .../inject`, `POST .../cancel`,
**the app shall** respond `404 Not Found` with `{"detail": "endpoint not
found"}`.

**Observable.** OpenAPI lists exactly the endpoints in the table at the top
of this document plus `GET /api/spawns`, `GET /api/spawns/{id}`, and
`POST /api/spawns`. Anything else is a regression.
