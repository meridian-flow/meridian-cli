# Decisions Log — workspace-config (redesign round)

Round: fresh redesign after a unanimous 5-0 reject of the prior design. Requirements
(`requirements.md`) are unchanged. This file records the addressed-or-rejected mapping
against `prior-round-feedback.md` (findings F1–F19) plus the non-trivial design calls
made during this round.

Evidence citations point at `probe-evidence/probes.md` and the live meridian-cli
checkout. Spec and architecture IDs point at the files under `design/spec/` and
`design/architecture/`.

## Prior-round findings (F1–F19) mapping

Each row states: the finding, the design response (addressed vs rejected), the spec
and architecture leaves that encode the response, and the evidence basis.

### F1 — Codex CLI has `codex exec --add-dir`
**Status:** Addressed.
**Response:** Design commits to codex as a supported target in v1. Workspace roots
reach codex through `codex exec --add-dir` in the codex projection.
**Encoded in:** `design/spec/context-root-injection.md` (`CTX-1.u1`);
`design/architecture/harness-integration.md` (A04 "Codex" section);
`design/feasibility.md` FV-1.
**Evidence:** `probe-evidence/probes.md §1` — captured `codex exec --help` output on
codex-cli 0.120.0 showing `--add-dir <DIR>` flag.

### F2 — Mars owns model-alias resolution; no Meridian-side `models.toml` migration is justified
**Status:** Addressed by explicit out-of-scope.
**Response:** Design declares `models.toml` migration out of scope. No spec leaves
reference it. Refactor agenda has no model-alias entry.
**Encoded in:** `design/spec/config-location.md` "Non-Requirement Edge Cases" (no
`models.toml` migration); `design/feasibility.md` FV-3.
**Evidence:** `probe-evidence/probes.md §3` — `rg "models\.toml|models_merged"`
returns zero hits in `src/` and `tests/`; `lib/catalog/model_aliases.py:229`
references `.mars/models-merged.json` only.

