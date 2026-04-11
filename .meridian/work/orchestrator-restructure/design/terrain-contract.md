# Terrain Analysis: Artifact Contract

This doc defines the **terrain analysis workflow** as a shared artifact contract — what design-orch produces when it studies the current-vs-target structure of the codebase, where those outputs land, and what consumers expect from them. Producer: design-orchestrator. Consumers: impl-orchestrator (pre-planning), @planner (decomposition), and reviewers (structural review pass).

The v2 version of this contract described a single "Terrain section" at the end of `design/overview.md`. **That shape is dropped in v3.** Terrain analysis now produces two first-class artifacts at the root of the design package — `design/refactors.md` and `design/feasibility.md` — alongside the target-state description that lives in `design/architecture/overview.md`. Each artifact is consumed by a different downstream agent through a different part of its input contract. Putting them in named files instead of a section buried at the end of an overview makes each one reference-able with `-f` during a spawn, auditable in isolation, and directly consumable without traversing an unrelated doc.

Read [overview.md](overview.md) for why structure, refactor intent, and feasibility are first-class design concerns under v3. Read [design-orchestrator.md](design-orchestrator.md) for how design-orch runs this workflow. Read [planner.md](planner.md) for how the planner consumes `refactors.md` and `feasibility.md` as decomposition inputs. Read [impl-orchestrator.md](impl-orchestrator.md) for how impl-orch consumes `feasibility.md` during pre-planning.

## Why a workflow contract, not ad-hoc analysis

Terrain analysis is consumed by three distinct agents — design-orch (produces the outputs), impl-orch (reads `feasibility.md` during pre-planning), @planner (reads both `refactors.md` and `feasibility.md` during decomposition) — plus by the structural reviewer in design-phase fan-out. Without a contract, each consumer interprets the outputs differently and the producer drifts. With a contract, the producer has a checklist for completeness and the consumers can reason about what they are guaranteed to find.

The contract is the source of truth for terrain analysis content. The design-orchestrator body references this doc for the required outputs. The planner body references it for what to consume. The impl-orchestrator body references it for what `feasibility.md` will contain at pre-planning time. All three must match.

## The two outputs

Terrain analysis writes to **three locations** in the design package. The architecture tree is not new — it is where the current + target structural posture lives under v3. `refactors.md` and `feasibility.md` are the new first-class artifacts.

| Output | What lives there | Primary consumer |
|---|---|---|
| `design/architecture/overview.md` and subtrees | Current + target structural posture — the import graph, interfaces, coupling map, and the post-implementation shape | Every downstream agent reads the architecture tree for the structural map |
| `design/refactors.md` | Refactor agenda — named structural changes that must land before feature phases can run in parallel | @planner reads every entry and maps each to a phase in `plan/overview.md` |
| `design/feasibility.md` | Gap-finding output — fix-or-preserve verdict, parallel-cluster hypothesis, probe evidence, known unknowns, integration-boundary risks | @impl-orchestrator reads during pre-planning; @planner reads as input to decomposition |

Architecture tree contents are specified in [design-orchestrator.md](design-orchestrator.md) §"The architecture tree". This contract governs `refactors.md` and `feasibility.md` — the two artifacts the terrain analysis workflow produces directly — and describes what the workflow *reads* from the architecture tree to generate them.

## `design/refactors.md` — required shape

`refactors.md` is the **refactor agenda**: an ordered list of structural changes that must land before feature phases can run in parallel. Each entry is a discrete, sequencing-relevant refactor — rearrangement of existing code (splits, extractions, renames, collapses) — not a feature change.

Under v2, refactors lived as `structural-prep-candidate: yes`-tagged bullets inside a "structural delta" subsection. Under v3 the tag is dropped: `refactors.md` is a dedicated artifact and every entry in it is a refactor candidate by construction. Feature-scoped changes noticed during structural analysis do not belong in `refactors.md` — they are recorded in the architecture tree (as differences between current and target posture for the affected subsystem) or in the spec tree (as new observable behaviors).

### Per-entry shape

Each refactor entry is a short titled subsection, not a one-line bullet. The nine-or-so entries of a typical work item deserve enough space to be read, reviewed, and mapped to a phase.

