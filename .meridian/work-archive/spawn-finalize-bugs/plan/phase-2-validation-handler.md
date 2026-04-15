# Phase 2: Validation Handler Fix (B-04)

## Scope
Fix `_validation_error_handler` in server.py to return 400 only for "mutually exclusive" errors, letting other validation errors fall through as 422.

## Files Touched
- `src/meridian/lib/app/server.py` — `_validation_error_handler()` (~lines 168-191)

## Changes
In `_validation_error_handler`, check the ValueError message. Only return 400 when the message contains "mutually exclusive". Otherwise, let it fall through to the default FastAPI 422 handler.

```python
if isinstance(underlying_error, ValueError):
    if "mutually exclusive" in str(underlying_error):
        return json_response_cls(
            status_code=400,
            content={"detail": str(underlying_error)},
        )
```

## Exit Criteria
- `uv run ruff check .` passes
- `uv run pyright` passes
- `uv run pytest-llm` passes
