# Architect Task — Rewrite R06 + D17 around the 3-driving-adapter framing

## Context

`workspace-config-design` has been through four review rounds on R06 (the launch-composition refactor). The earlier framings enumerated 8-9 call sites and fought to enforce "exactly one composition" invariants across all of them; reviewers kept finding holes.

A feasibility explorer (`.meridian/spawns/p1893/report.md`) established the honest architecture:

- **1 driving port** — `build_launch_context()`, the factory at the domain boundary.
- **1 driven port** — the harness adapter protocol (`resolve_launch_spec`, `project_workspace`, etc.).
- **3 driving adapters**, each with a named architectural reason:
  1. **Primary launch** (`launch/plan.py` → `launch/process.py`) — foreground PTY `os.execvpe` path. Process replacement semantics: meridian *becomes* the harness; it can't supervise a child.
  2. **Background worker** (`ops/spawn/execute.py` driven by `ops/spawn/prepare.py:build_create_payload`) — persistent queue lifecycle. Dequeues N jobs over its lifetime; async subprocess per job; output persisted to disk.
  3. **App streaming HTTP API** (`app/server.py:268-365`) — live in-process `SpawnManager` control channel. `/inject` and `/interrupt` require the HTTP handler to hold the subprocess in memory, so composition has to happen at request time, not deferred.
- **2 executors** — PTY execvpe (primary) and async subprocess_exec (worker + app-streaming share).
- **1 preview caller** — dry-run (`spawn create --dry-run`, primary dry-run) calls the factory to produce `composed_prompt` + `cli_command` but does not execute.

The previous 8-9 "ports" collapse because several were call locations inside one driving adapter, and two were **dead parallel implementations** that R06 should delete:

- `launch/streaming_runner.py:389-532` (`run_streaming_spawn`) duplicates `execute_with_streaming` at `streaming_runner.py:742-830`. Delete the former; collapse streaming serve CLI into the shared path.
- `streaming/spawn_manager.py:SpawnManager.start_spawn` has an unsafe-resolver fallback when callers omit `spec`. Delete it — callers always have a resolved `LaunchContext` post-R06.

Additional findings from the explorer that belong in R06:

- **`SpawnParams` is not a user-input DTO.** It carries resolved state (skills, session ids, appended system prompts, report paths). R06 should split it into `SpawnRequest` (user-facing, unresolved) + `SpawnParams` (or a renamed successor like `ResolvedLaunchInputs`) that only exists inside/after the factory.
- **`prepare_spawn_plan` is stale.** The actual pre-worker composer is `build_create_payload` at `ops/spawn/prepare.py:169-397`. Any remaining design references to `prepare_spawn_plan` should point to `build_create_payload`.

Read these before starting:
- `.meridian/spawns/p1893/report.md` — the explorer findings this rewrite is based on.
- `.meridian/spawns/p1891/report.md` — gpt-5.4 review of invariant enforceability (still applies).
- `.meridian/spawns/p1892/report.md` — opus review of scope completeness (largely dissolves with new framing, but some findings remain).
- `.meridian/spawns/p1890/report.md` — the previous R06 rewrite this supersedes.
- `.meridian/work/workspace-config-design/design/refactors.md` — current R05, R06.
- `.meridian/work/workspace-config-design/decisions.md` — current D17.
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` — current Launch composition section.

**This is a rewrite, not a fix list.** The decision is made. Your job is to render the new framing faithfully.

## The framing to encode

### Architecture shape

Meridian launch is a hexagonal (ports and adapters) core with 3 driving adapters and 3 harness adapters. Minimal and honest:

```
Primary launch ─┐
                │
Worker         ─┼──▶ build_launch_context() ──▶ LaunchContext ──▶ executor ──▶ harness adapter ──▶ process
                │    (driving port)                                (PTY or async)  (driven port/adapter)
App streaming  ─┘
                │
