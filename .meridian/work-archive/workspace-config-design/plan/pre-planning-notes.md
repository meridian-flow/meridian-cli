# Workspace Config Pre-Planning Notes (Remaining-Phases Refresh)

Explore phase owner: impl-orchestrator `p2070`.
Refresh date: 2026-04-16.
Input design: approved workspace-config design package for `WS-1`, `CTX-1`,
`SURF-1`, and `BOOT-1`, plus live repo state after the R01/R02 implementation
round.
Target: remaining workspace topology, launch projection, surfacing, and
bootstrap behavior, while folding in any residual R02 fixes the current code
still needs.

## Verified design claims

### Project-root config ownership moved out of `.meridian/`

- `src/meridian/lib/config/project_paths.py:10-34` now makes `ProjectPaths`
  the owner of `meridian.toml`, `workspace.local.toml`, and project-root ignore
  targets.
- `src/meridian/lib/config/project_config_state.py:11-38` introduces the
  shared `ProjectConfigState` read model for the canonical project config slot.
- `src/meridian/lib/config/settings.py:207-208,765-779` resolves project config
  through `ProjectConfigState` and feeds that state into `load_config()`.
- `src/meridian/lib/ops/config.py:722-753` and
  `src/meridian/cli/main.py:1319-1323` split generic runtime bootstrap from
  explicit project-config creation.

This confirms the approved design's core boundary shift: committed project
config lives at repo root in `meridian.toml`, not under `.meridian/`.

### Generic launch composition now has a workspace-projection seam

- `src/meridian/lib/launch/context.py:643-651` resolves the typed launch spec
  and then passes it through `apply_workspace_projection()` before argv
  construction.
- `src/meridian/lib/launch/command.py:63-92` defines that seam and allows
  adapters to transform `ResolvedLaunchSpec`.

The design dependency on post-R06 launch composition is therefore satisfied.
The remaining projection work is not blocked on missing launch-core structure.

### Workspace file naming and project-path placeholders already exist

- `src/meridian/lib/config/project_paths.py:24-34` already exposes
  `workspace_local_toml` and `workspace_ignore_targets`.
- `tests/test_state/test_project_paths.py:51-52` pins those names.

This means the remaining workspace work can build on an existing project-root
path abstraction rather than inventing a second one.

### The remaining workspace model and surfacing layers are still missing

- Code search under `src/meridian/lib/config/` finds no workspace parser or
  snapshot module beyond `project_paths.py` and `project_config_state.py`.
- `src/meridian/lib/ops/diag.py:109-189` has no workspace summary or
  workspace-specific finding codes.
- `src/meridian/cli/main.py:1149-1159` registers `spawn`, `report`, `session`,
  `work`, `models`, `config`, and `doctor`, but no `workspace` command group.
- The architecture's shared surfacing builder
  `src/meridian/lib/ops/config_surface.py` does not exist in `src/`.

So the design's workspace-model and surfacing slices remain real implementation
work, not just documentation cleanup.

### The handoff claim "R01/R02 are complete" is false in the live repo

Concrete residual R02 issues:

- `src/meridian/lib/ops/config.py:686-719,741-763` still couples
  `config init` to `_ensure_mars_init()`, so `meridian config init` can still
  create `mars.toml` or run Mars link behavior as a side effect.
- `src/meridian/lib/ops/config.py:591-595,766-785,821-830` computes
  user-config source attribution from `MERIDIAN_CONFIG` only, while the real
  loader falls back to `~/.meridian/config.toml` via
  `src/meridian/lib/config/settings.py:211-220,772-779`.
- `src/meridian/lib/ops/diag.py:109-189` does not share any config/workspace
  surfacing state with `config show`, which misses the design's one-surface
  intent and leaves `doctor` blind to project/workspace state.

Independent reviewer evidence agrees:

- `.meridian/spawns/p2068/report.md` marks R02 `FAIL` and calls out Mars-init
  coupling, user-config source drift, and missing diagnostics integration.
- `.meridian/spawns/p2069/report.md` marks the config-introspection source
  split as the main remaining structural issue.

Planning must therefore treat residual R02 convergence as in-scope for the next
phase sequence rather than assuming a clean handoff.

## Falsified claims

