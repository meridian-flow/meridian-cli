# Session Report - 5384f4e7-4a8a-4e14-9c19-9fc8128858fe

Session arc: spawn-control-plane redesign -> dead-code sweep / auth deletion -> finalize-path fixes -> config cleanup.

## Work Items Touched

- `spawn-control-plane-redesign`
  - Created, reviewed, respun, and cleaned up.
  - End state: design package converged, review drift closed, work archived.
- `dead-code-sweep`
  - Created to delete the auth feature and other retired surfaces.
  - End state: auth deleted, dead-code purge committed, smoke retest surfaced the surviving finalize bugs, work archived.
- `spawn-finalize-bugs`
  - Created from the smoke-retest survivors.
  - End state: B-01..B-05 fixed, app-path finalize fixed, timeout default bumped, default-agent config removed.
  - At session close this item was effectively done and ready to archive, but the transcript ended before the archive step.
- `workspace-config-design`
  - Background design work surfaced in the same session context and was finalized during the overall review/fix cycle.
- `spawn-lifecycle-docs-update`
  - Docs mirror + user-facing docs updated after the finalize refactor.

## Commits Made

| SHA | Message | What changed |
|---|---|---|
| `f6d9f20` | `feat(state): phase-1 reaper hardening + runner heartbeat (issue #14 PR1)` | Started the #14 hardening pass with reaper/heartbeat changes. |
| `42c185b` | `feat(core): phase-2 finalizing lifecycle foundation (issue #14 PR2)` | Added the `finalizing` lifecycle base and transition groundwork. |
| `d431085` | `feat(state,cli): phase-3+4 origin tagging, projection authority, CLI surface (issue #14 PR2)` | Added origin-aware finalization and the new CLI-facing projection rules. |
| `809f004` | `feat(state,launch): phase-5 finalizing CAS + reconciler admissibility (issue #14 PR2 closure)` | Added CAS-based finalization flow and reconciler admissibility checks. |
| `27d5237` | `fix(state,launch): final-review findings - spec compliance, crash safety, pid guard (issue #14)` | Closed the final review issues on spec compliance, crash safety, and PID reuse guard. |
| `42f9797` | `docs(fs): update spawn-lifecycle mirror for finalizing + authority refactor` | Updated the fs-facing mirror for the lifecycle/origin refactor. |
| `876d04f` | `docs: add finalizing status + orphan_finalization for spawn-lifecycle refactor` | Updated user-facing docs for the new terminal states and orphan labeling. |
| `20da31b` | `docs: changelog for spawn-lifecycle + reaper refactor (issue #14)` | Added the issue #14 / lifecycle refactor notes to the changelog. |
| `943ae7d` | `design(spawn-control-plane): archive rejected iteration before redesign` | Archived the rejected control-plane iteration before the respin. |
| `8d3b96f` | `design(spawn-control-plane): capture v1 review feedback for v2 respin` | Preserved v1 review findings to drive the v2 respin. |
| `634f322` | `design(spawn-control-plane): v2r2 + cleanup pass converged` | Marked the v2r2 design package converged after the cleanup round. |
| `c533d47` | `Phase 1: Foundation primitives for spawn control plane redesign` | Started the spawn control-plane redesign package. |
| `63faefa` | `Round 2: Transport+Auth (R-10/R-08), Interrupt classifier (R-04), Liveness (R-07)` | Advanced the transport/auth and interrupt/liveness leaves. |
| `1239ded` | `Phase 5: Cancel core - SignalCanceller with two-lane dispatch (R-03, R-06)` | Landed the cancel-core shape and two-lane dispatch concept. |
| `1c400b6` | `Phase 6: HTTP surface convergence - cancel endpoint, inject parity, cross-process bridge (R-05, R-09)` | Converged the HTTP surface and cross-process bridge. |
| `64ce2f9` | `Fix review findings: WS auth gap and cancel 404 ordering` | Closed the first round of review nits. |
| `a721c6c` | `work(dead-code-sweep): capture scope - auth deletion + dead code + smoke retest` | Opened the dead-code sweep work item. |
| `9bb4ce9` | `Add dead-code-sweep execution plan` | Added the sweep execution plan. |
| `da59ccd` | `Delete authorization feature and remove cancel from MCP surface` | Removed the auth feature and the cancel MCP surface. |
| `f0a89d5` | `Remove dead state/schema ballast and rename missing_worker_pid` | Scrubbed dead state/schema leftovers and renamed the stale error label. |
| `9da11ae` | `Remove retired compat shims and verified orphaned modules` | Deleted additional retired shims and dead modules. |
| `f77b723` | `Update dead-code-sweep status and decisions after smoke retest` | Recorded the smoke-retest outcome and surviving failures. |
| `dae251f` | `work(spawn-finalize-bugs): capture scope + surviving bugs from sweep retest` | Converted the smoke survivors into the next work item. |
| `983b9bd` | `work(spawn-finalize-bugs): investigations + research converge on fix plan` | Consolidated the investigations into a concrete fix plan. |
| `889e3e1` | `design(workspace-config): finalize package after redesign round` | Finalized the workspace-config design package that was referenced during the regressions. |
| `cfefbcd` | `Fix spawn finalize-path bugs (B-01..B-05)` | Fixed the initial finalize-path bugs and removed the report-create command. |
| `1bed682` | `deps: fold [app] extras into base dependencies` | Moved app extras into the base install path. |
| `cf213c2` | `config: bump wait_timeout_minutes default 30->120` | Increased the default wait timeout for long-running orchestrations. |
| `da075e8` | `work(spawn-finalize-bugs): cycle 2 scope - app-path fix + one-way executor deletion` | Scoped the second cycle to app-path finalize and executor deletion. |
| `a5b128e` | `Fix app-path spawn finalize + delete one-way executor` | Fixed the app-path finalize path and deleted the one-way executor. |
| `88fd361` | `Remove primary/default agent config defaults and run profile-less when -a is omitted` | Removed the implicit default-agent fallback and changed `spawn` to run profile-less when no agent is specified. |