Dry-run        ─┘ (no executor; preview output)
```

- Each of the 3 execution drivers calls the factory, hands `LaunchContext` to the appropriate executor.
- Dry-run calls the factory for its preview output and does not execute.
- Every builder has exactly one implementation in the domain core.
- Every driving adapter has a **named architectural reason** to exist as a separate driver (not an accidental bolt-on).

### Why 3, not 1 or 9

- Not 1: primary must execvpe (process replacement, not supervision); worker must own a persistent queue lifecycle; app-streaming must hold the subprocess live for `/inject`/`/interrupt`. These are incompatible driver semantics.
- Not 9: the previous enumeration mixed call locations inside the same adapter and included dead parallel code. Deleted in R06.

### What R06 delivers

1. **Domain core**
   - `build_launch_context()` factory in `launch/context.py` (or successor).
   - One builder per composition concern, each in its own module:
     - `resolve_policies()` in `launch/policies.py`
     - `resolve_permission_pipeline()` in `launch/permissions.py` (or existing location)
     - `project_workspace()` — the R05 deliverable, inserted as a pipeline stage
     - `build_env_plan()` in `launch/env.py`
     - `resolve_launch_spec()` stays on the harness adapter (already harness-owned; called once from the factory)
   - `LaunchContext = NormalLaunchContext | BypassLaunchContext` sum type. Frozen dataclasses. Required fields are required at type level. Post-launch session-id extraction is **not** on `LaunchContext` — it's an executor result value (separate `LaunchResult` or equivalent), per p1891 blocker 2.
   - `MERIDIAN_HARNESS_COMMAND` bypass: `build_launch_context()` runs policy + session resolution, then branches and returns `BypassLaunchContext` with concrete fields (`argv`, `env`, `cwd`, and any others required — verify against code). Bypass does not call spec resolution, workspace projection, or `build_harness_child_env`; it calls `inherit_child_env` instead.
   - Executor dispatch uses `match` + `assert_never` (or equivalent) for union exhaustiveness. Pyright enforces at build time.

2. **Three driving adapters route through the factory**
   - **Primary launch**: `launch/plan.py` → `launch/process.py` constructs `SpawnParams` + calls `build_launch_context()` → PTY executor consumes `LaunchContext`. Dry-run in this path calls the factory and returns preview without executing.
   - **Background worker**: `ops/spawn/prepare.py:build_create_payload` + `ops/spawn/execute.py` constructs `SpawnParams` + calls `build_launch_context()` → async subprocess executor. Fork materialization is a pipeline stage inside the factory (decide: see "Fork continuation" below).
   - **App streaming HTTP**: `app/server.py` handler constructs `SpawnParams` + calls `build_launch_context()` → hands `LaunchContext` to `SpawnManager` which uses async subprocess executor. `/inject` and `/interrupt` reach the same manager; composition does not happen there.
   - Dry-run callers (CLI + primary) call the factory for preview only. Named as the 4th factory caller but not an executor.

3. **Driven adapters**
   - Harness adapters (`harness/claude`, `harness/codex`, `harness/opencode`) implement the driven port. Receive `NormalLaunchContext`, produce harness-specific output via `resolve_launch_spec()`, `project_workspace()`, `build_command()`, etc.
   - Domain core imports from `harness/adapter.py` (abstract contract module) only. It does not import from `harness/claude`, `harness/codex`, `harness/opencode`, `harness/projections`. State this as the concrete import-graph invariant (p1891 F3).

4. **Deletions (part of R06 scope)**
   - `launch/streaming_runner.py:run_streaming_spawn` and its call in `cli/streaming_serve.py` — fold streaming serve CLI into the shared `execute_with_streaming` path that already uses `prepare_launch_context`.
   - `streaming/spawn_manager.py:SpawnManager.start_spawn` unsafe-resolver fallback — callers always hand in a resolved `LaunchContext` post-R06.

5. **Type renames / splits**
   - `SpawnParams` carries resolved execution state today. Split into:
     - `SpawnRequest` — user-facing args only (prompt, harness, model, approval, skills refs, workspace refs). Constructed by CLI/HTTP/app layers.
     - `SpawnParams` (or successor) — resolved execution inputs, constructed only inside the factory or by pre-worker composers. Carries skills-resolved-to-paths, continuation ids, appended prompts, report paths.
   - `RuntimeContext` unified to one type across the codebase (existing invariant).

6. **Fork continuation — pick one and be honest**
   - **Option A (absorb):** add `materialize_fork()` as a pipeline stage in the domain core, post-spec-resolution, pre-env. R06 delivers this consolidation.
   - **Option B (preserve divergence honestly):** fork materialization stays pre-execution in the two driver paths (primary `launch/process.py:68-104`, worker `ops/spawn/prepare.py:296-311`). Name it as a recognized remaining composition concern with a follow-up refactor. State the invariant weakening: fork materialization does not affect workspace projection inputs, so R05 is not blocked.
   - Verify against code (session state dependencies differ between primary and worker) and pick. Do not claim fork is "executor-produced" — that's the overclaim p1892 F3 caught.

### Exit criteria — genuinely mechanical

Each invariant must come with an exact command and expected result. No soft "grep for X returns one match" — state the exact `rg` pattern, anchor it (definition-anchored where possible), and name the exact expected hits. Examples:

- **Pipeline: one builder per concern.**
  - `rg "^def resolve_policies\(" src/` → exactly 1 match, in `src/meridian/lib/launch/policies.py`.
  - `rg "resolve_policies\(" src/ --files-with-matches` → only `launch/policies.py` (definition) and `launch/context.py` (sole caller in factory). Zero matches in driving adapters.
  - Repeat the pattern for `resolve_permission_pipeline`, `build_env_plan`, `build_harness_child_env`, `project_workspace`.

- **Plan Object: one sum type.**
  - `rg "^class NormalLaunchContext\b" src/` → 1 match.
  - `rg "^class BypassLaunchContext\b" src/` → 1 match.
  - Pyright enforces union exhaustiveness at executor dispatch via `match` + `assert_never`. Name the exact file(s) where the match statements live.

- **Adapter boundary: no domain→concrete-harness imports.**
  - `rg "from meridian.lib.harness\.(claude|codex|opencode|projections)" src/meridian/lib/launch/` → 0 matches.
  - Domain core may import from `meridian.lib.harness.adapter` (abstract contract).

- **Driving-adapter invariant: exactly 3 factory callers (+1 preview).**
  - `rg "build_launch_context\(" src/` → exactly 4 matches: `launch/plan.py` (primary + primary dry-run), `ops/spawn/execute.py` (worker), `app/server.py` (app streaming), and `ops/spawn/api.py` or equivalent (dry-run preview). Verify exact line locations.
  - No other file calls the factory.

- **No composition outside core:**
  - `rg "TieredPermissionResolver\(" src/` → only inside the permission builder (covers p1892 F2: `streaming_serve.py:85` hardcoded resolver construction goes away when streaming_serve is deleted or routed through factory).
  - `rg "MERIDIAN_HARNESS_COMMAND" src/` → only inside `build_launch_context()` bypass branch (plus tests).

- **Deletions completed:**
  - `rg "^def run_streaming_spawn\(" src/` → 0 matches.
  - `rg "^def start_spawn\(" src/meridian/lib/streaming/` → either deleted or no fallback branch.

### Suggested internal phasing (p1892 F7)

One paragraph naming the natural ordering. Something like:

> R06 naturally decomposes into: (1) `SpawnRequest`/`SpawnParams` split (standalone DTO change); (2) `RuntimeContext` unification (standalone); (3) domain-core pipeline + `LaunchContext` sum type; (4) rewire primary launch to call factory; (5) rewire worker to call factory; (6) rewire app-streaming to call factory; (7) delete `run_streaming_spawn` + `SpawnManager.start_spawn` fallback; (8) absorb bypass into factory. (1), (2), (3), and (7) can proceed independently; (4)-(6) land one driver at a time; (8) after (3). Each intermediate state satisfies a subset of the exit criteria.

## Your task

### 1. Rewrite R06 in `design/refactors.md`

Title: `R06 — Consolidate launch composition into a hexagonal core (3 driving adapters through one factory)`.

Structure:
- **Why** — state the drift problem in driver terms. Today 9 call locations compose independently; the right shape is 3 driving adapters with named architectural reasons (process replacement / queue lifecycle / live HTTP control channel) each calling one factory. Name the two dead parallel implementations being deleted.
- **Architecture** — the diagram above, the 3 driving adapters with their reasons, the 2 executors, the 1 driving port, the 1 driven port.
- **Scope**, organized as:
  1. Domain core (create the factory + builders + sum type).
  2. Three driving adapters (rewire each to call factory, do not resolve).
  3. Driven adapters (harness modules) — no composition leakage.
  4. Deletions (dead parallel code named above).
  5. Type splits (`SpawnRequest`/`SpawnParams`).
- **Exit criteria** — in the tight mechanical form above. Each invariant has an exact command and expected result.
- **Preserved divergences** — PTY executor stays, primary `child_cwd` stays, fork continuation per Option A or B (pick and justify).
- **Test blast radius** — keep the existing enumeration; add tests around the new type split and around the deleted paths.
- **Suggested internal phasing** — the paragraph above.

### 2. Rewrite D17 in `decisions.md`

Keep hexagonal naming, but sharpen:
- "Architecture name" paragraph names the 3 driving adapters with their architectural reasons.
- "Why not 1" paragraph explains the three driver reasons.
- "Why not 9" paragraph explains the previous enumeration was accidental (call locations + dead parallel code).
- "Scope evolution" timeline updated with this pass.
- Rejected alternatives unchanged except where they now mention numbers.

### 3. Update `design/architecture/harness-integration.md`

Rewrite the Launch composition section around 3 driving adapters + 1 factory + 1 driven port. Drop any language implying 8-9 ports.

### 4. Small cross-cutting touches

- Update R05's Why/Exit criteria: R05 inserts `project_workspace()` as a pipeline stage in `build_launch_context()`; with 3 driving adapters all routed through the factory, R05 has exactly one insertion point.
- Fix design references to `prepare_spawn_plan` → `build_create_payload` where the reference is to the live composer.
- R01/R02/R06 independence note already added to `refactors.md` preamble (from p1890). Keep.
- SURF-1.e6 narrowing + surfacing-layer row already landed (from p1890). Keep.

### 5. Do NOT

- Demote R06 or reverse the prereq ordering.
- Invent new spec requirements.
- Rewrite R01, R02, R03, R04, R05 beyond the small touches above.
- Touch `requirements.md` or `design/spec/config-location.md`.
- File separate work items or fix the `disallowed_tools` bug the explorer spotted — note it as a red flag only.

### 6. Deliverable

Edit files in place. Validate `bash .agents/skills/tech-docs/scripts/check-md-links.sh .meridian/work/workspace-config-design` passes.

Produce a report structured as:
1. R06 new shape (one paragraph).
2. D17 new shape (one paragraph).
3. harness-integration.md changes (one paragraph).
4. Cross-cutting touches (R05, file-reference fixes).
5. Fork continuation decision (A or B, with reason).
6. Exit-criteria verification — run each `rg` command you state in the design and show the result matches your claim. If any doesn't match, the design is wrong; fix it.
7. Verification (link check + no out-of-scope changes).

Do not commit.
