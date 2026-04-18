# Final Consistency Review — Workspace-Config Design

You are the **consistency reviewer** on a final pass before the design hands off to `@impl-orchestrator`. Your focus is internal coherence of the design package: do the spec, architecture, decisions, refactors, and feasibility artifacts describe the same thing consistently, with clean traceability?

This is not a design-quality review. The design has already gone through review-to-convergence. Your job is to catch the kind of drift that accumulates across many edits: stale cross-references, contradictory claims, orphaned EARS statements, abandoned open questions, terminology inconsistency.

## Files to load

Required:

- `.meridian/work/workspace-config-design/requirements.md`
- `.meridian/work/workspace-config-design/decisions.md`
- `.meridian/work/workspace-config-design/design/feasibility.md`
- `.meridian/work/workspace-config-design/design/refactors.md`
- `.meridian/work/workspace-config-design/design/spec/overview.md`
- `.meridian/work/workspace-config-design/design/spec/config-location.md`
- `.meridian/work/workspace-config-design/design/spec/workspace-file.md`
- `.meridian/work/workspace-config-design/design/spec/context-root-injection.md`
- `.meridian/work/workspace-config-design/design/spec/surfacing.md`
- `.meridian/work/workspace-config-design/design/spec/bootstrap.md`
- `.meridian/work/workspace-config-design/design/architecture/overview.md`
- `.meridian/work/workspace-config-design/design/architecture/paths-layer.md`
- `.meridian/work/workspace-config-design/design/architecture/config-loader.md`
- `.meridian/work/workspace-config-design/design/architecture/workspace-model.md`
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`
- `.meridian/work/workspace-config-design/design/architecture/surfacing-layer.md`

## Checks

### 1. EARS ↔ architecture traceability

For each architecture leaf (A01–A05), verify:
- Every EARS ID listed in `Realizes:` actually exists in the referenced spec leaf (not a renamed, deleted, or moved ID).
- Every substantive EARS statement in each spec leaf is `Realized by` at least one architecture leaf.

For each spec leaf, verify:
- `Realized by:` pointers name architecture files that exist and cover the spec's EARS IDs.
- No orphan EARS: every statement that imposes a constraint is reachable from some architecture leaf.

### 2. Decision ↔ artifact alignment

For each decision in `decisions.md` (D1–D16):
- Verify the `Encoded in` references actually contain the claimed content.
- Verify D12–D16 (the recent OQ resolutions) are reflected in the spec/architecture leaves they point at.
- Flag any decision whose rationale contradicts what the spec/architecture leaves actually say.

### 3. Open Questions status

- `feasibility.md §Open Questions` lists 7 OQs. Every OQ should either be resolved (pointing at a decision) or explicitly deferred.
- Any OQ that's still open without a deferral note is a blocker.

### 4. Refactor agenda coverage

- Every refactor in `refactors.md` (R01, R02, R03, R04, R05) has exit criteria that can be verified after implementation.
- R04 is documented as "folded into R01" — confirm R01's exit criteria actually cover R04's scope.
- R03 is documented as "follow-up only if post-R05 duplication remains" — confirm this is consistent with R05's exit criteria.
- No refactor entry references files or modules that no other artifact mentions (could indicate stale scope).

### 5. Terminology consistency

- No user-facing "repo root" term should appear anywhere in `spec/` (per D12). Internal "project root" is fine in `architecture/`.
- `ProjectPaths`, `ProjectConfigState`, `WorkspaceConfig`, `WorkspaceSnapshot`, `HarnessWorkspaceProjection`, `HarnessWorkspaceSupport` — used consistently across architecture leaves.
- `workspace.local.toml` (not `workspace.toml`) everywhere users see it.
- Applicability vocabulary (`active:add_dir`, `active:permission_allowlist`, `ignored:read_only_sandbox`, `unsupported:<reason>`) used identically across harness-integration, workspace-model, surfacing-layer, and any spec surfacing leaves.

### 6. Requirements ↔ design coverage

- Every goal in `requirements.md §Reframed Goals` (G1–G8) is addressed by at least one spec or architecture leaf.
- Every constraint (`requirements.md §Constraints`) is honored or explicitly rejected with justification.
- No scope creep: design doesn't claim to deliver things outside requirements.

### 7. Cross-artifact citation hygiene

- Probe evidence references (`probe-evidence/probes.md §X`) look plausible (the section exists).
- Inter-leaf links (e.g., `../architecture/paths-layer.md` from a spec file) point at real files.
- References to files outside the design package (e.g., `src/meridian/lib/state/paths.py:21`) are consistent across artifacts — if paths-layer says line 127 and refactors says line 93-128, that's internally consistent even if the actual source has drifted.

## Output

Structured report with sections for each check above. For each finding:

- **Severity**: HIGH (blocks impl handoff), MEDIUM (should fix but not blocking), LOW (cosmetic).
- **Location**: exact file and line/section.
- **Finding**: what's wrong.
- **Suggested fix**: one sentence.

End with a verdict: `ready-for-impl` / `minor-fixes-needed` / `blocking-issues`.

Keep it terse. No narrative; just findings.