## Spawns Dispatched

| ID | Description | Outcome |
|---|---|---|
| `p1789-p1792` | Initial v2 design-review fanout for `spawn-control-plane-redesign` | Completed; surfaced the first blocker set and forced the v2r2 respin. |
| `p1793` | `Spawn control plane v2 (redesign cycle 1)` | Succeeded; the design package was completed and ready for planning. |
| `p1794` | `v2 design alignment review` | Succeeded; found app-managed-cancel and auth-fallback blockers. |
| `p1795` | `v2 adversarial correctness review` | Succeeded; found the SIGTERM contract, finalizing race, peercred, and inject-ordering blockers. |
| `p1796` | `v2 structural/refactor review` | Succeeded; structural review lane completed. |
| `p1797` | `v2r2 behavioral correctness review (gpt-5.4)` | Succeeded; still requested changes for HTTP-contract and macOS fallback drift. |
| `p1798` | `v2r2 structural soundness review (opus)` | Succeeded; approved with notes, no structural blockers. |
| `p1799` | `v2r2 cleanup: close remaining drift items` | Failed/orphan_run, but the cleanup edits landed and the drift was closed. |
| `p1772` | `Update fs/ + docs/ for spawn-lifecycle refactor` | Succeeded; docs shipped in two commits. |
| `p1773-p1781` | fs/docs write-review-fix-reverify loop under `p1772` | Succeeded; writers, reviewers, fix spawns, and reverify closed the doc drift. |
| `p1818-p1820` | Dead-code sweep inventory + review fanout | Succeeded; produced the auth-delete and dead-code purge scope. |
| `p1821` | `Smoke: two-lane cancel + interrupt semantics` | Succeeded; mostly red and exposed live cancel/auth/ordering bugs. |
| `p1822` | `Smoke: AF_UNIX transport + auth + app liveness` | Succeeded; AF_UNIX passed, auth and app liveness failed. |
| `p1851` | `Fix spawn finalize-path bugs (B-01..B-05)` | Succeeded; source finalize-path bugs fixed. |
| `p1857` | `Verify B-01/B-03 against uv run meridian (source)` | Cancelled/terminated after reporting residual app-path bugs. |
| `p1858` | `Verify B-01/B-03 on Claude + OpenCode app spawns` | Succeeded; fed the cycle-2 rework and confirmed app-path follow-up was needed. |
| `p1861` | `Cycle 2: App-path finalize + one-way executor deletion` | Succeeded; app-path finalize was fixed and the one-way executor was deleted. |
| `p1862-p1867` | Cycle-2 internal subspawns for phase work, verify, smoke, fix, and re-smoke | Succeeded overall; the cycle converged after the drain-loop break fix. |
| `p1868` | `Investigate B-06: spawn wait returns before target finalizes` | Succeeded; concluded the failure was caller-side timeout masking, not a Meridian wait bug. |
| `p1872` | `Remove primary_agent + default_agent config` | Succeeded; the no-agent / profile-less path was kept as the default. |