### The execution handoff statement "R01/R02 are complete" is contradicted by current evidence

This is not a design-package falsification. The approved design still fits the
codebase. But the execution-status assumption in the current handoff is false:
the repo is mid-transition, not post-transition.

Planning implication: do not start workspace/surfacing/projection phases from a
premise that `config init`, `config show`, and `doctor` are already converged.

## Latent risks not fully spelled out in the design

1. **Residual R02 cleanup overlaps `SURF-1` directly.**
   The missing shared surfacing builder is both a leftover R02 issue and the
   foundation for `SURF-1`. If planner splits these carelessly, coder phases
   will duplicate config-source logic twice: once for config introspection and
   again for workspace surfacing.

2. **`ProjectPaths` already advertises workspace API surface before the real owner exists.**
   `workspace_local_toml` and `workspace_ignore_targets` exist in
   `src/meridian/lib/config/project_paths.py:24-34`, but there are no `src/`
   consumers yet. The next plan should either exercise these members
   immediately or trim speculative surface instead of letting it drift.

3. **`apply_workspace_projection()` is only a shape seam today, not a full contract.**
   `src/meridian/lib/launch/command.py:63-92` only hands adapters a
   `ResolvedLaunchSpec`. It does not yet carry workspace snapshot data,
   applicability classification, or transport-neutral diagnostics. CTX/SURF
   implementation likely needs a richer projection contract than the current
   stub.

4. **Workspace behavior has almost no dedicated tests yet.**
   The only current test coverage tied to workspace naming is
   `tests/test_state/test_project_paths.py:51-52`. Parser, invalid-file,
   unknown-key, missing-root, `workspace init`, `config show`, `doctor`, and
   launch-applicability behaviors will all need new tests in the first landing
   phases or drift will be immediate.

5. **Smoke evidence for phase 2 is informative but not terminal.**
   `p2067` reached the "final evidence collection" stage and reported positive
   runtime observations in its last emitted agent messages, but as of
   2026-04-16 it still had not written a terminal report. Treat that lane as
   advisory evidence, not phase-closure proof.

## Probe gaps

1. **Fresh runtime smoke is still required after residual R02 fixes land.**
   The positive p2067 runtime observations do not cover the remaining reviewer
   findings around Mars-init coupling or default user-config source attribution.

2. **Workspace-specific runtime coverage does not exist yet.**
   No probe has yet exercised:
   - invalid `workspace.local.toml`
   - unknown workspace keys
   - missing-root surfacing in `config show` / `doctor`
   - harness applicability downgrades
   - codex read-only ignored state
   - open-code projection behavior under real launch assembly

These are planner-owned verification obligations, not design blockers.

## Leaf-distribution hypothesis

Provisional ownership draft for the planner to confirm or revise:

| Phase | Scope hypothesis | Primary leaves / carryover |
|---|---|---|
| 1 | Residual config-surface convergence: remove Mars-init side effects from `config init`, unify user-config source resolution with loader semantics, and introduce the shared config/workspace surfacing builder seam. | Residual R02 carryover, `BOOT-1.e1`, `SURF-1.u1` foundation |
| 2 | Workspace file model and CLI: parse/evaluate `workspace.local.toml`, add `workspace init`, wire gitignore ownership, and add config/doctor inspection surfacing for `none/present/invalid`, unknown keys, and missing roots. | `WS-1.*`, `BOOT-1.e2`, `SURF-1.u1`, `SURF-1.e1`, `SURF-1.e2` |
| 3 | Launch-time context-root projection and applicability diagnostics: consume workspace snapshot in launch prep, emit roots in correct precedence order, omit missing roots, and surface ignored/unsupported states. | `CTX-1.*`, `SURF-1.e3`, `SURF-1.e4` |
| 4 | Final review / fix / verification loop. | GPT review fan-out + `@refactor-reviewer` |

Parallelism posture is likely still `limited`: coder phases look sequential
because phase 1 foundations feed both workspace inspection and launch-time
projection, while tester lanes can parallelize inside each phase.

## Exit state: **explore-clean with handoff correction**

The approved design still matches the codebase, so this is not a redesign
trigger. But the current execution handoff is wrong about R02 being closed, and
the plan artifacts must be regenerated from this corrected state before further
implementation.
