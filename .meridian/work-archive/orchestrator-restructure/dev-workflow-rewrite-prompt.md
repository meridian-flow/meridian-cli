# Update meridian-dev-workflow to the v3 shape

Update `meridian-dev-workflow/agents/*.md` and `meridian-dev-workflow/skills/*/SKILL.md` so the workflow matches the v3 orchestrator topology captured in the orchestrator-restructure design package.

The design package is the target spec. Read it end-to-end before editing:

- `$MERIDIAN_WORK_DIR/design/spec/` — hierarchical spec tree. Every leaf is an EARS statement naming a behavior the target topology must exhibit. The ID letter (`u/s/e/w/c`) encodes the EARS pattern. Root invariants in `design/spec/root-invariants.md` (S00.*) apply across every subsystem. Subsystems: requirements-and-scoping (S01), design-production (S02), plan-approval (S03), planning-cycle (S04), execution-cycle (S05), redesign-cycle (S06).
- `$MERIDIAN_WORK_DIR/design/architecture/` — hierarchical technical tree. Every leaf describes how the topology realizes the spec leaves, with `Realizes` links back to specific spec IDs. Subsystems: design-package (A01), artifact-contracts (A02), verification (A03), orchestrator-topology (A04), principles (A05).
- `$MERIDIAN_WORK_DIR/design/refactors.md` — R01–R07 rearrangement entries naming what moves from v2 to v3, including the meridian-dev-workflow edits themselves.
- `$MERIDIAN_WORK_DIR/design/feasibility.md` — probe records, fix-or-preserve verdicts, and research grounding (Fowler, Kiro, EARS, Thoughtworks).
- `$MERIDIAN_WORK_DIR/decisions.md` — D16–D26 plus the revised D24 carry the rationale chain for every v3 change.

## Direction summary

v3 adopts spec-anchored SDD in the Kiro mold. Each principle below names a rule and the reason the rule exists, because principles without reasoning are brittle — a model following the rule literally will miss the point in novel situations, while a model understanding *why* generalizes to cases the rule-writer didn't anticipate.

- **Hierarchical two-tree design output**: `design/spec/` (EARS leaves, stable IDs) + `design/architecture/` (technical realization with `Realizes` cross-links), plus `design/refactors.md` and `design/feasibility.md` as first-class sibling artifacts. *Why two trees*: separating business spec (behavior contracts) from technical design (realization) gives reviewers a clean focus surface — spec reviewers check testability and coverage, architecture reviewers check structure, alignment reviewers check the cross-links — and lets downstream agents load only the subtree they need (context offloading). Validated by Thoughtworks' business/technical separation pattern and Addy Osmani's hierarchical-TOC-for-agent-specs writeup.
- **EARS notation is the acceptance contract** for every spec leaf, with letter-encoded pattern IDs and a per-pattern parsing rule testers apply mechanically. *Why EARS*: the templates force triggers, preconditions, and responses to be explicit, so hand-wavy requirements show up as clause gaps during writing. Each leaf maps directly onto a test triple (setup / fixture / assertion), which makes "does the implementation satisfy this?" a mechanical question the tester can answer without interpretation.
- **Problem-size scaling**: dev-orch selects a tier (trivial / small / medium / large) that controls how much of the SDD ceremony applies. Trivial work skips design entirely; small work uses degenerate single-file trees; medium/large use the full hierarchy. *Why scaling*: uniform heavyweight process on small changes stalls feedback loops and invites agents to route around the ceremony or produce shallow artifacts to satisfy the shape. Thoughtworks' critique of over-formalization and Fowler's "no single workflow accommodates varying problem sizes" are the anchors.
- **Planning and execution impl-orch are separate spawns** per the terminated-spawn contract. Planning impl-orch runs pre-planning + spawns `@planner` + runs the structural gate + terminates. Execution impl-orch is a fresh spawn that runs the per-phase loop. *Why separate*: meridian is crash-only — state lives on disk, not in memory. A suspended impl-orch holding plan state in conversation context cannot survive a crash, a compaction, or a restart. D15 rejects suspended-spawn patterns explicitly.
- **`@planner` framing** is parallelism-first. Structural refactors from `refactors.md` land first to unlock parallel feature phases. Leaf ownership lives at EARS-statement granularity in `plan/leaf-ownership.md` (replacing `plan/scenario-ownership.md`). Planner sequences refactors design identified; it does not invent new ones. Cycle caps: K_fail=3 failed plans, K_probe=2 probe-requests. *Why parallelism-first*: parallelism bounds the critical path. Structural refactors that touch many files create merge conflicts if they run late, so landing them first unlocks everything downstream. *Why no-refactor-invention*: if planner is allowed to introduce new refactors, the design/plan separation collapses and the structural review that happened at design time stops being authoritative — runtime discoveries that need new refactors must route back through a design revision (the structural-blocking escape hatch), not get inlined into the plan.
- **Escape hatch** fires on spec-leaf falsification: runtime evidence contradicts a spec leaf → emit `redesign-brief.md` citing the falsified leaves → dev-orch routes back to design-orch autonomously. K=2 redesign cycles before user escalation. *Why falsification-only*: the escape hatch is cheap to invoke, so it needs a counterweight to prevent abuse. "Runtime evidence contradicts a specific spec leaf" is a falsifiable claim the design-orch can evaluate; "this feels wrong" is not. The falsification requirement filters bail-outs that should have been fix loops.
- **Preserved-phase re-verification** (D26): when a spec leaf claimed by a preserved phase is revised in place, the phase gets tester-only re-verification with three outcomes — stay preserved, become partially-invalidated, or route back through a redesign brief. *Why not always-respawn-coder*: not every revised spec leaf invalidates the phase code that claimed it. When only the leaf's language tightens (not its behavior), the existing phase code still satisfies it — a tester re-run is cheaper than a full coder respawn. The three-outcome branch keeps the shortcut honest by forcing a real re-verification decision instead of silent preservation.
- **`dev-principles` is shared operating guidance** loaded by every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns. It is never a binary pass/fail gate. Final implementation review applies the principles through every reviewer's rubric, not a separate lane. *Why not a gate*: principles are behavioral guidance, not checklists — they apply continuously as an agent works, not at one orchestration point. Gating them at design-orch convergence would make them a false binary, and the post-convergence agents (coders, reviewers, testers) would stop applying them if they only had to pass one check. Loading the skill as shared operating context is how the principles stay active across every surface where they matter.
- **Scenarios convention retires**: no `scenarios/` folder is produced, consumed, or referenced anywhere. Spec leaves subsume the verification contract at higher fidelity via EARS. *Why retire*: v2's `scenarios/` convention evaporated in practice. Authors forgot to maintain the ledger, so the verification contract drifted and implementation lost its verifiable target. Spec leaves put verification in the place reviewers already look, in a format that forces completeness. Consolidating into one artifact eliminates the drift surface.