### F3 — Meridian config commands bypass the loader's resolver
**Status:** Addressed with dedicated architecture leaf.
**Response:** Introduce one `ProjectConfigState` object shared by the settings
loader AND all five `config` subcommands AND runtime bootstrap AND diagnostics.
Half-migrations (loader-only) are explicitly forbidden.
**Encoded in:** `design/architecture/config-loader.md` (A02 "Command-family
consistency" section enumerates every consumer that must use the shared state);
`design/refactors.md` R02 (exit criteria: "One observed project-config state object
is shared by loader, config commands, bootstrap, and diagnostics. All project-config
reads and writes target `meridian.toml` through that shared state.").
**Evidence:** `probe-evidence/probes.md §4` — enumerated call sites
`lib/ops/config.py:758, 777, 827, 846, 872` all call `_config_path` directly, never
`_resolve_project_toml`.

### F4 — Dedupe ordering inverted last-wins semantics
**Status:** Addressed with explicit pinned ordering.
**Response:** `dedupe_nonempty` is first-seen; design pins emission order as
`user passthrough → projection-managed (execution_cwd, parent additional) → workspace`
on the claude path and `user passthrough (spec.extra_args) → workspace` on the codex
path. Explicit CLI intent wins under first-seen dedupe.
**Encoded in:** `design/spec/context-root-injection.md` `CTX-1.e1` (explicit
`--add-dir` wins), `CTX-1.c1` (projection-managed and parent-forwarded roots keep
precedence over workspace defaults); `design/architecture/harness-integration.md`
A04 "Shared ordered-root planner" and the per-harness subsections;
`design/feasibility.md` FV-2.
**Evidence:** `probe-evidence/probes.md §2` (`lib/launch/text_utils.py:8-19`),
`§5` (claude preflight ordering at `lib/harness/claude_preflight.py:131-147`),
`§6` (codex projection at `lib/harness/projections/project_codex_subprocess.py:189-227`).

### F5 — Flat `list[Path]` abstraction loses ordering and provenance
**Status:** Addressed.
**Response:** User-facing TOML stays minimal (`[[context-roots]]` with `path`,
`enabled`). Internal model carries structured root entries, evaluated
existence/state, unknown keys, and per-harness applicability instead of collapsing
everything into a flat list. This is the "minimal schema, structured internal
model" split the reviewers asked for.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.u3` (v1 schema minimal);
`design/architecture/workspace-model.md` (A03 "Target State" shows the
`WorkspaceRoot` shape).
**Evidence:** `prior-round-feedback.md:17-21` plus `probe-evidence/probes.md §2`
(order is load-bearing because downstream dedupe is first-seen).

### F6 — Silent harness no-op is a footgun
**Status:** Addressed with mandatory surfacing.
**Response:** Per-harness applicability is reported explicitly in `config show`
and `doctor`. Codex read-only sandbox is `ignored:read_only_sandbox`; opencode
is `active:permission_allowlist`; future unimplemented harnesses use
`unsupported:*`. No silent skip anywhere.
**Encoded in:** `design/spec/context-root-injection.md` `CTX-1.w1` (codex
read-only), `CTX-1.w2` (unsupported harnesses surface);
`design/spec/surfacing.md` `SURF-1.e4` (applicability downgrades are explicit),
`SURF-1.u1` (`config show` exposes the minimal workspace summary);
`design/architecture/harness-integration.md` A04 "Applicability reporting";
`design/architecture/surfacing-layer.md` A05 "Doctor Contract".

### F7 — RF-1 was drastically under-scoped
**Status:** Addressed with enumerated blast radius.
**Response:** `design/refactors.md` R02 enumerates every call site
(`lib/config/settings.py`, `lib/ops/config.py`, `lib/ops/runtime.py`,
`lib/ops/manifest.py`, `cli/main.py`, smoke tests, unit tests). Exit criteria
require simultaneous update of read/write/bootstrap/CLI-copy/tests.
**Encoded in:** `design/refactors.md` R02; `design/feasibility.md` FV-4.
**Evidence:** `probe-evidence/probes.md §4` — full enumerated list with line numbers.

### F8 — Root-file policy doesn't belong in `state/paths.py`
**Status:** Addressed.
**Response:** New `ProjectPaths` abstraction owns `meridian.toml`,
`workspace.local.toml`, and repo-root ignore policy.
`StatePaths` stays `.meridian`-scoped.
**Encoded in:** `design/architecture/paths-layer.md` (A01 "Ownership boundary"
table); `design/refactors.md` R01 (prep refactor, exit criteria explicit);
`design/feasibility.md` FV-5.
**Evidence:** `probe-evidence/probes.md §7` —
`lib/state/paths.py:21,33,93-128` shows `.meridian`-only scope.
**Rejected alternative:** Extending `StatePaths` to carry root-file fields —
rejected because it mixes repo-policy and state-root concerns and makes
`.meridian/.gitignore` the wrong owner of repo-root ignore policy.

### F9 — Auto-creating `meridian.toml` on first invocation violates progressive disclosure
**Status:** Addressed.
**Response:** Generic startup creates ONLY `.meridian/` runtime directories and
`.meridian/.gitignore`. `meridian.toml` is created only by explicit
`config init`. `workspace.local.toml` is created only by `workspace init`.
**Encoded in:** `design/spec/bootstrap.md` `BOOT-1.u1` (generic startup creates
runtime state only), `BOOT-1.e1` (init is the only root-config creator),
`BOOT-1.e2` (workspace init is the only workspace-file creator);
`design/feasibility.md` FV-6.
**Evidence:** `probe-evidence/probes.md §8` —
`lib/ops/config.py:737-763` currently auto-writes scaffold unconditionally via
`ensure_state_bootstrap_sync` called from `lib/ops/runtime.py:66`.

### F10 — "Fatal on parse error" is too blunt for inspection commands
**Status:** Addressed.
**Response:** Workspace-dependent commands (spawn, `workspace *`) fail before
launch on invalid workspace file; inspection commands (`config show`, `doctor`)
continue and surface `workspace.status = invalid`.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.c1` (scoped fatality);
`design/spec/surfacing.md` `SURF-1.e1` (inspection commands continue);
`design/architecture/workspace-model.md` A03 "Validation tiers" table;
`design/architecture/surfacing-layer.md` A05.

### F11 — Warn-on-every-missing-path becomes spawn noise
**Status:** Addressed.
**Response:** Missing-root noise stays OUT of the default spawn lane; it surfaces
in `config show`, `doctor`, and debug-level launch diagnostics instead.
Applicability downgrades (actual launch-behavior changes) DO surface at default
level because those are not noise — they indicate the launch will behave
differently than the user expects.
**Encoded in:** `design/spec/surfacing.md` `SURF-1.e3` (spawn-time missing-root
noise stays out of the default lane), `SURF-1.e4` (applicability downgrades
are explicit); `design/architecture/surfacing-layer.md` A05 "Warning Channels"
split between default and debug lanes.

### F12 — Unknown-keys "debug only" hides config typos
**Status:** Addressed.
**Response:** Unknown keys are preserved for forward compatibility AND surfaced
as warnings in `doctor` and `config show`. Not debug-only.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.e2`;
`design/spec/surfacing.md` `SURF-1.e2`;
`design/architecture/workspace-model.md` A03 (unknown-key handling in the model);
`design/architecture/surfacing-layer.md` A05 (`workspace_unknown_key` doctor code).

### F13 — `workspace init --from mars.toml` risks broken-by-default state
**Status:** Addressed.
**Response:** Default `workspace init` creates a file with commented examples
only. The `--from mars.toml` variant was later deferred out of v1 rather than
kept as a live commitment.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.e1` (default init commented
examples); `design/spec/bootstrap.md` non-requirement note deferring
`workspace init --from mars.toml`; `D14` (deferred).

### F14 — `config show` needs a crisp minimal answer set
**Status:** Addressed.
**Response:** Explicit JSON shape pinned:
`{status, path?, roots: {count, enabled, missing}}`.
Text output stays flat and grep-friendly. Rich per-root detail lives in
warnings and doctor findings, not in the steady-state payload.
**Encoded in:** `design/spec/surfacing.md` `SURF-1.u1`;
`design/architecture/surfacing-layer.md` A05 "Workspace Summary Shape" (both
JSON and text forms shown).

### F15 — Gitignored `workspace.toml` violates monorepo convention
**Status:** Addressed. The file is `workspace.local.toml`.
**Response:** Filename encodes locality. The `.local` suffix is consistent with
`.env.local`, `mars.local.toml`, `compose.override.yaml` precedents cited by the
reviewer. `workspace.toml` (unsuffixed) is explicitly refused.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.u1`;
`design/architecture/paths-layer.md` A01;
`design/feasibility.md` Open Questions §3 records the prior-art rationale.
**Rejected alternative:** `workspace.toml` under a gitignore rule — rejected
because across pnpm/npm/Yarn/Rush/Nx/Bazel/Go/Cargo/Bun/Deno, `workspace.*`
names mean committed team topology. A gitignored file under that name
mis-signals intent.

### F16 — `[context-roots]` naming is jargon-heavy
**Status:** Addressed (low priority acknowledged).
**Response:** Design commits to `[[context-roots]]` for consistency with
Meridian's existing "context" language (`MERIDIAN_CHAT_ID`, "context handoffs"
skill). Alternatives `[include-dirs]` / `[extra-dirs]` considered and rejected
on consistency grounds.
**Encoded in:** `design/spec/workspace-file.md` `WS-1.u3`;
`design/architecture/workspace-model.md` A03 (TOML schema example);
`design/feasibility.md` Open Questions §2 flags this as low-priority and
reversible if a reviewer insists.

### F17 — No sunset trigger for the dual-read fallback
**Status:** Obsolete per D8.
**Response:** No migration path exists. There is no dual-read fallback and no phase plan. Implementation breaks `.meridian/config.toml` without warning. Aggressive collapse is "no collapse required — no phases exist."

### F18 — "Emit a one-time advisory" is not implementable as specified
**Status:** Obsolete per D8.
**Response:** No legacy fallback means no migration advisory. The per-invocation advisory cadence question does not arise.

### F19 — `config migrate` idempotency underspecified for divergent files
**Status:** Obsolete per D8.
**Response:** No `config migrate` command exists. The question of four-case idempotency does not arise.

## Cross-cutting design calls

### D1 — Spec and architecture are two separate trees with explicit realizes/realized-by links
Spec leaves (`CFG-1`, `WS-1`, `CTX-1`, `SURF-1`, `BOOT-1`) are behavioral
contracts in EARS notation. Architecture leaves (`A01`–`A05`) are observational
— they describe the target shape implementation must preserve, not a step-by-step
plan. Each architecture leaf's `Realizes` section points at specific spec EARS
IDs. Each spec leaf's `Realized by` section points at architecture leaves.
Planning consumes both trees and the refactor agenda; it does not invent
structure the architecture tree did not declare.

### D2 — Repo-root file abstraction is a prep refactor, not a rename
R01 (`design/refactors.md`) creates `ProjectPaths` before R02 rewires the
command family. Doing the command-family rewire without the boundary split
first would either bloat `StatePaths` with repo-root concerns or create a
transient state where two layers both claim ownership of `meridian.toml`.
The sequencing is prep → rewire → observe.

### D3 — `context_directories()` abstraction is NOT introduced in v1
The prior design's single-consumer flat-list abstraction was rejected. The
replacement is an ordered-root planner plus `HarnessWorkspaceProjection`
(ordered, applicability-aware, transport-neutral). A separate shared direct
`--add-dir` emitter is still deferred until post-interface duplication actually
drifts. This follows the `dev-principles` rule "Leave two similar cases
duplicated. Extract at three."

### D4 — Historical unsupported stance is superseded
The earlier redesign sketch treated OpenCode as `unsupported`. That position is
superseded by D11 after the dedicated OpenCode probe landed. Keep this note only
so readers understand why older references may still mention
`unsupported:v1`.

### D5 — Migration detail decision is obsolete
This decision became obsolete once D8 removed migration from scope entirely.
Keep the slot for chronology only; there is no `config migrate` contract and no
`migration.md` leaf in the approved target-state package.

### D6 — `.meridian/.gitignore` `!config.toml` exception is scaffolding and is removed now
The exception exists today because `.meridian/` is otherwise fully gitignored
and `config.toml` was committed. With migration out of scope per D8, there is no
Phase C: the exception is removed in the target-state refactor so `.meridian/`
returns to the intended boundary of fully local/runtime state. R04
(`design/refactors.md`) is folded into R01, which owns this removal.

### D7 — Spec hierarchy size is deliberately small
Five spec subsystems (`CFG-1`, `WS-1`, `CTX-1`, `SURF-1`, `BOOT-1`) is the
right depth for this work-item tier. A deeper decomposition (per-EARS-ID
leaf files) would fragment the contract without improving readability.
Architecture mirrors this with five leaves (A01–A05).

### D8 — Migration is out of scope; target state only

**Directive (2026-04-14):** User directed that migration is out of scope. CLAUDE.md states "No backwards compatibility needed — completely change the schema to get it right." Specific consequences:

- No dual-read fallback. `meridian.toml` is the only project config location; `.meridian/config.toml` is not read.
- No `config migrate` command.
- No Phase A/B/C staged deprecation. There is one release that introduces the new location, breaking any legacy `.meridian/config.toml` without warning.
- `design/spec/migration.md` and `design/architecture/migration-flow.md` are deleted from the package.
- F17, F18, and F19 findings are marked obsolete per this decision.

### D9 — Architect independent sketch consumed and deleted

The independent architecture sketch (`architect-independent-sketch.md`) produced during the design round has been folded into the architecture tree:

- Module enumeration → `design/architecture/paths-layer.md` "Module Layout" section
- Three-layer workspace split (`WorkspaceConfig` / `WorkspaceSnapshot` / `HarnessWorkspaceProjection`) → `design/architecture/workspace-model.md`
- Harness integration refinements and `HarnessWorkspaceSupport` type → `design/architecture/harness-integration.md`
- Shared surfacing builder (`config_surface.py`) → `design/architecture/surfacing-layer.md`
- Four open architectural questions → `design/feasibility.md` "Open Questions"

The sketch file and its prompt (`architect-independent-prompt.md`) were deleted after folding. Future readers should not look for them.

### D10 — Harness-agnostic projection interface

The design extracts `HarnessWorkspaceProjection` as the transport-neutral output
from each harness adapter. Launch composition owns ordered-root planning and
field merging, but it does not branch on mechanism details. This aligns with the
project's core principles:

- Separate policy from mechanism: workspace topology remains policy; adapters own
  how one harness receives that topology.
- Extend, don't modify: adding a harness means one adapter implements one
  projection method rather than editing every launch path.
- Simplest orchestration: the shared layer merges one object instead of growing
  a special-case matrix for `--add-dir` and overlay transports.

**Rejected alternative:** keep an `add_dirs`-centric core and bolt OpenCode onto
it. Smaller delta, wrong abstraction. It would leak harness detail into launch
composition and force future harnesses to pretend they all work like Claude.

### D11 — OpenCode day-1 mechanism is `permission.external_directory`

OpenCode day-1 support uses the native permission surface documented in
`opencode-probe-findings.md §2`, `§4`, and `§5`. Meridian projects enabled
existing workspace roots into a `permission.external_directory` config overlay
and materializes that overlay through `OPENCODE_CONFIG_CONTENT`.

Why this wins:

- Native file tools get direct access to the extra roots.
- The projection interface can represent the mechanism without changing Claude or
  Codex paths.
- The remaining semantic gap is honest and inspectable:
  `active:permission_allowlist`, not fake `active:add_dir` parity.

**Rejected alternative:** MCP filesystem server. It changes the interaction
model for extra roots and adds lifecycle/config complexity with weaker semantic
parity.

**Rejected alternative:** wait for upstream multi-root support. PR #2921 closed
unmerged; no committed timeline exists.

**Rejected alternative:** symlink extra dirs into the project root. Operationally
fragile and hostile to filesystem tooling.

### D12 — Workspace anchor model (v1 scope)

**Directive (2026-04-14, updated 2026-04-16):** Meridian has a single effective working directory, defined as the parent of the active `.meridian/` directory. All meridian operations (spawn cwd, config discovery, default workspace-file location) anchor to this one directory. Users never see a named "repo root" concept. `MERIDIAN_WORKSPACE` is deferred out of v1.

**Committed shape:**

1. **Default workspace file location:** `<parent-of-.meridian/>/workspace.local.toml`. Described in docs by relationship to `.meridian/`, not by inventing a "repo root" term.

2. **No explicit env override in v1:** workspace discovery uses only the canonical sibling file. `MERIDIAN_WORKSPACE` and any alternate discovery path are deferred until the feature is reintroduced through requirements/spec.

3. **Paths inside `workspace.local.toml`:** relative to the file itself. Matches VS Code `.code-workspace` convention and every workspace-file tool in the industry. Portable — move the file, paths follow.

4. **Spawn cwd:** parent of `.meridian/` (unchanged behavior). Named as meridian's effective cwd.

**Rejected alternatives:**

- **Named "repo root" user-facing concept.** Implies git coupling that meridian doesn't actually have; overlaps with "parent of `.meridian/`" without adding precision.
- **Committed `workspace.toml` layer.** `mars.toml` already plays the "committed team topology" role; adding a second committed file duplicates it.

**Deferred to separate decision:** walk-up discovery of `.meridian/` (keep walk-up as ergonomic convention, switch to cwd-only, or add visibility instrumentation). This decision is orthogonal to the workspace anchor model — workspace config semantics are the same either way.

**Deferred with the feature:** `MERIDIAN_WORKSPACE` override semantics, including absolute-vs-relative path handling and missing-target behavior, are out of v1 scope until env override support is promoted back into requirements/spec.

**Spec/architecture touchpoints requiring sweep (follow-up pass):**

- `design/spec/workspace-file.md` — replace "repo root" references with relationship to `.meridian/`
- `design/architecture/paths-layer.md` — `ProjectPaths` description without a v1 env-override owner

### D13 — `MERIDIAN_WORKSPACE` missing-target behavior (deferred)

**Status (2026-04-16):** Deferred with the feature. Because `MERIDIAN_WORKSPACE` is out of v1 scope, missing-target semantics are not a v1 commitment.

If env override support is reintroduced later, this question should return through requirements/spec first, then architecture/decisions can choose between advisory-and-continue vs invalid-and-block behavior.

### D14 — `workspace init --from mars.toml` path emission (deferred)

**Status (2026-04-16):** Deferred out of v1. The feature was cut from requirements/spec, so its emitted file shape is not a live commitment for this package.

The prior design direction remains useful future context: if the variant returns, prefer commented identities plus empty paths over guessed filesystem heuristics. But that is a future v2 decision, not a v1 contract.

### D15 — OpenCode `OPENCODE_CONFIG_CONTENT` collision policy (OQ-1)

**Directive (2026-04-14):** If a parent environment already sets `OPENCODE_CONFIG_CONTENT`, meridian's OpenCode adapter **skips** workspace projection and emits a diagnostic ("workspace projection suppressed — `OPENCODE_CONFIG_CONTENT` already set by parent env"). The user's explicit env value wins.

**Rationale:** silent deep-merging of meridian's workspace overlay into user-supplied JSON is hostile. It modifies user config invisibly, producing surprising behavior that's hard to debug. Skip-with-diagnostic is predictable, makes the suppression visible, and users who want merge semantics can request them as a future opt-in flag.

Implementation is also simpler — no JSON deep-merge logic, no precedence rules between user fields and meridian fields.

**Rejected alternative:** deep-merge meridian's workspace overlay into the existing `OPENCODE_CONFIG_CONTENT` JSON. Rejected because silent modification of user-supplied JSON is the kind of invisible behavior that causes long debug sessions; predictable skip is safer, and merge can be added behind an opt-in flag later if real users ask.

**Rejected alternative:** meridian-precedence overwrite. Rejected because silently dropping the user's env value is worse than refusing to project; the user made an explicit assertion by setting the env.

### D16 — Streaming vs subprocess projection parity (OQ-7)

**Status:** Resolved via code investigation; no architecture change needed.

**Finding:** code inspection confirmed:

1. All three harness bundles register only streaming connections in `src/meridian/lib/harness/claude.py:444`, `src/meridian/lib/harness/codex.py:500`, and `src/meridian/lib/harness/opencode.py:310`, so spawn execution is effectively streaming-only.
2. Spawn execution unconditionally calls `execute_with_streaming` at `src/meridian/lib/ops/spawn/execute.py:459`; "streaming" refers to the IPC shape, not to the absence of a child process.
3. OpenCode env propagation still flows through `inherit_child_env` in `src/meridian/lib/launch/env.py:123` into `create_subprocess_exec(..., env=env)` in `src/meridian/lib/harness/connections/opencode_http.py:324`.

**Consequence:** `HarnessWorkspaceProjection.env_additions` works uniformly. The OpenCode workspace projection delivers `OPENCODE_CONFIG_CONTENT` through the standard env channel regardless of which runner code path is chosen.

**Related follow-up (out of scope):** issue #32 (`meridian-flow/meridian-cli#32`) filed to remove dead legacy subprocess-runner code and clarify the misleading `_subprocess` filenames on shared projection utilities. That cleanup is independent of workspace-config-design.

### D17 — Hexagonal launch core (3 driving adapters through one factory)

**Directive (2026-04-15, refined 2026-04-15):** Meridian launch composition
adopts a **hexagonal (ports and adapters)** architecture with a canonical
Plan Object at the center. The architecture has 1 driving port (the
`build_launch_context()` factory), 3 driving adapters with named
architectural reasons, and 3 driven adapters (harness implementations).

**Architecture — 3 driving adapters, each with a named reason:**

1. **Primary launch** (`launch/plan.py` → `launch/process.py`) — foreground
   process under meridian's control until exit. Two capture modes: **PTY
   capture** (intended, `pty.fork()` + `os.execvpe()` when stdin/stdout are
   TTYs and output log path is configured) and **direct Popen** (degraded
   fallback, `subprocess.Popen().wait()` when TTYs unavailable). PTY enables
   session-ID scraping; Popen loses session-ID observability today (GitHub
   issue #34 tracks filesystem-polling fix). Both paths consume the same
   `LaunchContext` and return the same `LaunchResult` contract.
2. **Background worker** (`ops/spawn/prepare.py:build_create_payload` →
   `ops/spawn/execute.py`) — detached one-shot subprocess per spawn.
   `meridian spawn` forks a detached `python -m
   meridian.lib.ops.spawn.execute` per spawn id; that process composes once,
   executes, writes its report, and exits. The architectural reason is
   **detached lifecycle** — the meridian parent can exit or crash without
   orphaning the spawn.
3. **App streaming HTTP** (`app/server.py:268-365`) — in-process
   `SpawnManager` control channel. The REST/WS interface is structured around
   a manager held by the HTTP handler; `/inject` and `/interrupt` route
   through the same in-memory connection. The architectural reason is
   **current API shape**: composition happens at request time to keep the
   manager local. Meridian's separate `control.sock` + `spawn_inject`
   mechanism demonstrates out-of-process control is possible; moving to
   queued exec + remote control is a separate refactor.

Each driving adapter constructs a `SpawnRequest` (user-facing args only),
calls the factory `build_launch_context()`, and hands the resulting
`LaunchContext` to the appropriate executor (PTY execvpe or async
subprocess). Dry-run callers call the factory for preview output without
executing.

**Why not 1 driver:** Primary is a foreground process meridian owns until
exit (PTY capture or direct Popen depending on environment). Worker must be
a detached one-shot subprocess that outlives the parent. App streaming must
keep the manager in-process for the current REST/WS API shape. These are
incompatible driver semantics that cannot collapse into a single code path.

**Why not 9 (the previous enumeration):** The earlier framings enumerated
8–9 "driving ports" by mixing call locations inside the same driver
(`plan.py` + `process.py` + `command.py` are all internal to primary launch)
and counting two dead parallel implementations. R06 deletes the dead code:
`run_streaming_spawn` at `streaming_runner.py:389` (a parallel
implementation beside the shared `execute_with_streaming` at line 742) and
the `SpawnManager.start_spawn` unsafe-resolver fallback at
`spawn_manager.py:196-199` (post-R06 all callers hand in a resolved
`LaunchContext`). Collapsing to 3 drivers is not simplification — it is
the honest count after removing dead code and recognizing internal structure.

**Three patterns provide drift protection (heuristic guardrails, not
mechanically impossible constraints):**

1. **Pipeline / functional composition.** Each composition concern has
   exactly one builder with one implementation: `resolve_policies()`,
   `resolve_permission_pipeline()`, `materialize_fork()`, `build_env_plan()`,
   plus adapter-owned `resolve_launch_spec()` and `observe_session_id()`.
   The factory `build_launch_context()` orchestrates the pipeline and
   returns a complete `LaunchContext`. One file per stage, one callsite per
   builder. CI-checkable via `rg` (heuristic — see R06 exit criteria for
   known evasion modes). Several stages read bounded configuration from disk
   (profiles, skills, session state, `.claude/settings*.json`);
   `materialize_fork()` is the sole stage that performs state-mutating I/O
   (Codex session API). The invariant is **centralization** — composition
   happens only in this pipeline — not purity.

2. **Plan Object (Evans) with algebraic sum.** `LaunchContext =
   NormalLaunchContext | BypassLaunchContext`. Frozen dataclasses, required
   fields at the type level. `NormalLaunchContext` carries
   policy/permission/workspace/env/spec/runtime/cwd.
   `BypassLaunchContext` carries `argv`, `env`, and `cwd` for
   `MERIDIAN_HARNESS_COMMAND`. Post-launch session-id is NOT on
   `LaunchContext` — it is on `LaunchResult`, returned post-execution via
   adapter-owned `observe_session_id()`. Executors dispatch on the union
   via `match` + `assert_never`; Pyright enforces exhaustiveness at build
   time (with `pyright: ignore` and `cast(Any, ...)` banned in executor
   modules — see R06 exit criteria). Compile-checkable with caveats.

3. **Adapter pattern (GoF) for harness translation.** Domain core imports
   from `harness/adapter.py` (abstract contract) only — no imports of
   `harness/claude`, `harness/codex`, `harness/opencode`, or
   `harness/projections`. Adapters implement `project_workspace()`,
   `observe_session_id()`, and similar translation methods.
   Import-graph-checkable.

**Type split — `SpawnRequest` / `SpawnParams`:** `SpawnParams` today carries
resolved execution state (skills, session ids, appended system prompts,
report paths) — it is not a user-input DTO. R06 splits it into
`SpawnRequest` (user-facing args, constructed by driving adapters) and
`SpawnParams` (or successor, resolved execution inputs, constructed only
inside/after the factory). This enforces the driving-adapter invariant at
the type level: driving adapters see `SpawnRequest`, only the factory sees
`SpawnParams`.

**Fork continuation — absorbed into domain core (I/O-performing stage):**
Fork materialization is pre-execution composition in both current sites
(`launch/process.py:68-105` and `ops/spawn/prepare.py:296-311`). Both call
`adapter.fork_session()`, mutate `SpawnParams`, and rebuild the command
before any executor runs. R06 adds `materialize_fork()` as a pipeline stage
in the domain core, running post-spec-resolution and pre-env-construction.
`materialize_fork()` performs state-mutating I/O: `fork_session()` opens
SQLite (`~/.codex/state_5.sqlite`), reads thread rows, copies rollout files
(`src/meridian/lib/harness/codex.py:425`). The factory's invariant is
**centralization** — composition happens only in this pipeline — not
purity; several other stages read bounded configuration from disk, but only
`materialize_fork()` writes. The previous claim that fork state is "a
separate value produced by the executor" was incorrect — both sites do
pre-execution composition, and R06 consolidates them honestly.

**Session-ID adapter seam (`observe_session_id()`):** Session-ID is a
post-launch observable, not a launch input. R06 moves session-ID off
`LaunchContext` (which is frozen, all-required) onto `LaunchResult`,
returned post-execution via adapter-owned `observe_session_id()`. This
closes the "all required, frozen" `LaunchContext` contradiction.

Executor contract: executors run the process and return `LaunchOutcome`
(raw: exit code, pid, captured PTY output). The driving adapter calls
`harness_adapter.observe_session_id(launch_context=...,
launch_outcome=...)` and assembles a `LaunchResult`. `observe_session_id()`
is a getter over adapter-held state — it returns the session-ID the adapter
observed during launch via harness-native mechanisms, not a parser of
`launch_outcome`. If observability fails (e.g., Popen fallback with
scrape-only Claude impl today), `session_id = None`.

Existing mechanisms are preserved, not changed: Claude's PTY path scrapes
terminal output; Codex streaming reads `connection.session_id` set during
WebSocket thread bootstrap
(`src/meridian/lib/harness/connections/codex_ws.py:190,270`); OpenCode
streaming reads `connection.session_id` set during session creation
(`src/meridian/lib/harness/connections/opencode_http.py:137,166`). The
refactor moves that logic behind the adapter method. GitHub issue #34
tracks swapping implementations to filesystem polling — the seam exists;
implementations change later without touching executors.

**Scope evolution (chronological):**

- *First narrowing (pre-p1882):* R06 scoped to `launch/` files only.
  Rejected because exit criteria required `ops/spawn/prepare.py`, primary
  fork, and `MERIDIAN_HARNESS_COMMAND` bypass.
- *First growth (post-p1882):* Added `ops/spawn/prepare.py`, primary fork
  paths, `RuntimeContext` unification. Still used function-centric invariants.
- *Second growth (post-p1888/p1889):* Reviewers found additional composition
  sites. Switched from function-centric to hexagonal/pattern-centric
  invariants.
- *Third reframe (post-p1893):* Feasibility explorer established the honest
  driver count is 3, not 8–9. Several "ports" were call locations inside
  one driver; two were dead parallel implementations. Absorbed fork
  materialization into the pipeline (correcting the earlier overclaim).
  Added `SpawnRequest`/`SpawnParams` split. Added concrete deletions.

**Drift protection invariants (exit criteria in `refactors.md` R06):** After
R06, the three patterns hold: one builder per concern (pipeline), one
`LaunchContext` sum type and one `RuntimeContext` type (plan object), domain
core isolated from concrete harness imports (adapter). Exactly 3 driving
adapters (+1 preview) call `build_launch_context()`. These invariants are
enforced by heuristic CI guardrails (`rg`-based checks in
`scripts/check-launch-invariants.sh`, Pyright exhaustiveness with
`pyright: ignore` and `cast(Any, ...)` banned in executor modules). They
are structurally difficult to violate but not mechanically impossible —
see R06 exit criteria for known evasion modes. These invariants are what
R05 depends on and what every future launch-touching feature inherits.

**Preserved divergences (branches, not flattening):**

- Primary executor has two capture modes (PTY capture + direct Popen)
  driven by runtime environment. Both consume `LaunchContext`, return
  `LaunchResult`. PTY enables session-ID scraping; Popen loses session-ID
  observability today. GitHub issue #34 tracks filesystem-polling fix.
- Claude-in-Claude sub-worktree cwd logic stays as a `child_cwd` field on
  `NormalLaunchContext`, populated by the pipeline.

**Rejected alternative — shared projection merge point only (R05 targets
both existing seams):** Both pipelines would keep their independent
composition and each call `harness.project_workspace(...)` at their own
merge point. Rejected because it leaves no domain core — the existing
duplications keep growing (workspace becomes the fifth), every future
launch-touching feature pays an N× implementation tax across all driving
adapters, and there is no central type to check invariants against.

**Rejected alternative — narrow spec to spawn-only:** `CTX-1.u1` would
apply only to spawned subagents; primary launches would not see workspace
roots. Rejected because the primary user flow is launching meridian from a
parent directory and wanting sibling-repo context there.

**Rejected alternative — demote R06 to optional follow-up:** Leave R06 as
cleanup triggered by "post-R05 drift." Rejected because the drift surface
is already five features wide, and the user's explicit directive is to
refactor first and make drift structurally difficult.

**Out of scope (separate follow-up work items):** Claude
session-accessibility symlinking (`p1878` Q5). Fork materialization is
absorbed into the domain core by R06; symlinking is a separate duplicated
feature beyond composition.

### D18 — Relative `MERIDIAN_WORKSPACE` values (deferred)

**Status (2026-04-16):** Deferred with the feature. Because `MERIDIAN_WORKSPACE`
is out of v1 scope, relative-path handling is not a v1 contract either.

If env override support returns in a future version, the design should resolve
this question alongside the broader override feature instead of treating the
relative-path case as an isolated commitment.

### D19 — R06 redesign: typed pipeline with raw `SpawnRequest` input + reviewer-as-drift-gate verification

**Directive (2026-04-16):** The first R06 implementation produced a hexagonal
*shell* — a `build_launch_context()` factory and a `LaunchContext` sum type —
but the *core* of R06 (composition centralization) did not land. Four
independent reviews (`reviews/r06-retry-design-alignment.md`,
`reviews/r06-retry-correctness.md`, `reviews/r06-retry-structural.md`,
`reviews/r06-retry-library-research.md`) converge on the same diagnosis: the
factory takes a pre-composed `PreparedSpawnPlan` whose `ExecutionPolicy`
already carries resolved `PermissionConfig` and live `PermissionResolver`. The
factory is downstream of composition, so policy/permission/command resolution
still lives in every driving adapter. CI `rg`-count guards pass while the
invariant they were meant to protect is structurally false.

R06 is rewritten as a *typed pipeline with raw `SpawnRequest` input*, with
verification moving from `rg`-count gaming surface to a CI-spawned `@reviewer`
architectural drift gate plus deterministic behavioral factory tests. Library
research (`reviews/r06-retry-library-research.md`) verdict
`roll-your-own-with-pattern` confirmed no DI container or framework solves the
underlying problem; the fix is composition-root pattern with raw-input DTO.

**Committed redesign — five load-bearing changes:**

1. **Type ladder collapses from 6 partial DTOs to 3 user-visible + 2
   factory-internal.** User-visible: `SpawnRequest` (pre-composition raw
   input), `LaunchContext = NormalLaunchContext | BypassLaunchContext`
   (post-composition executor input), `LaunchResult` (post-execution).
   Factory-internal: `ResolvedRunInputs` (renamed from `SpawnParams`,
   constructed only inside the factory), `LaunchOutcome` (executor → driving
   adapter handoff before `observe_session_id` runs). `PreparedSpawnPlan`,
   `ExecutionPolicy`, `SessionContinuation` (top-level), and
   `ResolvedPrimaryLaunchPlan` are deleted.

2. **Pipeline stages own real logic, not re-export shells.** `launch/policies.py`,
   `launch/permissions.py`, and `launch/fork.py` each house one stage function
   with implementation + behavioral tests. `launch/runner.py` is deleted.
   `launch/command.py` is repurposed to host the sole adapter
   `resolve_launch_spec` + `build_command` callsite (`project_launch_command`);
   the legacy `build_launch_env` wrapper is deleted.

3. **Driven port loses mechanism.** `harness/adapter.py` keeps protocol
   contracts only; permission-flag projection logic moves into each driven
   adapter (`harness/claude.py`, `harness/codex.py`, `harness/opencode.py`).

4. **Fork transaction ordering closes the orphan window.** `prepare.py`
   persists `SpawnRequest` only; it does not call `materialize_fork`. The
   worker's `execute.py` creates the spawn row, then calls
   `build_launch_context(..., dry_run=False)`, which materializes the fork.
   Fork happens only after the spawn row exists, in every driver. On fork
   failure, the spawn row is marked `failed` with reason
   `fork_materialization_error`. Streaming-runner fallback path requires a
   precondition: spawn row must exist before `execute_with_streaming` calls
   the factory.

5. **Verification swaps from `rg`-count CI to reviewer drift gate +
   behavioral tests.** `scripts/check-launch-invariants.sh` is deleted in
   this refactor. Replacement is three layers: behavioral factory tests
   (`tests/launch/test_launch_factory.py`) pin load-bearing invariants
   directly; a CI-spawned `@reviewer` reads diffs against
   `.meridian/invariants/launch-composition-invariant.md` and blocks merge on
   `fail`; pyright/ruff/pytest remain the correctness gate.

**Why typed pipeline, not richer DI/effect framework:** library research
shortlist (`dishka`, `dependency-injector`, `inject`, `punq`, `returns`) all
solve object-graph wiring at app boundary. R06 is one composition root, not
deep graph wiring. Adding container DSL pushes the problem sideways: meridian
still owns the stage pipeline. Pydantic discriminated unions (already in tree)
cover raw-input normalization; `singledispatch` (stdlib) covers per-adapter
observation strategy if ever needed. Lowest total complexity wins.

**Why raw `SpawnRequest`, not split `Unresolved/Resolved` plan pair:** the
worker's prepare/execute boundary needs a serializable artifact between the
two phases. The reviewer-recommended `(ii)` (`UnresolvedPreparedPlan` +
`ResolvedPreparedPlan` split) and the `(i)` (single raw DTO at factory input)
options collapse to the same shape once `PermissionResolver` is removed from
the persisted artifact: prepare persists raw inputs, execute reconstructs.
We name that artifact `SpawnRequest` because the user-facing DTO already exists
on the harness adapter protocol (`harness/adapter.py:150`) — currently dead.
Making `SpawnRequest` load-bearing closes the dead-abstraction signal flagged
by the structural review and removes the extra `Unresolved/Resolved` rename
churn.

**Why reviewer drift gate, not stricter `rg` checks:** the correctness review
enumerated 14 concrete `rg`-evasion patterns the current invariants script
cannot catch (aliasing imports, indirect dispatch, string-form `cast`, dead
parallel classes under different names, etc.). Adding more `rg` rules
expands the gaming surface without raising the bar. Semantic verification
catches shim patterns; deterministic factory tests pin the specific
invariants that must not drift; together they cover the failure modes
heuristic checks cannot.

**Rejected alternative — keep current `PreparedSpawnPlan` and just rename
fields to `unresolved_*`/`resolved_*`:** drift-symptom rename. The persisted
DTO would still carry `PermissionResolver` indirectly (via every consumer
needing to reconstruct from fields), and drivers would still need to compose
to produce it. Boundary stays in the wrong place.

**Rejected alternative — adopt `dishka` or `dependency-injector` for the
factory:** see library-research verdict. Adds container scope DSL, decorator
wiring, typing friction with strict pyright. Does not solve the input-shape
boundary. Real cost ≫ real benefit.

**Rejected alternative — keep `scripts/check-launch-invariants.sh` and
upgrade to AST checks:** same gaming surface in a more expensive
implementation. AST-based static checks for "no driver constructs a
permission resolver" still pattern-match on names (any field that holds the
resolver) and do not enforce the *behavioral* invariant (that the driver
never has the inputs needed to construct one). Behavioral factory tests +
reviewer drift gate enforce the behavior directly.

**Out of scope (filed separately):** GitHub issue #34 — Popen-fallback
session-ID observability via filesystem polling. R06 lands the
`observe_session_id()` adapter seam; the mechanism swap to filesystem polling
is a separate change.

**Spec/architecture touchpoints requiring sweep:**

- `design/refactors.md` R06 — rewritten in full (this redesign)
- `design/architecture/launch-core.md` — new architecture leaf (A06) for the
  launch domain core
- `design/architecture/overview.md` — TOC updated to include A06
- `design/feasibility.md` — add `FV-11` for DTO reshape feasibility
- Spec leaves unchanged: R06 is structural; it does not change user-facing
  EARS contracts

## D20 — R06 convergence-2 sweep (DTO completeness, A04↔A06 seam, invariant prompt as design artifact)

After D19's redesign, two convergence reviewers ran in parallel against the
redesigned R06:

- `reviews/r06-redesign-alignment.md` — opus design-alignment review.
  Verdict: `block` (1 blocker, 3 majors).
- `reviews/r06-redesign-dto-shape.md` — opus DTO-shape review.
  Verdict: `shape-change-needed` (1 blocker, 6 majors, 8 minors).

Both verdicts agreed the redesign's central call (raw `SpawnRequest` at the
factory boundary, six DTOs collapsed to a small named set,
`arbitrary_types_allowed=True` removed) was right. They independently surfaced
the same class of gap: schemas and seams enumerated at design altitude but
not specified in enough detail for implementation to proceed without
re-deciding mid-flight.

