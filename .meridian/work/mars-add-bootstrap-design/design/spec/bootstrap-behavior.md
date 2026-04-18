# Behavioral Spec: Init-Centric Bootstrap

## Overview

`mars init` is the canonical bootstrap primitive. Commands that carry clear project-setup intent may auto-initialize by invoking init semantics internally, eliminating the separate explicit init step for first-use.

## Core Principle

Bootstrap is initialization. Every auto-bootstrap path reuses `mars init` semantics — same root selection, same config creation, same messaging. There is no separate "bootstrap mode" with its own rules.

## Auto-Init Allowlist

Commands are explicitly classified as **auto-init allowed** or **init-required**:

| Command | Classification | Rationale |
|---------|---------------|-----------|
| `init` | auto-init allowed | The canonical bootstrap primitive |
| `add` | auto-init allowed | Clear project-setup intent (adding first dependency) |
| `sync` | init-required | Running sync on nothing is likely a user error |
| `list` | init-required | Listing an uninitialized project is an error |
| `upgrade` | init-required | No dependencies to upgrade = wrong directory |
| `remove` | init-required | No dependencies to remove = wrong directory |
| `doctor` | init-required | Nothing to diagnose = wrong directory |
| `repair` | init-required | Nothing to repair = wrong directory |
| `outdated` | init-required | No dependencies to check = wrong directory |
| `link` | init-required | Linking into an uninitialized project is an error |
| `why` | init-required | No dependencies to explain = wrong directory |
| `rename` | init-required | No items to rename = wrong directory |
| `resolve` | init-required | No conflicts to resolve = wrong directory |
| `override` | init-required | No sources to override = wrong directory |
| `adopt` | init-required | Adopting requires existing context |
| `version` | init-required | Versioning requires existing package |
| `models` | init-required | Models cache is project-scoped |
| `cache` | root-free | Global cache, no project context |
| `check` | root-free | Validates a source package, not a consumer project |

**Design rule**: A command is auto-init allowed only when the user's intent is unambiguous: they want this directory to become a mars project. `add` qualifies because you cannot add a dependency without a project. `sync` does not qualify because running `mars sync` in the wrong directory should fail fast.

## EARS Statements

### INIT-1: Init is the canonical bootstrap path

When `mars init` is invoked in a directory without `mars.toml`, the system shall create `mars.toml` at the target root with minimal content, create the managed directory, and report success.

**Rationale**: `init` defines what bootstrapping means. All other auto-init paths delegate to this behavior.

### INIT-2: Init root selection defaults to cwd

When `mars init` is invoked without `--root`, the system shall use the current working directory as the project root.

**Rationale**: The user ran the command from this directory. That is their declaration of intent.

### INIT-3: Init is idempotent on existing projects

When `mars init` is invoked in a directory that already contains `mars.toml`, the system shall report "already initialized" and succeed without modifying the existing config.

**Rationale**: Re-running init should not break existing projects. This also enables safe auto-init from other commands.

### INIT-4: Init creates minimal config

When `mars init` creates `mars.toml`, the content shall be `[dependencies]\n` only — no comments, no settings, no managed_root override.

**Rationale**: Minimal config is easier to read and modify. `.agents/` is the default managed root; specifying it adds noise.

### INIT-5: Init creates managed directory

When `mars init` creates `mars.toml`, the system shall also create the managed directory (default: `.agents/`) and the `.mars/` marker directory.

**Rationale**: A mars project needs its output directories. Create them atomically with the config.

### AUTO-1: Add invokes init when config is missing

When `mars add` is invoked and no `mars.toml` exists in the cwd-to-root walk, the system shall invoke init semantics at the current working directory before proceeding with the add operation.

**Rationale**: `mars add <source>` is a first-use command. The user wants this directory to be a project with this dependency.

### AUTO-2: Add reports bootstrap before proceeding

When `mars add` auto-initializes, the system shall print `initialized <path> with mars.toml` before the add output (unless `--json`).

**Rationale**: The user should know that init happened and where. This surfaces mistakes immediately.

### AUTO-3: Auto-init respects --root

When `mars add --root <path>` is invoked and `<path>` does not contain `mars.toml`, the system shall auto-initialize at `<path>`, not at cwd.

**Rationale**: `--root` is an explicit declaration of project location. Auto-init honors it.

### WALK-1: Walk-up finds existing config

When any command requiring context is invoked and `mars.toml` exists in the cwd or any ancestor directory, the system shall use the existing config (nearest wins). No initialization occurs.

**Rationale**: Existing projects work unchanged. Auto-init only triggers on first use.

