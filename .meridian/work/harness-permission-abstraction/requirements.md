# Harness Permission Abstraction

**Tracked:** https://github.com/meridian-flow/meridian-cli/issues/36 (and #23 — folded in)

## Problem

Meridian core leaks harness-specific vocabulary, and the abstractions it does have are partial, silent, and self-contradictory. Three concrete failures motivate this work:

1. **Silent allowlist drop on Codex.** `project_codex_subprocess.py:151` strips `--allowedTools` / `--disallowedTools` from codex spawns and logs a warning. A profile that says "this agent can only use Read and Grep" gets ignored on codex while pretending to work. Warnings cost LLM context bytes for every spawn that ever sees one, never get actioned, and train agents to ignore the warning channel.

2. **`acceptEdits` overrides disallow lists on Claude.** Spawn p1900 (impl-orchestrator on opus) had `disallowed-tools: [Edit, Write, NotebookEdit, ...]` plus `approval: auto`. Meridian projected `--permission-mode acceptEdits --disallowedTools Edit,Write,...`. Claude's `acceptEdits` mode auto-approves file editing tools regardless of `--disallowedTools`. Opus used Edit 6× and Write 12× with zero permission-denied events. Same structural failure: meridian projecting one thing, harness enforcing another, no signal to the user.

3. **Silent fall-through on OpenCode.** `_permission_flags_for_harness()` in `adapter.py` has no OpenCode branch at all. Every `approval` value falls through to `()`. A profile targeting OpenCode with `approval: yolo` gets no enforcement, no warning, no signal.

The structural shape is the same in all three cases: Meridian designs an abstraction (approval / sandbox / tool allowlist), each adapter implements part of it differently, and the gaps are filled with silent strips, warnings nobody reads, or hidden translations that are wrong.

The current plumbing also conflates two orthogonal concerns. `approval: yolo|auto|confirm` collapses (a) does the model prompt before tool use, and (b) what OS-level sandbox does it run in. Codex exposes both as separate flags; Claude only exposes approval at the CLI layer. Meridian tries to unify under one field and ends up over-specifying for Claude and under-specifying for Codex.

## Stance: Meridian-First

Previously implicit: "profile schema should map cleanly onto Claude's CLI shape so users can run agents through `claude` directly with minimal translation." That soft rule is **dropped**.

Meridian's permission vocabulary is the first-class abstraction. Each harness adapter is a translation target, not a constraint on the vocabulary. Meridian owns a single unified intent. Adapters realize the intent or refuse to spawn. There are no per-harness override blocks in profiles; there are no escape hatches for power users to write harness-native flags directly. If you want to bypass Meridian and run agents through `claude` / `codex` / `opencode` directly, you build your own translation. Meridian no longer owes anyone schema compatibility with any single harness's CLI shape.

