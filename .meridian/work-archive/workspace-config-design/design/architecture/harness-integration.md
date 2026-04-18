# A04: Harness Integration

## Summary

Workspace topology is policy. Granting one harness access to those roots is
mechanism. The boundary is a harness-owned `HarnessWorkspaceProjection`
contract: launch code computes the ordered set of enabled existing roots once,
asks the selected adapter to project them, then merges the returned args/env and
surfaces the returned diagnostics without branching on harness-specific
mechanics.

## Realizes

- `../spec/context-root-injection.md` — `CTX-1.u1`, `CTX-1.u2`, `CTX-1.e1`, `CTX-1.w1`, `CTX-1.w2`
- `../spec/surfacing.md` — `SURF-1.u1`, `SURF-1.e4`

## External Dependencies

This architecture leaf depends on the **launch-core-refactor** work item. The workspace projection is a pipeline stage (`apply_workspace_projection()`) that plugs into the launch domain core's factory. Without the single-composition-seam invariant, workspace projection would need independent wiring into each driving adapter.

## Current State

- Adapter contracts stop at `resolve_launch_spec()` and `preflight()` in
  `src/meridian/lib/harness/adapter.py:224-247`.
- Claude injects `--add-dir` inline during preflight in
  `src/meridian/lib/harness/claude_preflight.py:120-166`.
- Codex command projection has no workspace-root seam; it appends
  `spec.extra_args` directly in
  `src/meridian/lib/harness/projections/project_codex_subprocess.py:189-227`.
- OpenCode command projection likewise has no workspace-root seam; it only
  projects flags and passthrough args in
  `src/meridian/lib/harness/projections/project_opencode_subprocess.py:83-160`.
- Spawn launch assembly has one composition seam today:
  `src/meridian/lib/launch/context.py:148-223` builds preflight output,
  `SpawnParams`, resolved launch spec, and merged env for spawned subprocess
  harnesses.
- Primary launch still bypasses that seam and composes the same launch inputs in
  `src/meridian/lib/launch/plan.py:149-343`,
  `src/meridian/lib/launch/process.py:273-325`, and
  `src/meridian/lib/launch/command.py:16-28`.

The missing piece is not another shared `add_dirs` list. The missing piece is a
harness-owned projection interface that can represent both direct CLI args and
non-CLI mechanisms such as OpenCode config overlays.

## Target State

### Ordered-root planner

`src/meridian/lib/launch/context_roots.py` is the only place that decides which
workspace roots participate in one launch and in what order.

Responsibilities:

- Start from `WorkspaceSnapshot`.
- Keep only roots that are `enabled` and `exists`.
- Preserve declaration order from `workspace.local.toml`.
- Enforce the fixed ordering rule:
  `user passthrough -> projection-managed -> workspace-emitted`.
- Hand the resulting ordered roots plus launch context to the selected adapter.

The launch layer owns ordering. Adapters own mechanism.

### Projection types

`src/meridian/lib/harness/workspace_projection.py` owns the transport-neutral
types.

```python
type HarnessWorkspaceSupport = (
    "active:add_dir"
    | "active:permission_allowlist"
    | "ignored:read_only_sandbox"
    | f"unsupported:{reason}"
)


@dataclass(frozen=True)
class HarnessWorkspaceProjection:
    applicability: HarnessWorkspaceSupport
    extra_args: tuple[str, ...] = ()
    config_overlay: Mapping[str, object] | None = None
    env_additions: Mapping[str, str] = MappingProxyType({})
    diagnostics: tuple[str, ...] = ()
```

`config_overlay` stays in the contract even when the transport is environment
based. That keeps the semantic patch inspectable in tests and diagnostics rather
than hiding it inside an opaque env string. `env_additions` carries the
adapter-owned transport materialization, so launch composition still merges data
without knowing how any harness encodes it.

### Adapter contract

Extend the subprocess-harness contract with one adapter-owned method:

```python
def project_workspace(
    self,
    *,
    roots: tuple[Path, ...],
    execution_cwd: Path,
    child_cwd: Path,
    spec: ResolvedLaunchSpec,
) -> HarnessWorkspaceProjection: ...
```

Why this shape:

- It matches the existing contract style in
  `src/meridian/lib/harness/adapter.py:224-247`: the adapter owns harness
  translation, not a global registry of special cases.
- `spec` provides the effective harness configuration already resolved by the
  adapter, including permission state needed for Codex read-only handling.
- `execution_cwd` and `child_cwd` keep Claude's existing child-worktree logic
  available without hardcoding Claude behavior into launch assembly.

### Session-ID observation

Extend the adapter contract with a post-execution session-ID observation method:

