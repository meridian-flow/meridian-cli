# Post-R06 Review — Design Alignment

## Context

R06 (hexagonal launch core) was shipped by spawn `p1900` across 6 commits (`3f8ad4c`..`efad4c0`). No subagent review ran during the implementation. You're the design-alignment reviewer.

Your lane: **does the shipped code faithfully implement the approved design?** Not "does it work" (correctness reviewer), not "is it well-structured" (structural reviewer). You compare shipped-reality to designed-intent.

## Read first

- `.meridian/work/workspace-config-design/design/refactors.md` R06 — the designed scope, exit criteria, suggested phasing.
- `.meridian/work/workspace-config-design/decisions.md` D17 — architectural rationale.
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` — Launch composition + Session-ID observation sections.
- `.meridian/spawns/p1900/report.md` — claimed deliverables including deviations I01-I07.
- `git diff bb72a85..efad4c0 -- src/ scripts/ .github/` — the full R06 diff.
- `.meridian/work/workspace-config-design/plan/` (if present) — planner artifacts including impl-decisions.md.

## Review lanes

### 1. Exit criteria coverage

The design's R06 section lists specific exit criteria (definition checks, sole-caller checks, pyright bans, CI gate). For each:

- Run the `rg` command the design specifies. Does it return the expected count?
- If the p1900 report's verification table claims ✅ for an item, spot-check 3 of them manually to confirm.
- Any exit criterion the design listed that's not verified or not satisfied?

### 2. Architectural vocabulary

The design uses specific vocabulary: "3 driving adapters", "1 driving port (factory)", "1 driven port (adapter protocol)", "2 executors", "pipeline with centralization invariant", "bypass as `BypassLaunchContext` return", "`observe_session_id()` adapter seam". Does the code:

- Reflect this vocabulary in naming (module names, type names, method names)?
- Match the design's architectural boundaries (what lives in `launch/`, `harness/adapter.py`, `harness/<impl>`, `ops/spawn/`, `app/`)?
- Not introduce alternate concepts the design didn't sanction?

### 3. Documented deviations (I01-I07 from p1900)

The impl-orchestrator documented 7 deviations. Verify each:

- **I01 + I07**: phase combining (1+2 and 4+5+6) — was this just scheduling or did it introduce ordering that violates the design's stage boundaries?
- **I04**: `resolve_policies` called from driving adapters — is this a legitimate pre-composition step the design allows, or did composition leak out?
- **I05**: `TieredPermissionResolver` in `server.py` for input validation — is this truly validation, or composition dressed as validation?
- **I06**: duplicate `LaunchResult` name — does the design sanction two `LaunchResult` concepts, or should one be renamed?

For each deviation, answer: **does the design explicitly allow it, or did it creep in?** If the design doesn't cover it, is the deviation acceptable (minor) or a problem (blocker)?

### 4. Honest-claim compliance

The design went through multiple honesty passes to drop overclaims. Verify the shipped state is consistent:

- Did any overclaim slip back into docstrings, comments, or CI-message text? Grep for "impossible to drift," "pure, no I/O," "mechanically guaranteed."
- Does the code acknowledge the PTY/Popen split as capture-mode (per design) or does it still look like 2 separate executors?
- Is `materialize_fork()` honestly labeled as state-mutating in its docstring?
- Is `observe_session_id()` documented as a getter over adapter-held state (per the adjusted design), or as a parser of `launch_outcome`?

### 5. Scope boundary

R06 was supposed to deliver the adapter seam for `observe_session_id()`, not the filesystem-polling mechanism swap. Verify:

- R06 did NOT implement filesystem polling (that's issue #34).
- R06 DID implement the seam with existing scrape/parse mechanisms relocated.
- No scope creep in either direction.

R06 was supposed to be a prereq, not R05. Verify:

- R06 did NOT implement `project_workspace()` (R05's deliverable).
- R06 DID establish the pipeline insertion point R05 needs.

### 6. Test coverage alignment

The design's test blast radius listed specific test files to verify. Compare:

- Did those tests actually get updated/run?
- If any were deleted (5 tests per `bf4cf6c`), were their scenarios preserved elsewhere, or is coverage genuinely reduced?
- Is smoke-test guidance in `tests/smoke/` updated to reflect the new CLI flow (if relevant)?

### 7. Dev artifacts

- `.meridian/work/workspace-config-design/plan/status.md` (if present) — up to date?
- `.meridian/work/workspace-config-design/plan/leaf-ownership.md` — updated?
- `.meridian/work/workspace-config-design/decisions.md` — any in-session decisions recorded that should be preserved?
- CHANGELOG entry added? Per CLAUDE.md: "Write entries at commit time in an [Unreleased] section." Is there one for R06?

## Deliverable

Under 700 words:

- Findings as **Blocker / Major / Minor** with file:line references.
- For each deviation (I01-I07), state whether the design allows it, with evidence.
- Name any design-to-code drift concretely (what design said X, code shipped Y).
- End with a **Verdict**: `ships-as-designed` / `ships-with-documented-drift` / `ships-contradicting-design`.
- Do NOT modify code. Report only.