**Decisions made in convergence-2 (the four design changes that close every
blocker and major):**

### D20.1 — Workspace-projection seam reachable via stage split

The original D19 packed `resolve_launch_spec` + workspace projection +
`build_command` into a single `project_launch_command()` stage, leaving no
coherent place inside the factory for A04 to insert its
`adapter.project_workspace()` call. Resolution: split that stage into
three with sole-callsite invariants:

| Stage | Owns single callsite to |
|---|---|
| `resolve_launch_spec_stage()` | `adapter.resolve_launch_spec` |
| `apply_workspace_projection()` | `adapter.project_workspace` (A04 seam) |
| `build_launch_argv()` | `adapter.build_command` |

`apply_workspace_projection` extends `spec.extra_args` with
`projection.extra_args`; `build_launch_argv` then assembles the final argv
once. A04 and A06 can now both be true: the seam is reachable inside the
A06 stage ordering. This is the load-bearing change for the alignment
blocker.

### D20.2 — `LaunchRuntime` introduced as 4th user-visible DTO

The DTO reviewer found that `interactive`, `effort`, `unsafe_no_permissions`,
`debug`, `harness_command_override`, `report_output_path`, `state_paths`,
and `project_paths` are all runtime-injected (the driving adapter knows
them; an external caller does not provide them). They have no honest home
on `SpawnRequest`. Resolution: introduce `LaunchRuntime` as the second
factory input (`build_launch_context(SpawnRequest, LaunchRuntime, *,
dry_run)`).

