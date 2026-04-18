# A03: Workspace Model

## Summary

The workspace file is local-only and user-facing, but the internal model cannot
be a flat `list[Path]` if launch ordering, applicability, and diagnostics are
meant to stay correct. The target shape keeps the user-facing TOML minimal while
splitting the internal model into three layers: parsed document, evaluated
snapshot, and harness-owned projection.

## Realizes

- `../spec/workspace-file.md` — `WS-1.u2`, `WS-1.u3`, `WS-1.u4`, `WS-1.s1`, `WS-1.e1`, `WS-1.e2`, `WS-1.c1`
- `../spec/context-root-injection.md` — `CTX-1.u1`, `CTX-1.e1`
- `../spec/surfacing.md` — `SURF-1.e1`, `SURF-1.e2`

## Current State

- There is no workspace file or workspace read model in the current checkout.
- The prior round proposed a lossy `context_directories() -> list[Path]`
  abstraction, but reviewers rejected it because ordering and provenance matter
  to launch behavior (`prior-round-feedback.md:17-21`).
- Probe evidence confirmed that first-seen ordering is load-bearing anywhere
  dedupe happens (`probe-evidence/probes.md:20-47`).

## Target State

Use a minimal user-facing TOML schema:

```toml
[[context-roots]]
path = "../mars-agents"
enabled = true
```

The internal model is split into three types with distinct responsibilities. The
user-facing schema stays minimal; the internal types stay rich.

### `WorkspaceConfig` — parsed document only

```text
WorkspaceConfig
  path: Path
  context_roots: tuple[ContextRoot, ...]
  unknown_top_level_keys: tuple[str, ...]
  warnings: tuple[str, ...]
```

Contract:

- Represents a successfully parsed document.
- Does not evaluate filesystem existence or harness support.
- Unknown keys survive parsing and surface as warnings.

```text
ContextRoot
  path: str
  enabled: bool = True
  extra_keys: Mapping[str, object]
```

`extra_keys` preserves unknown per-entry keys for warnings and forward-compatible
round-tripping without expanding the v1 user schema.

### `WorkspaceSnapshot` — evaluated state

```text
WorkspaceStatus = none | present | invalid

WorkspaceSnapshot
  status: WorkspaceStatus
  path: Path | None
  roots: tuple[ResolvedContextRoot, ...]
  unknown_keys: tuple[str, ...]
  findings: tuple[str, ...]

ResolvedContextRoot
  declared_path: str
  resolved_path: Path
  enabled: bool
  exists: bool
```

Contract:

- Single shared inspection object for `config show`, `doctor`, and launch
  preparation.
- Built by evaluating a `WorkspaceConfig` against the filesystem.
- `status=invalid` keeps the file path and findings so inspection commands can
  continue.
- `status=none` is the quiet state for single-repo users (no workspace file).
- `status=present` indicates a valid workspace file was found and parsed.
- `roots` includes disabled and missing entries so diagnostics can report counts
  without reparsing.

### `HarnessWorkspaceProjection` — harness-owned launch contract

See [harness-integration.md](harness-integration.md) for the adapter boundary and
per-harness mechanics. The workspace model owns the fact that this is the third
layer in the split.

```text
HarnessWorkspaceSupport =
  active:add_dir
  | active:permission_allowlist
  | ignored:read_only_sandbox
  | unsupported:<reason>

HarnessWorkspaceProjection
  applicability: HarnessWorkspaceSupport
  extra_args: tuple[str, ...]
  config_overlay: Mapping[str, object] | None
  env_additions: Mapping[str, str]
  diagnostics: tuple[str, ...]
```

Contract:

- Transport-neutral output from `src/meridian/lib/launch/context_roots.py` and
  the selected harness adapter.
- Replaces the prior `WorkspaceLaunchDirectives` idea, which was too tied to
  direct `--add-dir` emitters.
- Can represent direct CLI flags (Claude, Codex) and config/env-based access
  mechanisms (OpenCode) without changing the workspace parser or snapshot model.
- Keeps applicability and diagnostics attached to the projection itself rather
  than forcing the surfacing layer to re-derive them.

### Resolution rules

- Resolve relative root paths relative to the containing workspace file, not the
  process cwd.
- Preserve declaration order across all three layers.
- Preserve unknown keys at both file scope and root-entry scope so future
  versions can round-trip them.
- Treat enabled-but-missing roots as snapshot findings; omit them before
  projection.

### Validation tiers

| Condition | Status | Launch impact | Inspection impact |
|---|---|---|---|
| No file next to `.meridian/` | `none` | no workspace behavior | no warnings |
| Parse/schema error | `invalid` | fatal for workspace-dependent commands | surfaced, non-fatal |
| Unknown key | `present` | non-fatal | warning |
| Enabled root missing on disk | `present` | root omitted before projection | warning |

## Init Template Shape

Realizes `../spec/workspace-file.md` — `WS-1.e1`.

### Default template

```toml
# Workspace topology — local-only, gitignored.
# Uncomment and fill paths to enable workspace roots.

# [[context-roots]]
# path = "../sibling-repo"
# enabled = true
```

Template properties:
- Starts with a header comment explaining the file's purpose and gitignored status.
- Emits commented `[[context-roots]]` entries rather than active ones.
- Does not include filesystem-path heuristics (no `~/gitrepos/...` guesses).
- Init is idempotent: if `workspace.local.toml` already exists, the command reports the file exists and does not overwrite.

## Design Notes

- The user-facing schema stays minimal on purpose. The internal richness belongs
  in `ContextRoot.extra_keys`, `WorkspaceSnapshot`, and
  `HarnessWorkspaceProjection`, not in v1 TOML boilerplate.
- This model keeps the door open for future per-root tags or access metadata
  without having to redesign the parser around a flat list later.
- `MERIDIAN_WORKSPACE` override support is deferred to a future version.
- Per D27, the workspace model lives in repo-level config (`workspace.local.toml`), but any runtime state it generates lives under `$MERIDIAN_HOME/projects/<project-key>/`. The workspace model is a topology declaration; it does not create runtime directories in the repo.

## Open Questions

None at the workspace-model layer. Open transport questions live in
[harness-integration.md](harness-integration.md).
