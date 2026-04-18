# Architect Task — Honesty pass on R06 + add `observe_session_id()` adapter seam

## Context

`workspace-config-design`'s R06 has been through five architect passes and a sixth review round. The 3-driving-adapter framing (p1894) is the right architecture. Three reviewers this round (p1895 framing / p1896 enforceability / p1897 consistency) converged on: **the framing is tight but overstates what's actually true in code and in CI.**

This pass is **honesty corrections + one substantive addition (session-ID adapter seam)**, not a rewrite. Do not change the 3-driving-adapter shape. Do not reopen settled decisions.

Read these first:
- `.meridian/spawns/p1895/report.md` — framing integrity findings
- `.meridian/spawns/p1896/report.md` — enforceability findings
- `.meridian/spawns/p1897/report.md` — consistency findings
- `.meridian/spawns/p1894/report.md` — the previous rewrite
- Current state: `design/refactors.md` (R06), `decisions.md` (D17), `design/architecture/harness-integration.md`

Also relevant — a new follow-up work item lives at **GitHub issue #34** (session-ID observation via filesystem polling). This architect pass introduces the adapter seam #34 will swap implementations on; the mechanism swap itself is out of scope.

## The honesty corrections

### 1. Primary executor is one executor with two capture modes (p1895 Blocker 1)

Current design says "primary = process replacement via `os.execvpe`." Live code (`src/meridian/lib/launch/process.py:159-219`) has two branches:

- **PTY path** (lines 190-219): `pty.fork()` + `os.execvpe`. Runs when `output_log_path is not None and sys.stdin.isatty() and sys.stdout.isatty()`. Enables session-ID observability via terminal scraping.
- **Popen path** (lines 167-188): `subprocess.Popen().wait()`. Runs when any of those three conditions is false. Degraded — session-ID observability is lost today.

Reframe the primary executor as **one executor with a capture-mode branch**:

> Primary executor runs the harness as a foreground process meridian owns until exit. It has two capture modes driven by environment and config:
> - **PTY capture** (intended): when meridian's stdin/stdout are TTYs and an output log path is configured, `pty.fork()` + `os.execvpe()`. Harness sees a terminal; session-ID observability is possible via adapter-owned scraping.
> - **Direct Popen** (degraded fallback): when the runtime lacks TTYs meridian can proxy, falls back to `subprocess.Popen().wait()`. Harness does not render its TUI fully; session-ID observability is lost on this path today. GitHub issue #34 tracks moving session-ID observation to filesystem polling, which removes this degradation.
>
> Both paths consume the same `LaunchContext` and return the same `LaunchResult` contract.

Keep the "2 executors total" claim: primary executor (PTY/Popen internal) + async subprocess executor (worker + app-streaming). Do not restructure this as 3 executors.

### 2. Worker is a detached one-shot subprocess, not a persistent queue (p1895 Major 1)

Current design says worker is "persistent queue lifecycle; dequeues N jobs over its lifetime." Live code (`src/meridian/lib/ops/spawn/execute.py:474,591,827`) is **one process per spawn**: `execute_spawn_background()` launches `python -m meridian.lib.ops.spawn.execute --spawn-id ...`, `_background_worker_main()` loads exactly one spawn id, executes it, exits.

Rename the worker's architectural reason:

> **Background worker** — detached one-shot subprocess per spawn. `meridian spawn` forks a detached `python -m meridian.lib.ops.spawn.execute` process per spawn id; that process composes once, executes, writes its report, and exits. The architectural reason for keeping worker as a separate driver is **detached lifecycle** — the meridian parent can exit or crash without orphaning the spawn.

### 3. App-streaming's "must be live in-process" is a current-API choice, not necessity (p1895 Major 2)

Current design claims app-streaming "requires the HTTP handler to hold the subprocess in memory." Live code has an out-of-process control plane: `src/meridian/lib/streaming/control_socket.py` exposes `control.sock` per active spawn, and `src/meridian/cli/spawn_inject.py` drives a running spawn from another process through that socket.

Soften to:

> **App streaming HTTP API** — `app/server.py`'s POST `/spawns` handler constructs the `LaunchContext` and hands the subprocess to an in-process `SpawnManager`. The manager exposes `/inject` and `/interrupt` as HTTP endpoints routed through the same in-memory connection. The architectural reason is **current API shape**: the REST/WS interface is structured around a manager held by the HTTP handler. Meridian's separate `control.sock` + `spawn_inject` mechanism demonstrates out-of-process control is possible; moving app-streaming to queued exec + remote control is a separate refactor (out of scope for workspace-config-design).

### 4. Factory is a pipeline, not pure (p1895 Blocker 2)

Current design says "domain core is pure, no I/O." But Option A absorbs `materialize_fork()` as a pipeline stage, and `fork_session()` opens SQLite, reads threads, copies rollout files (`src/meridian/lib/harness/codex.py:425`).