`LaunchRuntime.unsafe_no_permissions` is the seam for the app-streaming
driver's `--allow-unsafe-no-permissions` override; dispatch to
`UnsafeNoOpPermissionResolver` happens inside
`resolve_permission_pipeline()`, never at the driver. This closes DTO
finding 6 (UnsafeNoOpPermissionResolver had no driver-side construction
path under the prohibition list).

`launch_mode: Literal["primary", "background"]` on `LaunchRuntime` closes
DTO finding 1 (`interactive: bool` had no slot). It drives every driven
adapter's interactive projection from the factory, not the driver.

**Rejected alternative — put runtime fields on `SpawnRequest`:** breaks
the model that `SpawnRequest` carries only what an external caller can
express. Persisting `unsafe_no_permissions` on the worker prepare artifact
would also let operators alter the security mode by editing a JSON blob.

### D20.3 — `LaunchContext.warnings` channel for composition warnings

The DTO reviewer's blocker (Finding 4): deleting `PreparedSpawnPlan`
removed the `warning` channel that flowed to `SpawnActionOutput.warning`,
with no replacement on the new types. Resolution: add
`warnings: tuple[CompositionWarning, ...]` to both `NormalLaunchContext`
and `BypassLaunchContext`, populated by pipeline stages. Introduce a
`CompositionWarning` frozen pydantic model (`code`, `message`, optional
`detail` dict). Driving adapters surface them through
`SpawnActionOutput.warning`. Single sidechannel; no other path permitted.

