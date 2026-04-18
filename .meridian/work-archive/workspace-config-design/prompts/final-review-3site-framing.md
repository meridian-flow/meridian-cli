# Final Adversarial Review — 3-driving-adapter framing integrity

## Context

`workspace-config-design`'s R06 has been rewritten (p1894, opus) around the explorer's finding (p1893) that the honest architecture has:

- 1 driving port (`build_launch_context()` factory)
- 1 driven port (harness adapter protocol)
- **3 driving adapters** with named architectural reasons:
  1. Primary launch — process replacement (PTY execvpe)
  2. Background worker — persistent queue lifecycle
  3. App streaming HTTP — live in-process `SpawnManager` for `/inject`/`/interrupt`
- 2 executors (PTY + async subprocess, latter shared by worker and app-streaming)
- 1 preview caller (dry-run) — calls factory, does not execute

The previous 8–9 "port" enumeration collapsed because several were call locations inside one adapter, plus two dead parallel implementations (`run_streaming_spawn`, `SpawnManager.start_spawn` fallback) get deleted in R06. Fork materialization was absorbed into the factory as `materialize_fork()` (Option A). `SpawnParams` gets split into `SpawnRequest` (raw) + resolved successor.

## Your task — adversarial review, framing integrity focus

You are the **architecture correctness** reviewer. Your job is to stress-test whether the 3-driving-adapter claim is actually true, whether Option A fork absorption holds, and whether any hidden drivers or composition surfaces were missed.

Read these first:
- `.meridian/work/workspace-config-design/design/refactors.md` (R06 specifically, R05 cross-refs)
- `.meridian/work/workspace-config-design/decisions.md` (D17)
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`
- `.meridian/spawns/p1894/report.md` (what this rewrite delivered)
- `.meridian/spawns/p1893/report.md` (the explorer findings it was based on)

Probe the live code under `src/meridian/lib/` and `src/meridian/cli/` as needed.

### Pressure tests

1. **Are there exactly 3 driving adapters?** The framing names primary / worker / app-streaming as the only three. Probe for a 4th. Specifically:
   - Does any CLI subcommand launch a harness outside of spawn and primary? Check `src/meridian/cli/` for any entry point that might compose launches (e.g., a test runner, a debug launcher, session-replay that spawns).
   - Is there any MCP / IDE / SDK entry point in `src/meridian/lib/app/` or `src/meridian/lib/streaming/` that constructs launches directly?
   - Does `meridian mars` or any sync/worker path start a harness subprocess?
   - If you find a 4th driver, is its architectural reason for being separate real, or could it fold into one of the three?

2. **Is the "architectural reason" claim honest for each of the three?**
   - **Primary = process replacement**: verify primary launch actually execvpes, not supervises. If it supervises in some mode (e.g., `--no-pty`, dry-run, CI mode), does it really belong as its own driver or could it share with worker?
   - **Worker = persistent queue lifecycle**: verify the worker is actually a long-lived loop. If it's a one-shot execute-and-exit today, the "persistent queue" framing is overclaimed — the worker is just "the async executor for queued spawns" and might even collapse into app-streaming's executor.
   - **App streaming = live in-process SpawnManager**: verify `/inject` and `/interrupt` actually need the subprocess in the HTTP handler's process. Could they route through a PID file + signal / named pipe / queue message instead? If so, the "architectural reason" for keeping app-streaming as a separate driver is weaker than stated.

3. **Option A fork absorption — does it actually work?** The architect chose to add `materialize_fork()` as a pipeline stage in the factory. Verify:
   - Both current sites (`launch/process.py:68-105`, `ops/spawn/prepare.py:296-311`) use the same inputs: `adapter.fork_session()`, mutation of `SpawnParams`, command rebuild.
   - Are the inputs really identical? `launch/process.py` is called during primary execution; `ops/spawn/prepare.py` is called pre-worker (via `build_create_payload`). Do they resolve the continuation-session-id from the same source, or does one path require state the other doesn't have?
   - `fork_session()` is a network-adjacent side effect (contacts the Codex API?). Is it safe to call inside the factory (which should be pure or I/O-free)? If not, the factory contract is lying — it's not pure.
   - What's the executor contract post-fork? Does the executor receive a mutated `LaunchContext` with the new session ID, or is there some out-of-band state?

4. **Dry-run as a "4th caller that doesn't execute" — is it coherent?** The design names dry-run as a factory caller for preview but not an executor. Verify:
   - Primary dry-run and `spawn create --dry-run` are different callers. Are they both actually routed through the factory?
   - Dry-run returns `composed_prompt` + `cli_command`. Does producing these require the full factory pipeline, or could dry-run short-circuit before some stages (e.g., skip workspace projection, skip env building)?
   - If dry-run skips stages, is it really the same factory or a second factory? Naming matters — if dry-run is a separate code path, the "1 factory" claim is overclaimed.

5. **Deletions — are they safe?** R06 deletes `run_streaming_spawn` and `SpawnManager.start_spawn` unsafe fallback.
   - `run_streaming_spawn` is called from `cli/streaming_serve.py:98`. If `execute_with_streaming` is the replacement, does it support every feature `run_streaming_spawn` does today? Probe for divergence.
   - `SpawnManager.start_spawn` fallback — is it called from anywhere after the rewrite? Are there code paths that rely on the unsafe-resolver behavior?

6. **`SpawnParams` → `SpawnRequest` split — is this a clean refactor or a breaking change?**
   - `SpawnParams` is used in `harness/adapter.py:147-166`, `launch/plan.py`, `ops/spawn/prepare.py`, `ops/spawn/execute.py`, adapter implementations, and likely tests. Splitting it is touching harness adapter contracts.
   - Does the harness adapter contract take `SpawnParams` or `SpawnRequest`? If it takes the resolved kind, every adapter implementation signature changes. Scope check: is this in R06's scope or spilling over?

7. **The "Why not 1" and "Why not 9" arguments — are they sound?**
   - "Why not 1" says primary can't merge with worker because process replacement. But primary dry-run doesn't execvpe. If dry-run routes through factory without execution, primary-execute could theoretically route through the worker executor for non-PTY cases. Is the design locking in unnecessary divergence?
   - "Why not 9" says the previous 9 were call locations inside the 3 adapters. Name each of the 9 and which of the 3 it belongs to. Any that don't cleanly belong?

### Report format

- Findings as **Blocker / Major / Minor** with file:line references.
- End with a **Verdict**: approve / approve-with-minor-fixes / request-changes.
- Be adversarial. Four prior review rounds found gaps; don't assume this one closed them all.
- If a finding from the previous review rounds (p1891 gpt / p1892 opus) was NOT addressed, flag it explicitly.
- Do your own `rg` sweeps. Don't trust the design's claims without verification.
- Target length: ~600 words of findings, plus the verdict.