## Key Decisions

- The session kept returning to the same structural call: add a real `finalizing` state, then make every reconciler honor it. The clean fix came from the investigation, not from trying to patch around the symptom.
- User rejected a patch-only approach and pushed the full refactor. The most important quote was: "if we need to refactor, we should refactor. I don't want dead code or patchy stuff that is not good code."
- Auth was deleted rather than hardened. The user made that explicit: "we dont need 'auth'." The implementation followed that direction and removed the feature and the cancel surface instead of trying to salvage the guard.
- B-06 turned out to be self-inflicted. The key lesson was that `| tail -3` masked the `wait` timeout exit code, so the apparent early completion was a shell/pipeline artifact, not a Meridian state bug.
- The app-path finalize bug needed a different fix shape from the CLI path. The cycle-2 decision was to make the drain loop observe terminal events, break on them, and default to `failed` when no terminal event is seen.
- The default-agent config was removed instead of being turned into another hidden fallback. The user said: "we should just not have primary agent and default agent", and the final commit made `spawn` run profile-less when `-a` is omitted.
- The docs pass used the same write/review/fix discipline as the code pass. That was deliberate after the earlier docs review caught ordering mistakes.

## Files Changed Across The Session

- State and reconciliation: `src/meridian/lib/state/reaper.py`, `src/meridian/lib/state/spawn_store.py`, `src/meridian/lib/state/liveness.py`
- Launch/runtime: `src/meridian/lib/launch/runner.py`, `src/meridian/lib/launch/streaming_runner.py`, `src/meridian/lib/launch/resolve.py`, `src/meridian/lib/launch/plan.py`, `src/meridian/lib/launch/default_agent_policy.py` deleted
- Streaming / spawn execution: `src/meridian/lib/streaming/spawn_manager.py`, `src/meridian/lib/streaming/control_socket.py`, `src/meridian/lib/streaming/signal_canceller.py`, `src/meridian/lib/streaming/types.py`
- App surface: `src/meridian/lib/app/server.py`, `src/meridian/lib/app/ws_endpoint.py`, `src/meridian/cli/app_cmd.py`
- Core / config / lifecycle: `src/meridian/lib/core/spawn_lifecycle.py`, `src/meridian/lib/core/domain.py`, `src/meridian/lib/core/overrides.py`, `src/meridian/lib/core/context.py`, `src/meridian/lib/config/settings.py`
- Ops / spawn surface: `src/meridian/lib/ops/spawn/api.py`, `src/meridian/lib/ops/spawn/models.py`, `src/meridian/lib/ops/spawn/prepare.py`, `src/meridian/lib/ops/config.py`, `src/meridian/lib/ops/diag.py`
- Harness layer: `src/meridian/lib/harness/adapter.py`, `src/meridian/lib/harness/claude.py`, `src/meridian/lib/harness/codex.py`, `src/meridian/lib/harness/opencode.py`, `src/meridian/lib/harness/connections/__init__.py`, `src/meridian/lib/harness/launch_spec.py`
- Docs and changelog: `docs/_internal/ARCHITECTURE.md`, `docs/configuration.md`, `docs/troubleshooting.md`, `docs/mcp-tools.md`, `docs/commands.md`, `CHANGELOG.md`
- Tests: `tests/test_state/test_reaper.py`, `tests/test_state/test_spawn_store.py`, `tests/test_state/test_liveness.py`, `tests/ops/test_spawn_api.py`, `tests/ops/test_spawn_read_reconcile.py`, `tests/exec/test_lifecycle.py`, `tests/exec/test_streaming_runner.py`, `tests/test_launch_resolution.py`, `tests/test_overrides_convention.py`, `tests/ops/test_diag.py`, and multiple smoke guides under `tests/smoke/spawn/`
- Work artifacts: `.meridian/work/spawn-control-plane-redesign/`, `.meridian/work/dead-code-sweep/`, `.meridian/work/spawn-finalize-bugs/`, and the archived counterparts under `.meridian/work-archive/`

