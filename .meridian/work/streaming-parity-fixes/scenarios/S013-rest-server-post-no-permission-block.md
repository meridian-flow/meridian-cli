# S013: REST server POST with no permission block

- **Source:** design/edge-cases.md E13 + p1411 H3
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester (+ @unit-tester)
- **Status:** verified

## Given
REST server receives `/spawns` request with no permission metadata.

## When
Server resolves request permissions.

## Then
- Default mode returns `HTTP 400 Bad Request`.
- No implicit permission fallback is applied.
- Only with `--allow-unsafe-no-permissions` enabled does server construct `UnsafeNoOpPermissionResolver`.

## Verification
- Unit test default mode -> 400.
- Unit test opt-out mode -> resolver constructed + warning log.
- Grep confirms no `cast("PermissionResolver", None)` remains.

## Result (filled by tester)

**Status:** verified — 2026-04-10
**Tester:** @smoke-tester (p1450)

### Smoke test 1: default strict mode (port 18420)

```
$ uv run meridian app --port 18420 --no-browser &
$ curl -sS -X POST http://127.0.0.1:18420/api/spawns \
    -H 'content-type: application/json' \
    -d '{"prompt":"test","harness":"codex"}' \
    -w "\nHTTP_STATUS: %{http_code}\n"

{"detail":"permissions block is required: provide permissions.sandbox and permissions.approval"}
HTTP_STATUS: 400
```

**Result:** ✓ Returns HTTP 400 with a clear, actionable error message. No implicit permission fallback applied.

### Smoke test 2: unsafe opt-out mode (port 18421)

```
$ uv run meridian app --port 18421 --no-browser --allow-unsafe-no-permissions &
$ curl -sS -X POST http://127.0.0.1:18421/api/spawns \
    -H 'content-type: application/json' \
    -d '{"prompt":"test","harness":"codex"}' \
    -w "\nHTTP_STATUS: %{http_code}\n"

{"spawn_id":"p1451","harness":"codex","state":"connected","capabilities":{...}}
HTTP_STATUS: 200
```

Server stderr showed both warning lines:
```
[04/10/26 20:45:10] WARNING  Handling /api/spawns request without  server.py:207
                             permission metadata because
                             --allow-unsafe-no-permissions is enabled.
                    WARNING  UnsafeNoOpPermissionResolver      permissions.py:83
                             constructed; no permission enforcement will be applied
```

**Result:** ✓ Request passes (200); `UnsafeNoOpPermissionResolver` constructed; both warnings emitted.

### Smoke test 3: grep gate

```
$ rg "cast\(\s*['\"]PermissionResolver['\"]" src/
(no output)
EXIT: 1 (no matches)

$ rg "UnsafeNoOpPermissionResolver" src/
src/meridian/lib/safety/permissions.py:class UnsafeNoOpPermissionResolver(BaseModel):
src/meridian/lib/safety/permissions.py:                "UnsafeNoOpPermissionResolver constructed; ..."
src/meridian/lib/app/server.py:    UnsafeNoOpPermissionResolver,
src/meridian/lib/app/server.py:            permission_resolver = UnsafeNoOpPermissionResolver()
...
```

**Result:** ✓ No `cast("PermissionResolver", ...)` remains; `UnsafeNoOpPermissionResolver` found at definition + REST wiring.

### Smoke test 4: CLI flag visibility

```
$ uv run meridian app --help

ALLOW-UNSAFE-NO-PERMISSIONS, --allow-unsafe-no-permissions,
--no-allow-unsafe-no-permissions: Allow /api/spawns requests with missing
permissions metadata by using UnsafeNoOpPermissionResolver. [default: False]
```

**Result:** ✓ Flag visible and description names `UnsafeNoOpPermissionResolver`, communicating danger.

### Exploratory edge cases

| Input | HTTP Status | Response |
|---|---|---|
| `permissions: null` (explicit null) | 400 | "permissions block is required…" |
| `permissions.sandbox: ""` | 400 | "permissions.sandbox is required" |
| `permissions.approval: ""` | 400 | "permissions.approval is required" |
| `permissions.sandbox: "invalid_sandbox_value"` | 400 | "Unsupported sandbox mode '…'. Expected: …" |
| `prompt: ""` | 400 | "prompt is required" |
| `harness: "invalid_harness"` | 400 | "unsupported harness '…'" |
| malformed JSON body | 422 | FastAPI JSON validation error |
| two concurrent no-permissions POSTs | 400, 400 | both rejected; no state corruption |

All edge cases behave correctly.

### Usability notes

- 400 response body is helpful: names the required fields (`permissions.sandbox`, `permissions.approval`).
- CLI flag name `--allow-unsafe-no-permissions` communicates danger clearly; description also names `UnsafeNoOpPermissionResolver`.
- Warning log at WARNING level (not DEBUG/INFO) ensures it's visible in production uvicorn output.
- One minor note: the `--no-allow-unsafe-no-permissions` negation toggle in `--help` is cosmetic noise but harmless (boolean CLI pattern). Not a blocker.
