# Final Sweep — Workspace-Config Design

You are a @tech-writer. Land the final set of edits on the workspace-config design package before it hands off to `@impl-orchestrator`. This is the last writing pass — after you, the design is frozen and implementation begins.

The work splits into **design-level additions** (a new decision, a new refactor, an architecture update) and **mechanical traceability fixes**. Do them all in one pass.

## Source of truth for findings

Read these three review reports first. They contain the concrete findings and evidence you need:

- `.meridian/spawns/p1876/report.md` — consistency review (traceability, terminology, requirements vs decisions)
- `.meridian/spawns/p1877/report.md` — general review (codepath freshness, stale D16 symbols)
- `.meridian/spawns/p1878/report.md` — launch-seam exploration (evidence for the new R06 refactor)

All file:line citations for R06 come from the p1878 explorer report. Use them exactly.

## Design-level additions

### 1. New decision: D17 — Unify launch composition seam (Depth 1)

Add D17 to `.meridian/work/workspace-config-design/decisions.md` after D16, in the "Cross-cutting design calls" section. Follow the existing D-entry format (directive + rationale + rejected alternatives + risks).

Content:

- **Directive (2026-04-15):** Primary and spawn launch pipelines unify through a single composition seam before workspace projection is wired. `prepare_launch_context()` (or successor) becomes the sole composition point; the primary path delegates into it. Executors remain split (streaming runner vs PTY/Popen).

- **Rationale:** The `p1878` launch-seam exploration found four composition features already duplicated between `src/meridian/lib/launch/context.py` and `src/meridian/lib/launch/plan.py` + `src/meridian/lib/launch/process.py` + `src/meridian/lib/launch/command.py`: policy resolution, permission pipeline, `SpawnParams` construction, and child env building. Workspace projection would be the fifth. `dev-principles` mandates acting on structural findings in the active loop rather than deferring them.

- **Preserved divergences (branches, not flattening):**
  - `MERIDIAN_HARNESS_COMMAND` bypass (primary-only raw env inherit) becomes an explicit mode switch inside the shared seam.
  - Claude-in-Claude sub-worktree cwd logic (spawn-only) stays conditional on `SpawnParams` context.
  - PTY `os.execvpe` path (primary-only) remains in the primary executor, not the composition seam.
  - Primary's post-launch session-id extraction and `PrimarySessionMetadata` attach as an optional field on `LaunchContext`, not into the shared seam's control flow.

- **Rejected alternative — Depth 2 (shared projection merge point only):** Both pipelines would keep their composition and each call `harness.project_workspace(...)` at their own seam. Rejected because it leaves the four existing duplications growing and makes every future launch-touching feature pay a 2× implementation tax.

- **Rejected alternative — Depth 3 (narrow spec to spawn-only):** `CTX-1.u1` would apply only to spawned subagents; primary launches would not see workspace roots. Rejected because the primary user flow is launching meridian from a parent directory and wanting sibling-repo context there, same as in spawned agents.

- **Risks acknowledged:**
  - Mode-switch complexity for `MERIDIAN_HARNESS_COMMAND` — needs an explicit branch, not a silent override.
  - Two `RuntimeContext` types exist today (`src/meridian/lib/launch/context.py` and `src/meridian/lib/core/context.py`); R06 must unify them or the seam stays split at the type level.

- **Out of scope (future follow-up):** The four duplicated features beyond composition itself (Codex fork materialization, Claude session-accessibility symlinking — see `p1878` report Q5) stay duplicated. R06 unifies only the composition seam; those features are cleaned up in separate follow-up work items.

### 2. New refactor: R06 — Unify launch composition seam

Add R06 to `.meridian/work/workspace-config-design/design/refactors.md` after R05. It orders **before R05** in the implementation plan (prep refactors run first).

Follow the existing R-entry format (Type, Why, Scope with file:line citations, Exit criteria). Cite the explorer's line numbers exactly.

Content:

- **Type:** prep refactor (blocks R05).
- **Why:** Primary and spawn pipelines duplicate policy resolution, permission pipeline, `SpawnParams` build, `build_harness_child_env()` calls, and adapter `resolve_launch_spec()` usage. Four features already implemented twice (per `p1878` Q5). Unifying composition now keeps R05 targeting one seam and stops future launch-touching features from paying a 2× cost.
- **Scope:** use these exact citations from the p1878 report:
  - `src/meridian/lib/launch/context.py:148-223` — spawn-side `prepare_launch_context()` becomes the shared seam.
  - `src/meridian/lib/launch/plan.py:149` and `src/meridian/lib/launch/plan.py:343` — `resolve_primary_launch_plan()` delegates into the shared seam instead of duplicating its composition.
  - `src/meridian/lib/launch/process.py:273` and `src/meridian/lib/launch/process.py:325` — primary-side `run_harness_process()` consumes the unified `LaunchContext`.
  - `src/meridian/lib/launch/command.py:16` and `src/meridian/lib/launch/command.py:28` — `build_launch_env()` collapses into delegation to the shared seam's env construction.
  - `src/meridian/lib/launch/context.py:41` and `src/meridian/lib/core/context.py:13` — two `RuntimeContext` types unify into one.
