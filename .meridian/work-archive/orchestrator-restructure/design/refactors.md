# Orchestrator Restructure: Refactor Agenda

These entries capture the v2 -> v3 rearrangement work implied by the SDD reshape. Each entry is a sequencing-relevant refactor for the workflow package or the work-item design package, not feature work and not foundational prep.

## R01: Flatten the flat design package into `design/spec/` + `design/architecture/`

**Target:** `.meridian/work/orchestrator-restructure/design/overview.md`, `design-orchestrator.md`, `impl-orchestrator.md`, `dev-orchestrator.md`, `planner.md`, `terrain-contract.md`, `feasibility-questions.md`, `redesign-brief.md`, and `preservation-hint.md` -> `design/spec/overview.md` + spec subtrees, `design/architecture/overview.md` + architecture subtrees, with the root overviews becoming TOC indexes rather than long mixed-altitude narratives.

**Affected callers:** `meridian-dev-workflow/agents/dev-orchestrator.md`, `meridian-dev-workflow/agents/design-orchestrator.md`, `meridian-dev-workflow/agents/impl-orchestrator.md`, `meridian-dev-workflow/agents/planner.md`, every reviewer brief that currently attaches flat design docs, and any future `meridian spawn -f $MERIDIAN_WORK_DIR/design/*.md` handoff that assumes flat sibling files.

**Coupling removed:** The current work-item design package is a flat sibling set where topology, verification contract, artifact contract, redesign protocol, and agent-body deltas all live at the same directory altitude. Concrete witness: `ls .meridian/work/orchestrator-restructure/design` returns nine peer markdown files and no `spec/` or `architecture/` trees, while `.meridian/work/orchestrator-restructure/design/overview.md` must serve simultaneously as orientation doc, SDD rationale, artifact map, and cross-doc switchboard. That shape couples every consumer to file-name trivia and section-search instead of tree navigation.

**Must land before:** R02, R03, R04, R05, R06, and R07; every downstream v3 artifact in this agenda assumes real `design/spec/` and `design/architecture/` anchor paths rather than the current flat file set.

**Architecture anchor:** `design/architecture/design-package/two-tree-shape.md` section `Target layout — two-tree package with root TOCs`.

**Preserves behavior:** no - downstream readers move from flat-file entry points to tree-root overviews, and cross-links move from section prose to subtree identity.

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D18; `.meridian/work/orchestrator-restructure/design/overview.md` sections `Design output: two hierarchical trees plus two sibling artifacts` and `Why two trees`; current on-disk witness from `ls .meridian/work/orchestrator-restructure/design` showing only flat docs.

## R02: Materialize the Terrain split as real sibling artifacts instead of described outputs

**Target:** `.meridian/work/orchestrator-restructure/design/terrain-contract.md`, `overview.md`, and the missing root artifacts `design/refactors.md` and `design/feasibility.md`, with terrain-analysis content moved out of narrative prose into those files and the architecture tree.

**Affected callers:** `meridian-dev-workflow/agents/planner.md`, `meridian-dev-workflow/agents/impl-orchestrator.md`, `meridian-dev-workflow/agents/design-orchestrator.md`, any reviewer lane reading terrain-analysis outputs, and future spawns that should be able to attach `design/refactors.md` or `design/feasibility.md` directly.

**Coupling removed:** Terrain analysis is currently specified as something multiple consumers should read directly, but the actual work-item package still ships only the contract prose that describes those outputs. Concrete witness: `.meridian/work/orchestrator-restructure/design/terrain-contract.md` says terrain analysis now lands in `design/refactors.md` and `design/feasibility.md`, yet `ls .meridian/work/orchestrator-restructure/design` shows neither file exists. The planner and impl-orch are therefore coupled to explanatory prose about artifacts instead of to the artifacts themselves.

**Must land before:** R05 and R06; the planning topology rewrite and the verification-contract rewrite both need concrete `refactors.md` and `feasibility.md` files as `-f` inputs rather than descriptive stand-ins.

**Architecture anchor:** `design/architecture/artifact-contracts/terrain-analysis.md` section `Three-output terrain workflow`.

**Preserves behavior:** no - planner and impl-orch inputs change from "read the doc that describes the artifact" to "read the artifact itself".

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D19 and D20; `.meridian/work/orchestrator-restructure/design/terrain-contract.md` sections `The outputs - three locations, two first-class artifacts`, ``design/refactors.md` - required shape`, and ``design/feasibility.md` - required shape`; current missing-file witness from `ls .meridian/work/orchestrator-restructure/design`.

## R03: Publish the v3 artifact convention through `dev-artifacts` instead of the retired `scenarios/` contract

**Target:** `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` -> replace the current `design/` + `plan/` + `scenarios/` convention with the v3 two-tree design package, `design/refactors.md`, `design/feasibility.md`, `plan/leaf-ownership.md`, and preserved-leaf status language.

