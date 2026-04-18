# Architect Task — Targeted fixes to R06 + D17 after final review

## Context

`workspace-config-design` has been through four review rounds. The p1890 architect rewrote R06 + D17 around hexagonal (ports and adapters) framing. The final adversarial review (p1891 gpt-5.4 on invariant enforceability + p1892 opus on scope completeness) returned **request-changes** with converging findings.

**This is a targeted-fix task, not a rewrite.** The hexagonal framing is correct. The exit criteria shape is correct. Seven specific gaps need to close before the package is planner-ready. Do those, no more.

Read these first so you know what problems are being solved:
- `.meridian/spawns/p1891/report.md` — gpt-5.4, invariant-enforceability focus
- `.meridian/spawns/p1892/report.md` — opus, scope-completeness focus
- `.meridian/spawns/p1890/report.md` — the rewrite these reviews are critiquing

Then read the design state:
- `.meridian/work/workspace-config-design/design/refactors.md` (R05, R06)
- `.meridian/work/workspace-config-design/decisions.md` (D17)
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` (Launch composition section)

## The seven fixes

### Fix 1 — Add `run_streaming_spawn` as a 9th driving port (both reviewers, blocker/major)

`src/meridian/lib/launch/streaming_runner.py:389-420` has `run_streaming_spawn()`, called from `cli/streaming_serve.py:98`. It calls `adapter.resolve_launch_spec(params, perms)` directly. The design's current list of 8 ports is incomplete.

Action: add `launch/streaming_runner.py:389-420` (or whatever line range the function occupies; verify) as the 9th port in R06's driving-ports list. After R06, it receives `LaunchContext` from `build_launch_context()` instead of resolving spec itself. Update D17 scope-evolution section to mention this addition.

### Fix 2 — Rewrite `rg` gates to be actually mechanical (gpt blocker)

gpt verified the current exit-criteria `rg` patterns produce multiple hits on the live tree today and miss alternate composition shapes:
- `rg "resolve_policies\("` hits `launch/resolve.py`, `launch/plan.py`, `ops/spawn/prepare.py`
- `rg "resolve_permission_pipeline\("` hits `safety/permissions.py`, `launch/plan.py`, `ops/spawn/prepare.py`, `ops/spawn/execute.py`
- `rg "build_harness_child_env\("` hits `launch/context.py`, `launch/command.py`, plus the definition
- Direct permission-builder usage in `app/server.py`, `cli/streaming_serve.py`, `streaming/spawn_manager.py` wouldn't be caught
- `MERIDIAN_HARNESS_COMMAND` branches in `launch/plan.py:259-268` and `launch/command.py:53-57` have no guard

Action: replace the soft `rg` claims in R06's Exit Criteria with one of two honest forms:

**Option A (preferred):** definition-anchored patterns + "outside-core" guards. Example format:
- `rg "^def resolve_policies\(" src/` returns exactly one file (the domain-core implementation).
- `rg "resolve_policies\(" src/ --files-with-matches` returns only the domain-core module; zero matches in driving-port modules.
- `rg "MERIDIAN_HARNESS_COMMAND" src/` returns only the bypass branch inside `build_launch_context()`.

Specify the exact command and the exact expected result for each of: the four pipeline builders (`resolve_policies`, `resolve_permission_pipeline`, `build_env_plan`, `build_harness_child_env`), the factory (`build_launch_context`), the sum-type construction (`NormalLaunchContext(`, `BypassLaunchContext(`), and the bypass env check (`MERIDIAN_HARNESS_COMMAND`).

**Option B (honest softening):** if some checks are genuinely not `rg`-mechanical, label them "convention-enforced with CI-assist" rather than "impossible to drift." Don't overclaim.

Pick A where you can, B where you can't.

### Fix 3 — Plan Object: resolve the post-launch session-id tension + name exhaustiveness (gpt blocker)

Current R06 claims `LaunchContext` has "all fields required, frozen dataclasses, compile-checkable." But R06's "Preserved divergences" also says post-launch session-id is an optional field set after launch. That contradicts both "all required" and "frozen."

Reviewer's fix direction is correct: post-launch observation (session-id extraction at `launch/process.py:435-458`, `launch/streaming_runner.py:999-1022`) is executor *output*, not part of the immutable plan.

Action:
- Remove post-launch session-id from `LaunchContext`. Make it an executor-produced result value (e.g., `LaunchResult` or part of the existing post-launch update path). Update R06's "Preserved divergences" to state this clearly.
- State the exhaustiveness mechanism explicitly: executor dispatch uses Python `match` with `assert_never` (or equivalent) on the `NormalLaunchContext | BypassLaunchContext` union. Pyright (already 0-errors per CLAUDE.md) flags missing arms. Name this in the Plan Object exit criterion so a planner knows what "compile-checkable" means concretely.

### Fix 4 — Adapter invariant: distinguish abstract contracts from harness-specific modules (gpt major)

Current invariant: `rg "from meridian.lib.harness" src/meridian/lib/launch/` should go to zero. But `launch/` legitimately needs abstract adapter contracts like `ResolvedLaunchSpec`, `HarnessWorkspaceProjection`, the base adapter protocol. Today `launch/context.py`, `launch/resolve.py`, `launch/env.py`, `launch/plan.py`, `launch/process.py` all import harness-layer types — not all equally "harness-specific."

Action: rewrite the adapter invariant to name the boundary precisely. Example shape:
- Abstract harness contracts live in `src/meridian/lib/harness/adapter.py` (or a new `harness/contracts.py` if separation is preferred). The domain core may import from this module.
- Harness-specific implementations live in `src/meridian/lib/harness/{claude,codex,opencode,projections}/`. The domain core may not import from these.
- CI check: `rg "from meridian.lib.harness.(claude|codex|opencode|projections)" src/meridian/lib/launch/` returns zero.

If `adapter.py` doesn't cleanly contain only abstract contracts today, name the R06 task of extracting them (or accept the current boundary and tighten the check accordingly).

### Fix 5 — Fork continuation: stop claiming it's executor-produced (opus major)

R06's "Preserved divergences" says "Codex fork continuation state is a separate value produced by the executor, not a mutation of `LaunchContext`." D17 repeats this. Code contradicts both:
- `launch/process.py:68-104` (`_resolve_command_and_session`) calls `fork_session()`, creates a new `run_params` via `model_copy`, rebuilds command via `adapter.build_command()`. Pre-execution.
- `ops/spawn/prepare.py:296-311` does the same thing during `prepare_spawn_plan()`. Pre-execution.

Action: pick one and make the design match code reality:

**Option A (absorb):** add `materialize_fork()` as a pipeline stage in the domain core, post-spec-resolution, pre-env. R06 delivers this consolidation. Fork materialization becomes a 5th composition concern tracked by the pipeline invariant. Update R06 scope, exit criteria, and "Preserved divergences" accordingly.

**Option B (honest divergence):** remove fork from "Preserved divergences" altogether. Add it as a recognized remaining composition concern with its own follow-up refactor after R06. Explicitly state the invariant weakening: "one composition concern (fork materialization) is not consolidated in R06 and remains duplicated across the two pre-execution sites above. This is not a blocker for R05 because fork materialization does not affect workspace projection inputs."

Pick A if fork cleanly factors into the pipeline. Pick B if it doesn't (e.g., fork depends on session state resolved differently on primary vs spawn paths). Verify against code before choosing.

### Fix 6 — `BypassLaunchContext` fields + branching order (opus minor, raise to major)

Current claim: "raw argv/env for MERIDIAN_HARNESS_COMMAND and nothing else." Code does partial composition before branching (`plan.py:167` policies, session resolution) and calls `inherit_child_env` (not `build_harness_child_env`) at `command.py:53-56`. The frozen dataclass needs concrete fields.

Action: specify `BypassLaunchContext` fields explicitly in R06 or D17. Minimum realistic set (verify against code):
- `argv: tuple[str, ...]` — raw command
- `env: Mapping[str, str]` — result of `inherit_child_env` (not `build_harness_child_env`)
- `cwd: Path` — execution cwd
- Plus: anything else the bypass path actually needs (session id if applicable, runtime context, etc.)

State the branching order: `build_launch_context()` runs policy resolution and session resolution first, then checks `MERIDIAN_HARNESS_COMMAND` and returns `BypassLaunchContext` (skipping adapter spec resolution, env shaping, workspace projection). Correct the "nothing else" phrasing.

### Fix 7 — Suggested internal phasing for R06 (opus minor)

R06 is realistically four coupled sub-refactors: (1) RuntimeContext unification, (2) domain-core pipeline + LaunchContext sum type, (3) driving-port rewiring (9 ports, incrementally), (4) bypass absorption. Exit criteria are all-or-nothing (correct for end state, useless for planning).

Action: add a "Suggested internal phasing" paragraph to R06. Don't prescribe commits — just name the natural internal ordering so a planner can schedule intermediate milestones. One paragraph is enough. Example:

> R06 naturally decomposes into: (1) RuntimeContext unification (no behavioral change, standalone); (2) domain-core pipeline + `LaunchContext` sum type (structural prerequisite); (3) driving-port rewiring, one port per commit; (4) bypass absorption into the factory. Each intermediate state satisfies a subset of the exit criteria. Order (1) → (2) → (3) → (4) is one viable phasing; (1) and (2) can proceed independently.

### Also: converging `run_streaming_spawn` + `streaming_serve.py:85` permission composition

gpt and opus both flagged that `streaming_serve.py:85` constructs `TieredPermissionResolver(config=PermissionConfig())` directly. This is covered partly by Fix 1 (routing `run_streaming_spawn` through the factory) and partly by the driving-ports invariant from Fix 2 (the factory must do permission resolution; ports must not).

Make sure the fixed exit criteria and driving-ports list cover this case. Specifically: if the factory takes a pre-resolved `PermissionResolver`, document that `streaming_serve.py` must construct its `PermissionConfig` and let the factory resolve — not hand in a pre-built resolver. Or if the factory accepts a resolver as input, document when that's legitimate. Pick one and state it.

## Do NOT

- Rewrite anything else. Don't touch `requirements.md`, `config-location.md`, R01, R02, R03, R04, D18.
- Demote R06 or change ordering. Firm directive: refactor first.
- Invent new spec requirements.
- Change R05 scope beyond what Fix 1 propagates (R05 still has one insertion point IF Fix 1 lands).
- Re-open settled decisions (D18 relative-override, D17 prereq ordering, hexagonal framing).

## Deliverable

Edit the design files in place. Files you'll touch (verify, don't just assume):
1. `design/refactors.md` — R06 driving-ports list (Fix 1), exit criteria (Fix 2, 3, 4), Preserved divergences (Fix 3, 5), BypassLaunchContext fields (Fix 6), phasing paragraph (Fix 7)
2. `decisions.md` — D17 scope-evolution update for Fix 1, post-launch session-id clarification for Fix 3, fork treatment for Fix 5
3. `design/architecture/harness-integration.md` — only if Fix 1 or Fix 4 changes the integration contract wording

Validate `bash .agents/skills/tech-docs/scripts/check-md-links.sh .meridian/work/workspace-config-design` passes.

Produce a report structured as: one short paragraph per fix (1-7) naming what changed and where. No prose expansion; terse is better. End with a "Verification" line confirming link check passed and nothing outside the scoped fix list was touched.

Do not commit.