### D20.4 — Invariant prompt drafted as design artifact, not implied future detail

The alignment reviewer's major: D19 promised
`.meridian/invariants/launch-composition-invariant.md` as part of the
verification triad but did not draft it. A version-controlled prose
artifact that no one has written cannot be reviewed for ambiguity.
Resolution: draft the full invariant prompt now, in the design package, at
`design/launch-composition-invariant.md`. Implementation copies it
verbatim to the production location during R06 implementation, and both
files stay in sync as legitimate architecture changes land.

The drafted prompt enumerates 10 numbered invariants (I-1 composition
centralization, I-2 driving-adapter prohibition list, I-3 single owners
table, I-4 observation path, I-5 DTO discipline, I-6 stage modules own
real logic, I-7 driven port keeps shape only, I-8 executors stay
mechanism-only, I-9 workspace-projection seam reachable, I-10
fork-after-row ordering), the protected file lists, an explicit "what does
NOT count as a violation" carve-out, and a structured JSON output format
with file:line violations.

### Schema completeness (closing the six DTO-completeness majors)

Beyond the four substantive changes above, convergence-2 enumerated every
field today's drivers carry, with the new home named explicitly:

- `interactive: bool` → `LaunchRuntime.launch_mode` (D20.2).
- `effort: str | None` → `SpawnRequest.effort` (caller-overridable).
- 3 dropped `SessionContinuation` fields (`continue_harness`,
  `continue_source_tracked`, `continue_source_ref`) →
  `SpawnRequest.session: SessionRequest` carries all 8 prior fields.