## Open Follow-Ups At Close

- Sibling prompt/skill repo cleanup still flagged as useful: the session called out a `.agents/` skill source update for the spawn/report docs, even though the generated mirror had already moved on in some places.
- Optional verification: a dedicated Claude SIGKILL smoke was still considered worthwhile even though the code path was structurally covered by the default-failed fallback.
- The session ended with `spawn-finalize-bugs` effectively complete, but the archive step itself was not shown in the transcript.

## Doc Debt Candidates

| Change | Likely stale refs | Suggested fix |
|---|---|---|
| Removed implicit default primary/default agent behavior; `spawn` now runs profile-less when `-a` is omitted | [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/configuration.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/configuration.md) still lists `defaults.primary_agent`; the same file still teaches a default wait/agent model that no longer matches the runtime | Remove `defaults.primary_agent` from the table, explain profile-less default behavior, and update any examples that imply hidden primary-agent fallback. |
| `wait_timeout_minutes` default changed from 30 to 120 | [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/configuration.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/configuration.md) still says `timeouts.wait_minutes = 30` | Update the timeout table and any guidance that says `spawn wait` is a 30-minute ceiling. |
| New `finalizing` state and `orphan_finalization` outcome | [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md) and [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/debugging.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/debugging.md) still talk only about `orphan_run` / `orphan_stale_harness` | Add `finalizing` to the status model and teach the diagnostics docs to distinguish `orphan_run` from `orphan_finalization`. |
| `missing_worker_pid` was renamed | [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md) still says `missing_worker_pid` | Rename the failure-mode label to `missing_runner_pid` and keep the wording aligned with the code. |
| Auth/cancel surface was deleted | Several generic auth-flavored examples in [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/SKILL.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/SKILL.md), [`/home/jimyao/gitrepos/prompts/meridian-dev-workflow/skills/context-handoffs/SKILL.md`](/home/jimyao/gitrepos/prompts/meridian-dev-workflow/skills/context-handoffs/SKILL.md), and [`/home/jimyao/gitrepos/prompts/meridian-dev-workflow/skills/issues/SKILL.md`](/home/jimyao/gitrepos/prompts/meridian-dev-workflow/skills/issues/SKILL.md) still center auth-refactor workflows | If those examples are meant to teach Meridian workflows, replace them with non-auth examples or drop them; the runtime no longer has the auth feature. |
| Removed `report create` subcommand | I did not find a stale source-repo hit in the sibling repos; [`/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/resources/advanced-commands.md`](/home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/resources/advanced-commands.md) already says there is no external `report create` command | No source-repo fix needed if the current text stays as-is. If a generated `.agents` mirror still has `report create`, resync the mirror rather than rewriting source docs. |

## Bottom Line

The session closed three loops:

1. Control-plane redesign converged after two review passes and a cleanup pass.
2. The dead-code/auth sweep deleted the unwanted surface area and exposed the true finalize bugs.
3. The finalize-bug work fixed the runtime path, cleaned up the config defaulting behavior, and left only small doc-sync follow-ups.
