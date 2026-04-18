# Smoke-Test R06 — end-to-end verification of the refactored launch surfaces

## Context

R06 (hexagonal launch core) was just shipped by spawn `p1900` across 6 commits on main. The refactor rewrote launch composition — every harness launch path now routes through `build_launch_context()` in `src/meridian/lib/launch/context.py`. Unit tests pass (653) and the CI invariants script passes (18/18), but **no end-to-end smoke testing was done** during the refactor. You're closing that gap now.

Commits to verify:
- `3f8ad4c` — `SpawnRequest` DTO + `RuntimeContext` unification
- `5e8aae1` — domain core (sum type, factory, pipeline stubs, `observe_session_id()` seam)
- `b19d999` — all 3 driving adapters (primary, worker, app-streaming) rewired through factory
- `bf4cf6c` — `run_streaming_spawn` + `SpawnManager.start_spawn` fallback deleted
- `c042478` — `MERIDIAN_HARNESS_COMMAND` bypass absorbed, `match`/`assert_never` dispatch, CI invariants
- `efad4c0` — CI script grep fallback

## What to smoke test

Exercise the refactored surfaces end-to-end. Use `uv run meridian ...` against the local source. Don't trust unit tests; run the real CLI against a real harness.

Golden paths:

1. **Primary launch** — `uv run meridian` starts interactive Claude session. Verify session ID is captured (look at `.meridian/sessions.jsonl` or equivalent for the new session entry with a harness_session_id). Ctrl-D or exit to return. PTY path should engage.

2. **Primary dry-run** — `uv run meridian --dry-run` or equivalent flag. Should print composed command/env without launching. Verify the factory path runs but executor is skipped.

3. **Spawn (subprocess)** — `uv run meridian spawn -p "write a haiku about dragons"` with default harness. Verify the spawn completes, output is captured, session ID is recorded. Use `meridian spawn show <id>` to check state.

4. **Spawn with continue/fork** — `uv run meridian spawn --continue <existing-session-id>` (or equivalent). Verify fork materialization runs (`materialize_fork()` pipeline stage) and the forked spawn completes.

5. **Streaming serve** — if there's a `meridian streaming-serve` or similar command, start it and verify it can accept a streaming spawn. If it no longer exists (the refactor folded it into the shared path), note that.

6. **App HTTP API** — start `uv run meridian app` (or however the HTTP server launches), then:
   - `POST /spawns` — create a spawn via HTTP. Verify 200 response with a spawn id.
   - `POST /spawns/<id>/inject` — send a follow-up message into a running spawn.
   - `POST /spawns/<id>/interrupt` — interrupt a running spawn.
   - All three need to survive the factory rewire.

7. **`MERIDIAN_HARNESS_COMMAND` bypass** — `MERIDIAN_HARNESS_COMMAND="echo hello" uv run meridian`. Should run the echo command instead of the real harness. Verify `BypassLaunchContext` is dispatched (look for echo output; should exit successfully without invoking Claude).

8. **Codex harness path** — run a spawn or primary with `--harness codex`. Verify session observation still works (Codex uses stream-event parsing, not PTY scrape).

9. **OpenCode harness path** — if OpenCode is locally available, run a spawn with `--harness opencode`. Verify workspace projection still flows (this is where R05 will insert, but R06 shouldn't have broken existing OpenCode behavior).

## What counts as a pass

Each of the 9 items above either:
- **PASS**: the flow works end-to-end as expected, observable outputs match pre-R06 behavior.
- **FAIL**: concrete breakage — crash, wrong output, missing session id, HTTP 500, etc. Capture the command, output, stderr, relevant logs.
- **SKIP**: not locally reproducible (e.g., OpenCode not installed). Name the reason.

Don't gloss over things. If session-ID isn't captured on primary PTY, that's a FAIL even if the harness ran. If `/inject` returns 200 but doesn't actually reach the subprocess, that's a FAIL.

## Cleanup

Any temporary spawns/sessions you create for testing: either leave them (they're harmless scratch data) or delete via `meridian spawn cancel` / `rm` after confirming results. Don't commit.

## Deliverable

Under 800 words:

1. **Environment** — model you used for each harness test, any harnesses skipped and why.
2. **Per-item table** — 9 rows with PASS/FAIL/SKIP, one-line evidence per row.
3. **Failures** — for each FAIL: command run, observed output, expected output, hypothesis on root cause (which commit/change introduced it).
4. **Regressions not in the golden path** — anything surprising you noticed even if not on the list.
5. **Verdict** — `R06-ships-clean` / `R06-ships-with-minor-fixes` / `R06-has-regressions` with a one-sentence justification.

Report findings. Do not fix anything — the coder lane picks up FAILs. You're the witness, not the patcher.
