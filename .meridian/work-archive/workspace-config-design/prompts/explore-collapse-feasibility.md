# Explorer Task — Can we collapse 9 launch composition sites to 2?

## The question

`workspace-config-design`'s R06 refactor currently enumerates 8-9 driving-port call sites that each do some amount of launch composition (policy resolution, permission resolution, spec resolution, env building, `SpawnParams` construction). Four review rounds keep finding holes in that enumeration.

The hypothesis: **most of those sites are accumulated bolt-ons, not essential fan-out.** If composition only needs to happen at *execution time*, the architecture collapses to:

1. **Background worker** (`ops/spawn/execute.py`) — one `build_launch_context()` call for all spawn paths
2. **Primary launch** (`launch/plan.py` or its successor) — one `build_launch_context()` call for foreground PTY path

Total: **2 composition sites**. Everything upstream becomes pure enqueue — construct a `SpawnRequest` (user-facing args only), persist it, return a handle. No policies, no permissions, no env, no spec. The worker resolves everything when it picks up the job.

**Your job: verify whether this collapse is actually feasible.** Yes = the R06 refactor gets dramatically smaller. No = we keep fighting invariant enforcement on 9 sites.

## Sites to analyze

For each of the following, determine (a) what composition it does today, (b) **why** — what decision or side effect requires pre-worker composition, and (c) whether that reason is essential or incidental.

1. **CLI spawn** — `src/meridian/cli/spawn.py` or wherever `meridian spawn ...` is handled. When the user runs the CLI, what composition happens before the spawn is enqueued? Is any of it required to produce user-facing output (error messages, dry-run preview)?

2. **HTTP API POST /spawns** — `src/meridian/lib/app/server.py:333` and surroundings. What does the handler construct before persisting the spawn? Any of it needed to return a 200/400 response? Could validation happen without full resolution?

3. **Streaming dispatcher** — `src/meridian/lib/streaming/spawn_manager.py:197` and surrounding `enqueue_spawn`/dispatch logic. What does it compose to dispatch a streaming spawn? Is streaming dispatch structurally different from non-streaming, or just IO capture mode?

4. **Streaming serve CLI** — `src/meridian/cli/streaming_serve.py:80+` and its helper `src/meridian/lib/launch/streaming_runner.py:389-420` (`run_streaming_spawn`). This one calls `adapter.resolve_launch_spec(params, perms)` directly. Why does it resolve here instead of deferring? Is there a streaming-specific reason, or is it duplicating worker logic?

5. **Background worker** — `src/meridian/lib/ops/spawn/execute.py:861` and `src/meridian/lib/ops/spawn/prepare.py:202,323`. What does `prepare_spawn_plan` do today? If composition moves entirely here, what parts of `prepare` are actually composition vs. fork handling vs. session resolution?

6. **Primary launch** — `src/meridian/lib/launch/plan.py`, `process.py`, `command.py`. What does this path compose? Is there a reason primary launch couldn't share a common `build_launch_context()` with the worker, or is the PTY executor the only real divergence?

## Specific probes for the "essential pre-worker composition?" question

For each site, check whether pre-worker composition is required by:

- **Validation** — does the site need to call a resolver to return an error to the user before enqueueing? (e.g., "no such profile," "permission denied," "invalid skills list")
- **Dry-run / preview** — does the site produce a preview that needs resolved output?
- **Session state** — does the site need to read/write session state (resume, fork, parent linkage) in a way that requires resolved spec?
- **Fork materialization** — does the site need to fork a Codex session before enqueueing?
- **Streaming setup** — does the streaming path need output-capture machinery set up before the subprocess launches?
- **Permission/approval prompts** — does the site need to prompt the user for approval before the spawn starts?

## What "essential" means

If a composition step happens pre-worker because:
- **Essential**: removing it would change user-visible behavior (error messages, prompts, immediate responses).
- **Incidental**: it's there because "that's how the code was written when feature X was added" — moving it to the worker would not change external behavior.

Flag each composition step as essential or incidental with evidence (call graph, what the result is used for).

## Also verify

- Does `prepare_spawn_plan` in `ops/spawn/prepare.py` belong in the worker or pre-worker? What does it do that isn't composition?
- Does the streaming runner's `run_streaming_spawn` share an execution path with the non-streaming spawn execute, or is it a parallel implementation?
- Is there a single `executor` abstraction today, or are PTY and subprocess paths truly parallel pipelines?
- Are `SpawnParams` legitimate user-input adapter shape, or do they carry resolved state that should only be materialized in the worker?

## Report

Structure:

1. **Collapse verdict** — one line, one of:
   - `feasible` — all non-worker sites can be reduced to pure enqueue
   - `feasible-with-caveats` — collapse works for most sites, N remain with documented essential pre-worker composition
   - `not-feasible` — K sites have essential composition reasons; listing them

2. **Per-site table** — one row per site above with:
   - Current composition performed
   - Why (user-visible reason or "incidental historical bolt-on")
   - Collapse outcome (fully enqueue / keep subset / keep composition)

3. **If feasible-with-caveats or not-feasible**: name the specific composition concerns that must stay pre-worker and why.

4. **R06 scope implication** — one paragraph: if collapse is feasible, what does R06 shrink to? Just "introduce `LaunchContext` sum type, build factory, rewire worker + primary, delete composition from other sites"?

5. **Red flags** — anything you noticed that's unrelated but suspicious (dead composition, parallel implementations that shouldn't be, etc.).

Keep the whole report under ~800 words. This is a feasibility check, not a full audit. Cite file:line for every claim. Don't trust the design docs' enumeration — verify from code.
