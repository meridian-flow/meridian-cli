# Behavioral Spec: mars add Bootstrap

## Overview

When `mars add` runs and no `mars.toml` exists, the system should auto-create `mars.toml` at the bootstrap target and continue with the add operation — eliminating the separate `mars init` step for first-use.

## Root Selection Rule

**Bootstrap at current working directory.** Git is not consulted.

The user invoked `mars add` from a specific directory. That is the project root unless `--root` says otherwise.

## EARS Statements

### BOOT-1: Auto-bootstrap at cwd

When `mars add` is invoked and no `mars.toml` exists anywhere in the cwd-to-root walk, the system shall create `mars.toml` at the current working directory, then continue with the add operation.

**Rationale**: `mars add` carries clear mutation intent. The user ran it from this directory. Requiring a separate init step is friction without benefit.

### BOOT-2: Walk-up still finds existing config

When `mars add` is invoked and `mars.toml` exists in the cwd or any ancestor directory, the system shall use the existing config (nearest wins). No bootstrap occurs.

**Rationale**: Existing projects work unchanged. Bootstrap only triggers on first use.

### BOOT-3: Explicit --root with no mars.toml

When `mars add --root <path>` is invoked and `<path>` does not contain `mars.toml`, the system shall auto-bootstrap at `<path>` (creating `mars.toml` and `.agents/`), then continue with the add operation.

**Rationale**: `--root` is an explicit declaration of project location. The user has already made the placement decision.

### BOOT-4: Explicit --root overrides cwd

When `mars add --root <path>` is invoked, the system shall use `<path>` as the project root regardless of cwd or any ancestor config files.

**Rationale**: `--root` is the escape hatch for non-standard layouts. It must win unconditionally.

### BOOT-5: Non-interactive consistency

When `mars add` runs in non-interactive mode (CI, scripts, spawns), the system shall behave identically to interactive mode — auto-bootstrap at cwd when safe, no prompts.

**Rationale**: Prompting in CI would hang. The bootstrap location is deterministic and logged, so scripts can verify.

### BOOT-6: Bootstrap creates minimal config

When auto-bootstrap creates `mars.toml`, the content shall be `[dependencies]\n` only — no comments, no settings, no managed_root override.

**Rationale**: Minimal config is easier to read and modify. `.agents/` is the default managed root; specifying it adds noise.

### BOOT-7: Bootstrap creates managed directory

When auto-bootstrap creates `mars.toml`, the system shall also create the `.agents/` directory if it does not exist.

**Rationale**: The add operation will fail immediately if the managed directory is missing. Batch both creations.

### BOOT-8: Idempotent on existing config

When `mars add` runs and `mars.toml` already exists (found via walk-up or --root), the system shall not modify it (except to add the new dependency entry). Bootstrap is a no-op.

**Rationale**: Re-running `mars add` on an established project must not reset or overwrite config.

### BOOT-9: Bootstrap message

When auto-bootstrap creates `mars.toml`, the system shall print a status message (unless `--json`):
```
initialized <path> with mars.toml
```

**Rationale**: The user should know that config was created and where. This surfaces mistakes immediately if the user ran from the wrong directory.

### BOOT-10: Walk-up boundary is filesystem root

When searching for existing `mars.toml`, the system shall walk from cwd to filesystem root. There is no git-based boundary.

**Rationale**: Git is not a requirement. A `mars.toml` in any ancestor directory is a valid project root.

## Non-requirements

- **Git detection**: Git presence does not affect bootstrap behavior.
- **Prompting**: No interactive confirmation before auto-bootstrap. The intent is already clear from `mars add <source>`.
- **`--init` flag**: No explicit flag to enable auto-bootstrap. It is always on when config is missing.
- **`--no-init` flag**: Not needed initially. Can be added later if users want to fail-fast on missing config.
- **Project marker heuristics**: No scanning for `pyproject.toml`, `package.json`, etc. The user's cwd is the signal.

## Error Messages

### Walk-up with --root conflict

If `--root` points to a different project than what walk-up would find, `--root` wins. No error — it's the expected escape hatch.

### Permission errors

Standard I/O errors surface naturally. No special handling.

## Tradeoffs

### Risk: Bootstrap in wrong directory

**Scenario**: User is in `/project/src/lib` and runs `mars add owner/repo`. Bootstrap creates `/project/src/lib/mars.toml` instead of `/project/mars.toml`.

**Mitigations**:
1. Clear message shows exactly where config was created
2. User explicitly ran the command from this directory
3. Easy recovery: delete `mars.toml`, cd to correct location, retry
4. Walk-up finds existing config, so this only happens on first use

**Alternative rejected**: Prompt before bootstrap — breaks CI/scripts, adds friction for the common case (user is in the right directory).

### Risk: Nested projects

**Scenario**: User has `/project/mars.toml` and runs `mars add` from `/project/subproject`. Walk-up finds `/project/mars.toml` and uses it.

**This is correct behavior**. If the user wanted a separate project, they'd use `--root .` to force cwd.

### Benefit: Works everywhere

Unlike the git-based design, this works in:
- Non-git directories
- Detached worktrees
- Tarball extracts
- Temporary test directories
- Any environment without VCS

### Comparison to other tools

| Tool | First-use behavior |
|------|-------------------|
| `npm install <pkg>` | Creates package.json at cwd |
| `cargo add <crate>` | Errors if no Cargo.toml |
| `pip install` | No project file needed |
| `go mod init` + `go get` | Two-step |
| **mars add (new)** | Creates mars.toml at cwd |

The npm model is the closest match: single command works on first use, creates config at invocation location.
