# Behavioral Spec: Walk-Up Add, Explicit Init

## Overview

`mars add` finds the nearest existing project by walking up from cwd. `mars init` creates a new project at cwd (or `--root`). This matches mainstream tooling semantics: `uv add`, `cargo add`, and npm local project resolution.

**Core invariant**: `add` never creates `mars.toml`. Only `init` creates projects.

## Separation of Concerns

| Concern | Commands | Behavior | Walk-Up |
|---------|----------|----------|---------|
| **Context discovery** | `add`, `sync`, `list`, `upgrade`, etc. | Find nearest existing `mars.toml`. Error if not found. | YES |
| **Project creation** | `init` | Create `mars.toml` at target. Target is cwd or `--root`. | **NO** |

The difference matters:
- All commands that operate on an existing project use walk-up
- Only `init` creates new projects, and it does so at an explicit location

## Command Classifications

| Command | Classification | Behavior |
|---------|---------------|----------|
| `init` | create | Creates project at cwd (or `--root`). No walk-up. |
| `add` | context | Walks up to find project. Errors if not found. |
| `sync` | context | Walks up to find project. Errors if not found. |
| `list` | context | Walks up to find project. Errors if not found. |
| `upgrade` | context | Walks up to find project. Errors if not found. |
| `remove` | context | Walks up to find project. Errors if not found. |
| `doctor` | context | Walks up to find project. Errors if not found. |
| `repair` | context | Walks up to find project. Errors if not found. |
| `outdated` | context | Walks up to find project. Errors if not found. |
| `link` | context | Walks up to find project. Errors if not found. |
| `why` | context | Walks up to find project. Errors if not found. |
| `rename` | context | Walks up to find project. Errors if not found. |
| `resolve` | context | Walks up to find project. Errors if not found. |
| `override` | context | Walks up to find project. Errors if not found. |
| `adopt` | context | Walks up to find project. Errors if not found. |
| `version` | context | Walks up to find project. Errors if not found. |
| `models` | context | Walks up to find project. Errors if not found. |
| `cache` | root-free | Global cache, no project context. |
| `check` | root-free | Validates a source package, not a consumer project. |

**Design rule**: All commands except `init`, `cache`, and `check` use walk-up context discovery. Only `init` creates projects.

## EARS Statements

### INIT-1: Init creates project at target location

When `mars init` is invoked, the system shall create `mars.toml` at the target root with minimal content, create the managed directory, and report success.

The target is:
- `--root <path>` if specified
- Current working directory otherwise

**Rationale**: `init` is the explicit project creation command. It does not search for existing projects.

### INIT-2: Init does not walk up

When `mars init` is invoked, the system shall NOT walk up to find an existing `mars.toml`. The target is determined solely by cwd or `--root`.

**Rationale**: Init creates a new project. Walking up would conflate creation with discovery.

### INIT-3: Init is idempotent on existing projects

When `mars init` is invoked in a directory that already contains `mars.toml`, the system shall report "already initialized" and succeed without modifying the existing config.

**Rationale**: Re-running init should not break existing projects.

### INIT-4: Init creates minimal config

When `mars init` creates `mars.toml`, the content shall be `[dependencies]\n` only — no comments, no settings, no managed_root override.

**Rationale**: Minimal config is easier to read and modify. `.agents/` is the default managed root; specifying it adds noise.

### INIT-5: Init creates managed directory

When `mars init` creates `mars.toml`, the system shall also create the managed directory (default: `.agents/`) and the `.mars/` marker directory.

**Rationale**: A mars project needs its output directories. Create them atomically with the config.

### ADD-1: Add walks up to find existing project

When `mars add` is invoked without `--root`, the system shall walk from cwd to filesystem root searching for `mars.toml`. The nearest config wins.

**Explicit behavior**:
1. Check `cwd/mars.toml`
2. If not found, check `parent(cwd)/mars.toml`
3. Continue walking up until filesystem root
4. If found at any level, use that project
5. If not found anywhere, error (see ADD-2)

**Rationale**: This matches `uv add`, `cargo add`, and npm semantics. Users expect to be able to run `add` from any subdirectory of their project.

### ADD-2: Add fails when no project exists