### WALK-2: Walk-up boundary is filesystem root

When searching for existing `mars.toml`, the system shall walk from cwd to filesystem root. Git boundaries do not stop the walk.

**Rationale**: Git is not a requirement. A `mars.toml` in any ancestor directory is a valid project root.

### WALK-3: Windows drive root termination

When the walk-up reaches a Windows drive root (e.g., `C:\`), `Path::parent()` returns `None`. The system shall treat this as filesystem root and terminate the walk-up.

**Rationale**: Windows filesystem roots are drive letters, not `/`. The walk-up must terminate correctly on all platforms.

### WALK-4: UNC path handling

When the walk-up encounters a UNC path (e.g., `\\server\share\project`), the system shall walk up through directories and terminate when `Path::parent()` returns `None` at the server/share root.

**Rationale**: UNC paths are valid project locations on Windows. Walk-up should work identically.

### FAIL-1: Init-required commands fail on missing config

When a command classified as init-required is invoked and no `mars.toml` exists in the cwd-to-root walk, the system shall error with:
```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

**Rationale**: These commands have no clear project-setup intent. Failing fast is safer than guessing.

### PATH-1: Path style normalization

When `--root` accepts a path, the system shall accept both forward-slash (`C:/project`) and backslash (`C:\project`) styles on Windows. Path display in messages shall use the platform-native style.

**Rationale**: Windows supports both slash styles. Users should not be rejected for using either.

### PATH-2: Extended-length path handling

When `canonicalize()` returns an extended-length path on Windows (prefixed with `\\?\`), the system shall use the canonicalized path for filesystem operations and `display()` for user-facing messages.

**Rationale**: Extended-length paths are correct but verbose in messages.

## Non-requirements

- **Git detection**: Git presence does not affect bootstrap or walk-up behavior.
- **Prompting**: No interactive confirmation before auto-init. Intent is clear from command + arguments.
- **`--init` flag**: No explicit flag to enable auto-init on `add`. It is always on.
- **`--no-init` flag**: Not needed initially. Can be added later if users want to fail-fast on missing config.
- **Project marker heuristics**: No scanning for `pyproject.toml`, `package.json`, etc. The user's cwd is the signal.

## Error Messages

### Missing config (init-required command)

```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

### Permission errors

Standard I/O errors surface naturally. No special handling.

## Tradeoffs

### Risk: Auto-init in wrong directory

**Scenario**: User is in `/project/src/lib` and runs `mars add owner/repo`. Auto-init creates `/project/src/lib/mars.toml` instead of `/project/mars.toml`.

**Mitigations**:
1. Clear message shows exactly where config was created
2. User explicitly ran the command from this directory
3. Easy recovery: delete `mars.toml`, cd to correct location, retry
4. Walk-up finds existing config, so this only happens on first use

### Risk: Expanding allowlist over time

**Scenario**: Adding more commands to the auto-init allowlist dilutes the safety of init-required classification.

**Mitigation**: The allowlist is explicit in this spec. Adding a command requires updating this document and justifying the intent-is-clear criterion.

### Benefit: Single bootstrap model

All bootstrap paths share the same behavior. Users learn one model (`init`), and auto-init is a convenience that reuses it. No hidden one-off bootstrap modes.

## Comparison to other tools

| Tool | First-use behavior |
|------|-------------------|
| `npm install <pkg>` | Creates package.json at cwd |
| `cargo add <crate>` | Errors if no Cargo.toml |
| `pip install` | No project file needed |
| `go mod init` + `go get` | Two-step |
| `uv add` | Errors if no project file |
| **mars add (new)** | Auto-inits at cwd, then adds |

The npm model is the closest match for `add`: single command works on first use.

## Follow-On Design Tracks

These concerns are scoped out of this design:

### 1. Remove accidental git assumptions

The current implementation of `find_agents_root_from()` stops at `.git` boundaries. This design specifies git-agnostic walk-up, but a focused implementation pass is needed to:
- Remove the `.git` check from walk-up
- Update error messages that reference "repository root"
- Remove or update tests that assume git boundaries

This is a discrete refactor, not part of the auto-init feature.

### 2. Repo-wide Windows compatibility

While this design specifies Windows-correct behavior for bootstrap/walk-up, a separate repo-wide audit is needed to ensure Windows compatibility across all mars commands and the sync/install pipeline. That audit should cover:
- Path handling in source resolution
- File operations in the install pipeline
- Shell invocations and process spawning
- Extended-length path support beyond root discovery

This is its own design track with its own scope.
