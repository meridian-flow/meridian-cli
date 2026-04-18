# Behavioral Spec: mars add Bootstrap

## Overview

When `mars add` runs and no `mars.toml` exists, the system should auto-create `mars.toml` at the detected project root and continue with the add operation — eliminating the separate `mars init` step for first-use.

## EARS Statements

### BOOT-1: Auto-bootstrap in git repo

When `mars add` is invoked from within a git repository and no `mars.toml` exists at the detected project root, the system shall create `mars.toml` with `[dependencies]` at the project root, then continue with the add operation.

**Rationale**: `mars add` carries clear mutation intent. Requiring a separate init step is friction without benefit.

### BOOT-2: Git root as project root

When `mars add` auto-bootstraps, the system shall place `mars.toml` at the git repository root (the directory containing `.git`), not at the current working directory.

**Rationale**: The git root is the canonical project boundary. Placing config anywhere else risks creating orphaned state.

### BOOT-3: Submodule boundary

When `mars add` is invoked from within a git submodule, the system shall bootstrap at the submodule root (where the `.git` file or directory exists), not the parent repository.

**Rationale**: Submodules are independent units with their own package manifests.

### BOOT-4: No git repo detected

When `mars add` is invoked from a directory that is not inside any git repository, the system shall fail with an actionable error message suggesting `mars init` or `--root`.

**Rationale**: Without a git boundary, there is no safe place to create config. Auto-creating at cwd risks pollution of arbitrary directories.

### BOOT-5: Explicit --root with no mars.toml

When `mars add --root <path>` is invoked and `<path>` does not contain `mars.toml`, the system shall auto-bootstrap at `<path>` (creating `mars.toml` and `.agents/`), then continue with the add operation.

**Rationale**: `--root` is an explicit declaration of project location. The user has already made the placement decision.

### BOOT-6: Non-interactive consistency

When `mars add` runs in non-interactive mode (CI, scripts, spawns), the system shall behave identically to interactive mode — auto-bootstrap when safe, error when unsafe, no prompts.

**Rationale**: Prompting in CI would hang. The safety rules are strict enough that interactive confirmation adds no value.

### BOOT-7: Bootstrap creates minimal config

When auto-bootstrap creates `mars.toml`, the content shall be `[dependencies]\n` only — no comments, no settings, no managed_root override.

**Rationale**: Minimal config is easier to read and modify. `.agents/` is the default managed root; specifying it adds noise.

### BOOT-8: Bootstrap creates managed directory

When auto-bootstrap creates `mars.toml`, the system shall also create the `.agents/` directory if it does not exist.

**Rationale**: The add operation will fail immediately if the managed directory is missing. Batch both creations.

### BOOT-9: Idempotent on existing config

When `mars add` runs and `mars.toml` already exists, the system shall not modify it (except to add the new dependency entry). Bootstrap is a no-op.

**Rationale**: Re-running `mars add` on an established project must not reset or overwrite config.

### BOOT-10: Bootstrap message

When auto-bootstrap creates `mars.toml`, the system shall print a status message (unless `--json`):
```
initialized <path> with mars.toml
```

**Rationale**: The user should know that config was created, not just that the add succeeded.

## Non-requirements

- **Prompting**: No interactive confirmation before auto-bootstrap. The intent is already clear from `mars add <source>`.
- **`--init` flag**: No explicit flag to enable auto-bootstrap. It is always on when safe.
- **`--no-init` flag**: Not needed initially. Can be added later if users want to fail-fast on missing config.
- **Config migration**: Bootstrap does not migrate from legacy config files. That is a separate concern.

## Error Messages

### BOOT-4 error (no git repo)

```
error: no git repository found from <cwd> to filesystem root.
hint: run `mars init` to create mars.toml here, or use `mars add --root <path>` to specify the project root.
```

### BOOT-5 recovery path (--root without mars.toml)

This is success, not error. Bootstrap proceeds at the specified root.