```python
@dataclass(frozen=True)
class LaunchOutcome:
    """Raw executor output before adapter post-processing."""
    exit_code: int
    child_pid: int | None
    captured_stdout: bytes | None  # PTY-captured output, if any

@dataclass(frozen=True)
class LaunchResult:
    """Post-processed launch result returned to driving adapters."""
    exit_code: int
    child_pid: int | None
    session_id: str | None  # populated by adapter.observe_session_id()

def observe_session_id(
    self,
    *,
    launch_context: NormalLaunchContext,
    launch_outcome: LaunchOutcome,
) -> str | None: ...
```

Why this shape:

- Session-ID is a post-launch observable, not a launch input. Moving it off
  `LaunchContext` (which is frozen, all-required) and onto `LaunchResult`
  makes the plan object genuinely complete at construction time.
- The adapter owns the observation mechanism and returns what it observed.
  Claude's PTY path scrapes terminal output; Codex streaming reads
  `connection.session_id` set during WebSocket thread bootstrap
  (`src/meridian/lib/harness/connections/codex_ws.py:190,270`); OpenCode
  streaming reads `connection.session_id` set during session creation
  (`src/meridian/lib/harness/connections/opencode_http.py:137,166`).
  `observe_session_id()` reads per-launch inputs only — either parsed from
  `launch_outcome.captured_stdout` (for harnesses whose executor's PTY mode
  populated it) or read from per-launch state reachable via
  `launch_context` (e.g. connection objects for HTTP/WS-driven harnesses).
  The adapter MUST NOT hold session state on the adapter-class instance
  shared across launches. Executors return raw `LaunchOutcome`; the driving
  adapter calls `observe_session_id()` and assembles `LaunchResult`.
  Executors stay mechanism-agnostic.
- When observability fails (e.g., Popen fallback with today's scrape-only
  Claude impl), `session_id = None`. The surfacing layer already handles
  missing-session-id. GitHub issue #34 tracks moving to filesystem polling,
  which removes the Popen-path degradation without touching executors.

The mechanism swap to filesystem polling is GitHub issue #34 — out of scope for workspace-config-design.

### Launch composition

Post-launch-core-refactor, Meridian launch uses a hexagonal (ports and adapters) architecture
with 3 driving adapters, 1 factory, and 3 driven adapters (harness
implementations). The domain core lives in `src/meridian/lib/launch/context.py`;
`build_launch_context()` is the factory that orchestrates a pipeline of
composition stages and returns a complete
`LaunchContext = NormalLaunchContext | BypassLaunchContext`.

```
Primary launch ─┐
                 │
Worker         ─┼──▶ build_launch_context() ──▶ LaunchContext ──▶ executor ──▶ harness adapter
                 │    (driving port / factory)                     (PTY or async)  (driven port)
App streaming  ─┘
                 │
Dry-run        ─┘ (preview only)
```

Workspace projection is its own pipeline stage inside the
`build_launch_context()` factory — `apply_workspace_projection()` —
sitting between `resolve_launch_spec_stage()` (which calls
`harness.resolve_launch_spec`) and `build_launch_argv()` (which calls
`harness.build_command`). The stage receives the resolved spec, calls
`adapter.project_workspace()` once, returns the spec with `extra_args`
extended by `projection.extra_args`, and `build_launch_argv` then assembles
the final argv.

Composition contract:

1. `context_roots.py` computes ordered enabled existing roots.
2. `harness.project_workspace(...)` returns one
   `HarnessWorkspaceProjection`.
3. `projection.extra_args` appends to the resolved spec's `extra_args` tail.
4. `projection.env_additions` merges with runtime, plan, and preflight env
   overrides before `build_harness_child_env(...)`.
5. `projection.config_overlay` is preserved for surfacing/tests and is the
   semantic source of any harness-specific transport already reflected in
   `env_additions`.
6. `projection.diagnostics` flows to `config show`, `doctor`, and the selected
   launch's warning/debug lanes.

The launch layer does not branch on Claude vs Codex vs OpenCode. It merges one
projection object at one seam.

## Per-Harness Projection

### Claude

Mechanism:

- One enabled existing workspace root projects to
  `("--add-dir", "<abs-path>")` in `extra_args`.
- `applicability = "active:add_dir"`.
- `config_overlay = None`.
- `env_additions = {}`.

Ordering:

- Existing preflight behavior remains the projection-managed middle section:
  user passthrough, then `execution_cwd`, then parent
  `additionalDirectories` from `.claude/settings*.json`
  (`src/meridian/lib/harness/claude_preflight.py:120-147`).
- Workspace roots append after those parent-forwarded directories.
- First-seen dedupe remains authoritative
  (`src/meridian/lib/launch/text_utils.py:8-19`), so explicit user
  `--add-dir` values stay first and survive dedupe.

Target result:

```text
<user passthrough --add-dir ...>
<projection-managed execution_cwd>
<projection-managed parent additionalDirectories>
<workspace-emitted roots>
```

### Codex

**Status:** Deferred to `harness-permission-abstraction` work item per D-POST-REVIEW.

Mechanism understanding (empirical, 2026-04-17, per D25):