**Affected callers:** Every workflow agent that loads `/dev-artifacts`, especially `meridian-dev-workflow/agents/dev-orchestrator.md`, `design-orchestrator.md`, `impl-orchestrator.md`, `docs-orchestrator.md`, and any tester or planner skill that points at `/dev-artifacts` for the canonical artifact layout.

**Coupling removed:** The shared convention skill still hard-codes `scenarios/` as the verification contract and makes every orchestrator depend on that older layout. Concrete witness: `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` defines `scenarios/` as a first-class directory, gives it lifecycle ownership across design/planning/impl, and says `@dev-orchestrator` uses `scenarios/overview.md` as the convergence check. That central skill now disagrees with D18/D19/D20/D22, so the package is coupled to two incompatible artifact conventions at once.

**Must land before:** R04 and R05; prompt bodies and tester/planner flow rewrites should point at one shared convention rather than each carrying bespoke migration prose.

**Architecture anchor:** `design/architecture/artifact-contracts/shared-work-artifacts.md` section `Canonical work-item layout after scenario retirement`.

**Preserves behavior:** no - the authoritative artifact map changes for every agent that loads `/dev-artifacts`.

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D22 and the `Coordinated skill edit follow-up`; `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` sections `The Directories`, `Who Writes What`, and `Scenarios Folder`.

## R04: Retire the `scenarios/` convention from orchestrator and planner prompt bodies

**Target:** `meridian-dev-workflow/agents/design-orchestrator.md`, `impl-orchestrator.md`, and `planner.md`, plus any v3 body text that still frames acceptance through scenario files rather than spec leaves and leaf ownership.

**Affected callers:** Design-phase spawns that currently seed scenarios, planning spawns that currently promise scenario extraction, implementation runs that gate phase closure on scenario files, and any tester handoff copied from those bodies.

**Coupling removed:** The checked-in prompt bodies still make `scenarios/` the canonical acceptance surface even though the v3 design package made spec leaves authoritative. Concrete witness: `meridian-dev-workflow/agents/design-orchestrator.md` tells the agent to seed `scenarios/`; `meridian-dev-workflow/agents/planner.md` requires every edge case to become a tester acceptance scenario; `meridian-dev-workflow/agents/impl-orchestrator.md` starts every phase with `scenario review -> coder -> testers`. The same verification contract is therefore duplicated once in the v2 folder convention and again in the v3 spec-tree design, which guarantees drift.

**Must land before:** R05; leaf-ownership and EARS-based tester flows cannot be authoritative while the orchestrator bodies still instruct agents to create and gate on scenario files.

**Architecture anchor:** `design/architecture/verification/orchestrator-verification-contract.md` section `Spec leaves replace scenario files`.

**Preserves behavior:** no - design/planning/implementation prompts stop creating and reading scenario files and instead route all acceptance through spec leaves and leaf ownership.

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D22; `meridian-dev-workflow/agents/design-orchestrator.md` sections `You operate in caveman full mode` and `Scenarios folder`; `meridian-dev-workflow/agents/planner.md` paragraphs on `tester acceptance scenario` and `Scenarios to Verify`; `meridian-dev-workflow/agents/impl-orchestrator.md` phase loop and `Phase Convergence` sections.

## R05: Replace scenario ownership with spec-leaf ownership and EARS-driven tester handoffs

**Target:** `meridian-dev-workflow/skills/planning/SKILL.md`, `skills/smoke-test/SKILL.md`, `skills/unit-test/SKILL.md`, the planner blueprint template they imply, and the ownership artifact name `plan/scenario-ownership.md` -> `plan/leaf-ownership.md`.

**Affected callers:** `meridian-dev-workflow/agents/planner.md`, `impl-orchestrator.md`, `smoke-tester`, `unit-tester`, any phase blueprint that currently emits a `Scenarios` section, and every tester report format that currently updates scenario files as the system of record.

**Coupling removed:** Planning and testing are still coupled to a sidecar scenario-file ledger instead of to the EARS leaf IDs the v3 spec tree is supposed to own. Concrete witness: `meridian-dev-workflow/skills/planning/SKILL.md` says verification contracts live in `scenarios/` and every blueprint must include `Scenarios to Verify`; `meridian-dev-workflow/skills/smoke-test/SKILL.md` and `skills/unit-test/SKILL.md` both require testers to open `$MERIDIAN_WORK_DIR/scenarios/` and update per-scenario result sections. The same acceptance state is thus split across spec prose, blueprint scenario lists, and scenario files.

**Must land before:** `design/spec/` subtrees under the future verification tree, `plan/leaf-ownership.md`, and any execution-loop implementation built on the planner/impl-orch v3 topology; R06 depends on this contract existing.

**Architecture anchor:** `design/architecture/verification/leaf-ownership-and-tester-flow.md` section `EARS statement ownership and tester execution`.