This unblocks: introducing intent vocabulary that no single harness uses natively (e.g., a unified "tool allowlist" even though codex doesn't expose one as a flag); adapters generating per-spawn config files instead of being limited to flag projection; failing closed when a harness can't realize an intent rather than silently degrading.

## Design Direction

**Three orthogonal intent axes, owned by meridian:**

- `approval` — does the model prompt before tool use. Vocabulary TBD at design time; current `{yolo, auto, confirm}` is a starting point but the rename should distinguish "autonomous" (no prompts) from "bypass" (autonomous + skips sandbox).
- `sandbox` — what **OS-level** process sandbox the spawn runs in. This is genuinely codex-only (claude `--permission-mode plan` is prompt-level, not OS-level; opencode is roughly the same). Defense in depth: the `tools` axis controls what the *model* invokes; `sandbox` controls what the *process* can actually do at the kernel level. An allowlisted `Bash` tool is one prompt injection away from `Bash("rm -rf $HOME")`; only the OS sandbox stops that. Vocabulary candidates from parity work: `read-only`, `workspace`, `full`. Profiles that demand a non-`full` sandbox on claude/opencode raise `HarnessCapabilityMismatch` — no fake denylist-as-sandbox translation. If you want OS sandboxing, you pin `harness: codex`.
- `tools` — which tools the *model* is allowed to invoke through the harness tool layer. Profile-level fields `tools:` / `disallowed-tools:` migrate into this axis. They are no longer adapter-coupled. This is the layer the model sees; it is independent from sandbox, which is the layer the process runs under.

**Adapter contract:** every adapter must realize every intent combination, or raise `HarnessCapabilityMismatch` with a specific reason. There is no third option. No warn-and-degrade. No silent strip. No fallthrough to defaults. No warnings of any kind on capability mismatches — either it's realizable (silently and correctly) or it's a hard error that fails the spawn.

**Realization mechanisms per harness** (locked in from parity design):

- **Codex tools axis:** per-spawn `CODEX_HOME` with generated `config.toml`. Codex adapter materializes the config from the `tools` intent: `[features]` flags + `[apps._default].enabled = false` + `default_permissions` for the allowlist; `[profile].sandbox_mode` + `approval_policy` for the other two axes. Reference: `.meridian/work/managed-readonly-allowlist-parity/design/architecture/codex-home.md`.
- **Codex sandbox axis:** native `--sandbox` flag.
- **Claude tools axis:** `--allowedTools` / `--disallowedTools` (existing).
- **Claude sandbox axis:** `--permission-mode plan` (read-only) plus explicit denylist of mutating tools — plan alone is not fail-closed.
- **OpenCode tools axis:** `OPENCODE_PERMISSION` env JSON (existing).
- **OpenCode sandbox axis:** same env JSON with `*: "deny"` baseline + per-tool allow.

## Folded In: `managed-readonly-allowlist-parity`

That work item produced a converged design package focused on read-only + tool allowlist enforcement parity across the three harnesses. Its scope is fully absorbed here. Status set to `superseded by harness-permission-abstraction`.

**Artifacts to consume as input** (live at `.meridian/work/managed-readonly-allowlist-parity/`):

- `requirements.md` — parity-specific framing.
- `design/spec/` — EARS contract for cross-harness fail-closed behavior, per-harness enforcement, dry-run surfacing.
- `design/architecture/` — `codex-home.md` (per-spawn `CODEX_HOME` materialization), `capability-check.md` (where `HarnessCapabilityMismatch` raises), `smoke-matrix.md`.
- `design/feasibility.md` — live-probed against codex 0.120.0; per-spawn `CODEX_HOME` config override verified working.
- `design/refactors.md` — 7 sequenced refactors. R1 (fix `CodexAdapter.resolve_session_file()` hard-code at `codex.py:392`) is foundational. R4 (delete `_strip_tool_flags_for_codex`) is the structural signal that parity has shipped.
- `decisions.md` — concrete answers to overlapping open questions.
- Prior research spawns: p1722 (investigator), p1723 (explorer), p1724 (researcher), p1729 (codex `config.toml` schema), p1730 (CODEX_HOME plumbing), p1734 (parity design synthesis).

## What Changes

**Schema:**

- Profile `approval` field migrates from `{yolo, auto, confirm}` to the new vocabulary.
- New (or renamed) `sandbox` field carries the OS-level concern separately.
- Existing `tools:` / `disallowed-tools:` fields stay structurally but are now consumed by the unified permission resolver, not piped directly into adapter-specific projections.
- All profiles in `meridian-base`, `meridian-dev-workflow` migrated in lockstep.

**Code:**

- Delete `_permission_flags_for_harness()` in `src/meridian/lib/harness/adapter.py`.
- Delete `_strip_tool_flags_for_codex` in `src/meridian/lib/harness/projections/project_codex_subprocess.py` (parity refactor R4).
- Delete the warn-on-strip path entirely. Warnings on capability mismatch are forbidden.
- Add `realize_permission(intent) -> PermissionRealization` (or equivalent) on each harness adapter.
- Codex adapter gains a config.toml materializer that writes to per-spawn `CODEX_HOME` under `.meridian/spawns/<id>/codex-home/`. Narrow-copy `auth.json` + `.credentials.json` from user's `~/.codex` for auth continuity; everything else fresh per spawn.
- Fix `CodexAdapter.resolve_session_file()` at `codex.py:392` to honor injected `CODEX_HOME` (parity R1).
- OpenCode adapter gets a real implementation, not the current silent no-op.
- Central `resolve_permission_pipeline` raises `HarnessCapabilityMismatch` *before* any launch-layer side effect when an intent is unrealizable.

## Constraints

- **No backwards compatibility needed.** Per CLAUDE.md "No real users" policy. Break the schema.
- **Every intent combination gets explicit handling per harness** — either a realization or an explicit raise. No silent no-ops, no warnings.
- **Test coverage:** unit tests for each adapter's realization method, covering every cell in the intent × harness matrix (including unsupported cells that must raise).
- **Smoke tests:** verify each harness actually refuses a write under `sandbox: read-only` and actually refuses a non-allowlisted tool under `tools: [Read, Grep]`. Smoke matrix from parity design (`design/architecture/smoke-matrix.md`) carries forward.
- **Codex version floor:** config layering relied on here landed in codex-rs `0.78.0`+. Declare and probe.
- **Plumbing already safe:** `CODEX_HOME` passes the `preflight.extra_env` merge guard (streaming-parity-fixes S046), and the codex session extractor honors `launch_env["CODEX_HOME"]` (streaming-parity-fixes F12). Build on top, do not redesign.
- **Meridian-state-write exceptions in codex sandbox.** When the codex adapter generates a `config.toml` with a non-`full` sandbox, it must add `[permissions.<name>.filesystem]` write exceptions for paths meridian itself writes to during the spawn lifecycle: `<state_root>/spawns/<spawn_id>/` (artifact dir — heartbeat, report, output.jsonl, harness.pid), `<state_root>/work/<work_id>/` (when the spawn has a work item), and `$MERIDIAN_FS_DIR` (when shared filesystem is in use). These are derived from the spawn context the adapter already has access to. The user never specifies them. **Not** included by default: `~/.uv`, `~/.cache/*`, repo-root writes (the `tools` axis governs whether the agent can edit the repo). Sandboxed agents should not be running tooling installs.
- **No per-harness override blocks in profiles.** Profiles speak meridian intent. If a profile cannot run on a chosen harness, that's a hard spawn-time error.
- **Projections stay CLI-shape-only.** Filesystem writes (codex config.toml materialization) belong in a launch-context / connection-start hook, not in the projection layer.

## Open Questions for Design

1. Exact intent vocabulary for `approval`. Starting points: `{autonomous, interactive, bypass}`, where `bypass` covers codex's `--dangerously-bypass-approvals-and-sandbox` semantic.
2. Exact intent vocabulary for `sandbox`. Parity design used `{read-only, workspace, full}`; design should validate this maps cleanly onto every harness's native concept.
3. Is `bypass` an `approval` value or a separate axis? Current codex `yolo` is a combined bypass — suggests it might want its own axis.
4. Where does the unified permission resolver live? Today `_permission_flags_for_harness()` is in `harness/adapter.py`; the new resolver probably belongs at the launch-context level since it needs `spawn_id` to materialize codex config dirs.
5. How are tool intent + sandbox intent combined per harness when realization mechanisms differ? On codex they both fold into the same generated config.toml; on claude they're different flags; on opencode they're both in the same env JSON. The adapter contract needs to express that one intent → one realization, not three independent translations.

## Success Criteria

1. `adapter.py` contains no harness-specific flag strings. Grep for `--permission-mode`, `--full-auto`, `--dangerously-*` returns zero hits outside per-harness adapter files.
2. Each harness adapter (`claude.py`, `codex.py`, `opencode.py`) owns its full permission realization. Adding a fourth harness = one new adapter file, no central edits.
3. OpenCode permission intent is realized. No silent drops anywhere.
4. Codex tool allowlist is realized via generated `config.toml`. The `_strip_tool_flags_for_codex` warning path is deleted.
5. `acceptEdits`-style hidden semantic shifts (the p1900 bug) are structurally impossible — the resolver either refuses contradictory intents or realizes them coherently across all selected projections.
6. Every profile in `meridian-base` and `meridian-dev-workflow` migrated to the new schema and verified.
7. Documentation in `agent-creator` skill, CLAUDE.md, and relevant docs updated to the new vocabulary.
8. Smoke matrix passes: each harness × (read-only sandbox, narrow allowlist, both) confirms enforcement is real, not theatrical.
9. No warnings emitted anywhere on capability mismatch. Either realization succeeds or spawn fails.
