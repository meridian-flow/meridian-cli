Smoke retest is done and the report is saved at [report.md](/home/jimyao/gitrepos/meridian-cli/.meridian/spawns/p1713/report.md).

Main outcome: the install/auth blockers folded away, but the liveness/cancel bugs are still live. `meridian app` now starts on the installed `0.0.28` binary, AF_UNIX-only behavior is correct, GET/inject work without auth, and HTTP/CLI cancel no longer hit `403 caller identity unavailable`. `DELETE /api/spawns/{id}` now returns `405`, and terminal inject/cancel behave as `410` / `409`.

The surviving failures are in lifecycle accounting:
- `/inject` with a missing field still returns `400` instead of the expected `422`.
- HTTP cancel and CLI cancel both finalize spawns as `succeeded`/`exit_code: 0` even when the stream emitted `cancelled`/`143`.
- A forced worker `SIGKILL` on `p6` still finalized as `succeeded` after 9.6s, with only an in-progress `sleep 120` and `error/connectionClosed` in `output.jsonl`.
- Completed spawns can stay stuck in `running` after the command and final answer are already finished (`p1`, `p4`).