- **Workspace shaping:** `--cd <dir>` sets primary workspace + `--add-dir <dir>` for extra writable roots. These are workspace projection mechanisms, not home isolation.
- **Limitation:** `--add-dir` grants write access only, NOT read access. Read-only directory access requires `CODEX_HOME` config generation with permission profiles.
- **Home isolation:** `CODEX_HOME` controls where Codex stores native state (auth, sessions, config). It is NOT for extra workspace roots — that is a key distinction per D25.
- **Auth bootstrap:** Fresh isolated `CODEX_HOME` environments empirically require auth bootstrap. Treat Codex home as a monolithic native-state boundary unless upstream docs expose a split auth/state mechanism.

V1 behavior:

- `applicability = "unsupported:requires_config_generation"`.
- `extra_args = ()`, no projection.
- Users check `config show` or `doctor` for applicability status.

Future design (harness-permission-abstraction):

- Full workspace projection requires Meridian-managed `CODEX_HOME` with projected permission profiles.
- Per-project isolated homes at `$MERIDIAN_HOME/projects/<project-key>/spawns/<spawn-id>/codex-home/` (see `runtime-home.md` A00, `paths-layer.md` A01 per D27).
- The `MERIDIAN_HOME` concept from D27 directly enables this: user-level runtime state is already keyed by `spawn_id`, so projected harness homes fit naturally.
- Auth bootstrap handling as part of isolated-home lifecycle.

### OpenCode

Mechanism understanding (empirical, 2026-04-17, per D25):

- **No `--add-dir` equivalent:** OpenCode does not have a direct workspace-root flag like Claude or Codex. Extra-path access is permission-based, not topology-based.
- **Extra-path access:** Handled via launch root (the directory passed to opencode invocation) plus config/permissions such as `permission.external_directory`.
- **Config transport:** `OPENCODE_CONFIG_CONTENT` environment variable carries inline config overlays.

V1 projection:

- Meridian projects enabled existing workspace roots into:

```json
{
  "permission": {
    "external_directory": [
      "/abs/root-1",
      "/abs/root-2"
    ]
  }
}
```

- `config_overlay` carries that semantic patch.
- `env_additions` carries the transport materialization:
  `{"OPENCODE_CONFIG_CONTENT": "<serialized-json>"}`.
- `applicability = "active:permission_allowlist"`.

Semantic gap:

- This is day-1 support, not fake `--add-dir` parity.
- OpenCode's native file tools gain access to the extra roots, but the harness
  does not surface them as named workspace roots in its UX.
- The roots behave like extra allowlisted directories beside the primary project
  root, not like a visible multi-root workspace list.

Alternative rejected:

- MCP filesystem servers were considered but rejected for day-1 support because
  they change the interaction model for extra roots instead of extending the
  same native file-tool path the primary root already uses
  (`opencode-probe-findings.md §4` and `§8`).

## Applicability Contract

`HarnessWorkspaceSupport` values are precise because surfacing depends on them.

| Value | Meaning | Expected harnesses |
|---|---|---|
| `active:add_dir` | Workspace roots are projected as repeated `--add-dir` args. | Claude |
| `active:permission_allowlist` | Workspace roots are projected through a config overlay that grants file-tool access. | OpenCode |
| `ignored:read_only_sandbox` | Harness selected a mode where workspace projection is inert for this launch. | (reserved for future Codex use) |
| `unsupported:requires_config_generation` | Harness needs Meridian-managed home/config generation for workspace projection. | Codex (v1) |
| `unsupported:<reason>` | Harness has no workspace-root mechanism yet. | future harnesses |

Note: Codex workspace projection is deferred to `harness-permission-abstraction` per D-POST-REVIEW. V1 returns `unsupported:requires_config_generation` because `--add-dir` only grants write access, not read access. Full workspace projection requires `CODEX_HOME` config generation with permission profiles.

## Diagnostics

Projection diagnostics are per-invocation findings emitted by the adapter.

Required cases:

- Codex read-only sandbox ignored-state diagnostic.
- Future `unsupported:*` diagnostic with reason.
- Optional debug diagnostic when OpenCode delivered a permission-allowlist
  overlay instead of direct workspace-root UX.

Missing roots are not projection diagnostics. They are snapshot findings owned
by `WorkspaceSnapshot` and surfaced by the surfacing layer.

## Resolved Behaviors

- Per D15, if a parent environment already sets `OPENCODE_CONFIG_CONTENT`, the
  OpenCode adapter skips workspace projection and records a
  `HarnessWorkspaceProjection.diagnostics` entry for that invocation
  (`workspace_projection_suppressed_parent_opencode_config_content`). The
  parent environment value wins; Meridian does not deep-merge or overwrite it.
- Per D16, subprocess and streaming launches use the same
  `HarnessWorkspaceProjection.env_additions` channel. Both paths reach
  `asyncio.create_subprocess_exec(..., env=env)`, so OpenCode workspace
  projection reaches the child process identically regardless of transport.
