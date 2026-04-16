# Feasibility Record

Probe evidence and assumption verdicts for the workspace-config design round. Every claim is cited to a live code line in the `meridian-cli` checkout or to a `codex-cli 0.120.0` help-output capture. This document is ground truth for the spec and architecture trees; `decisions.md` maps prior-round findings to design responses; `design/refactors.md` consumes the blast-radius list below to build the refactor agenda.

> Detailed source captures live in `$MERIDIAN_WORK_DIR/probe-evidence/probes.md`. This file records the verdicts distilled from those probes so the planner and reviewers don't need to re-run them.

## Verdicts

### FV-1 Codex supports `--add-dir`

**Verdict**: feasible. v1 injects workspace roots into claude and codex.

**Evidence**: `codex exec --help` on codex-cli 0.120.0 documents `--add-dir <DIR>` as "Additional directories that should be writable alongside the primary workspace" (see `probes.md §1`).

**Residual risk**: `--add-dir` is inert when the effective sandbox is `read-only`. Codex emits a runtime warning but `config show` / `doctor` must also surface this applicability so users don't reason from assumed behavior. Captured in `architecture/harness-integration.md` and spec `SURF-1.*` leaves on surfacing.

### FV-2 `dedupe_nonempty` is first-seen, and ordering of workspace projection is deterministic

**Verdict**: confirmed. Design commits to the ordering
`user passthrough → projection-managed → workspace-emitted` on the Claude path,
and `user passthrough (spec.extra_args) → workspace-emitted` on the Codex path.

**Evidence**: `lib/launch/text_utils.py:8-19`; `lib/harness/claude_preflight.py:131-147`; `lib/harness/projections/project_codex_subprocess.py:219`. See `probes.md §2`, `§5`, `§6`.

**Residual risk**: none. The design fixes prior F4 by putting user passthrough first so any downstream first-seen dedupe preserves explicit CLI intent.

### FV-3 Meridian does not read `models.toml`; no Meridian-side models migration is justified

**Verdict**: out of scope. `rg "models\.toml|models_merged"` returns zero hits in `src/` and `tests/`. Mars owns alias resolution via `.mars/models-merged.json` (`lib/catalog/model_aliases.py:229`). The design does not propose a Meridian-owned `models.toml` and does not touch mars-agents.

**Evidence**: `probes.md §3`.

**Residual risk**: none. If a future change introduces Meridian-side model ownership, that is a separate decision with separate ownership analysis.

### FV-4 Moving committed config to the project root has a fully enumerated blast radius

**Verdict**: feasible, but the refactor agenda MUST cover all call sites. Any "one-function change" framing is rejected.

**Evidence**: `probes.md §4` enumerates ≥ 9 source sites + help text + smoke + unit tests:

- `lib/state/paths.py:21, 33, 127` — canonical path, gitignore policy.
- `lib/config/settings.py:25, 206-210, 213-227` — loader resolver + user-config env.
- `lib/ops/config.py:342-343, 602-606, 737-763, 758, 777, 827, 846, 872` — command family + bootstrap.
- `lib/ops/manifest.py:242, 266` — CLI help.
- `cli/main.py:806-815` — config_app description.
- `tests/smoke/quick-sanity.md:45-47`, `tests/ops/test_runtime_bootstrap.py`, `tests/ops/test_config_warnings.py`, `tests/config/test_settings.py`, `tests/test_state/test_paths.py`, `tests/cli/test_sync_cmd.py`, `tests/test_cli_bootstrap.py` — tests.

**Residual risk**: the command family (`config show/get/set/reset/init`) currently bypasses `_resolve_project_toml` and operates directly on `_config_path`. A partial refactor that rewires only the loader would leave reads resolving from the new location while writes still target `.meridian/config.toml`. `design/refactors.md` pins this as a single coordinated refactor (R02), not two.

### FV-5 `StatePaths` is `.meridian`-scoped and is the wrong home for project-root file policy

**Verdict**: new module required. Root-file discovery and root `.gitignore`
policy live outside `state/paths.py`. If `MERIDIAN_WORKSPACE` returns in a
future version, its override handling belongs there too rather than in the
state-paths layer.

**Evidence**: `lib/state/paths.py:93-128`, `lib/config/settings.py:789-823` (only `resolve_repo_root` exists at project-root level today; no file enumeration (this will be renamed to `resolve_project_root` per R01)). See `probes.md §7`.

**Residual risk**: naming bikeshed (`ProjectPaths` vs `RepoFiles` vs `RootConfigPaths`). The architecture tree commits to one name; no functional implication.

### FV-6 First-run auto-bootstrap currently creates `.meridian/config.toml` unconditionally; root-file creation must be opt-in

**Verdict**: the bootstrap path must be split. `.meridian/` state directories and `.meridian/.gitignore` continue to be created on every run (runtime state is always needed). Root `meridian.toml` is created ONLY by `config init`.

