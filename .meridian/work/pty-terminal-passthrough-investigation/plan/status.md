# Plan Status

| Item | Type | Status | Dependencies | Notes |
|---|---|---|---|---|
| Phase 1: child-pty-login-tty-fix | implementation | not-started | none | minimal `process.py` patch only |
| Phase 2: build-health | verification | not-started | Phase 1 | `uv run ruff check .` and `uv run pyright` |
| Phase 3: smoke-classification-and-fallbacks | verification | not-started | Phase 1 | baseline-first T-01 through T-12, corrected `--harness` usage |
| Final review loop | review | not-started | Phases 2 and 3 | reviewer fan-out plus refactor review |