- `context_from_resolved` channel → mirrors the skills pattern (raw
  `context_from` on `SpawnRequest`; resolved counterpart inside
  `ResolvedRunInputs`).
- `UnsafeNoOpPermissionResolver` seam → `LaunchRuntime.unsafe_no_permissions`
  (D20.2).
- Worker prepare→execute re-resolution semantics → explicitly declared:
  `execute.py` re-reads filesystem state and re-composes via the factory;
  no persisted `cli_command` preview is cached. `spawn show --plan` shows
  the persisted `SpawnRequest`, not a pre-composed plan. Behavior-preserving
  (today's worker also reconstructs the resolver at execute time per
  FV-11).
- `RetryPolicy` split from `ExecutionBudget`: `RetryPolicy` carries
  `max_attempts` and `backoff_secs`; `ExecutionBudget` carries
  `timeout_secs` and `kill_grace_secs`. Names stay faithful to scope.
- `agent_metadata: dict[str, str]` typed explicitly (matches
  `template_vars`).
- `debug: bool` → `LaunchRuntime.debug` (D20.2).
- All `Path`-shaped fields stored as `str` for `model_dump_json` round-trip
  without custom encoders.

### Observe-session-ID contract clarification

The alignment reviewer's major found A04/D17 ("getter not parser") and the
prior R06 ("Claude scrapes from `launch_outcome.captured_stdout`") in
contradiction. Resolution: unify the contract. `observe_session_id()` is
purely a function of its per-launch inputs (`launch_context`,
`launch_outcome`). It may parse `launch_outcome.captured_stdout` (legitimate
for Claude's PTY mode) or read per-launch state reachable via
`launch_context` (e.g. `connection.session_id` for codex/opencode). What
remains forbidden is any field on the adapter class instance that holds a
session id, chat id, or last-launch state shared across launches.

Driving adapters MUST NOT inspect `LaunchOutcome.captured_stdout` directly
to scrape session ids — that observation is exclusively the driven
adapter's job via `observe_session_id()`. Added to the driving-adapter
prohibition list.

### Behavioral test additions (closing the D7 verification gap)

Five new deterministic behavioral tests added to the verification triad:

- `test_child_cwd_not_created_before_spawn_row` — pins D7 ordering directly
  (closes the alignment reviewer's major).
- `test_composition_warnings_propagate_to_launch_context` — pins D20.3.
- `test_workspace_projection_seam_reachable` — pins D20.1.
- `test_unsafe_no_permissions_dispatches_through_factory` — pins D20.2.
- `test_session_request_carries_all_eight_continuation_fields` — pins
  schema completeness for the SessionRequest expansion.

The invariant prompt's I-3 single-owner table also names "child cwd
creation (`mkdir`) inside the factory after spawn row exists" so the
drift gate carries the same constraint as the behavioral test.

### Findings explicitly preserved (not adopted)

- The structural review's `LaunchInputs`/`LaunchAttempt` decomposition
  remains rejected per D19. The DTO reviewer's "Comparative honesty"
  section confirmed `SpawnRequest` at the boundary wins on two grounds:
  (1) closes the dead-abstraction signal on the existing protocol, and
  (2) makes `model_dump_json` / `model_validate_json` the single
  persistence mechanism for the worker artifact.
- Background-worker `disallowed_tools` correctness fix remains out-of-R06
  scope (separate commit with own test). `SpawnRequest.disallowed_tools`
  makes it structurally fixable.

### Out-of-scope (preserved from D19)

- GitHub issue #34 — Popen-fallback session-ID observability via
  filesystem polling. R06 lands the `observe_session_id()` adapter seam;
  the mechanism swap is a separate change.
- GitHub issue #32 — dead legacy subprocess-runner code; misleading
  `_subprocess` filenames. Tracked in feasibility.md open question 7.

**Spec/architecture touchpoints updated by convergence-2:**

- `design/refactors.md` R06 — pipeline diagram (stage split), pipeline
  stages section (3 stages now), single-owner constraints table (6 rows
  added/changed), DTO reshape (4 user-visible types including
  `LaunchRuntime`, `LaunchContext.warnings` field, expanded fields,
  expanded `SessionRequest`, `RetryPolicy`+`ExecutionBudget` split,
  `Path` stored as `str`), `observe_session_id` contract clarification,
  6 new behavioral tests, invariant-prompt section now references the
  design-package draft.
- `design/architecture/launch-core.md` (A06) — same convergence-2 changes
  mirrored: pipeline stages, type ladder, single-owner table, prohibition
  list, observation contract, persisted-artifact section,
  shape constraints, verification section.
- `design/architecture/harness-integration.md` (A04) — workspace
  projection composition contract now references the new stage names
  (`resolve_launch_spec_stage` / `apply_workspace_projection` /
  `build_launch_argv`).
- `design/launch-composition-invariant.md` — new design artifact carrying
  the full CI drift-gate reviewer prompt for production at
  `.meridian/invariants/launch-composition-invariant.md`.
- Spec leaves unchanged: convergence-2 is still structural and DTO-shape;
  no user-facing EARS contract changes.

## D21 — R06-v1 smoke evidence folded back into design

**Date:** 2026-04-16 (post v0.0.30 release)
**Status:** design refinement, no structural shape change
**Trigger:** R06-v1 skeleton (reverted in `d1360df` after shipping as
unreleased commits `3f8ad4c..45d18d7`) was smoke-tested across 5
parallel lanes (reports at `smoke/lane-{1..5}-*.md`). Two HIGH-severity
regressions were R06-adjacent: fork lineage split-brain in the new
`launch/fork.py`, and row-before-fork ordering questionable (I-10
signal). One MEDIUM was R06-plausible: OpenCode report extraction
returning raw `session.idle` envelopes instead of the assistant message.
Three others were likely pre-existing state-layer issues orthogonal to
R06 (`meridian doctor` reconciliation gap, LIFE-7 finalizing filter,
stale `.flock` sidecars).

**Root-cause context:** the R06-v1 skeleton was built while the codex
harness silently truncated coder briefs above 50 KiB (bug fixed in
aeb160e for v0.0.30). We cannot rule out that some of the skeleton's
bugs were artifacts of truncated context rather than design flaws. But
three of the smoke findings point at design gaps the current R06 design
did not name explicitly. Folding them back in strengthens the design
for the retry regardless of skeleton-quality attribution.

### D21.1 — Fork lineage coherence as I-11

The current 10 invariants enforce pipeline ownership, stage ordering,
and DTO discipline. None assert that `spawns.jsonl` and `sessions.jsonl`
stay coherent across a fork transaction. Smoke lane 4 showed these
diverging: `spawns.jsonl.chat_id` held the parent's chat while
`sessions.jsonl` created a new chat, silently breaking `spawn children`
and `--fork <session_id>` follow-ons.

Added **I-11 Fork lineage coherence** to
`design/launch-composition-invariant.md`. Behavioral test
`test_fork_produces_consistent_lineage_across_jsonl_stores` added to
`design/refactors.md` R06 verification section.

### D21.2 — Report content type as I-12

The `observe_session_id` contract was tightened in D20. A sibling seam
— the method returning report content — was not. Smoke lane 2 showed
OpenCode's `report.md` containing a raw `session.idle` event envelope
instead of the assistant message, likely fallout from the streaming-
runner consolidation where a content-extraction seam was collapsed
without preserving its semantic contract.

Added **I-12 Report content type** to
`design/launch-composition-invariant.md`. Behavioral test
`test_report_content_contract_across_harnesses` added. I-7 prose also
tightened: driven-port typing should expose content contracts beyond
Python shape — a `-> str` return type documented as "user-facing
assistant message text" is the bar.

### D21.3 — I-10 tightened on fork start-row shape

Current I-10 says "spawn row created before fork transaction opens."
Smoke lane 4 observed that fork spawn *start* rows pre-populated
`harness_session_id`, unlike non-fork starts that receive it via a
later `update` event. That violates the spirit of row-before-fork
without violating the letter.

Tightened **I-10** wording to explicitly forbid pre-populating
`harness_session_id` on a fork child's `start` event. Behavioral test
`test_fork_start_row_omits_harness_session_id` added.

### D21.4 — Adapter transforms observable as I-13 (scope-wider addition)

Cross-cutting invariant inspired by the codex truncation bug that
corrupted the R06-v1 implementation cycle itself. Silent lossy
transforms at adapter boundaries produce work product that looks right
and is built against partial input. The `LaunchContext.warnings`
channel R06 already provides is the enforcement mechanism; the new
rule is that adapters either preserve semantics or surface a
`CompositionWarning`.

Added **I-13 Adapter transforms are observable** to
`design/launch-composition-invariant.md`. Noted as slightly wider than
original R06 scope but free to include given the machinery already
exists.

### D21.5 — Workspace-projection test tightened from reach to content

`test_workspace_projection_seam_reachable` asserts the seam runs inside
the pipeline. Smoke lane 2 showed reachable-but-wrong: a nearby seam
(report extraction) was reachable yet produced wrong content. Added
`test_workspace_projection_produces_semantically_correct_argv` to
assert the projected argv is semantically correct per harness, not
just that the sentinel appears somewhere.

### D21.6 — Plan-level constraints encoded as design inputs

Four new constraints added to `design/refactors.md` R06 for the
planning impl-orch to honor:
- Net pytest count non-negative across the R06 series (skeleton's
  landing deleted 5 tests without explicit replacement).
- Per-phase smoke lane assignment in `plan/overview.md`, not just
  per-phase unit-test lanes. Use the 5-lane pattern from R06-v1 smoke.
- Pre-implementation smoke baseline against HEAD before Phase 1, stored
  under `plan/pre-impl-smoke-baseline/`.
- Implementation runs against meridian-cli ≥ v0.0.30 (post-Fix-A).
  Prior R06 code artifacts are evidence-zero.

### D21.7 — Invariant → test coverage audit mandated before planning

Added a coverage-audit table in `refactors.md` mapping each of I-1..I-13
to at least one behavioral test. Invariants without a test are claims
the design cannot verify. The planning impl-orch MUST refine this
mapping during planning; gaps become planner-level blockers, not
implementation-level surprises.

### What D21 does not change

- DTO shape: unchanged. The 4 user-visible + 1 auxiliary + 2 internal
  type ladder from D20 holds.
- Pipeline stage decomposition: unchanged. 10 stages with sole owners
  remain.
- `observe_session_id` contract (D20): unchanged. Per-launch state
  legitimate, adapter-singleton forbidden.
- Verification triad: unchanged. Behavioral factory tests + CI drift
  gate + pyright/ruff/pytest. The drift gate now enforces 13 invariants
  instead of 10.
- Convergence verdict: the existing `ready-with-minor-followups` +
  architect closure still stands. D21 is additive refinement, not a
  convergence gap that requires another review round.

### Preserved findings / still out of scope

- Background-worker `disallowed_tools` correctness (unblocked by R06,
  separate work item).
- Issue #34 Popen-fallback session-ID observation (unblocked by
  `observe_session_id` seam, separate work item).
- `meridian doctor` reconciliation gap (smoke lane 5, likely
  pre-existing, state-layer; track as new work item after verifying via
  `git log` whether it predates the skeleton).
- LIFE-7 `spawn list --status finalizing` filter (smoke lane 2,
  unclear R06-relation).
- Stale `.flock` sidecars (smoke lane 5, cosmetic).

## How this file is used

- Reviewers: validate that every F1–F19 response is actually encoded in the
  spec/architecture leaves named under "Encoded in" for each row. If a response
  points at a spec/architecture leaf but the leaf does not make the claim, that
  is a convergence gap to flag.
- Planner: use D1–D21 as constraints that survive into the plan. D2, D3, D17,
  D18, D19, D20, and D21 in particular govern phase sequencing, the R06
  typed-pipeline invariants (3 driving adapters through one factory, raw
  `SpawnRequest` + `LaunchRuntime` at the boundary, split spec/projection/argv
  stages, fork after spawn row with no pre-populated session-id on start,
  fork lineage coherence across jsonl stores, report content type discipline,
  adapter transforms observable via `CompositionWarning`, `LaunchContext.warnings`
  as the only composition-warning sidechannel, reviewer drift gate verification
  with the 13-invariant prompt), and workspace-loading behavior. **D19 supersedes
  parts of D17 that named "hexagonal" as the load-bearing pattern**; the framing
  inside the shell is a typed pipeline. **D20 supersedes parts of D19 that named
  `project_launch_command` as a single stage**; the spec/projection/argv split is
  what makes the A04 seam reachable inside the A06 ordering. **D21 adds I-11,
  I-12, I-13 and tightens I-10 + I-7** based on R06-v1 smoke evidence; these are
  additive refinements, not convergence gaps. Hexagonal labels can stay as outer
  naming, but composition centralization is what makes R06 honest.
- Future rounds: when a new prior-round feedback file gets produced, append a
  new section here rather than rewriting these rows.

### D22 — Manual planning fallback after repeated planner stalls

**Directive (2026-04-16):** The implementation plan package for
workspace-config-design is authored directly by impl-orchestrator `p2037`
after two planner spawns (`p2039`, `p2040`) stalled without materializing
plan artifacts.

**Rationale:** At the time of planning fallback, the package still contained a
live contradiction around `MERIDIAN_WORKSPACE` scope. The contradiction was
understood well enough to keep planning moving, so direct plan authorship was
lower risk than stalling on more planner retries. Planning fallback kept the
work item moving while preserving spawn-based implementation, verification, and
review for all source changes.

**Historical note:** This was a temporary planning escape hatch, not a standing
precedence rule. After the 2026-04-16 design-package alignment pass, the v1
scope for `MERIDIAN_WORKSPACE` is again defined consistently by requirements,
spec, architecture, and decisions.

### D23 — Remaining-work planning must reopen residual R02 instead of assuming a clean handoff

**Directive (2026-04-16):** The remaining-work implementation plan must treat
R02 as still open. The handoff statement "R01/R02 are complete" is not used as
planning truth.

**Why:** Fresh review evidence from `.meridian/spawns/p2068/report.md` and
`.meridian/spawns/p2069/report.md` shows three unresolved issues in the live
repo:

- `meridian config init` still routes through `_ensure_mars_init()` and can
  create Mars-owned artifacts as a side effect.
- `config show` / `config get` do not share the loader's full user-config
  source resolution semantics, so default user config can be reported as
  `builtin`.
- `doctor` still has no shared config/workspace surface, which overlaps
  directly with upcoming `SURF-1`.

**Decision:** Regenerate the remaining-phase plan from the live repo state.
Residual R02 cleanup is explicit planning input and may share ownership with the
first workspace/surfacing phase.

**Alternatives rejected:**

- Assume R02 is closed and begin `WS-1` / `CTX-1` / `SURF-1` directly.
  Rejected because it would build new phases on a false config/surfacing
  baseline.
- Hold planning until every stale phase-2 lane writes a perfect terminal
  report. Rejected because the substantive blockers are already confirmed by two
  independent review lanes, and waiting on non-terminal sibling state does not
  improve planning quality.