- **Exit criteria:**
  - Single `prepare_launch_context()` (or successor) is the sole composition point consumed by both spawn and primary executors.
  - Both executors consume a single `LaunchContext` type.
  - `RuntimeContext` is a single type, not two.
  - `MERIDIAN_HARNESS_COMMAND` bypass lives as an explicit mode switch inside the shared seam, not as a parallel code path.
  - Preflight seam is reachable from primary path (was spawn-only before).
  - No duplicate calls to `resolve_policies()`, `resolve_permission_pipeline()`, `SpawnParams`-build, or `build_harness_child_env()` across the two pipelines.

### 3. Architecture update: A04 (harness-integration)

Update `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`:

- The "Launch composition" section currently describes `launch/context.py:148-223` as the single merge point. Keep that language, but add a note that post-R06 this *is* the single merge point for both pipelines. Remove any language that implies a split.
- Remove or update any phrasing that suggests primary launch is out of scope.
- Add a paragraph (near "Applicability Contract" or a new short section) defining `unsupported:harness_command_bypass` as the applicability value emitted when `MERIDIAN_HARNESS_COMMAND` is set on a primary launch. Surfacing layer (`../surfacing-layer.md`) already handles `unsupported:*` generically; just mention the new reason code.

Do not change the three per-harness subsections (Claude, Codex, OpenCode). The mechanism stays the same; only the seam description changes.

## Mechanical fixes

The p1876 consistency review enumerates each finding with a suggested fix. Apply all of them. Short list:

1. Add `SURF-1.e6` to `architecture/surfacing-layer.md` `## Realizes` list.
2. Add `WS-1.s1` to `architecture/workspace-model.md` `## Realizes` list.
3. Fix `spec/config-location.md` ↔ `architecture/surfacing-layer.md` asymmetric link. Either remove `surfacing-layer.md` from `Realized by:` in `config-location.md`, or add the relevant `CFG-1.*` IDs to A05's `Realizes:`. Recommendation: remove from `config-location.md`; A05 surfacing does not actually realize CFG leaves.
4. Fix `spec/surfacing.md` ↔ `architecture/config-loader.md` asymmetric link. Same pattern — remove `config-loader.md` from `Realized by:` in `surfacing.md` (A02 config-loader does not realize surfacing leaves).
5. Strike the migration-compatibility constraint in `requirements.md §Constraints` ("Must support incremental migration — old `.meridian/config.toml` continues to work during transition"). Replace with a short note that this constraint is superseded by D8 (2026-04-14 directive), and link to it.
6. Add a `§Scope boundaries` (or similar) section to `requirements.md` marking the two problem-statement items not addressed in this work item:
   - "Mars has no local state directory" — deferred to a future Mars-scoped work item.
   - "AGENTS.md hardcodes personal filesystem paths" — deferred; workspace file addresses the topology problem but AGENTS.md copy edits are separate.
7. Mark `feasibility.md §Open Questions` #2 (`[context-roots]` naming) with an explicit `**Status:** deferred` line at the top of that bullet.
8. Add a one-line "Includes former R04 scope" callout to the R01 header in `refactors.md` so the fold is visible when scanning headers. R04 stays as-is below, with its "folded into R01" note.
9. Standardize probe-evidence citation style across `decisions.md` and `feasibility.md`. Current style is mixed `§N` vs `Probe N`. Pick `§N` (matches existing decisions.md format) and update any `Probe N` references to match. Or inverse — pick one and apply consistently.
10. Update D16 in `decisions.md` to drop references to `supports_bidirectional` and `execute_with_finalization` (per p1877 LOW finding). Those symbols are gone from the tree. Replace with the current reality: all three harness bundles register only streaming connections; spawn execution unconditionally calls `execute_with_streaming`; env propagates through `inherit_child_env` → `create_subprocess_exec(..., env=env)`. Cite `src/meridian/lib/harness/claude.py:444`, `src/meridian/lib/harness/codex.py:500`, `src/meridian/lib/harness/opencode.py:310`, `src/meridian/lib/harness/connections/opencode_http.py:319`, `src/meridian/lib/launch/env.py:123` exactly as they appear in the p1877 report.

## Guardrails

- Preserve all other existing content. Only edit what these instructions name.
- Keep the existing writing voice: terse, observational, citation-dense.
- Do not renumber existing D/R/FV/OQ/CP identifiers.
- Do not introduce new EARS statements; only link existing ones where their realizing architecture leaf is missing.
- Use exact file:line citations from the three review reports. Don't paraphrase them.
- This is a documentation edit only. Do not touch any `src/` files.

## Verification before you finish

After editing:

- `rg "SURF-1.e6|WS-1.s1" .meridian/work/workspace-config-design/design/architecture/` must return at least one hit each in the `Realizes:` sections.
- `rg "supports_bidirectional|execute_with_finalization" .meridian/work/workspace-config-design/decisions.md` must return zero hits.
- `rg "incremental migration" .meridian/work/workspace-config-design/requirements.md` must return zero hits, or only inside a "superseded by D8" note.
- `rg "R06" .meridian/work/workspace-config-design/design/refactors.md .meridian/work/workspace-config-design/decisions.md` must return hits in both.
- `rg "D17" .meridian/work/workspace-config-design/decisions.md` must return at least one hit.

Report what you changed, grouped by file.
