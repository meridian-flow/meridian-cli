# A02: Config Loader and Command-Family Resolution

## Summary

Today Meridian has two separate project-config read paths: the loader resolves project config through `_resolve_project_toml()`, while every `config` subcommand uses a private `_config_path()` helper. The target shape replaces those split decisions with one observed project-config state machine consumed by both reads and writes.

## Realizes

- `../spec/config-location.md` — `CFG-1.u1`, `CFG-1.u2`, `CFG-1.u3`
- `../spec/bootstrap.md` — `BOOT-1.e1`

## Current State

- The settings loader resolves project config through `_resolve_project_toml()` and currently points at `StatePaths.config_path` (`probe-evidence/probes.md:72-79`).
- `config init/show/set/get/reset` bypass that loader and all call the single `_config_path()` helper in `lib/ops/config.py` (`probe-evidence/probes.md:75-77`).
- `ensure_state_bootstrap_sync()` writes the scaffold template automatically on normal startup if the current `_config_path()` is absent (`probe-evidence/probes.md:77`, `probe-evidence/probes.md:147-158`).
- CLI help, manifest strings, smoke tests, and unit tests hard-code `.meridian/config.toml` today (`probe-evidence/probes.md:80-100`).

## Target State

Introduce a shared observed-state object for project config:

```text
ProjectConfigState
  status = absent | present
  path?              # present only when status = present
  write_path         # always meridian.toml
```

### Read path

- `present` → read `<project-root>/meridian.toml`
- `absent` → no project config; loader runs on built-in defaults

### Write path

- Writes always target `<project-root>/meridian.toml`.
- If `meridian.toml` is absent, `config init` creates it; mutation commands that require a config file surface a clear "no project config; run `config init`" message.

### Command-family consistency

The following consumers must use the same `ProjectConfigState` rather than independent path helpers:

- settings loader
- `config init`
- `config show/get/set/reset`
- runtime bootstrap path
- any command help or manifest copy that names the canonical project-config location

This is the only way to avoid reads resolving from one location while writes land in another, which is the failure mode the prior design missed (`probe-evidence/probes.md:75-77`).

## Design Notes

- The precedence stack does not change. Only the project-config slot moves to `<project-root>/meridian.toml`.
- `config init` creates an opt-in root file on clean repos. There is no `config migrate` command.
- The loader should not special-case workspace topology. `workspace.local.toml` is a sibling read model, not part of `MeridianConfig`.
- Generic bootstrap (`ensure_state_bootstrap_sync`) no longer auto-creates root config. It creates only `.meridian/` runtime directories and `.meridian/.gitignore`.

## Open Questions

None at the architecture level.
