# Architect Task: workspace-config design package (fresh redesign)

You are authoring the **spec tree + architecture tree + refactor agenda** for the `workspace-config` work item. A prior design round was rejected 5-0 by reviewers and removed. Requirements are unchanged. Your goal is a package that addresses every prior finding and reintroduces none of the flagged flaws.

## Load these first (required reading)

- `$MERIDIAN_WORK_DIR/requirements.md` — authoritative intent, constraints, non-goals. Do not re-derive.
- `$MERIDIAN_WORK_DIR/prior-round-feedback.md` — the 19 findings the prior design must address. Every one of them must be visible in your design (addressed in-line, or explicitly rejected with justification in comments; the design-orchestrator will do the final mapping in `decisions.md`, but your architecture should make the intent obvious).
- `$MERIDIAN_WORK_DIR/probe-evidence/probes.md` — live-code probe evidence already run. **Use this as ground truth; do not re-probe or re-derive.** Cite file + line from this document when you anchor design claims.

Load these skills as you work:

- `architecture` — design methodology and stress-testing.
- `dev-artifacts` — artifact conventions (spec/ tree, architecture/ tree, EARS IDs, hierarchical structure).
- `dev-principles` — operating guidance; treat violations as self-review findings before emitting.
- `ears-parsing` — EARS notation for spec leaves.
- `tech-docs` — keep the tree navigable; don't dump one flat wall.

## What you are producing

Under `$MERIDIAN_WORK_DIR/design/`:

1. **`spec/`** — hierarchical behavioral contract. EARS statements are the leaves with stable IDs (e.g. `CFG-1.2`, `WS-3.1`). Produce an `overview.md` that indexes the tree, plus subsystem files:
   - `spec/config-location.md` — where committed config lives, migration states, divergent-file policy.
   - `spec/workspace-file.md` — workspace topology file schema, discovery, scope, validation behavior.
   - `spec/context-root-injection.md` — how declared roots reach harness launches, per-harness applicability, ordering against parent-forwarding / user passthrough.
   - `spec/surfacing.md` — how `config show`, `doctor`, and spawn diagnostics expose workspace/config state.
   - `spec/bootstrap.md` — first-run behavior, what is and isn't auto-created at the repo root.

   Split further if a subtree passes the "too many responsibilities" threshold; fold back if a file has three bullets.

2. **`architecture/`** — hierarchical technical realization, observational rather than prescriptive. Produce `overview.md` plus subsystem files that cross-link to the spec leaves they realize. Suggested shape, adapt as needed:
   - `architecture/paths-layer.md` — repo-root file abstraction (new module), relationship to `StatePaths`, `MERIDIAN_WORKSPACE` env, discovery order.
   - `architecture/config-loader.md` — dual-read (legacy + root) during migration, end-state single-read, precedence unchanged, resolver + command-family consistency.
   - `architecture/workspace-model.md` — internal data shape for workspace roots (structured entries per prior F5), parsing, validation levels (fatal vs. advisory per prior F10), forward-compat for unknown keys.
   - `architecture/harness-integration.md` — how workspace roots reach claude and codex projections, ordering relative to user passthrough and parent-forwarding, dedupe semantics, per-harness applicability reporting (prior F6), opencode stance (v1).
   - `architecture/surfacing-layer.md` — concrete JSON shape for `config show`'s workspace section (per prior F14), `doctor` output, spawn-time noise policy (prior F11).
   - `architecture/migration-flow.md` — staged deprecation, `config migrate` semantics including the four divergent-file cases (prior F19), advisory cadence scope (prior F18), sunset trigger (prior F17).

3. **`refactors.md`** — agenda of structural rearrangement the planner must sequence. Every entry has: title, scope (touched files/modules with line numbers citing probes.md), exit criteria, whether it's a prep refactor (before feature work) or a follow-up. Key refactor entries the prior round got wrong — these must be present and correctly scoped:
   - Separating repo-root file policy from `state/paths.py` (prior F8).
   - Rewiring the config command family end-to-end (not just the loader; prior F3, F7).
   - Centralizing `--add-dir` emission across harness projections if duplication emerges.
   - Removing the `.meridian/config.toml` gitignore exception after the migration completes (sunset).

## Hard constraints — do not regress

Prior-round flaws that must not reappear:

- **F1 (codex has --add-dir)**: v1 supports both claude and codex. `--add-dir` is inert under codex `read-only` sandbox — surface this per-harness in `config show`/`doctor`, don't silently no-op.
- **F2 (models is Mars-owned)**: no `models.toml` migration in this design.
- **F3 (config commands bypass loader)**: any location change rewires `_config_path` AND `_resolve_project_toml` AND `ensure_state_bootstrap_sync` AND the CLI help AND the manifest strings AND smoke/unit tests. See probes §4 for the full site list.
- **F4 (dedupe ordering)**: `dedupe_nonempty` is first-seen (probes §2). User passthrough `--add-dir` must come first in the emitted command; workspace-emitted `--add-dir` comes after. State this ordering in `architecture/harness-integration.md` with the probe citation.
- **F5 (premature abstraction)**: internal workspace-root model has structured entries (path, enabled, source, order, [optional: tags]); user-facing TOML schema stays minimal in v1. Do not expose a flat `list[Path]` abstraction.
- **F6 (silent no-op)**: explicit per-harness applicability in `config show`/`doctor`. No silent skips.
- **F7 (under-scoped RF-1)**: covered by probes §4; refactors.md must enumerate these.
- **F8 (StatePaths pollution)**: new `ProjectPaths` / `RepoFiles` module. Do not push root-file policy into `state/paths.py`.

UX/convention findings to honor:

- **F9 (silent file creation)**: first-run creates `.meridian/` state dirs and `.meridian/.gitignore`. Root `meridian.toml` is created ONLY via `config init` / `config migrate`. Advisory messages are fine.
- **F10 (fatal scope)**: invalid `workspace.local.toml` is fatal only for commands that need workspace-derived dirs (spawns, `workspace *` commands). Inspection commands report `workspace.status = invalid` and continue.
- **F11 (warn spam)**: missing roots warn at `doctor`/`config show` level only; spawn-level: either warn-once-per-session or debug-level. Pick one, pin it.
- **F12 (unknown keys)**: preserve for forward-compat; surface in `doctor`/`config show` as warnings, not silent debug.
- **F13 (workspace init --from mars.toml)**: default init produces a minimal file with commented examples. Any entries sourced from mars default to `enabled = false` pending user edit.
- **F14 (config show shape)**: `workspace: {status, path, roots: {count, enabled, missing}, harness_support: {claude: ..., codex: ...}}`. Text output stays flat/grep-friendly.
- **F15 (naming)**: **rename the local file to encode locality** — `workspace.local.toml` (or equivalent `.local`/`.override` suffix). Rationale: convention across pnpm/npm/Yarn/Rush/Nx/Bazel/Go/Cargo/Bun/Deno is that `workspace.*` is committed team topology. A gitignored `workspace.toml` lies to the reader. If you reject this rename, justify explicitly in architecture comments so the design-orchestrator can fold the reasoning into `decisions.md`.
- **F16 ([context-roots] naming)**: low priority. Pick `[context-roots]` or `[extra-dirs]`/`[include-dirs]`. State the choice.
- **F17 (no sunset trigger)**: design Phase A (dual-read + advisory), Phase B (warning + remediation), Phase C (fallback removed). Pin the transitions to explicit triggers (version bumps; CLAUDE.md says "No backwards compatibility needed — completely change the schema to get it right", so Phase B/C can be aggressive).
- **F18 ("one-time advisory")**: pick per-invocation. Simplest, no new suppression state needed. State this explicitly.
- **F19 (migrate idempotency)**: specify the four cases — byte-equal → delete legacy; legacy-only → move; root-only → no-op; divergent → abort with explicit "pick a winner" error. No destructive defaults.

## What to carry forward

From the prior round's sound framing (prior-round-feedback.md "What should carry forward"):

- Boundary-first reframing: committed project policy at repo root, `.meridian/` trends local/runtime/gitignored.
- Mars / Meridian separability.
- `org/repo` canonical identifiers for AGENTS.md and workspace config.
- Workspace is topology, not a settings junk drawer.
- Single-repo users experience zero new complexity.
- TOML format everywhere.
- Non-goals held firm per requirements.md.

## Deliverable checklist (self-review before emitting)

- Every subsystem in `spec/` has EARS statements with stable IDs; every statement is testable (has a concrete trigger/pre-condition, a concrete observable behavior).
- Every `architecture/` file cross-links to the spec IDs it realizes.
- `refactors.md` covers the call-site blast radius from probes §4.
- No regression on F1–F19. Where you've chosen to reject a finding, leave an explicit inline note so `decisions.md` can reference it.
- Opencode stance is either "supported with probe evidence" or "unsupported in v1, surfaced in `config show`/`doctor`" — no silent no-op.
- Divergent-file policy in `config migrate` is explicit for all four cases.
- Ordering of `--add-dir` emission in claude and codex projections is explicit and cites probe §2 + probe §5/§6.

## Report

Produce a terminal report with: files written, subsystem decomposition, outstanding open questions (if any), and a short self-check mapping to F1–F19. Do not block on perfection — log open questions in `architecture/overview.md` under "Open Questions" if they genuinely cannot be resolved without upstream input.

Stay at design altitude. Observational, not prescriptive. No implementation code. Let the planner and coder decompose later.