**Preserves behavior:** no - the ownership unit changes from scenario IDs to EARS statement IDs, and tester evidence moves from scenario files to spec-leaf-centered plan artifacts and reports.

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D17, D21, and D22; `.meridian/work/orchestrator-restructure/design/planner.md` sections `Outputs the planner produces` and `What is changed from the v2 planner`; `meridian-dev-workflow/skills/planning/SKILL.md` section `Scenarios to Verify`; `meridian-dev-workflow/skills/smoke-test/SKILL.md` section `The Scenarios Contract`; `meridian-dev-workflow/skills/unit-test/SKILL.md` section `The Scenarios Contract`.

## R06: Rewire planning so impl-orch owns pre-planning and the planner spawn

**Target:** `meridian-dev-workflow/agents/dev-orchestrator.md`, `impl-orchestrator.md`, and `planner.md` -> move from the current dev-orch -> planner -> impl-orch handoff to the v3 chain where planning impl-orch writes `plan/pre-planning-notes.md`, spawns planner, enforces the structural gate, terminates for plan review, and execution resumes in a fresh impl-orch spawn.

**Affected callers:** `@dev-orchestrator`, `@impl-orchestrator`, `@planner`, any staffing or status flow that assumes the plan already exists before impl-orch starts, and any review checkpoint that assumes a suspended impl-orch process survives the plan-review pause.

**Coupling removed:** The current source topology couples plan creation to dev-orch and leaves impl-orch blind to runtime context until after the plan is fixed. Concrete witness: `meridian-dev-workflow/agents/dev-orchestrator.md` has a dedicated `Planning Phase` that spawns `@planner` directly; `meridian-dev-workflow/agents/impl-orchestrator.md` begins immediately with the per-phase execution loop and has no pre-planning artifact or planner spawn; `meridian-dev-workflow/agents/planner.md` describes itself as a direct bridge from design to execution rather than as an impl-orch sub-step. That caller arrangement is the stale-plan coupling D1, D3, D12, and D15 were written to break.

**Must land before:** any architecture subtree under `design/architecture/orchestrator-topology/` that assumes terminated-spawn plan review, and before execution-loop work that consumes `plan/pre-planning-notes.md` or the planner `Parallelism Posture` gate.

**Architecture anchor:** `design/architecture/orchestrator-topology/planning-and-review-loop.md` section `Impl-orch-owned planning boundary`.

**Preserves behavior:** no - planner caller, plan-review boundary, and impl-orch lifecycle all change.

**Evidence:** `.meridian/work/orchestrator-restructure/decisions.md` D1, D3, D12, and D15; `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md`, `impl-orchestrator.md`, and `planner.md` target-shape docs; current source witnesses in `meridian-dev-workflow/agents/dev-orchestrator.md` sections `Planning Phase` and `Implementation Handoff`, `meridian-dev-workflow/agents/impl-orchestrator.md` section `The loop for every phase`, and `meridian-dev-workflow/agents/planner.md` opening contract.

## R07: Universalize `dev-principles` loading and remove gate-only framing

**Target:** `meridian-dev-workflow/agents/planner.md`, `coder.md`, `reviewer.md`, and the prompt-body framing in `design-orchestrator.md` and `impl-orchestrator.md` so `dev-principles` becomes shared judgment context across structural/correctness-critical agents instead of a special gate narrative attached to only part of the topology.

**Affected callers:** `@planner`, `@coder`, `@reviewer`, `@design-orchestrator`, `@impl-orchestrator`, and any review or coding loop whose structural or correctness judgment is currently shaped by ad-hoc prose rather than by the common skill.

**Coupling removed:** The current package splits structural principles between some agents' skill arrays and other agents' body text, so the same engineering heuristics arrive through different channels or not at all. Concrete witness: `meridian-dev-workflow/agents/planner.md`, `coder.md`, and `reviewer.md` do not load `dev-principles`, while `design-orchestrator.md` and `impl-orchestrator.md` v3 design docs still describe special gate/lens handling for the same principles. That leaves principle application coupled to which agent happened to mention the rule inline rather than to one shared skill load.

**Must land before:** any v3 reviewer or coder loops that rely on structural-principle context, and before finalizing the orchestrator prompt rewrites in R04 and R06 so those bodies do not reintroduce bespoke gate language.

**Architecture anchor:** `design/architecture/principles/dev-principles-application.md` section `Shared context, no per-agent gate choreography`.

**Preserves behavior:** no - additional agents gain principle context, and design/impl bodies stop treating the principles as a special-case gate narrative.

**Evidence:** `.meridian/work/orchestrator-restructure/design/overview.md` section `Why dev-principles as a convergence gate`; `.meridian/work/orchestrator-restructure/design/design-orchestrator.md` section ``dev-principles` as convergence gate`; current skill-load witnesses from `meridian-dev-workflow/agents/planner.md`, `coder.md`, and `reviewer.md`; user-scoped correction in this work item overriding the earlier D24 gate-only reading.
