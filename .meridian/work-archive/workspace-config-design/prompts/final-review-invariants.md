# Final Adversarial Review — Hexagonal Invariant Enforceability

## Context

`workspace-config-design` has been through three review rounds. The latest rewrite (p1890) reframed R06 from "exactly one composition function" (overclaimed) to a hexagonal (ports and adapters) architecture with three pattern-level invariants:

1. **Pipeline** — one builder per composition concern, `rg`-checkable
2. **Plan Object** — `LaunchContext = NormalLaunchContext | BypassLaunchContext` sum type, compile-checkable
3. **Adapter** — domain core has no harness imports, import-graph-checkable

Plus a **driving-ports invariant**: every launch-initiating port must call `build_launch_context()` and must not resolve policies, build env, or construct `LaunchContext` directly. Ports are allowed to construct `SpawnParams`.

Prior review history:
- `.meridian/spawns/p1882/report.md` (gpt) + `.meridian/spawns/p1883/report.md` (opus): round 1 — found original R06 overclaimed
- `.meridian/spawns/p1888/report.md` (gpt) + `.meridian/spawns/p1889/report.md` (opus): round 2 — found grown R06 still missed facade sites
- `.meridian/spawns/p1890/report.md`: architect rewrite around hexagonal framing

## Your task — adversarial review, invariant enforceability focus

You are the **mechanism check** reviewer. Your job is to stress-test whether the three hexagonal invariants are **genuinely mechanically enforceable** — not just aspirationally stated.

Specific questions to pressure-test:

1. **Pipeline invariant** — "one builder per concern, `rg`-checkable." Pull up the actual `rg` commands in R06's exit criteria. Run them (or mentally simulate them against current `src/`). Do they actually return exactly one match each? Are there aliases, re-exports, or call shapes that would produce false positives/negatives? Would a coder see a green CI signal while violating the invariant?

2. **Plan Object invariant** — "exactly one `LaunchContext` sum type, all fields required, compile-checkable." Can the Python type system actually enforce this? `NormalLaunchContext | BypassLaunchContext` is a union; pattern match coverage relies on `match`/`assert_never` or similar. Is that stated? Does any current code path produce a partial `LaunchContext` that would defeat the "all fields required" claim? What about optional fields like the post-launch session-id extraction — are those scoped out cleanly?

3. **Adapter invariant** — "domain core has no harness-specific imports." Is there a concrete check command (e.g. `rg "from meridian.lib.harness" src/meridian/lib/launch/`)? Is the module boundary actually clean, or does `launch/` already depend on `harness/` types (e.g. `ResolvedLaunchSpec`)? If the latter, the invariant needs wording that distinguishes abstract contracts from harness-specific modules.

4. **Driving-ports invariant** — "every port calls `build_launch_context()`, doesn't resolve." Are all 8 listed ports in scope (`app/server.py:333`, `streaming/spawn_manager.py:197`, `cli/streaming_serve.py:80`, `ops/spawn/execute.py:861`, `ops/spawn/prepare.py:202,323`, `launch/plan.py`, `launch/process.py`, `launch/command.py`)? Does any unlisted site construct `SpawnParams` or call `resolve_policies`/`resolve_permission_pipeline`/`build_harness_child_env` from outside the domain core today? The round-2 reviewers found R06 missed sites twice — is the list now complete?

5. **Bypass handling** — `BypassLaunchContext` is claimed to handle `MERIDIAN_HARNESS_COMMAND`. Does the current bypass logic actually live in a single branch that can be absorbed into the builder, or is it scattered? Could the bypass branch leak back into executors despite the invariant?

6. **Overclaim check** — the prior two review rounds found overclaims. Is there any remaining "impossible to drift" language that a planner would take as mechanically guaranteed but is only aspirationally true?

Read the following files before reviewing:
- `.meridian/work/workspace-config-design/design/refactors.md` (R06 specifically)
- `.meridian/work/workspace-config-design/decisions.md` (D17 specifically)
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` (Launch composition section)
- `.meridian/spawns/p1890/report.md` (what changed)
- `.meridian/spawns/p1888/report.md`, `.meridian/spawns/p1889/report.md` (what the previous round found)
- Probe live code under `src/meridian/lib/launch/`, `src/meridian/lib/ops/spawn/`, `src/meridian/lib/app/server.py`, `src/meridian/lib/streaming/spawn_manager.py`, `src/meridian/lib/cli/streaming_serve.py` as needed

## Report format

- Findings as **Blocker / Major / Minor** with file:line references to the design docs and any live-code evidence.
- End with a **Verdict**: approve / approve-with-minor-fixes / request-changes.
- Be adversarial. If something is soft-stated ("will be checkable", "should return one match"), challenge whether it actually is.
- Don't rehash what the prior reviewers found — focus on what **this rewrite** introduced or failed to address.
