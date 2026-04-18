# Final Adversarial Review — R06 Scope Completeness + Drift Risk

## Context

`workspace-config-design` has been through three review rounds. The latest rewrite (p1890) reframed R06 from "exactly one composition function" (overclaimed) to a hexagonal (ports and adapters) architecture:

- **Domain core** — pure builders + `LaunchContext` sum type + `build_launch_context()` factory
- **Driving ports** — 8 entrypoints listed: `app/server.py:333`, `streaming/spawn_manager.py:197`, `cli/streaming_serve.py:80`, `ops/spawn/execute.py:861`, `ops/spawn/prepare.py:202,323`, `launch/plan.py`, `launch/process.py`, `launch/command.py`. Each allowed to construct `SpawnParams`; must call `build_launch_context()` and not resolve independently.
- **Driven adapters** — harness adapters receive `NormalLaunchContext`, produce harness-specific output
- **Executors** — PTY execvpe + async subprocess_exec, pattern-match on the sum

Prior review history:
- `.meridian/spawns/p1882/report.md` (gpt) + `.meridian/spawns/p1883/report.md` (opus): round 1 — found R06 overclaimed
- `.meridian/spawns/p1888/report.md` (gpt) + `.meridian/spawns/p1889/report.md` (opus): round 2 — found R06 still missed composition sites (exactly what p1890 then broadened)
- `.meridian/spawns/p1890/report.md`: architect rewrite

**Round 2 repeatedly found the port list incomplete. This round's core question: is it complete now?**

## Your task — adversarial review, scope-completeness focus

You are the **coverage check** reviewer. Your job is to verify R06 as scoped actually delivers what it promises, and to find remaining drift risk that would land on R05 or future launch-touching work.

Specific questions to pressure-test:

1. **Port list completeness** — Sweep `src/meridian/lib/` for every site that today: (a) calls `resolve_launch_spec`, `resolve_policies`, `resolve_permission_pipeline`, or builds env; or (b) constructs `SpawnParams`, `PreparedSpawnPlan`, or equivalent launch-intermediate types; or (c) invokes `asyncio.create_subprocess_exec`, `os.execvpe`, or PTY spawning with harness-derived argv/env. Does every such site appear in R06's driving-ports list as either "routes through core" or "executor"? Name any that are missing.

2. **R05 insertion point** — R05 promises exactly one `project_workspace()` insertion inside `build_launch_context()`. Does R06's pipeline definition actually give R05 one insertion point, or would R05 still have to touch multiple places? Walk through what an R05 diff would look like post-R06 and see if it's really a single-point change.

3. **Fork continuation** — round 2 (p1888) flagged Codex fork materialization as an unresolved contradiction: duplicated across `launch/process.py:68` and `ops/spawn/prepare.py:297`, both mutating continuation state and rebuilding launch inputs after the supposed single seam. Did p1890 address this, or is it still post-seam recomposition that breaks the "one plan" claim? Check `refactors.md` "Preserved divergences" section — fork state is claimed to be an executor-produced value, not a LaunchContext mutation. Is that actually true in code today, or is it aspirational?

4. **Primary-launch bypass path** — `MERIDIAN_HARNESS_COMMAND` is handled by `BypassLaunchContext`. Current code branches this at `launch/process.py` early-return. Does absorbing it into the builder actually work, or does the early-return carry execution-path implications (e.g., cwd handling, env inheritance) that don't cleanly factor into a frozen dataclass?

5. **Drift-after-R06 risk** — if a future contributor adds a 9th launch site (e.g., a new CLI subcommand, a new HTTP endpoint, a new streaming path), what mechanism prevents them from composing independently? Is the "must call `build_launch_context()`" invariant enforced by anything other than documentation + review? If it's only documentation, R06's "impossible to drift" promise is still aspirational — name that explicitly.

6. **Blast radius for R06 itself** — R06 is scoped as a prereq refactor. How big is it realistically? 8 ports + domain core consolidation + sum-type introduction + fork extraction + bypass absorption — is this one refactor or four? Would a planner split it? If so, does the design give them the dependency ordering to do that safely?

7. **R05 dependency statement** — p1889 F6 asked R05 to cite which R06 invariants it depends on. Check R05's Why section — does it actually name the specific invariants (one `build_launch_context()`, one `LaunchContext` sum, no composition in driving ports), or does it just say "depends on R06"?

Read the following files before reviewing:
- `.meridian/work/workspace-config-design/design/refactors.md` (R05 and R06)
- `.meridian/work/workspace-config-design/decisions.md` (D17)
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`
- `.meridian/spawns/p1890/report.md`
- `.meridian/spawns/p1888/report.md`, `.meridian/spawns/p1889/report.md`
- Probe live code under `src/meridian/lib/` broadly to verify port list completeness — don't trust the design's list, verify it

## Report format

- Findings as **Blocker / Major / Minor** with file:line references.
- End with a **Verdict**: approve / approve-with-minor-fixes / request-changes.
- Be adversarial — the prior two rounds found scope gaps; assume the third rewrite might still miss something.
- Do your own `rg` sweeps. The design's enumeration is the claim under test, not the evidence.
