# Auto-extracted Report

# Report

Read the requirements in `.meridian/work/context-env-projection/requirements.md` and traced the current implementation paths. No files were changed in this pass.

## 1. `meridian context`

- [src/meridian/cli/main.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/cli/main.py#L1254) has the top-level `context_cmd()` wrapper. Its docstring still says `work_id, repo_root, state_root, depth`, so the CLI help text will need to change with the output shape.
- [src/meridian/lib/ops/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/context.py#L23) defines `ContextOutput`, and [context_sync()](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/context.py#L69) builds the payload. This is the main schema change point: replace `work_id` with `work_dir`, add `fs_dir`, and add `context_roots`.
- [src/meridian/lib/ops/manifest.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/manifest.py#L655) registers the `context` operation metadata. Its description string still names the old fields and should be updated alongside the payload.
- [src/meridian/lib/config/workspace.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L166) parses `workspace.local.toml`, and [resolve_workspace_snapshot()](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L266) is the read path the context command should call. `WorkspaceSnapshot.roots` already carries resolved absolute paths.
- [src/meridian/lib/config/workspace.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L109) exposes `get_projectable_roots(snapshot)`, which returns the expanded enabled/existing roots already used by launch projection. If `context_roots` should match what can actually be projected into launches, this is the helper to reuse.
- [src/meridian/lib/ops/config_surface.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/config_surface.py#L38) is a useful precedent: it already converts a `WorkspaceSnapshot` into a serializable workspace summary using `get_projectable_roots(snapshot)`.

## 2. `meridian work current`

- [src/meridian/cli/work_cmd.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/cli/work_cmd.py#L210) implements `_work_current()`. It currently just emits `work_current_sync(WorkCurrentInput())`.
- [src/meridian/lib/ops/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/context.py#L49) defines `WorkCurrentOutput`, and [work_current_sync()](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/context.py#L100) currently returns the work id string.
- [src/meridian/lib/ops/manifest.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/manifest.py#L667) registers `work.current` and still describes it as returning `work_id`.
- Change needed: return the expanded work scratch directory path instead of the id, and return empty when no work is attached. The obvious path builder is `resolve_work_scratch_dir(...)` from [src/meridian/lib/state/paths.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/state/paths.py#L213).

## 3. Env var projection

- [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/context.py#L79) is the actual launch env projection gate. `ChildEnvContext.child_context()` currently emits only `MERIDIAN_REPO_ROOT`, `MERIDIAN_STATE_ROOT`, `MERIDIAN_DEPTH`, and `MERIDIAN_CHAT_ID`.
- [src/meridian/lib/launch/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/context.py#L515) merges that context into `merged_overrides` and then hands it to `build_env_plan()`. If `MERIDIAN_WORK_DIR` and `MERIDIAN_FS_DIR` are supposed to come back, this is the launch-time merge point where they need to be present.
- [src/meridian/lib/launch/env.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/env.py#L44) contains the normalization helpers. `_normalize_meridian_fs_dir()` already knows how to derive `MERIDIAN_FS_DIR` from `MERIDIAN_REPO_ROOT`, and `_normalize_meridian_work_dir()` already knows how to derive `MERIDIAN_WORK_DIR` from work id / chat id inputs. `build_env_plan()` is the final assembly point.
- [src/meridian/lib/core/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/core/context.py#L13) is the runtime-context DTO. It currently parses `MERIDIAN_WORK_ID` and can emit `MERIDIAN_WORK_DIR`, but it does not model `fs_dir` yet. If you want the env projection represented in one canonical runtime object, this is the model to extend.
- [src/meridian/lib/ops/spawn/execute.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/spawn/execute.py#L159) has the background-worker env helper `_spawn_background_worker_env()`. It already sets `MERIDIAN_WORK_ID` and `MERIDIAN_WORK_DIR` for the detached worker process, so this is the parallel path to keep in sync if the projection is restored everywhere.
- [src/meridian/cli/work_cmd.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/cli/work_cmd.py#L48) and [src/meridian/lib/ops/context.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/ops/context.py#L61) both depend on `MERIDIAN_CHAT_ID` to recover the active work attachment, which is the current workaround the requirements want to replace with direct projected paths.

## 4. Workspace config reading

- [src/meridian/lib/config/workspace.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L35) defines `ContextRoot` and [parse_workspace_config()](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L166) parses `[[context-roots]]` from `workspace.local.toml`.
- [src/meridian/lib/config/workspace.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L211) evaluates those entries into resolved absolute paths via `ResolvedContextRoot.resolved_path`.
- [src/meridian/lib/config/workspace.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/config/workspace.py#L266) is the clean entry point from the context command. From there, `snapshot.roots` gives all resolved roots, and `get_projectable_roots(snapshot)` gives the launch-ready subset.
- Current recommendation from the code shape: have `ops/context.py` call `resolve_workspace_snapshot(repo_root)` and then map either `snapshot.roots` or `get_projectable_roots(snapshot)` into `context_roots`, depending on whether you want all declared roots or only roots that are enabled and exist on disk.

## 5. `--desc` alias on `work start`

- [src/meridian/cli/work_cmd.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/cli/work_cmd.py#L56) defines `_work_start()` and currently declares the option as `Parameter(name="--description", ...)`.
- [src/meridian/cli/spawn.py](/home/jimyao/gitrepos/meridian-cli/src/meridian/cli/spawn.py#L193) is the local precedent for a short description flag (`--desc`), and [the skills/CLI code already shows list-style parameter naming](https://example.invalid) via `name=["--skills", "-s"]` in the same file.
- Change needed: add `--desc` as an alias on the `_work_start()` parameter declaration while leaving `WorkStartInput.description` unchanged.

## Tests and follow-up

- [tests/lib/config/test_workspace.py](/home/jimyao/gitrepos/meridian-cli/tests/lib/config/test_workspace.py#L34) already covers workspace-root resolution and is the best place to pin `context_roots` extraction behavior.
- [tests/exec/test_permissions.py](/home/jimyao/gitrepos/meridian-cli/tests/exec/test_permissions.py#L212) covers child-env sanitization. It also contains a stale note at [lines 310-312](/home/jimyao/gitrepos/meridian-cli/tests/exec/test_permissions.py#L310) saying the work-dir derivation tests were removed, which will need to be revisited if env projection comes back.
- [tests/test_launch_resolution.py](/home/jimyao/gitrepos/meridian-cli/tests/test_launch_resolution.py#L246) already validates workspace projection into launch args/env and is a good place for end-to-end assertions on restored `MERIDIAN_WORK_DIR` / `MERIDIAN_FS_DIR`.
- I did not run the test suite in this pass. This was source inspection only.

## Files changed

- Created: none
- Modified: none

## Blockers

- None. The repo was readable enough to map the change points directly.