**Evidence**: `lib/ops/config.py:737-763` — `ensure_state_bootstrap_sync` auto-writes `_scaffold_template()` if the config file is missing; called unconditionally from `lib/ops/runtime.py:66`. See `probes.md §8`.

**Residual risk**: when no `meridian.toml` exists at the project root, the loader runs on built-in defaults silently. `config init` is the user's entrypoint to opt into a committed project config. Stale `.meridian/config.toml` files in existing repos are ignored — the file is no longer read and is deleted by `R01` as part of the boundary cleanup.

### FV-7 Claude already has a projection-managed middle section; workspace projection extends it

**Verdict**: feasible. Claude's existing preflight-owned `execution_cwd` and
parent-forwarded `additionalDirectories` become the projection-managed middle
section, and workspace roots append after them.

**Evidence**: `lib/harness/claude_preflight.py:131-147`. See `probes.md §6`.

**Residual risk**: interaction with parent-forwarding edge cases (no parent `.claude/settings.json`, symlink to parent session dir). Existing behavior unchanged.

### FV-8 — (obsolete) config migrate policy

Removed per D8 (no migration).

### FV-9 OpenCode has day-1 workspace support through `permission.external_directory`

**Verdict**: feasible. OpenCode does not expose native `--add-dir` parity, but
it does expose `permission.external_directory` in its config schema plus inline
config delivery via `OPENCODE_CONFIG_CONTENT`. Day-1 support is therefore a
projection to `active:permission_allowlist`, not an unsupported state.

**Evidence**:

- `.meridian/work/workspace-config-design/opencode-probe-findings.md §1-§2` —
  no first-class multi-root field or agent roots field was found.
- `.meridian/work/workspace-config-design/opencode-probe-findings.md §4` —
  `permission.external_directory` is the documented native permission mechanism
  for paths outside the primary root.
- `.meridian/work/workspace-config-design/opencode-probe-findings.md §8` —
  recommendation is day-1 support via native file-tool access, not a wait-for-upstream posture.

**Residual risk**: semantic gap, not capability gap. The extra roots are usable by
OpenCode's file tools, but they are not surfaced as named workspace roots in the
harness UX. The architecture captures this as
`active:permission_allowlist` rather than pretending OpenCode gained `--add-dir`
parity.

### FV-10 OpenCode config overlay can be delivered through `OPENCODE_CONFIG_CONTENT`

**Verdict**: feasible. The OpenCode projection can keep a structured
`config_overlay` and materialize it into `env_additions` without adding a
launch-layer branch.

**Evidence**:

- `.meridian/work/workspace-config-design/opencode-probe-findings.md §5` —
  `OPENCODE_CONFIG_CONTENT` exists as an inline config env mechanism.
- `.meridian/work/workspace-config-design/opencode-probe-findings.md §2` —
  config schema includes the relevant permission surface.
- `.meridian/work/workspace-config-design/opencode-probe-findings.md §4` —
  config layering is already how OpenCode accepts non-CLI capability changes.

**Residual risk**: explicit merge semantics remain to be pinned if a parent
environment already supplies `OPENCODE_CONFIG_CONTENT`. The architecture records
that as an open question instead of hiding it.

### FV-11 R06 raw-`SpawnRequest` factory boundary is viable

**Verdict**: feasible. The factory can accept a fully raw `SpawnRequest`
(prompt, model ref, harness id, agent ref, skills refs, sandbox/approval/
allowed/disallowed tools, extra_args, mcp_tools, retry policy, raw session
intent) and produce a complete `LaunchContext` without driver-side
pre-resolution. The persisted prepare→execute artifact reduces to a serialized
`SpawnRequest`; the resolver and resolved permission config are reconstructed
by the factory at execute time.

**Evidence**: code probe of current behavior shows resolver is *already*
constructed twice today — once in `lib/ops/spawn/prepare.py:323` to seed the
preview command and store the persisted plan, and again in
`lib/ops/spawn/execute.py:861` for the live launch. The current resolver
object stored on `PreparedSpawnPlan.execution.permission_resolver` is not
load-bearing across the boundary; only the raw inputs survive serialization
in any meaningful way (the persisted `PermissionConfig` is a frozen pydantic
DTO with no live mutable state). Removing the persisted resolver and
reconstructing in the factory is a behavior-preserving consolidation.

**Evidence**: `lib/launch/context.py:175-203` — the current factory body
already reads `plan.execution.permission_resolver` and
`plan.execution.permission_config` *without* mutating them. They function as
opaque pass-throughs from the driver. The raw-input redesign is the same
data flow inverted: instead of driver → factory passing pre-resolved objects,
factory consumes raw fields and produces them locally. No new reachability
or lifetime constraint emerges.

**Evidence**: `lib/harness/adapter.py:150-163` — `SpawnRequest` already
exists on the harness adapter protocol but is unused. Making it load-bearing
removes the dead-abstraction signal and sidesteps the naming churn of
introducing yet another DTO.

