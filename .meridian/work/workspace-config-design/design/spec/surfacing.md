# SURF-1: Workspace and Config State Surfacing

## Context

The previous design failed by hiding important behavior changes behind silent no-ops or chatty warnings. Surfacing must answer two questions cleanly: "what state am I in?" and "will my roots actually apply to this harness?"

**Realized by:** `../architecture/workspace-model.md`, `../architecture/surfacing-layer.md`, `../architecture/harness-integration.md`.

## EARS Requirements

### SURF-1.u1 — `config show` exposes a minimal structured workspace summary

`config show --json shall expose workspace as {status, path?, roots: {count, enabled, missing}}, and text output shall expose the same facts as flat grep-friendly key-value lines. Status shall be one of: none, present, or invalid. Path shall be present when Meridian found workspace.local.toml and omitted when status = none.`

### SURF-1.e1 — Inspection commands continue across invalid workspace files

`When workspace.local.toml is invalid, inspection commands such as config show and doctor shall continue running and shall surface workspace.status = invalid together with the validation findings.`

### SURF-1.e2 — Missing roots and unknown keys are surfaced per invocation

`When workspace.local.toml contains missing roots or unknown keys, doctor and config show shall surface those findings on every invocation that inspects workspace state, without requiring persistent suppression state.`

### SURF-1.e3 — Spawn-time missing-root noise stays out of the default lane

`When a launch encounters configured workspace roots that are missing on disk, Meridian shall keep those findings out of the default spawn warning lane and shall expose them through config show, doctor, and debug-level launch diagnostics instead.`

### SURF-1.e4 — Applicability downgrades are explicit

`When the selected harness or sandbox will ignore or reject workspace-root injection for the current launch, Meridian shall emit an explicit applicability diagnostic for that invocation rather than silently behaving as though workspace roots were active.`

## Non-Requirement Edge Cases

- **No warning flood for healthy single-repo users.** `workspace.status = none` is a quiet state.
- **No hidden JSON shape creep.** Additional detail belongs in warnings/diagnostics, not in a bloated replacement for the minimal workspace summary.
- **No per-harness support matrix in v1 surfacing.** Harness support is determined at launch time, not pre-computed in `config show`.
