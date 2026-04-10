---
name: dev-artifacts
description: Shared artifact convention between orchestrators — what goes where, how artifacts flow between phases, and what each directory means. Use whenever work artifacts, design docs, plans, status tracking, or work structure are being created, referenced, or discussed.
---
# Dev Artifacts

All work artifacts live under `$MERIDIAN_WORK_DIR/`. This convention defines what each directory and file means, who writes it, and how artifacts flow between orchestrators. Every orchestrator shares this understanding — it's how design intent survives the handoff to implementation.

## The Directories

**`design/`** — The target system state. Model how the system *should* look after implementation, including existing parts the work interacts with. Design docs follow the structure and writing conventions in `/tech-docs` — one concept per doc, linked, hierarchically organized. Describes what the system should become, not how it evolved to get there.

**`plan/`** — The delta from current codebase to designed state. Each phase file is scoped, ordered, and verifiable against design/. Plan says *what changes*; design says *what it should look like*.

**`scenarios/`** — The verification contract. A flat, cumulative list of every edge case, failure mode, and boundary condition that must be tested before the work is considered complete. See the "Scenarios Folder" section below for structure and lifecycle. Lives alongside `design/` and `plan/` as a first-class artifact because verification is a first-class concern — it is not a subsection of design (which describes intent) or plan (which describes delta).

**`decisions.md`** — Execution-time pivots, review triage, overruled @reviewers — with reasoning. Written as implementation discovers reality that the design didn't anticipate. (See the decision-log skill for the craft of writing decisions.)

**`plan/status.md`** — Ground truth for phase progress. The @impl-orchestrator maintains this as phases start, complete, or hit blockers.

**`requirements.md`** (optional) — Captured user intent, constraints, and success criteria. Write this when the problem needs anchoring before design begins. @design-orchestrator optimizes toward it; @impl-orchestrator verifies against it.

## Who Writes What

| Artifact | Written by | Read by |
|---|---|---|
| requirements.md | @dev-orchestrator | @design-orchestrator, @impl-orchestrator |
| design/ | @design-orchestrator (via @architects) | @impl-orchestrator, @dev-orchestrator |
| plan/ | @design-orchestrator (via @planners) | @impl-orchestrator, @dev-orchestrator |
| scenarios/ | every stage appends (design, plan, impl) | testers (verify), @dev-orchestrator (convergence) |
| plan/status.md | @impl-orchestrator | @dev-orchestrator |
| decisions.md | @impl-orchestrator | @dev-orchestrator |
| $MERIDIAN_FS_DIR | @docs-orchestrator (via @code-documenters) | all agents |

Artifacts flow forward: @design-orchestrator writes the specification (design/ + plan/), @impl-orchestrator reads it and writes the execution record (plan/status.md + decisions.md), @dev-orchestrator reads everything to review with the user. `scenarios/` is the exception — it is append-only and shared, written by every stage as edge cases surface and read by every tester as their acceptance contract.

## Scenarios Folder

`scenarios/` is the verification contract — a shared, cumulative, append-only record of every edge case, failure mode, boundary condition, and audit-flagged gap that the work must prove is handled. It is the single source of truth for "what does it mean for this work to be correctly complete." Without it, edge cases documented in design docs evaporate before reaching testers, and testers default to happy-path coverage.

### Layout

```
scenarios/
  overview.md          -- index listing every scenario with ID, title, tester role, and status
  S001-<slug>.md       -- one file per scenario
  S002-<slug>.md
  ...
```

Small work items may keep everything in a single `scenarios.md` instead of a folder. Use the folder once there are more than ~10 scenarios or once multiple stages are contributing.

### Scenario file format

```markdown
# S007: Sandbox flag propagation through streaming path

- **Source:** design/overview.md §4.2 (edge case E3) + audit p1386 (gap #2)
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** pending

## Given
User launches spawn with `--sandbox read-only`.

## When
Streaming runner bootstraps the Codex harness.

## Then
Codex process receives the sandbox directive and enforces it for all subsequent tool calls.

## Verification
- Inspect debug.jsonl for the sandbox flag in the startup frame
- Attempt a write operation and confirm it is rejected
- Confirm no silent downgrade to default sandbox

## Result (filled by tester)
_pending_
```

### Who appends, when

- **@design-orchestrator** seeds the folder during design by extracting scenarios from every edge case the design enumerates, every rejected alternative with a failure mode, and every audit or investigation report in context. Design phase cannot be declared complete if the design enumerates edge cases that have no scenario.
- **@planner** appends during planning if decomposition surfaces new cross-phase interactions, sequencing hazards, or phase-boundary edge cases that the design did not anticipate. Each scenario gets tagged with the phase that owns it.
- **@impl-orchestrator** appends during implementation whenever a @coder or tester discovers an edge case the design and plan missed. New scenarios block phase completion until tested.
- **testers** never append scenarios — they execute them. Their report fills the "Result" section with verified / failed / skipped and evidence.
- **@dev-orchestrator** uses `scenarios/overview.md` as the convergence check. Work is not done while any scenario is pending or failed.

### Status values

- **pending** — scenario exists, no tester has executed it yet
- **verified** — tester executed it and confirmed expected behavior with evidence
- **failed** — tester executed it and observed wrong behavior (phase cannot close)
- **skipped** — tester could not execute it (explain why; orchestrator decides whether to accept or reassign)

### Traceability

Every scenario has an ID (S001, S002, ...). Design docs reference scenarios by ID when discussing edge cases. Plan blueprints list scenario IDs under "Scenarios to Verify" for each phase. Tester reports cite scenario IDs in their status entries. Decisions in decisions.md reference scenario IDs when explaining why a scenario was reclassified or dropped. The ID chain makes it impossible for a scenario to vanish between stages.

## Rejected Iterations

Replace rejected designs atomically. Approved artifacts live at `design/` and `plan/` — not versioned alongside rejected drafts. Git history preserves prior iterations if anyone needs them. The current state of these directories is always the approved state.

## Documentation Layers

Three distinct documentation surfaces exist, each serving a different audience:

**`$MERIDIAN_FS_DIR` (fs/)** — Agent-facing codebase mirror. Domain-structured compression of the architecture: what exists, how it works, why it's that way. Organized by conceptual domain (named for architectural concepts, not source paths). Agents read this to orient on unfamiliar subsystems without scanning every source file. The @code-documenter maintains it; the @dev-orchestrator triggers the @docs-orchestrator to coordinate updates after implementation completes.

**`docs/`** — User-facing documentation. CLI reference, getting started guides, configuration docs. Written for humans who use the project, not agents navigating the codebase.

**`$MERIDIAN_WORK_DIR`** — Work-scoped artifacts including research, design, and plans. Research stays here — it's ephemeral context for the current work item. Lasting findings from research get synthesized into the relevant fs/ domain doc when the work completes, not copied verbatim.

fs/ has no `research/` subdirectory. If you're writing research, it belongs in the work item. If the research produced durable knowledge about a subsystem, that knowledge belongs in the fs/ domain doc for that subsystem.

## This Convention Is Swappable

A project or workflow can replace this skill with its own artifact conventions — different directory names, different flow, different files — without touching orchestrator or agent bodies. The convention is a skill, not hardcoded structure.
