# A01: Paths Layer

## Summary

The current codebase has `StatePaths` for `.meridian/` files plus an early `ProjectPaths` abstraction for project-root Meridian files. The target shape tightens that boundary: `ProjectPaths` owns project-root file policy only, while `StatePaths` stays focused on local/runtime state.

Terminology: **project root** names the parent directory of the active `.meridian/`. It is an internal concept and does not appear in user-facing spec leaves; user-facing docs describe files by relationship to `.meridian/`. See `decisions.md` D12.

## Realizes

- `../spec/config-location.md` — `CFG-1.u1`, `CFG-1.u3`
- `../spec/workspace-file.md` — `WS-1.u1`, `WS-1.u2`
- `../spec/bootstrap.md` — `BOOT-1.u1`, `BOOT-1.e2`

## Current State

- `StatePaths` is `.meridian`-scoped today: it exposes `root_dir`, `spawns_dir`, and `cache_dir`, while runtime bootstrap still owns `.meridian/.gitignore` policy (`probe-evidence/probes.md:64-71`, plus current `src/meridian/lib/state/paths.py`).
- `ProjectPaths` now exists at `src/meridian/lib/config/project_paths.py` and already exposes `meridian.toml`, `workspace.local.toml`, and project-root ignore targets. This leaf tightens its ownership boundary and downstream consumer contract rather than inventing the abstraction from scratch.
- `resolve_project_root()` already exists in `lib/config/settings.py`; the remaining work is keeping file-policy ownership and call-site expectations aligned with that boundary.
- `.meridian/.gitignore` currently still carries legacy compatibility cleanup for the old `.meridian/config.toml` world, which remains a symptom of the wrong boundary rather than a durable contract (`probe-evidence/probes.md:70-71` plus current `src/meridian/lib/state/paths.py`).

## Target State

Introduce a separate project-root file abstraction, referred to here as `ProjectPaths`, with responsibility for:

- locating `meridian.toml`
- locating `workspace.local.toml`
- exposing project-local ignore policy for `workspace.local.toml`

`StatePaths` remains responsible only for `.meridian/` runtime and cache files.

### Proposed shape

```text
ProjectPaths
  project_root
  meridian_toml
  workspace_local_toml
  workspace_ignore_target

StatePaths
  root_dir (.meridian)
  spawns_dir
  artifacts_dir
  cache_dir
  sessions_path
  spawns_path
  ...
```

### Discovery rules

- **Project config**: canonical path is `<project-root>/meridian.toml`. If absent, no project config is in effect.
- **Workspace file**: Meridian checks `<project-root>/workspace.local.toml`. If absent, workspace topology is absent.
- **Paths inside `workspace.local.toml`**: resolved relative to the file itself (VS Code `.code-workspace` convention), so the file remains portable across moves.

### Ownership boundary

| Concern | Owner |
|---|---|
| `.meridian/` directories, pid files, JSONL state, `.meridian/.gitignore` | `StatePaths` |
| `meridian.toml`, `workspace.local.toml`, project-root ignore targets, file location resolution | `ProjectPaths` |
| `workspace.local.toml` loading, parsing, schema validation, snapshot construction | `config/workspace.py` + `workspace_snapshot.py` |

## Module Layout

Modules in scope for this design:

| Module | Ownership |
|---|---|
| `src/meridian/lib/config/project_paths.py` | Project-root Meridian file policy. Defines `ProjectPaths` and resolves the file locations for `meridian.toml` and `workspace.local.toml` without touching state-root concerns. |
| `src/meridian/lib/config/project_config_state.py` | Canonical project-config state machine (`absent | present`). Shared by loader and mutation commands so read/write behavior cannot diverge. |
| `src/meridian/lib/config/workspace.py` | `workspace.local.toml` loading, parsing, schema validation, unknown-key preservation, and `WorkspaceConfig` document model after `ProjectPaths` chooses which file to consult. |
| `src/meridian/lib/config/workspace_snapshot.py` | Filesystem evaluation and diagnostic shaping: missing roots, enabled counts, invalid-file findings. Produces `WorkspaceSnapshot`. |
| `src/meridian/lib/launch/context_roots.py` | Shared launch-time ordered-root planner. Chooses which enabled existing roots participate in a launch and in what order; harness adapters translate that plan into tokens or overlays. |
| `src/meridian/lib/ops/workspace.py` | New `meridian workspace` command family, starting with `workspace init`. File creation for `workspace.local.toml` lives here, not in generic bootstrap. |
| `src/meridian/lib/ops/config_surface.py` | Shared builder for `config show` and `doctor` workspace/config surfacing payloads so both commands report the same state vocabulary. |

## Design Notes

- The workspace file should be locally ignored without requiring a committed project-file diff. The project-root abstraction should own that policy because it is a property of a project-root local file, not of `.meridian/`.
- `ProjectPaths` should expose file locations only. Mutation policies live in the loader and command layers.
- `ProjectPaths` does not own a workspace override environment variable in v1. Discovery stays at the canonical sibling file beside the active `.meridian/`.

## Open Questions

None at the architecture level.
