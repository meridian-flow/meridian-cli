# WS-1: Workspace Topology File

## Context

Workspace configuration is a local topology declaration, not shared project policy. The file therefore has to encode locality in its name, stay optional for single-repo users, and remain minimal even though the internal model needs richer structure.

**Realized by:** `../architecture/paths-layer.md`, `../architecture/workspace-model.md`, `../architecture/surfacing-layer.md`.

## EARS Requirements

### WS-1.u1 — The workspace file name encodes locality

`The workspace topology file shall be named workspace.local.toml, shall be treated as local-only configuration, shall be gitignored by default, and shall not be introduced under the ambiguous name workspace.toml.`

### WS-1.u2 — Discovery uses the canonical location

`Workspace file discovery shall use workspace.local.toml located next to the active .meridian/ directory when that file exists, and otherwise shall treat workspace topology as absent.`

### WS-1.u3 — The v1 schema stays minimal and topology-only

`The v1 user-facing workspace file schema shall use [[context-roots]] entries with required path and optional enabled fields, shall not contain a [settings] table, and shall default enabled to true when omitted.`

### WS-1.u4 — Path resolution is relative to the workspace file

`Relative paths in [[context-roots]] entries shall be resolved relative to the directory containing the workspace file, not relative to the process working directory or the active .meridian/ directory.`

### WS-1.s1 — Absent workspace file means zero added behavior

`While no workspace file is present, Meridian shall behave as a single-repository installation and shall not emit workspace warnings or prompts.`

Note: The single-repository behavior is realized through the absence of workspace-derived launch directives (see `../architecture/workspace-model.md`, `status=absent` handling). The "no prompts" requirement is realized through the surfacing layer (see `../architecture/surfacing-layer.md`, quiet-state handling for `workspace.status=none`).

### WS-1.e1 — Default init creates a minimal file with commented examples

`When workspace init runs and workspace.local.toml does not exist, Meridian shall create a minimal workspace.local.toml containing commented examples rather than active roots. When workspace.local.toml already exists, Meridian shall not overwrite it and shall report that the file already exists.`

### WS-1.e2 — Unknown keys are preserved and surfaced

`When Meridian parses workspace.local.toml and encounters unknown keys, Meridian shall preserve those keys for forward compatibility and shall surface them as warnings rather than dropping them or treating them as silent debug-only metadata.`

### WS-1.c1 — Invalid workspace files are fatal only on workspace-dependent commands

`While workspace.local.toml is syntactically invalid or violates schema requirements, commands that require workspace-derived directories shall fail before harness launch, and commands that only inspect state shall continue and surface the invalid status.`

## Non-Requirement Edge Cases

- **No auto-detection of local checkouts.** Workspace roots are user-declared, not discovered.
- **No per-harness subsets in v1.** The file declares one root set for all supporting harnesses.
- **No `MERIDIAN_WORKSPACE` override in v1.** Environment-variable overrides are a future enhancement.
- **No `workspace init --from mars.toml` in v1.** Scaffold generation from mars.toml is deferred.
