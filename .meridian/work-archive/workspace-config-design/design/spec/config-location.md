# CFG-1: Project Config Location

## Context

The primary problem is boundary clarity, not just file renaming. Committed project policy belongs alongside `mars.toml` in the same directory as the active `.meridian/`; `.meridian/` itself is local/runtime state. `meridian.toml` in that same directory is the canonical committed Meridian project configuration. `.meridian/config.toml` is not supported.

**Realized by:** `../architecture/paths-layer.md`, `../architecture/config-loader.md`.

## EARS Requirements

### CFG-1.u1 — Canonical committed project config lives beside the active `.meridian/`

`The canonical committed Meridian project configuration shall live at meridian.toml in the same directory as the active .meridian/ directory. .meridian/config.toml is not supported.`

### CFG-1.u2 — Config precedence does not change

`The project-config location change shall not change precedence ordering: CLI flags shall continue to override environment variables, environment variables shall continue to override profile values, profile values shall continue to override project config, project config shall continue to override user config, and user config shall continue to override harness defaults.`

### CFG-1.u3 — Settings stay in `meridian.toml`; topology stays out

`Repository-level operational settings such as model, harness, approval, timeout, and other MeridianConfig fields shall remain in meridian.toml, and workspace topology shall not be stored in meridian.toml.`

## Non-Requirement Edge Cases

- **No `models.toml` migration in this design.** Meridian does not read `.meridian/models.toml`; model aliasing is Mars-owned per `probe-evidence/probes.md:49-59`.
- **No workspace settings table.** Workspace topology remains a separate file and does not become a second project-settings container.