```markdown
## R01: Split `auth/handler.py` into parser and persistence

**Target:** `auth/handler.py` → `auth/parser.py` + `auth/persistence.py`
**Affected callers:** `api/routes/login.py`, `api/routes/register.py`, `tests/auth/`
**Coupling removed:** parser and persistence are unrelated concerns currently mashed into one class. Splitting them lets later feature phases touch one side without invalidating work on the other.
**Must land before:** any feature phase that adds parser rules (unblocks P3, P4) or persistence backends (unblocks P5).
**Architecture anchor:** `design/architecture/auth/overview.md` §"Target topology — parser + persistence split".
**Preserves behavior:** yes — this is a rearrangement, no observable behavior change. No spec leaves depend on it directly.
**Evidence:** current `handler.py` mixes `parse_claims()` with `write_session()`; grep shows 14 callers of `handler.py` across `api/routes/`, all of which could take either the parser or the persistence adapter but not both.
```

Required fields per entry:

1. **ID** — `R01`, `R02`, ... stable across redesign cycles so plans can reference them by ID.
2. **Title** — a one-line imperative naming the refactor.
3. **Target** — the exact files/modules/symbols being restructured. Before → after shape if applicable.
4. **Affected callers** — every downstream module, caller, or test file that touches the restructured surface and may need updating.
5. **Coupling removed** — the specific coupling or structural debt this entry eliminates, in concrete terms (not "cleans up the code").
6. **Must land before** — the feature phases or later refactors this must precede, named by the work the refactor unblocks. If the refactor unblocks nothing, it is not a refactor candidate; it is cleanup and belongs elsewhere.
7. **Architecture anchor** — a link into `design/architecture/` naming the subtree that describes the target state of the affected surface. This is the traceability line from refactor intent to target topology.
8. **Preserves behavior** — `yes` if the refactor is pure rearrangement with no observable behavior change, `no` if it changes observable behavior (which means spec leaves also change — list them).
9. **Evidence** — a file path, import-graph observation, grep hit, or probe result backing the claim. Vibes-based "this feels coupled" is not evidence.

### Ordering and grouping

`refactors.md` is written in sequence order as best design-orch can anticipate it, but the planner makes the final sequencing call. Entries do not need explicit dependency edges between themselves unless one refactor makes another impossible until it lands — in which case the `must land before` field names it.

Grouping: if two refactors are independent and touch disjoint modules, they stay as two entries (so the planner can run them in parallel within a single refactor-prep round). If two refactors must land as a single atomic change to preserve invariants, they get one combined entry with both targets listed.

### What is *not* in `refactors.md`

