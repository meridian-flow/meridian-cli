# Final Reviewer Round — workspace-config-design

## Context

Design package for `workspace-config-design` work item is in the same work directory. Requirements in `requirements.md`, decisions in `decisions.md`, spec under `design/spec/`, architecture under `design/architecture/`, refactor agenda in `design/refactors.md`, feasibility in `design/feasibility.md`.

This is the final review pass before the design is handed to planning. The prior round (F1–F19 feedback) was a unanimous 5-0 reject; the current round is the fresh redesign. User wants an adversarial final sweep.

CLAUDE.md constraint: "No backwards compatibility needed — completely change the schema to get it right." D8 operationalizes this: no migration, no dual-read, no `config migrate`.

## What to review

Read the full design package in this order:
1. `requirements.md`
2. `decisions.md` (D1–D17)
3. `design/feasibility.md` (FV-1..FV-10 + Open Questions 1–7)
4. `design/spec/` (`overview.md`, then `config-location.md`, `workspace-file.md`, `context-root-injection.md`, `surfacing.md`, `bootstrap.md`)
5. `design/architecture/` (`overview.md`, then `paths-layer.md`, `config-loader.md`, `workspace-model.md`, `harness-integration.md`, `surfacing-layer.md`)
6. `design/refactors.md` (R01..R06)

Then address your assigned focus area below.

## Specific concerns flagged during orchestrator read

Use these as probes, not a checklist. Find what's actually wrong, not just what I suspected.

1. **D17 / R06 — launch-seam unification as a prereq to the workspace feature.** D17 mandates unifying primary and spawn composition seams *before* wiring workspace projection. Rationale: four features already duplicated; workspace would be the fifth. Questions worth probing:
   - Is R06's blast radius (`launch/context.py`, `plan.py`, `process.py`, `command.py`, plus unifying two `RuntimeContext` types) scoped correctly? Is anything missing that would leave R06 half-done?
   - D17 rejects "Depth 3 (narrow spec to spawn-only)" — primary launches don't get workspace roots. Is the rejection actually correct? What percentage of real meridian users launch primary vs spawn? (Implementation risk: we could ship spawn-only in v1 and defer R06.)
   - Does the `MERIDIAN_HARNESS_COMMAND` bypass mode-switch actually fit inside a unified seam cleanly, or does it force branches that leave the seam "unified" in name only?

2. **WS-1.u2 vs D12 — what happens when `MERIDIAN_WORKSPACE` is set to a *relative* path?** Spec says the env var is consulted "when set to an absolute path." But it doesn't say what happens when set to a relative path. Silent fallthrough to default discovery? Hard error? Parse warning? This edge case is unspecified.

3. **`SURF-1.e3` is missing from `design/spec/surfacing.md`.** Numbering jumps e1 → e2 → e4 → e5 → e6. Intentional deletion or stale numbering?

4. **D6 references R04 as a separate refactor.** `design/refactors.md` folds R04 into R01. D6 text is stale.

5. **R02 exit criteria: "No command reads from root while another writes to legacy."** D8 removed the legacy path entirely — there is no legacy to write to. Stale exit-criteria language.

6. **`unsupported:harness_command_bypass` applicability code.** Lives in `A04` (`harness-integration.md`) and is surfaced via `SURF-1.e5` generically. But spec `CTX-1.*` never mentions `MERIDIAN_HARNESS_COMMAND`. Is this an intentional spec/architecture layering choice or a spec gap?

7. **`extra_keys` on `ContextRoot`.** v1 user-facing schema is `path` + `enabled`. `extra_keys` exists purely for forward-compat unknown keys. Is this the right bucket for round-tripping, or does it over-engineer parsing for v1?

8. **Workspace-file path resolution when `MERIDIAN_WORKSPACE` points outside the project.** A01 says paths in `workspace.local.toml` resolve relative to the file. If the override file lives at `/home/user/shared-ws.toml`, a `path = "../sibling"` resolves to `/home/user/sibling`, not the project root's sibling. Is that the intended semantics? (VS Code convention says yes, but it deserves explicit confirmation in the design.)

9. **Schema `enabled` default of `True` (WS-1.u3) + `--from mars.toml` default of `false` (WS-1.e2).** These are consistent (explicit `enabled = false` wins), but worth sanity-checking the test plan covers both round-trips.

## Output contract

Report findings with severity: **blocker** (design is wrong), **major** (gap that needs resolution before planning), **minor** (stale text, doc nit), **nit** (optional improvement).

For each finding, cite the spec/architecture leaf, the decision ID, or the refactor ID. If you find problems I didn't list, prioritize those — the nine above are probes, not the target.

Keep the report structured and cite file paths + line numbers where relevant.
