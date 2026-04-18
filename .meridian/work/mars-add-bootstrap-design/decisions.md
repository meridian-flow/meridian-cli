# Decisions: mars add Bootstrap

## D1: Auto-bootstrap by default, no flag required

**Choice**: `mars add` auto-creates `mars.toml` when none exists. No `--init` flag needed.

**Alternatives rejected**:
- `--init` flag required for bootstrap — adds friction, defeats purpose
- Interactive prompt before bootstrap — breaks CI/spawn workflows, adds ceremony

**Rationale**: The command `mars add <source>` already carries clear mutation intent. Requiring explicit opt-in to bootstrap adds a step without preventing any real mistakes.

## D2: Bootstrap at current working directory (REVISED)

**Choice**: When bootstrapping, `mars.toml` is created at the current working directory, not at any detected boundary.

**Supersedes**: Previous design (D2) that used git repository root.

**Alternatives rejected**:
- Git root as bootstrap target — git is not a requirement, adds complexity for non-git users
- Walk-up to first common project marker — over-engineered, heuristic-based
- Prompt asking where to init — breaks CI/scripts

**Rationale**: The user ran `mars add` from this directory. That's the signal. Simple, universal, no VCS dependency.

**Tradeoff accepted**: If the user is in a subdirectory and wanted the project root elsewhere, they'll see the bootstrap message and can delete/retry. Easy recovery, rare case.

## D3: No git boundary in walk-up (REVISED)

**Choice**: When searching for existing `mars.toml`, walk from cwd to filesystem root. Git is not consulted.

**Supersedes**: Previous design that stopped walk-up at `.git` boundary.

**Alternatives rejected**:
- Stop at git root — makes git a requirement, fails in non-git directories
- Stop at first common project marker — heuristic, varies by ecosystem

**Rationale**: Git is not a requirement. A valid mars project is simply a directory with `mars.toml`. Walk-up finds the nearest one.

## D4: `--root` enables bootstrap unconditionally

**Choice**: `mars add --root /path` auto-bootstraps at `/path` even if it's not a git repo or any special directory.

**Unchanged from previous design**.

**Rationale**: `--root` is an explicit declaration of intent. The user has already decided where the project lives.

## D5: Bootstrap adds `[dependencies]` only

**Choice**: Auto-created `mars.toml` contains only `[dependencies]\n` — no settings, no comments, no managed_root.

**Unchanged from previous design**.

**Rationale**: Minimal config is easier to read and modify. Defaults are self-documenting through behavior.

## D6: Only `add` gets auto-bootstrap (initially)

**Choice**: Only `mars add` auto-bootstraps. Other commands (`sync`, `list`, `upgrade`) error on missing config.

**Unchanged from previous design**.

**Rationale**: `mars add` has clear first-use intent. Running `mars list` or `mars sync` in a directory without config is probably a user error (wrong directory).

**Implementation**: Pass an `auto_bootstrap` flag to `find_agents_root`. Only `add` sets it to `true`.

## D7: Git submodule handling removed (REVISED)

**Choice**: Git submodules receive no special treatment. They are ordinary directories.

**Supersedes**: Previous design (D7) that isolated submodules at their `.git` boundary.

**Rationale**: Git is not a requirement. The submodule-specific logic was only relevant when git was the boundary signal.

## D8: No changes to meridian CLI (initially)

**Choice**: All changes land in `mars-agents`. Meridian docs may reference the new behavior but no code changes needed.

**Unchanged from previous design**.

**Rationale**: `meridian mars add` is a passthrough. The bootstrap behavior is a mars concern.

## D9: Visible bootstrap message (NEW)

**Choice**: When bootstrap occurs, print `initialized <path> with mars.toml` before the add output.

**Rationale**: Since bootstrap now happens at cwd (which could be "wrong"), the message surfaces mistakes immediately. If the user sees the wrong path, they know to fix it.

## D10: Error message updated for non-git context (NEW)

**Choice**: When `auto_bootstrap=false` and no config is found, the error says:
```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

**Supersedes**: Previous error that mentioned "repository root" (implying git).

**Rationale**: The error should not reference git since git is not involved.
