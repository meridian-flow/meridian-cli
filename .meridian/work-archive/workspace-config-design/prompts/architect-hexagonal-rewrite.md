# Architect Task — Rewrite R06 + D17 around hexagonal / plan-object / pipeline / adapter vocabulary

## Context

`workspace-config-design` is in final cleanup before planning. Two review rounds happened:

- **First pass** (`.meridian/spawns/p1882/report.md` gpt-5.4, `.meridian/spawns/p1883/report.md` opus): found R06 as originally scoped didn't satisfy its own invariants.
- **Orchestrator grew R06** to include `ops/spawn/prepare.py` + primary fork recomposition + `MERIDIAN_HARNESS_COMMAND` bypass + `RuntimeContext` unification. Kept R06 as prereq to R05.
- **Second pass** (`.meridian/spawns/p1888/report.md` gpt-5.4, `.meridian/spawns/p1889/report.md` opus): found the grown R06 *still* misses composition sites in `app/server.py:333`, `streaming/spawn_manager.py:197`, `cli/streaming_serve.py:80`, `ops/spawn/execute.py:861`. The "exactly one composition function" invariant is still overclaimed.

The orchestrator + user concluded the old function-centric invariants are the wrong framing. The correct framing is **pattern-centric**: canonical Plan Object + pipeline composition + adapter translation, structured as a hexagonal (ports and adapters) architecture.

**This is a rewrite task, not a design-question task. The decision has been made. Your job is to render it faithfully in the design docs.**

## The framing to encode

Read `.meridian/spawns/p1888/report.md` and `.meridian/spawns/p1889/report.md` first so you know what problems are being solved. Then encode the following pattern framing into R06 and D17.

### Architecture name and mental model

Meridian launch is a **hexagonal (ports and adapters)** core with a canonical Plan Object at the center:

- **Domain core** — pure, no I/O. Contains the canonical `LaunchContext` type (sum of `NormalLaunchContext | BypassLaunchContext`) plus exactly one builder per composition concern (policies, permissions, workspace, env, spec assembly). The builders form a pipeline; `build_launch_context()` is the factory that runs the pipeline and returns a complete `LaunchContext`.
- **Driving ports** — the callers that initiate a launch: CLI spawn, HTTP API (`app/server.py`), streaming dispatcher (`streaming/spawn_manager.py`), streaming serve CLI (`cli/streaming_serve.py`), background worker (`ops/spawn/execute.py`). They prepare input, call `build_launch_context()`, and hand off the plan to an executor. They are **allowed to exist** and **allowed to construct `SpawnParams`** — they must not re-implement composition.
- **Driven adapters** — harness adapters (`harness/claude.py`, `harness/codex.py`, `harness/opencode.py`). They receive a `NormalLaunchContext` and produce harness-specific output: CLI tokens, env overlays, config JSON. One method per translation concern (e.g., `project_workspace()`), implemented once per harness.
- **Executors** — PTY execvpe (primary) and async subprocess_exec (spawn/streaming). Both consume the full `LaunchContext` sum and dispatch by pattern match. Different execution strategies, same plan.

### The three patterns that enforce drift protection

1. **Pipeline / functional composition (build time).** Each stage is a pure function with exactly one implementation:
   - `resolve_policies()` — in `launch/policies.py` (or successor)
   - `resolve_permission_pipeline()` — in `launch/permissions.py`
   - `project_workspace()` — the R05 deliverable
   - `build_env_plan()` — in `launch/env.py`
   - `resolve_launch_spec()` — on the adapter (already harness-owned)
   - `build_launch_context()` — in `launch/context.py`, orchestrates the above
   The invariant is **one file per stage, one callsite per builder**. CI-checkable via `rg`.

2. **Plan Object (Evans) with algebraic sum (build-result contract).**
   `LaunchContext = NormalLaunchContext | BypassLaunchContext`
   Frozen dataclasses. Required fields are required at the type level. `NormalLaunchContext` carries policy/permission/workspace/env/spec/runtime/cwd. `BypassLaunchContext` carries raw argv/env for `MERIDIAN_HARNESS_COMMAND` and nothing else. Harness adapters accept only `NormalLaunchContext`; executors accept the sum and pattern-match.
   The invariant is **exactly one `LaunchContext` sum type, all fields required**. Compile-checkable.

