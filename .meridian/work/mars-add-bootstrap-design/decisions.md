# Decisions: mars add Bootstrap

## D1: Auto-bootstrap by default, no flag required

**Choice**: `mars add` auto-creates `mars.toml` when none exists and a safe project root can be identified. No `--init` flag needed.

**Alternatives rejected**:
- `--init` flag required for bootstrap — adds friction, defeats purpose
- Interactive prompt before bootstrap — breaks CI/spawn workflows, adds ceremony

**Rationale**: The command `mars add <source>` already carries clear mutation intent. Requiring explicit opt-in to bootstrap adds a step without preventing any real mistakes.

## D2: Git root as bootstrap target

**Choice**: When bootstrapping, `mars.toml` is created at the git repository root (directory containing `.git`), not at cwd.

**Alternatives rejected**:
- Bootstrap at cwd — risks creating config in arbitrary subdirectories
- Bootstrap at first ancestor with a specific marker — over-engineered

**Rationale**: The git root is the canonical project boundary. This matches user mental models and prevents scattered config files.

## D3: Error outside git (no silent bootstrap anywhere)

**Choice**: If no git repository is found, `mars add` errors with a helpful message suggesting `mars init` or `--root`.

**Alternatives rejected**:
- Bootstrap at cwd regardless — dangerous, creates config in arbitrary directories
- Interactive prompt asking where to init — complex, doesn't scale to CI

**Rationale**: Without a git boundary, there's no reliable signal about project location. The user should make an explicit choice.

## D4: `--root` enables bootstrap unconditionally

**Choice**: `mars add --root /path` auto-bootstraps at `/path` even if it's not a git repo.

**Rationale**: `--root` is an explicit declaration of intent. The user has already decided where the project lives.

## D5: Bootstrap adds `[dependencies]` only

**Choice**: Auto-created `mars.toml` contains only `[dependencies]\n` — no settings, no comments, no managed_root.

**Alternatives rejected**:
- Include commented examples — adds noise
- Include `managed_root = ".agents"` — this is the default, specifying it adds clutter

**Rationale**: Minimal config is easier to read and modify. Defaults are self-documenting through behavior.

## D6: Only `add` gets auto-bootstrap (initially)

**Choice**: Only `mars add` auto-bootstraps. Other commands (`sync`, `list`, `upgrade`) error on missing config.

**Alternatives rejected**:
- All context-requiring commands bootstrap — `mars sync` in an uninitialized repo is likely a mistake, not intent

**Rationale**: `mars add` has clear first-use intent. Running `mars list` or `mars sync` in a repo without config is probably a user error (wrong directory).

**Implementation**: Pass an `auto_bootstrap` flag to `find_agents_root`. Only `add` sets it to `true`.

## D7: Submodule isolation preserved

**Choice**: In a git submodule, bootstrap targets the submodule root (innermost `.git`), not the parent repo.

**Rationale**: Submodules are independent projects. A submodule should have its own `mars.toml` if it uses mars.

## D8: No changes to meridian CLI (initially)

**Choice**: All changes land in `mars-agents`. Meridian docs may reference the new behavior but no code changes needed.

**Rationale**: `meridian mars add` is a passthrough. The bootstrap behavior is a mars concern. Meridian's init convenience (`meridian init --link`) remains separate from mars's internal bootstrap.
