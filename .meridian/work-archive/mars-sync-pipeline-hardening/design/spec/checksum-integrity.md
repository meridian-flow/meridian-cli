# Spec: Checksum Validation Discipline (R5, R6)

## Mandatory Checksums (R5)

### CKSUM-01: Write-producing actions must yield checksums
When an action produces a write to disk (Install, Overwrite, Merge),
the `ActionOutcome` shall have non-None `installed_checksum`.
If checksum computation fails, the action shall return an error rather than persisting an empty or missing checksum.

### CKSUM-02: Lock file rejects empty checksums
When building a new lock file from apply outcomes,
the system shall error if any write-producing outcome has a None or empty-string `installed_checksum`.
No lock entry shall be persisted with an empty `installed_checksum` or empty `source_checksum`.

### CKSUM-03: Post-write verification
When a file or directory is written to disk during Install or Overwrite,
the system shall re-hash the written content and verify it matches the expected checksum before recording success.
If verification fails, the system shall return an error.

### CKSUM-04: Merge writes must produce checksums
When a merge operation writes merged content to disk,
the system shall compute the checksum of the merged content.
The merge outcome shall carry this checksum as `installed_checksum`.

## Disk-Lock Divergence Detection (R5)

### CKSUM-05: Detect disk-lock divergence on sync start
When sync begins and the lock file contains items,
the system shall compare the on-disk hash of each managed item against the lock's `installed_checksum`.
If any item's disk hash does not match the lock's `installed_checksum`, that item is divergent.

### CKSUM-06: Warn on divergence
When disk-lock divergence is detected for one or more items,
the system shall emit a warning listing the divergent items.

### CKSUM-07: Preserve divergent items
When disk-lock divergence is detected,
the system shall NOT overwrite the divergent content. The local edit is preserved.
The user must run `mars sync --force` or `mars repair` to reset to source state.

### CKSUM-08: Target sync failure reporting and self-healing
When the target sync phase fails to write to a target directory due to permission errors,
the system shall report the failure per-target as a non-fatal error (existing behavior via `DiagnosticCollector`).
The lock file's `installed_checksum` SHALL still advance (`.mars/` canonical store has correct content).
On the next sync, the target sync phase shall detect that target content diverges from `.mars/` content and re-copy, self-healing the stale target.

**Rationale:** The lock tracks `.mars/` state, not target state. Blocking lock advancement would force a wasteful re-fetch from source on the next sync. The self-healing approach (CKSUM-09) catches both the permission-failure case and the manual-edit case.

### CKSUM-09: Target divergence detection and reporting
When target sync processes skipped items (items unchanged in `.mars/`),
the system shall verify that each target's content matches the `.mars/` canonical content.
If target content is missing, the system shall re-copy from `.mars/` to the target.
If target content exists but diverges (different hash from manual edit or failed prior copy),
the system shall warn the user and preserve the local content.
The user must run `mars sync --force` or `mars repair` to reset divergent targets to canonical state.

## Unix Permission Gating (R6)

### PERM-01: Unix permissions behind cfg(unix)
The existing `#[cfg(unix)]` gating on `PermissionsExt` usage shall be preserved.
On non-Unix platforms, the system shall use default file permissions.

### PERM-02: Read-only file overwrite on Windows
When overwriting an existing file during sync on Windows,
the system shall handle read-only files gracefully.
If a file is read-only and cannot be overwritten, the system shall attempt to clear the read-only attribute before writing, or report a clear error.
