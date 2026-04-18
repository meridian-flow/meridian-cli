# Planner — Workspace Config Remaining Phases

## Task

Produce the refreshed implementation plan for the remaining
`workspace-config-design` scope in this repo. The approved design package is the
authority for `WS-1`, `CTX-1`, `SURF-1`, and `BOOT-1`, but the live repo is not
starting from a clean post-R02 handoff.

You must plan from the **current code and artifact state**, not from the stale
claim that "R01/R02 are complete."

## Inputs you must read

1. `requirements.md`
2. `decisions.md`
3. `design/spec/overview.md`
4. `design/spec/workspace-file.md`
5. `design/spec/context-root-injection.md`
6. `design/spec/surfacing.md`
7. `design/spec/bootstrap.md`
8. `design/architecture/overview.md`
9. `design/architecture/workspace-model.md`
10. `design/architecture/harness-integration.md`
11. `design/architecture/surfacing-layer.md`
12. `design/refactors.md`
13. `plan/pre-planning-notes.md` — this file is freshly updated and corrects the
    execution handoff
14. Review artifacts:
    - `.meridian/spawns/p2068/report.md`
    - `.meridian/spawns/p2069/report.md`

## Planning directives

1. Treat residual R02 convergence as explicit planning input.
   The next plan must account for:
   - removing `config init` -> `_ensure_mars_init()` side effects
   - sharing full user-config source resolution semantics between loader and
     config introspection
   - introducing the shared config/workspace surfacing builder used by both
     `config show` and `doctor`

2. Do not reopen design.
   The design package is approved. If you find a true design contradiction,
   terminate `structural-blocking`; otherwise plan implementation from the
   current state.

3. Keep phase boundaries safe.
   Workspace surfacing and launch projection are structurally coupled to the
   shared workspace snapshot / config surface. A plan that parallelizes these
   before the shared state exists is unsafe.

4. Review staffing must use GPT reviewer lanes plus `@refactor-reviewer`.
   Do not route final review to Sonnet.

## Deliverables

Write these artifacts under `plan/`:

### `plan/overview.md`

- refreshed parallelism posture with cause
- round definitions and why
- refactor handling / carryover handling
- mermaid fanout matching the text
- staffing section concrete enough for execution impl-orch

### `plan/phase-N-<slug>.md`

One file per implementation phase. Each must include:
- scope / boundaries
- touched files/modules
- claimed EARS statement IDs
- dependencies
- tester lane assignment
- exit criteria

### `plan/leaf-ownership.md`

One row per remaining spec EARS statement:
- `WS-1.u1`
- `WS-1.u2`
- `WS-1.u3`
- `WS-1.u4`
- `WS-1.s1`
- `WS-1.e1`
- `WS-1.e2`
- `WS-1.c1`
- `CTX-1.u1`
- `CTX-1.u2`
- `CTX-1.e1`
- `CTX-1.w1`
- `CTX-1.w2`
- `SURF-1.u1`
- `SURF-1.e1`
- `SURF-1.e2`
- `SURF-1.e3`
- `SURF-1.e4`
- `BOOT-1.u1`
- `BOOT-1.e1`
- `BOOT-1.e2`

Add one note column when a leaf also carries residual R02 cleanup or depends on
the shared surfacing builder.

### `plan/status.md`

Seed every new phase as `pending`. Make the run-level status reflect that the
old remaining-phase plan is superseded by this regenerated plan.

## Hard constraints

- Do not assume the old `plan/overview.md`, `plan/leaf-ownership.md`, or
  `plan/status.md` are still valid. Rewrite them from current reality.
- Keep coder phases sequential unless you can justify safe non-overlap from the
  refreshed explore evidence.
- Use the design package's EARS IDs as the verification contract.
- Include explicit review/fix convergence after implementation closes.

## Terminal states

- `plan-ready` — all plan artifacts written and internally consistent
- `probe-request` — you need runtime evidence not already captured
- `structural-blocking` — the design cannot be safely decomposed from the live
  current state

## Format for terminal report

```markdown
## Terminal state
<plan-ready | probe-request | structural-blocking>

## Plan files written
- plan/overview.md
- plan/phase-1-<slug>.md
- ...

## Sequencing cause
<short paragraph>

## Judgment calls
<phase-boundary refinements from the explore hypothesis>

## Handoff notes for execution impl-orch
<specific execution notes>
```