- Feature-scoped changes (new behaviors, new fields, new endpoints). Those are spec leaves + architecture target-state.
- Foundational prep — net-new scaffolding that exists only to unblock later work (type definitions, new helper modules, new interface contracts that don't yet exist). Foundational prep is *creation*, not *rearrangement*, and lives in `feasibility.md` under its own subsection. See "Refactors vs foundational prep" below.
- "Nice to have" cleanups with no unblocking purpose. If the refactor unblocks nothing, it belongs in a follow-up work item, not in the current refactor agenda.

## `design/feasibility.md` — required shape

`feasibility.md` is the **gap-finding output**: what design-orch probed, what evidence came back, which constraints are grounded in evidence versus unprobed assumption, and what impl-orch needs to re-verify during pre-planning. This is where design-phase investigation results land so the planner and impl-orch can consume them directly instead of inferring from prose.

Required sections, in this order:

### 1. Fix-or-preserve verdict

```markdown
fix_or_preserve: fixes | preserves | unknown
reasoning: <one paragraph>
```

- **fixes** — the architecture tree's target topology eliminates the coupling problems the current topology has. The design has done the structural work the user is depending on. Backing evidence: every named coupling problem in the current posture is addressed by a `refactors.md` entry or by a target-state change described in the architecture tree.
- **preserves** — the design adds features without resolving the underlying structural coupling. Convergence blocker. Design-orch must either revise the architecture tree + refactor agenda to fix the structure or document why preservation is acceptable for this work item (and the structural reviewer must concur).
- **unknown** — design-orch could not determine whether the target fixes or preserves, usually because runtime data is needed to confirm. Convergence blocker until resolved. The structural reviewer should treat `unknown` the same as `preserves` — push back until the answer is concrete.

The reasoning paragraph is required for every value. A `fixes` answer with no reasoning is not a real answer; it is design-orch declaring victory without making the case.

### 2. Parallel-cluster hypothesis

A hypothesis about which clusters of work should be parallelizable after the refactor agenda lands. Required even if the planner later corrects it with runtime data.

Format: a list of named clusters with the architecture subtree + modules they touch.

```markdown
- **Cluster A — auth refactor.** Subtree: `architecture/auth/`. Modules: `auth/parser.py`, `auth/persistence.py`, `tests/auth/`. Unblocks spec leaves S03.1.*, S03.2.*.
- **Cluster B — token store interface.** Subtree: `architecture/tokens/`. Modules: `tokens/`, `middleware/tokens/`, `tests/tokens/`. Unblocks spec leaves S05.1.*, S05.2.*.
- **Cluster C — telemetry hooks.** Subtree: `architecture/telemetry/`. Modules: `telemetry/`, `hooks/`. Unblocks spec leaves S08.*.
```

The point is forcing design-orch to actually imagine the decomposition. If design-orch cannot name two or more clusters, the design is probably not decomposable for parallelism — that is the structural reviewer's signal to push back.

Evidence requirement: each cluster must name specific modules and link to an architecture subtree, not abstract concepts. "Frontend cluster" is not concrete; "`architecture/ui/auth/` + `components/SignIn.tsx` + `components/SignUp.tsx` + `tests/components/auth/`" is concrete. Each cluster should also name the spec leaves it unblocks, so the planner can trace the path from cluster to phase to leaf.

### 3. Probe evidence

A record of the runtime probes design-orch ran during design-phase investigation, with their results. This is the section that distinguishes grounded claims from unprobed assumptions, and it is the section impl-orch reads during pre-planning to decide whether a probe needs re-running.

Each probe entry:

```markdown
### Probe P1: Does the codex CLI accept `--sandbox read-only` when streaming?

**Why asked:** architecture/permission-pipeline/codex.md target state assumes the flag propagates through streaming startup. Needs empirical verification.
**How probed:** ran `codex spawn --sandbox read-only --stream` against a local installation; captured `debug.jsonl` from the startup handshake.
**Result:** flag propagates and is enforced. Debug log shows `sandbox=read-only` in the bootstrap frame. Write operations to `/tmp` are rejected as expected.
**Backs constraint:** `spec/permission-pipeline/codex.md` leaf L12.3.e1, architecture subtree `architecture/permission-pipeline/codex.md` §"Sandbox propagation".
**Stale-if:** codex CLI minor version bump, streaming runner refactor.
```

Required fields:

- **Why asked** — the assumption this probe was checking.
- **How probed** — the concrete action (command, script, test run) with enough detail that impl-orch can re-run it.
- **Result** — what actually came back, including any partial or surprising results.
- **Backs constraint** — the spec leaves, architecture sections, or refactor entries that depend on this probe's outcome. This is the traceability line — downstream agents can ask "is this claim grounded?" and follow the link to the probe.
- **Stale-if** — the conditions under which the probe result is no longer reliable (version bump, refactor in a dependency, environment change). Impl-orch re-runs the probe if any `stale-if` condition holds when pre-planning begins.

### 4. Foundational prep

Any net-new scaffolding that exists only to unblock later work and has no standalone value — type definitions, abstract base classes, shared helpers, interface contracts that don't yet exist. Distinct from refactors (see "Refactors vs foundational prep" below).

Format: a list of scaffolding items with the work each unblocks.

```markdown
- **New helper `harness_protocol.py`.** Defines the shared protocol adapters will implement. Unblocks refactor R03 (harness adapter extraction) and spec leaves S07.*. Greenfield — no current file.
- **New type `SpawnEnvelope`.** Shared type for the spawn envelope passed between runner and harness. Unblocks Cluster A and Cluster B in the parallel-cluster hypothesis.
```

Design-orch does not commit to an ordering here — the planner decides when scaffolding lands relative to the refactor agenda. But naming the scaffolding at design time means the planner reads it as input instead of inventing it.

### 5. Integration boundaries

Which protocols, binaries, or APIs need real probing before coding against them, and which were already probed (pointing into the probe evidence section). This is the risk surface where "code against assumed protocol" goes wrong, and design-orch surfaces it so impl-orch can decide how to cover it during pre-planning.

```markdown
- **codex CLI integration.** Probed (P1, P2). Protocol verified against v0.47.0.
- **claude CLI integration.** NOT probed. Risk: assumed behavior of `--session-id` override; needs impl-orch pre-planning probe.
- **Supabase realtime subscription.** Probed docs only (no runtime probe). Stale-if: library minor version bump; impl-orch should re-run probe before planning.
```

### 6. Known unknowns — impl-orch must resolve during pre-planning

Things design-orch judged it could not resolve without runtime data that will not be available until impl-orch runs. These are tagged explicitly with `impl-orch must resolve during pre-planning` so impl-orch reads them as a checklist during its pre-planning step.

```markdown
- **Test-suite fixture layout.** Design-orch did not enumerate which fixtures are shared across the parallel clusters. `impl-orch must resolve during pre-planning` by running the suite and checking for fixture races between clusters.
- **Current installation of claude CLI on dev machines.** Design-orch could not confirm version. `impl-orch must resolve during pre-planning` by running `claude --version` and updating the feasibility entry P4 if the version differs from what was probed.
```

This is not a place to dump every open question — only the structural or probe-evidence questions design-orch could not answer with architectural reasoning alone, that block decomposition. Questions that are preferences or taste calls do not belong here.

## Refactors vs foundational prep

Terrain analysis distinguishes two related but separate categories. The distinction matters because `refactors.md` and `feasibility.md` treat them differently and the planner does too.

- **Refactors (rearrangement).** Change to existing structure: split a module, extract an interface, collapse duplicates, rename across consumers. The starting point exists; the change moves things around. Lives in `refactors.md` as a numbered entry.
- **Foundational prep (new scaffolding).** Net-new code that exists only to unblock later work and has no standalone value: type definitions, abstract base classes, shared helpers, interface contracts that don't yet exist. The starting point is empty; the change adds something later phases depend on. Lives in `feasibility.md` §"Foundational prep".

Both can land in cross-cutting prep phases. Both can unlock parallelism. The difference is whether the change is rearrangement (refactor) or creation (foundation). A planner reading the design package should be able to identify which category each item is in by looking at which file the item came from.

If a single change is both ("split module X into A and B *and* add a new shared helper Z"), record it as two items in the appropriate files so the planner can sequence them independently if needed.

## Evidence and convergence

The structural reviewer in the design-phase fan-out checks both outputs for evidence:

**`refactors.md`:**
- Every entry has a target, affected callers, coupling removed, must-land-before, architecture anchor, behavior-preservation flag, and evidence.
- No entry is feature-scoped (no new-behavior items mixed in).
- Every entry's architecture anchor resolves to a real subtree in `design/architecture/`.

**`feasibility.md`:**
- `fix_or_preserve` has a value other than `unknown` and a reasoning paragraph.
- Parallel-cluster hypothesis has at least two named clusters with specific modules and architecture anchors.
- Every probe entry has why/how/result/backs/stale-if fields filled in.
- The known-unknowns section lists only structural or probe questions, not preferences.

A design package that fails any of these checks is not converged on the structural axis, even if functional review has passed. The structural reviewer is required in the design-phase fan-out for exactly this purpose; see [design-orchestrator.md](design-orchestrator.md) §"Active structural review during convergence".

## Anti-patterns the contract is designed to prevent

- **Vibes-based "fixes coupling" prose.** The fix_or_preserve field plus the evidence requirements in both `refactors.md` and `feasibility.md` force a real answer backed by probe evidence or architecture-anchor traceability.
- **Refactors without a planner-usable signal.** Dedicating `refactors.md` as a first-class artifact instead of tagging bullets inside a section makes the handoff to @planner direct — the planner reads one file and every entry is a refactor candidate. No tag-parsing, no sub-section traversal.
- **Aspirational target posture with no architecture-doc backing.** The architecture-anchor field on every refactor entry forces the target state to exist in `design/architecture/` before the refactor can be claimed — design-orch cannot describe a cleaner architecture it has not actually designed.
- **No parallel-cluster hypothesis at all.** A design that cannot name two clusters is probably not decomposable for parallelism, and the structural reviewer catches that before convergence.
- **Probe assumptions without evidence.** The probe-evidence section forces design-orch to distinguish "we checked this" from "we assumed this." Impl-orch reads `stale-if` conditions and decides what to re-probe.
- **Terrain analysis buried in an overview.** Under v2 the section lived at the end of `design/overview.md` and downstream agents had to load the entire overview to consume it. Under v3 each output is `-f`-able independently; a planner spawn attaches `refactors.md` without dragging `overview.md` into the context window.

## Why the contract lives in its own doc

Earlier drafts had terrain analysis content described inline in `design-orchestrator.md`. That tangles producer responsibility with consumer expectations: a planner reading `planner.md` would have to also read `design-orchestrator.md` to understand what it could expect from `refactors.md` and `feasibility.md`, and a structural reviewer would have to read both to know what to check.

Extracting the contract into its own doc means:

- The producer (design-orchestrator.md) references this doc for the required output shape rather than re-stating it.
- The planner consumer (planner.md) references this doc for what `refactors.md` and `feasibility.md` contain.
- The impl-orch consumer (impl-orchestrator.md) references this doc for what `feasibility.md` contains at pre-planning time.
- The structural reviewer is briefed against this doc directly.
- Updates to the contract land in one place and propagate by reference to all consumers.

This is the same pattern the rest of the design package follows: shared concerns get their own doc; agents reference shared docs from their own bodies.