3. **Adapter pattern (GoF) for harness translation.**
   Adapters implement `project_workspace(context: NormalLaunchContext) -> HarnessWorkspaceProjection` (and similar translation methods). The domain core never imports harness-specific modules; harness modules never re-implement composition.
   The invariant is **domain core has no harness-specific imports; every harness has one `project_*()` method**. Import-graph-checkable.

### The driving-ports invariant (replaces the overclaimed "one composition function")

**Rewrite the invariant**: every driving port that launches a harness must call `build_launch_context()` to obtain the plan; policy/permission/workspace/env composition exists **only** inside the domain-core builders. Driving ports are **allowed** to construct `SpawnParams` (that's their job — adapting request shape). They are **forbidden** to call resolvers, construct `LaunchContext` directly, or build env themselves.

CI-checkable form:
- `rg "resolve_policies\(" src/` returns exactly one implementation and N call sites inside the domain core.
- `rg "LaunchContext\(" src/` returns only the factory `build_launch_context()`.
- `rg "build_harness_child_env\(" src/` returns one implementation in `launch/env.py`, called only from `build_env_plan()`.

This replaces the current R06 claim "exactly one policy/permission/`SpawnParams` resolution site" (overclaimed) with "exactly one policy resolver, one permission resolver, one env builder; driving ports construct `SpawnParams` as needed but do not resolve."

## Your task

### 1. Rewrite `design/refactors.md` R06

Keep R06 as the prereq to R05. Rewrite its title, Why, Scope, and Exit criteria around the hexagonal framing above. Concrete structure to aim for:

- **Title**: `R06 — Establish hexagonal launch core (canonical Plan Object + pipeline + adapters)`
- **Type**: `prep refactor (blocks R05)`
- **Why**: state the drift problem in port/adapter terms — launch composition is currently scattered across driving ports (HTTP/streaming/CLI/worker facades) rather than consolidated in a domain core. Future launch-touching features (workspace is the 5th) would compound the drift. The fix is to establish a domain core that every driving port must use.
- **Scope** split into three sections:
  1. **Domain core (create/consolidate)**: the builders and their one-file-per-stage locations; the `LaunchContext` sum type in a single module.
  2. **Driving ports (route through core)**: list each entrypoint that today composes independently and say what has to change. The list is broader than the current R06 — include `app/server.py:333`, `streaming/spawn_manager.py:197`, `cli/streaming_serve.py:80`, `ops/spawn/execute.py:861`, `ops/spawn/prepare.py:202, 323`, plus the current `launch/plan.py`, `launch/process.py`, `launch/command.py`. Each port's change is "construct request-specific inputs, call `build_launch_context()`, hand off the plan."
  3. **Driven adapters (no composition leakage)**: harness adapters keep harness-specific translation only; any composition logic currently inside harness modules moves to the domain core.
- **Exit criteria (invariants in hexagonal vocabulary)**:
  - Exactly one `LaunchContext` sum type with required fields (`NormalLaunchContext | BypassLaunchContext`); compile-time.
  - Exactly one builder per composition concern (policies, permissions, workspace, env, launch-spec assembly); `rg`-checkable.
  - Exactly one `RuntimeContext` type across the codebase.
  - Every driving port obtains its plan from `build_launch_context()` and does not resolve policies, build env, or construct `LaunchContext` directly.
  - Domain core has no imports of harness-specific modules; adapters have no composition code.
  - `MERIDIAN_HARNESS_COMMAND` bypass is handled by returning `BypassLaunchContext` from the builder — not by a branch inside executors or driving ports.
  - Preflight remains adapter-owned but is passed through the `LaunchContext` as an opaque field (no adapter-specific branching in the domain core).
- **Preserved divergences (not flattened)**:
  - PTY `os.execvpe` path stays in the primary executor (strategy-pattern sibling).
  - Claude-in-Claude sub-worktree cwd stays as a `child_cwd` field on `NormalLaunchContext`, populated by the pipeline.
  - Primary post-launch session-id extraction attaches as an optional field on `LaunchContext` set post-launch.
  - Codex fork continuation state is a separate value produced by the executor, not a mutation of `LaunchContext`.
- **Test blast radius**: expand the `rg` pattern per `p1889` F3. Enumerate the tests that touch shared builders, the sum type, executor entry, and the driving ports. Include `tests/test_app_server.py`, `tests/ops/test_spawn_prepare_fork.py`, `tests/harness/test_codex_fork_session.py` per `p1888`.

### 2. Rewrite `decisions.md` D17

Replace the current D17 body with the hexagonal framing. Keep the prereq ordering and the rejection of Depth-2 / Depth-3 / demotion. Add:

- A short "Architecture name" paragraph naming this as **hexagonal (ports and adapters)** with a canonical Plan Object, and briefly describing the three patterns (pipeline / plan object / adapter) that enforce drift protection.
- A "Why not function-centric invariants" paragraph explaining that "exactly one composition function" was the wrong framing — driving ports legitimately exist (HTTP API, streaming, CLI facades) and constructing request-specific `SpawnParams` is their job, not a drift site. The real invariant is that *composition* lives in the domain core, not that every `SpawnParams()` call is colocated.
- Keep the three rejected alternatives (Depth-2, Depth-3, demote). Update Depth-2's rationale to reflect that the rejection is not about "one function" but about "no domain core" — keeping both seams with independent composition leaves no central type to check against.
- Remove the literal "Depth 2 / Depth 3" labels per `p1889` F5. Use descriptive names.

### 3. Update `design/architecture/harness-integration.md`

The "Launch composition" section currently says `launch/context.py:148-223` is "the single merge point." Rewrite in hexagonal terms:

- The domain core is `launch/context.py` (or successor); `build_launch_context()` is the factory.
- Adapters accept `NormalLaunchContext` (not the sum).
- Executors accept `LaunchContext` and pattern-match on the sum.
- `project_workspace()` is the adapter's translation step; R05 implements it per harness.

### 4. Small cross-cutting touches

- Update `design/refactors.md` R05's Why/Exit criteria to reference the R06 domain core explicitly in hexagonal terms: "R05 adds the `project_workspace()` adapter method per harness; the ordered-root computation lives in `launch/workspace.py` as a domain-core builder."
- Update any other docs that reference R06 invariants with the old "exactly one composition function" wording — use the new pattern-vocabulary wording.
- Address `p1889` F2 explicitly (R01/R02 vs R06 independence): add a dependency note in `refactors.md` preamble or D2. State that R01, R02, and R06 have no file-level overlap and can run in any order; the only ordering constraints are R01 → R02 and R06 → R05.
- Address `p1889` F4: SURF-1.e6's "launch warning lane" tension — either narrow SURF-1.e6 to "config show and doctor" (absent workspace has no launch-lane context) or add an explicit row to `surfacing-layer.md`'s spawn-time diagnostics for "absent with broken override reason." Pick one and encode it.
- Address `p1889` F6: R05's exit criteria should cite which R06 invariants it depends on. Add a one-liner.

### 5. Do NOT

- Demote R06 or reverse the prereq ordering. The user directive is firm: refactor first, make drift impossible via type system + import-graph + single-callsite checks.
- Invent new spec requirements beyond what exists. The spec leaves (CFG-1, WS-1, CTX-1, SURF-1, BOOT-1) are substantively done.
- Rewrite R01, R02, R03, R04, or R05 scope beyond the small touches above.
- Touch `requirements.md` or `design/spec/config-location.md` (pre-existing uncommitted changes that aren't yours).

### 6. Deliverable

Edit the design files in place. Validate `bash .agents/skills/tech-docs/scripts/check-md-links.sh .meridian/work/workspace-config-design` passes.

Produce a report summarizing what changed, structured as: (1) R06 new shape, (2) D17 new shape, (3) harness-integration.md changes, (4) cross-cutting touches per review findings F2/F4/F6. The orchestrator will then run a final reviewer pass before handoff to planning.

Do not commit.
