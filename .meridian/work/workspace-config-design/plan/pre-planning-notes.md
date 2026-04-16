# Workspace Config Pre-Planning Notes (Fresh Explore Phase)

Explore phase owner: impl-orchestrator `p2037`.
Input design: approved workspace-config design package after `launch-core-refactor` completion.
Target: repo-root `meridian.toml`, local-only `workspace.local.toml`, shared workspace/config surfacing, and launch-time workspace projection.

## Verified design claims

### `.meridian/config.toml` and its gitignore exception are still state-layer policy

- `src/meridian/lib/state/paths.py:13-40` hard-codes `.meridian/.gitignore` with a tracked `!config.toml` exception.
- `src/meridian/lib/state/paths.py:102-148` still models `config_path` on `StatePaths` and resolves it as `<state-root>/config.toml`.
- `src/meridian/lib/state/paths.py:93-99,127-135` does have a `ProjectPaths` type, but it is only a minimal `repo_root/execution_cwd` holder. It does not own `meridian.toml`, `workspace.local.toml`, or root-level ignore policy yet.

This matches the design's claim that R01 must separate project-root file policy from `.meridian` state ownership.

### Loader, config commands, and bootstrap are all still wired to `.meridian/config.toml`

- `src/meridian/lib/config/settings.py:206-210` resolves project config through `resolve_state_paths(repo_root).config_path`.
- `src/meridian/lib/ops/config.py:316-317` routes the config command family through `_config_path()`, which also uses `StatePaths.config_path`.
- `src/meridian/lib/ops/config.py:707-733` auto-creates that file from generic bootstrap when it is missing.
- `src/meridian/lib/ops/runtime.py:54-67` calls `ensure_state_bootstrap_sync()` on ordinary runtime resolution, so generic command startup still scaffolds project config.
- `src/meridian/cli/main.py:1316-1323` triggers that bootstrap on top-level CLI startup.

This confirms the design's blast-radius framing: moving project config is not a loader-only tweak.

### User-facing copy and smoke tests still describe the legacy config location

- `src/meridian/cli/main.py:813-823` describes repository config as `.meridian/config.toml`.
- `tests/smoke/config/init-show-set.md:18-24` asserts `config init` creates `.meridian/config.toml`.
- `tests/smoke/quick-sanity.md:40-47` asserts generic first-run bootstrap creates `.meridian/config.toml`.

R02 therefore has to update help/manifests/smokes along with code, not after.

### Workspace file, workspace command family, and shared surfacing model are absent

- File probe of `src/meridian/lib/config/` shows only `__init__.py` and `settings.py`; there is no `workspace.py`, `project_config_state.py`, or `project_paths.py`.
- File probe of `src/meridian/lib/ops/` shows no `workspace.py` or `config_surface.py`.
- `src/meridian/cli/main.py:803-835` registers `work`, `models`, `streaming`, `config`, and `completion`, but no `workspace` command family.
- `src/meridian/lib/ops/diag.py:109-189` reports only generic warnings (`missing_skills_directories`, `missing_agent_profile_directories`, `updates_check_failed`, `outdated_dependencies`, `active_spawns_present`); there is no workspace finding vocabulary.

This matches the design assumption that workspace topology/surfacing is largely new code, not a rename of an existing feature.

### Launch-core dependency is satisfied, but workspace projection is only a stub seam

- `src/meridian/lib/launch/context.py:550-669` already composes launch requests through the post-R06 `build_launch_context()` factory and calls `apply_workspace_projection()` at one seam.
- `src/meridian/lib/launch/command.py:63-92` defines `apply_workspace_projection()`, but it only accepts an optional adapter method that transforms `ResolvedLaunchSpec -> ResolvedLaunchSpec`.
- `src/meridian/lib/harness/adapter.py:137-220` does not define a typed `project_workspace(...)` contract on `SubprocessHarness`.
- Code search found no adapter implementation of `project_workspace(...)`.

So the dependency is unblocked, but A04 still requires real projection types, root planning, adapter methods, and diagnostics plumbing.

## Falsified design claims

None. The approved design package still fits the live codebase. No redesign trigger surfaced during explore.

## Latent risks not fully spelled out in the design

1. **`ProjectPaths` already exists and is imported broadly.**
   `src/meridian/lib/launch/context.py:25,561-564` and `src/meridian/lib/ops/spawn/execute.py` already consume `ProjectPaths` from `state.paths`. R01 must expand or relocate that abstraction without introducing circular imports or duplicated types during the transition.

2. **Bootstrap splitting is cross-cutting and easy to get partially wrong.**
   `ensure_state_bootstrap_sync()` currently handles runtime dirs, `.meridian/.gitignore`, `mars init`, and config scaffolding in one function (`src/meridian/lib/ops/config.py:707-733`), and that function is called from both `config init` and generic runtime bootstrap (`src/meridian/lib/ops/runtime.py:54-67`, `src/meridian/cli/main.py:1316-1323`). Planner should isolate "runtime bootstrap" from "root-file creation" early so later phases do not fight first-run behavior.

3. **`config show` output shape already has consumers/tests.**
   `ConfigShowOutput` is the current surface for both text and JSON config inspection (`src/meridian/lib/ops/config.py:222-270` plus `config_show_sync` at `745-777`). Adding workspace summary data must preserve existing resolved-value behavior rather than replacing it.

4. **Workspace projection needs a richer contract than the current stub.**
   `apply_workspace_projection()` today has no access to workspace roots, execution cwd, child cwd, or transport-neutral diagnostics (`src/meridian/lib/launch/command.py:63-92`). A04 is not a narrow adapter patch; it requires new launch/config model types plus a widened adapter contract.

5. **No existing parser/snapshot means validation behavior must be pinned with tests immediately.**
   Because there is no `workspace.local.toml` reader or snapshot model yet, WS-1/SURF-1 behavior can drift quickly unless the first implementation phase lands focused parser/snapshot tests before launch wiring.

## Probe gaps

None blocking planning. The external harness-capability questions were already covered in `design/feasibility.md`, and current repo-state verification was code-visible.

## Leaf-distribution hypothesis

Provisional phase ownership for the planner to confirm or revise:

| Phase | Scope hypothesis | Primary leaves / refactors |
|---|---|---|
| 1 | Paths/config foundation: expand `ProjectPaths`, add project-config state, rename `resolve_repo_root`, remove `.meridian` config exception ownership from `StatePaths` | `CFG-1.u1`, `CFG-1.u3`, R01 |
| 2 | Rewire config command family and bootstrap to `meridian.toml`; update CLI copy and existing config smokes/tests | `CFG-1.u2`, `BOOT-1.u1`, `BOOT-1.e1`, R02 |
| 3 | Add workspace file model + `workspace init` + shared surfacing for `config show`/`doctor` | `WS-1.*`, `SURF-1.u1`, `SURF-1.e1`, `SURF-1.e2`, `BOOT-1.e2` |
| 4 | Wire launch-time workspace projection and applicability diagnostics through the launch core | `CTX-1.*`, `SURF-1.e3`, `SURF-1.e4`, possible R03 follow-up if emission drift remains |

Parallelism posture note is stale. Regenerate the plan before relying on sequencing assumptions; phase dependencies and any parallel verification lanes should be recalculated from the current artifact set.

## Exit state: **explore-clean**

Fresh workspace-config explore complete. No design contradiction found. Planning can proceed against the current artifact set.