Pick one of two reframes, justified against code:

**Option A (preferred): rename "pure" to "pipeline with explicit I/O stages."** Factory is a pipeline of builders most of which are pure (policy resolution, permission resolution, env construction, workspace projection). One stage (`materialize_fork()`) is explicitly marked as I/O-performing. The invariant becomes "factory is the only place composition happens," not "factory is pure."

**Option B: keep fork outside the factory.** Fork materialization stays pre-factory in the driving adapter (worker's `build_create_payload`, primary's `_resolve_command_and_session`). Document as a preserved composition concern, with the honest invariant weakening: "fork materialization is not consolidated in R06 but does not affect workspace projection inputs, so R05 is unblocked. A follow-up refactor can absorb it once session state dependencies are unified."

Pick A unless code analysis shows fork depends on driver-specific state that genuinely can't factor into the pipeline. If A, clearly mark `materialize_fork()` as the I/O-performing stage in the scope + exit criteria. The factory's contract becomes: "pipeline of composition stages; `materialize_fork()` performs I/O (Codex session API); all other stages are pure."

### 5. Drop "impossible to drift" language (p1895 Minor, p1896 Blocker 1)

Any remaining phrasing that says invariants are "impossible to drift" or "mechanically guaranteed" must be softened to "heuristic guardrails" unless backed by a genuinely structural check (Pyright, import graph). The `rg`-based checks are heuristic — gameable by aliasing, indirection, dynamic dispatch (per p1896 Blocker 2 specific examples). State this honestly.

### 6. CI gate for `rg` checks (p1896 Blocker 1)

Current design says "CI-checkable via rg." Live CI (`.github/workflows/meridian-ci.yml:34-44`) runs ruff/pyright/pytest/build only — no `rg` step.

**Add to R06 scope:** a CI step that runs the `rg` suite. Minimum form is a shell script at `scripts/check-launch-invariants.sh` that runs each exit-criterion command and exits nonzero on drift. Wire it into `.github/workflows/meridian-ci.yml` as a required status check. Name this addition in R06's scope section and its exit criteria ("CI job `check-launch-invariants` passes"). Without this, "CI-checkable" is false.

### 7. Tighten `rg` gameability — explicit acknowledgment + targeted hardening (p1896 Blocker 2, Major 1)

For each exit-criterion `rg` check, state both the command and its known evasion modes. Example shape:

> `rg "resolve_policies\(" src/` → expected matches: `policies.py` (definition) + `launch/context.py` (factory callsite).
>
> **Heuristic limitations.** Evadable by: aliasing on import (`from policies import resolve_policies as rp`), indirect dispatch (`fn = resolve_policies; fn()`), or reimplementation under a different name. Reviewers must verify that the builder is called exclusively through its canonical name in driving-adapter modules. GH issue #<new-or-existing> tracks upgrading to AST-based enforcement.

Do this for each of the 4-5 builder checks and the bypass-env check. Don't pretend they're absolute.

Also: add **"sole caller" exact commands for every builder**, not only `resolve_policies`. p1896 Major 2 caught that `resolve_permission_pipeline`, `build_env_plan`, `build_harness_child_env` only have definition greps, not caller greps.

### 8. Pyright exhaustiveness — require `match` + `assert_never`, ban `pyright: ignore` in executor modules (p1896 Major 3)

Current design claims compile-time exhaustiveness via Pyright. `pyright: ignore` is already used in-tree (`src/meridian/lib/harness/bundle.py:35`, `src/meridian/lib/app/server.py:342`), and `cast(Any, ctx)` evades match checking.

Tighten the exit criterion:

> **Plan Object exhaustiveness.**
> - `rg "match\s+.*launch_context" src/meridian/lib/launch/process.py src/meridian/lib/launch/streaming_runner.py` → matches a `match` statement per executor.
> - `rg "assert_never\(" src/meridian/lib/launch/` → at least one per executor dispatch site.
> - `rg "pyright:\s*ignore" src/meridian/lib/launch/ src/meridian/lib/ops/spawn/` → 0 matches (enforced by the CI invariants script).
> - `rg "cast\(Any," src/meridian/lib/launch/ src/meridian/lib/ops/spawn/` → 0 matches.

### 9. Consistency fixes (p1897)

- Standardize the factory diagram label across `refactors.md`, `harness-integration.md`, and D17 prose. Pick one: `(driving port / factory)`. Update all three occurrences.
- Fix drifted line-number citations: `src/meridian/lib/harness/opencode_http.py:319` → verify current line for `create_subprocess_exec`; `src/meridian/lib/config/settings.py:804-838` → verify `resolve_repo_root` function boundaries, adjust.

## The substantive addition: `observe_session_id()` adapter seam

### What to add to R06