**Residual risk**: per-driver constructions of `SpawnRequest` will need to
populate every raw field today's drivers compute incidentally (e.g. profile
name from `--agent` resolution). The structural review already enumerated
the construction sites (`launch/plan.py:178-213`,
`ops/spawn/prepare.py:356-397`, `app/server.py:332-350`,
`cli/streaming_serve.py:69-87`, `ops/spawn/execute.py:397-425`); R06 collapses
each to a single `SpawnRequest(...)` call followed by `build_launch_context()`.
No driver computes inputs the factory cannot reconstruct from raw fields.

**Residual risk**: the worker prepare→execute serialization needs round-trip
fidelity. `SpawnRequest` is a frozen pydantic model with primitive-typed
fields; pydantic's `model_dump_json` / `model_validate_json` cover this with
no `arbitrary_types_allowed=True` escape hatch (the current
`PreparedSpawnPlan` requires this hatch to carry the live `PermissionResolver`).
Removing the live resolver from the persisted artifact is a strict simplification.

### FV-12 Reviewer-as-drift-gate fits the CI loop

**Verdict**: feasible. The agent-staffing skill documents reviewer-as-CI
architectural drift gate as an established pattern for surfaces where
declared invariants are too semantic for grep checks. Meridian itself has the
spawn machinery to invoke it from CI (`meridian spawn -a reviewer`).

**Evidence**: `agent-staffing` skill resource section "@reviewer as
Architectural Drift Gate" describes the exact pattern. The skill recommends
pairing with deterministic behavioral tests as backstop, which matches R06's
verification design.

**Residual risk**: reviewer judgments are probabilistic. R06 mitigates this
by (a) pinning the highest-leverage invariants as deterministic factory
tests, and (b) using a cheaper model variant for the routine drift check
(`meridian models list` → use a `mini`/`flash` family for routine PRs;
escalate to default reviewer model on PRs that touch the protected surface
heavily). The invariant prompt at
`.meridian/invariants/launch-composition-invariant.md` is version-controlled
and updated alongside legitimate architecture changes.

**Residual risk**: CI cost. R06 sets the drift gate to spawn only on PRs
touching files under `src/meridian/lib/(launch|harness|ops/spawn|app)/` so
typical PRs do not pay the cost.

## Open Questions

1. **OpenCode overlay collision policy.** Resolved per D15. If a parent
   environment already sets `OPENCODE_CONFIG_CONTENT`, meridian's OpenCode
   adapter skips workspace projection and emits a diagnostic. The user's
   explicit env value wins. Silent deep-merge rejected as hostile
   invisible-modification behavior.

2. **`[context-roots]` vs `[extra-dirs]` table naming (prior F16).**
   **Status:** deferred. Low priority; architecture commits to `[context-roots]`
   for consistency with Meridian's existing "context" language
   (`MERIDIAN_CHAT_ID`, "context handoffs"). If a reviewer prefers
   `[extra-dirs]`, trivial rename.

3. **`workspace.local.toml` rename rationale (prior F15).** Accepted. The
   architecture uses `workspace.local.toml` explicitly; decisions.md records the
   rationale (pnpm/npm/Yarn/Rush/Nx/Bazel/Go/Cargo/Bun/Deno all treat
   `workspace.*` as committed team topology; a gitignored `workspace.toml` lies
   to the reader).

4. **`MERIDIAN_WORKSPACE` path resolution semantics.** Deferred with the
   feature per updated D12/D13/D18. V1 uses only canonical sibling discovery:
   `workspace.local.toml` next to the active `.meridian/` directory. Paths
   *inside* `workspace.local.toml` still resolve relative to the file itself,
   matching VS Code `.code-workspace` convention.

5. **Missing env-target file behavior.** Deferred with the feature per updated
   D13. V1 has no env override path, so there is no env-target error surface in
   this version.

6. **`workspace init --from mars.toml` path heuristic.** Deferred out of v1 per
   updated D14. The open question remains archived as future context only; no
   v1 implementation or test plan should assume this variant exists.

7. **OpenCode subprocess/streaming parity.** Resolved per D16 via code
   investigation. Both paths ultimately call `asyncio.create_subprocess_exec`
   with an `env` param (see `src/meridian/lib/harness/connections/opencode_http.py:311-330`
   and `src/meridian/lib/ops/spawn/execute.py:462`). `env_additions` — including
   `OPENCODE_CONFIG_CONTENT` — flow identically to the child process in both
   modes. No architecture change needed; the projection `env_additions` channel
   works uniformly. A separate cleanup issue (meridian-flow/meridian-cli#32)
   tracks removing the unreachable subprocess-runner code.

## How this file was produced

Probes re-run on 2026-04-14 against `meridian-cli` HEAD and `codex-cli 0.120.0`. Full capture in `$MERIDIAN_WORK_DIR/probe-evidence/probes.md`. Verdicts above are distilled from that capture. When reviewers rerun probes, probes.md is the starting point; if any probe changes behavior, update this file's verdicts first, then propagate to spec/architecture/refactors.