When `mars add` is invoked and no `mars.toml` is found from cwd to filesystem root, the system shall error with:
```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

**Rationale**: `add` operates on existing projects. It does not create them.

### ADD-3: Add does not create projects

The system shall NOT auto-initialize a project when `mars add` finds no existing config. Project creation is exclusively the responsibility of `mars init`.

**Rationale**: This prevents surprising file creation and matches mainstream tooling semantics.

### CONTEXT-1: Walk-up boundary is filesystem root

When walking up to find `mars.toml`, the system shall walk from cwd to filesystem root. Git boundaries do not stop the walk.

**Rationale**: Git is not a requirement. A `mars.toml` in any ancestor directory is a valid project root.

### CONTEXT-2: Windows drive root termination

When the walk-up reaches a Windows drive root (e.g., `C:\`), `Path::parent()` returns `None`. The system shall treat this as filesystem root and terminate the walk.

**Rationale**: Windows filesystem roots are drive letters, not `/`. The walk-up must terminate correctly on all platforms.

### CONTEXT-3: UNC path handling

When the walk-up encounters a UNC path (e.g., `\\server\share\project`), the system shall walk up through directories and terminate when `Path::parent()` returns `None` at the server/share root.

**Rationale**: UNC paths are valid project locations on Windows. Walk-up should work identically.

### ROOT-1: --root sets search start for context commands

When a context command (`add`, `sync`, etc.) is invoked with `--root <path>`:
1. Walk up from `<path>` to filesystem root searching for `mars.toml`
2. If found, use that project
3. If not found, error with the standard message

The system shall NOT check cwd when `--root` is specified.

**Rationale**: `--root` overrides where the walk-up starts, not where the project is created.

### ROOT-2: --root sets target for init

When `mars init --root <path>` is invoked:
1. Check if `<path>/mars.toml` exists
2. If exists, report "already initialized" and succeed
3. If not exists, create `mars.toml` at `<path>`

The system shall NOT walk up from `<path>`.

**Rationale**: `--root` for init sets the creation target, not a search start.

### PATH-1: Path style normalization

When `--root` accepts a path, the system shall accept both forward-slash (`C:/project`) and backslash (`C:\project`) styles on Windows. Path display in messages shall use the platform-native style.

**Rationale**: Windows supports both slash styles. Users should not be rejected for using either.

### PATH-2: Extended-length path handling

When `canonicalize()` returns an extended-length path on Windows (prefixed with `\\?\`), the system shall use the canonicalized path for filesystem operations and `display()` for user-facing messages.

**Rationale**: Extended-length paths are correct but verbose in messages.

## Non-requirements

- **Git detection**: Git presence does not affect walk-up or init behavior.
- **Auto-init**: No command auto-creates `mars.toml`. That is init's job.
- **Ancestor warnings**: Since `add` adopts the nearest ancestor (correct behavior), no warning is needed.
- **Nested project magic**: Nested projects are created explicitly with `mars init`.

### Explicit Prohibitions

These behaviors are explicitly NOT supported and must NOT be implemented:

- **Auto-init from add**: `mars add` NEVER creates `mars.toml`.
- **Cwd-first for add**: `mars add` walks up, it does not check cwd-only.
- **Walk-up for init target**: `mars init` creates at cwd or `--root`, it does not search.
- **Git boundary**: Walk-up continues to filesystem root, git is irrelevant.

## Error Messages

### Missing config (all context commands)

```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

### Permission errors

Standard I/O errors surface naturally. No special handling.

## Tradeoffs

### Risk: User forgets to init

**Scenario**: User runs `mars add owner/repo` in a fresh directory, expects project creation.

**Mitigations**:
1. Clear error message directs user to `mars init`
2. Two-command flow is familiar from `cargo new` + `cargo add`, `uv init` + `uv add`
3. Once initialized, all subdirectory usage "just works"

### Benefit: No surprising file creation

`add` never creates files in unexpected locations. Users know exactly when `mars.toml` is created: only when they run `mars init`.

### Benefit: Works from any subdirectory

Once a project exists, users can run `mars add` from any subdirectory. This is the common workflow when editing code in `src/` and wanting to add a dependency.

### Benefit: Explicit nested projects

Nested mars projects require explicit `mars init`. No accidental nesting, no warnings to parse.

### Benefit: Predictable behavior

Same walk-up logic for all context commands. Users learn one model.

## Comparison to other tools

| Tool | Add behavior | Project creation |
|------|-------------|------------------|
| `uv add` | Walks up to find pyproject.toml | Requires `uv init` |
| `cargo add` | Walks up to find Cargo.toml | Requires `cargo new` or `cargo init` |
| `npm install <pkg>` | Walks up to find package.json | Requires `npm init` (or creates minimal package.json) |
| `pnpm add` | Walks up to find package.json | Requires `pnpm init` |
| **mars add (new)** | Walks up to find mars.toml | Requires `mars init` |

Mars now matches the mainstream pattern: walk-up for operations, explicit init for creation.

## Follow-On Design Tracks

These concerns are scoped out of this design:

### 1. Remove accidental git assumptions

The current implementation of `default_project_root()` walks up to git root. This design specifies cwd-only init, but a focused implementation pass is needed to:
- Remove the git-root default from init
- Remove or update tests that assume git boundaries

This is a discrete refactor, not part of the walk-up add feature.

### 2. Repo-wide Windows compatibility

While this design specifies Windows-correct behavior for walk-up, a separate repo-wide audit is needed to ensure Windows compatibility across all mars commands and the sync/install pipeline.