## What to edit

Use judgment on which files in `meridian-dev-workflow/` need touching. The design package's refactors.md catalogs the moves at a high level, and the architecture tree's `orchestrator-topology/` subsystem names which agents own which behaviors. Cross-reference those to figure out the file set.

Judgment calls the rewrite resolves on its own:

- Whether `feasibility-questions` earns a new shared skill or inlines into the three orchestrator bodies that use it (design-orch, impl-orch planning role, planner). The multi-consumer test (skill-creator skill) applies.
- Whether EARS parsing reference lives once in a new shared skill or duplicates into smoke-test, unit-test, and verification skills. Same multi-consumer test.
- How faithful the agent body prose should be to specific EARS leaves. Quote them when a precise contract matters; paraphrase when the prose reads better.
- Where v3 diverges from a spec leaf because making the prompt strictly faithful would make the prompt worse. Record the divergence in the terminal report.
- Minor wording, ordering, and section-breakdown choices that don't affect downstream consumer expectations.

Flag in the terminal report:

- Files touched with a one-line change summary each
- Judgment calls made on the skill-boundary questions above
- Any place where the design package and the existing meridian-dev-workflow content disagree on non-cosmetic points (flag for user review)
- Any new files created (e.g., a new skill) with reasoning
- Files you expected to touch but left alone, with reasoning
- Follow-up work for meridian-base or other submodules if the v3 shape requires changes outside meridian-dev-workflow

## Quality bar

After the edits:

- Spawning `@dev-orchestrator`, `@design-orchestrator`, `@impl-orchestrator`, `@planner`, `@coder`, `@reviewer`, and the tester lanes should produce behavior consistent with the D16–D26 decision chain.
- The `dev-artifacts` skill body describes the two-tree convention, not the retired `scenarios/` convention.
- EARS is the acceptance notation wherever spec verification is discussed.
- `dev-principles` is framed as shared operating guidance loaded by relevant agents, not as a gate.
- The agent prompts read cleanly at the right altitude per the `agent-creator` skill (no role identity claims, reasoning attached to constraints, no prescriptive sequences, positive framing).

## Out of scope

- Commits to git (leave the working tree modified; dev-orchestrator handles commit scope).
- Running `meridian mars sync` to regenerate `.agents/` (dev-orchestrator runs this after inspecting the edits).
- Changes to `meridian-base/` or other submodules unless strictly required for the v3 shape to function.
- Editing the orchestrator-restructure design package itself — it is input, not output.

## Return

Terminal report with the flag list above, plus a high-level "here's how v3 reads end-to-end now" summary so the reviewer can verify the rewrite landed coherently.
