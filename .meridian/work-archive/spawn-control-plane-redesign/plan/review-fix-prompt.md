# Review Fixes: Auth Gaps and Error Ordering

Fix two issues found during final review.

## Fix 1: WS endpoint auth gap (HIGH)

`src/meridian/lib/app/ws_endpoint.py` lets WebSocket clients send `interrupt` and `cancel` without any authorization check. This violates AUTH-001/AUTH-003.

**Fix:** In the WS message handler, before dispatching interrupt or cancel, add an authorization check. Since WS connections also go through AF_UNIX, use the same peercred-based auth or at minimum use `caller_from_env()` if peercred isn't available on WS. If peercred isn't feasible for WS, add a comment explaining why and add a TODO.

Actually, the simplest correct fix: WS clients connecting via AF_UNIX have the same peercred available. But if the WS transport doesn't expose peercred easily, an alternative is to read the auth at WS connection time and cache it.

Read `ws_endpoint.py` to understand the current structure, then add auth checks for interrupt and cancel paths.

## Fix 2: 403 vs 404 on cancel (MEDIUM)

`POST /api/spawns/{id}/cancel` uses `dependencies=[Depends(require_authorization)]`. The `authorize()` function returns `missing_target` reason when the spawn doesn't exist, which surfaces as 403. But CAN-004 says missing spawn should be 404.

**Fix:** In `require_authorization` or in the cancel endpoint, check the auth decision reason. If reason is `"missing_target"`, raise HTTPException(404, detail="spawn not found") instead of 403.

Alternatively, restructure so the existence check happens first. The simplest approach: in `require_authorization`, if the decision reason is `"missing_target"`, raise 404.

## Verification

```bash
uv run ruff check .
uv run pyright
uv run pytest-llm -k "not test_execute_with_finalization_continues_when_terminal_heartbeat_touch_fails"
```