Introduce an adapter-owned session-ID observation method. Session-ID moves off `LaunchContext` entirely (closing p1891's "all required, frozen" contradiction) onto a new `LaunchResult` returned by executors.

New types:

```python
@dataclass(frozen=True)
class LaunchResult:
    exit_code: int
    child_pid: int | None
    session_id: str | None  # populated by adapter.observe_session_id()
    # + any other post-launch observables the current code carries
```

New adapter method on the harness adapter protocol:

```python
def observe_session_id(
    self,
    *,
    launch_context: NormalLaunchContext,
    launch_outcome: LaunchOutcome,  # raw executor output: exit_code, captured_stdout, child_pid
) -> str | None: ...
```

Executor contract:
- Executor runs the process, returns a `LaunchOutcome` (raw: exit, pid, any captured output).
- The driving adapter calls `harness_adapter.observe_session_id(...)` post-exec and assembles a `LaunchResult`.
- If observability fails (e.g., Popen path with today's scrape-only Claude impl), `session_id = None`. Surfacing layer already handles missing-session-id.

**Do not change existing observation mechanisms.** Claude still PTY-scrapes; Codex still parses stream events; OpenCode still does whatever it does today. The refactor **moves that logic behind the adapter method**. The mechanism swap to filesystem polling is GitHub issue #34.

### What this closes

- **p1891 Blocker 2**: `LaunchContext` can honestly be frozen + all-required. Post-launch session-ID is on `LaunchResult`, not `LaunchContext`.
- Executor contract is cleaner: one input (`LaunchContext`), one output (`LaunchOutcome` → adapter → `LaunchResult`). No optional mutable fields on the plan.
- Prepares the ground for issue #34's mechanism swap — the seam exists; implementations change later without touching executors.

### R06 scope additions (specific)

1. Add `LaunchResult` frozen dataclass. Add `LaunchOutcome` (raw executor output) if not already captured.
2. Add `observe_session_id()` to the harness adapter protocol in `src/meridian/lib/harness/adapter.py`. Signature per above.
3. Implement `observe_session_id()` in each harness adapter by **relocating existing session-ID code from executors** (Claude: scraper logic from `launch/process.py` or `streaming_runner.py`; Codex/OpenCode: stream-parse logic from streaming runner).
4. Executors return `LaunchOutcome`; driving adapters call `observe_session_id` and assemble `LaunchResult`.
5. Remove `session_id` / `launch_session_id` fields from `LaunchContext`. `NormalLaunchContext` becomes genuinely all-required, frozen.
6. Update executors' `match` + `assert_never` dispatch to the new type.

### Acknowledged forward-looking change

R06 lands the seam. GitHub issue #34 swaps implementations to filesystem polling. Between those two, the Popen-fallback-loses-session-ID bug persists for primary launch. Name this in the design as a known limitation with a follow-up reference.

## Your task

Edit the design files in place:

1. `design/refactors.md` — R06:
   - Honesty corrections #1-#5 applied to Architecture + Preserved Divergences.
   - Scope addition #6 (CI check script + workflow wiring).
   - Exit criteria rewrites per #7-#8 (sole-caller commands for every builder; evasion-mode acknowledgment; Pyright tightening).
   - Add `observe_session_id()` adapter seam as a new scope section.
2. `decisions.md` — D17:
   - Drop overclaim language per #5.
   - Update "Preserved Divergences" per #1 and #4.
   - Add session-ID adapter-seam rationale + #34 follow-up reference.
   - Update fork-continuation treatment per #4.
3. `design/architecture/harness-integration.md`:
   - Update Launch composition section wording for #1, #2, #3.
   - Add adapter-protocol method documentation for `observe_session_id()`.
4. Consistency fixes per #9.

Validate link check passes: `bash .agents/skills/tech-docs/scripts/check-md-links.sh .meridian/work/workspace-config-design`.

### Do NOT

- Change the 3-driving-adapter shape.
- Reopen settled decisions (D1-D16, D18).
- Rewrite R01-R05 beyond session-ID field removal cross-references.
- Touch `requirements.md` or `design/spec/*` except where line-number drift needs fixing.
- Implement filesystem polling — that's issue #34.
- Add R07 or other new work items in-repo — #34 is the only follow-up reference needed.

### Deliverable report

Structure:
1. Honesty corrections applied (one bullet per correction #1-#5 with the before→after wording).
2. CI script + workflow wiring scope added (#6). Name the file path and workflow job.
3. `rg` check tightening (#7) — one line per builder check showing the new form.
4. Pyright exhaustiveness tightening (#8) — the new commands.
5. Consistency fixes applied (#9) — file + line.
6. Session-ID adapter seam addition (which files/sections changed, what the new types/methods look like).
7. Fork-continuation decision (A or B; justify against code).
8. Verification — link check result, no out-of-scope file touched, exit-criteria `rg` commands still well-formed.

Do not commit.
