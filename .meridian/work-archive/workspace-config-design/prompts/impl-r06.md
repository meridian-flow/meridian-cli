# Impl-Orchestrator Task — Execute R06 (Consolidate launch composition into a hexagonal core)

## Context

`workspace-config-design`'s design is complete and approved (work status: "design complete, ready for planning", committed at `b325ac8`). The full design package is at `.meridian/work/workspace-config-design/`.

**Your scope is R06 only.** R06 is the prerequisite refactor that establishes the hexagonal launch core. R05 (workspace projection) depends on R06 and is out of scope for this orchestrator — a separate impl-orchestrator will pick it up after R06 merges. R01, R02, R03 are also separate chains scheduled after R06 lands.

Do not begin R05. Do not begin R01–R03. Ship R06 only.

## Source of truth

Read these first:
- `.meridian/work/workspace-config-design/design/refactors.md` — R06 full scope, exit criteria, suggested internal phasing, test blast radius.
- `.meridian/work/workspace-config-design/decisions.md` — D17 (hexagonal launch core, architectural reasons for 3 driving adapters).
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` — Launch composition section + Session-ID observation section.

If you need the prior review context for why the design landed where it did:
- `.meridian/spawns/p1894/report.md` (3-site framing rewrite)
- `.meridian/spawns/p1898/report.md` (honesty pass + session-ID adapter seam)
- `.meridian/spawns/p1899/report.md` (final spot-check; request-changes already resolved)

## What R06 delivers

Summary (authoritative version in `refactors.md`):

1. **Domain core** — `build_launch_context()` factory; one builder per composition concern (`resolve_policies`, `resolve_permission_pipeline`, `materialize_fork`, `build_env_plan`, plus adapter-owned `resolve_launch_spec`); `LaunchContext = NormalLaunchContext | BypassLaunchContext` frozen dataclass sum type.
2. **3 driving adapters** route through the factory — primary launch, background worker, app streaming HTTP. Dry-run is a 4th factory caller (preview, no executor).
3. **Type split** — `SpawnRequest` (user-facing args) vs. `SpawnParams` (resolved execution inputs). Driving adapters see `SpawnRequest`; only the factory sees `SpawnParams`.
4. **`observe_session_id()` adapter seam** — session-ID moves off `LaunchContext` onto `LaunchResult`, observed post-execution by the harness adapter. Current scrape/parse mechanisms relocate behind this method unchanged. Issue #34 tracks the filesystem-polling mechanism swap (out of scope here).
5. **Deletions** — `launch/streaming_runner.py:run_streaming_spawn` + `SpawnManager.start_spawn` unsafe-resolver fallback.
6. **`MERIDIAN_HARNESS_COMMAND` bypass** absorbed into factory as a `BypassLaunchContext` return path.
7. **CI invariants script** — `scripts/check-launch-invariants.sh` + `.github/workflows/meridian-ci.yml` job. Runs `rg` patterns from exit criteria; exits nonzero on drift.
8. **Pyright hardening** — ban `pyright: ignore` and `cast(Any,` in `src/meridian/lib/launch/` and `src/meridian/lib/ops/spawn/` modules. Require `match` + `assert_never` for executor dispatch on `LaunchContext` union.

## Suggested internal phasing (from the design)

The design decomposes R06 into 8 phases with natural ordering. Use this as your planning baseline; the planner may refine.

1. `SpawnRequest`/`SpawnParams` split (DTO, no behavior change).
2. `RuntimeContext` unification (standalone, no behavior change).
3. Domain-core pipeline + `LaunchContext` sum type + `build_launch_context()` factory.
4. Rewire primary launch to call factory.
5. Rewire background worker to call factory.
6. Rewire app streaming HTTP to call factory.
7. Delete `run_streaming_spawn` + `SpawnManager.start_spawn` fallback.
8. Absorb `MERIDIAN_HARNESS_COMMAND` bypass into factory.

`observe_session_id()` adapter seam and CI invariants script land as part of phases 3 + (3/4/5/6 respectively). Pyright hardening lands in phase 3 + whenever executor dispatch is introduced.

Each phase should be a committable, testable, reviewable unit. Commit after each phase passes tests per CLAUDE.md.

## Working tree state

Working tree is clean. HEAD is at `b325ac8` (design close-out). 4 commits ahead of origin/main:
- `b325ac8 work: close workspace-config-design → ready for planning`
- `122fb9a chore: primary agent config + mars-dev-workflow v0.0.24 bump`
- `0259dc9 work: add managed-readonly-allowlist-parity design scaffolding`
- `07cbd66 work: add windows-port-research phase-4 probes`

## Guardrails

- **No user real data.** Per CLAUDE.md: "No real users, no real user data. No backwards compatibility needed — completely change the schema to get it right." Break schemas freely; do not add backwards-compat shims.
- **Testing.** Prefer smoke tests (`tests/smoke/`) over unit tests. Unit tests only for genuinely hard-to-smoke behavior (concurrency, env sanitization, parsing edge cases). Do not proliferate unit tests for a refactor whose behavior should be invariant.
- **Type checking.** `uv run pyright` must be 0 errors. `uv run ruff check .` clean. `uv run pytest-llm` passes.
- **Do not write new files gratuitously.** Prefer editing existing files.
- **Do not skip CI hooks** unless explicitly asked.
- **Do not delete untracked files** without asking.

## Strong model signals

Per CLAUDE.md: prefer **gpt-5.3-codex** as the primary code implementer. Use **opus** for documentation-heavy subtasks. Fan out reviewers across gpt-5.4 / gpt-5.2 / opus with different focus areas; don't send all reviewers to one model.

For consistency checks (mechanical lookups), prefer cheap models (haiku or gpt-5.2-mini), not opus.

## Deliverable

One shipped R06 refactor. All 8 phases merged into main via phase-commits, all exit criteria from `refactors.md` R06 satisfied, CI green.

At the end, the work item `workspace-config-design` stays in "design complete, ready for planning" until R05, R01-R03 also land (separate orchestrators). But R06 itself is done.

Return a final report summarizing phase-by-phase what shipped, which exit criteria now hold (with the `rg` verification output), and any design drift discovered during implementation that needs a back-note in the design docs.
