# Preservation Hint: Artifact Contract

This doc defines the preservation-hint artifact that carries phase-state information across redesign cycles. Producer: dev-orchestrator (when routing a redesign, derived from the redesign brief). Consumers: the next impl-orchestrator cycle and its spawned @planner.

The preservation-hint exists because default-preserve (D8) is the central claim of the autonomous redesign loop, but without a concrete data contract impl-orch's next cycle has no structured way to know which phases to skip. Without this contract, "default-preserve" is a verbal assertion that would degrade into ad-hoc handling.

Read [architecture/artifact-contracts/preservation-and-brief.md](architecture/artifact-contracts/preservation-and-brief.md) for the canonical shape of this artifact and [spec/redesign-cycle/preservation-hint-production.md](spec/redesign-cycle/preservation-hint-production.md) for the spec-side rules. Read [redesign-brief.md](redesign-brief.md) for the bail-out artifact this is derived from. Read [architecture/orchestrator-topology/redesign-loop.md](architecture/orchestrator-topology/redesign-loop.md) for how dev-orch produces the hint and [architecture/orchestrator-topology/planning-and-review-loop.md](architecture/orchestrator-topology/planning-and-review-loop.md) for how impl-orch consumes it.

## Location and lifecycle

The hint lives at `$MERIDIAN_WORK_DIR/plan/preservation-hint.md`. It is written by dev-orchestrator after a successful design-orch revision cycle, before spawning the next impl-orch. It is consumed by impl-orch as the first thing it reads, before pre-planning, so impl-orch knows which phases are already valid and can scope its pre-planning to the invalidated portion only.

The hint is overwritten on each redesign cycle, not appended. Cycle history is preserved in the redesign-brief.md (which is append-only) and in `decisions.md`. The hint is current-state only — what to preserve right now, what to replan right now.

Impl-orch's pre-planning step reads the hint first. If the hint exists, impl-orch:

1. Loads the preserved-phase list and treats those phases as immutable starting state.
2. Loads the invalidated-phase list and scopes its pre-planning notes to runtime constraints affecting those phases and any new phases that will be added.
3. Spawns @planner with the hint attached via `-f`. The planner uses it to anchor its decomposition — preserved phases stay as-is, invalidated phases are replanned, and the planner explicitly accounts for both in `plan/overview.md`.

## Structure

```markdown
# Preservation Hint: <work item name>

## Source

Derived from `redesign-brief.md` cycle <n>. Design revision: `decisions.md` D<m> (revised design docs: list).

## Preserved phases

Phases whose committed work is still valid under the revised design. Preserved has **two sub-categories** depending on whether the phase owns any spec leaves that the redesign revised in place:

- **Preserved, no re-verification.** None of the phase's claimed spec leaves appear in the "New or revised spec leaves" section with a `revised:` annotation. The next impl-orch cycle skips the phase entirely — coder is not respawned, no testers are spawned, commits stay in place.
- **Preserved but requires re-verification.** At least one of the phase's claimed spec leaves is listed as `revised: <reason>` in the leaves section below. The commits still stand (no coder respawn) but the next impl-orch cycle spawns a tester-only re-verification pass for those specific revised leaves against the existing code. The outcomes are in [architecture/orchestrator-topology/execution-loop.md](architecture/orchestrator-topology/execution-loop.md) §"Preserved-phase re-verification pass": the phase stays `preserved` if re-verification passes, promotes to `partially-invalidated` if any revised leaf falsifies. This category exists because the spec-anchored discipline requires code to match the *current* spec text, not the text that existed when the code was committed — preserving commits without re-verifying against revised leaves is the exact silent-drift failure Fowler warns against.

The table below lists all preserved phases; the `Revised leaves?` column names which sub-category applies.

**Column semantics:** the `Spec leaves satisfied` column contains **EARS statement IDs** at `S<subsystem>.<section>.<letter><number>` granularity, matching `plan/leaf-ownership.md` — not leaf-file paths. A single spec leaf file may contribute multiple statement IDs to this column if the phase claims several statements from it. The planner copies these IDs verbatim into the new `plan/leaf-ownership.md` when consuming the hint.

| Phase | Commit SHA | Spec leaves satisfied (EARS statement IDs) | Revised leaves? | Reason preserved |
|-------|-----------|---------------------------------------------|-----------------|------------------|
| Phase 1 (typed leaves) | abc123 | S01.1.e1, S01.1.e2, S01.2.e1 | none | unaffected by revision; type contracts unchanged |
| Phase 2 (permission pipeline) | def456 | S02.3.e1, S02.3.e2 | none | revision is Codex-specific; shared pipeline unchanged |
| Phase 3 (shared approval router) | ghi789 | S03.1.e1 (revised), S03.1.e2 | S03.1.e1 | routing shape unchanged; language of S03.1.e1 tightened, re-verification required to confirm |

## Partially-invalidated phases

Phases whose commits are kept (git history preserved) but whose work has parts that depend on the falsified assumption and must be reworked. The next impl-orch cycle treats these as "needs revision" — coder respawned with the partial-invalidation scope, spec leaves re-verified, fix landed as a new commit on top.

| Phase | Commit SHA | Spec leaves | What is invalid | What is salvaged |
|-------|-----------|-------------|-----------------|------------------|
| Phase 4 (Codex projection) | ghi789 | S04.2.e1, S04.2.e2 | The two-channel approval mapping (lines 40-80 of projection.py) | The base projection class and the streaming connection setup |

## Fully-invalidated phases

Phases whose work cannot be salvaged under the revised design. Commits stay in git history but the next impl-orch cycle treats them as not-yet-done — replanned, recoded, retested.

| Phase | Commit SHA | Spec leaves | Reason fully invalidated |
|-------|-----------|-------------|--------------------------|
| Phase 5 (approval routing) | jkl012 | S05.1.e1 | Built on Phase 4's two-channel assumption; fixing Phase 4 requires complete rewrite of routing |

## Replan-from-here

The first phase number that must be replanned. Everything before this phase number is preserved or partially-invalidated; everything from this phase forward is replanned by @planner.

`replan-from-phase: 4`

The planner is required to honor this anchor: the new plan must keep phase numbering up to `replan-from-phase - 1` consistent with the preservation list, and may renumber or reorganize from `replan-from-phase` onward.

## New or revised spec leaves from the redesign

Spec leaves added or revised in `design/spec/` during the redesign cycle that the planner must claim in the new plan. A leaf that existed in the prior cycle and was revised in-place keeps its ID and is listed with a `revised: <reason>` annotation; a newly introduced leaf gets a fresh ID.

- **S04.2.e3** (new) — confirm-mode on single channel. Added to `spec/permission-pipeline/codex.md` during redesign. Planner must claim this in `plan/leaf-ownership.md`; likely owner is the replanned Phase 4.
- **S04.2.e1** (revised: two-channel assumption dropped, rewritten as single-channel confirm behavior) — the existing leaf kept its ID but the EARS statement was rewritten. Phase 4's coder must re-verify against the new statement even on preserved code.

## Constraints from the original intent

Replays the "constraints that still hold" section from the redesign brief, so impl-orch and the planner have it in their direct context without needing to load the brief separately.

- Meridian must never silently downgrade a confirm-mode request to YOLO.
- Phase 1's type contracts must not be broken.
```

## Status field representation

The hint shapes how `plan/status.md` represents phases after a redesign cycle. The status values used:

- **`preserved`** — phase exists from a previous cycle, marked as complete, will be skipped entirely in this cycle (no coder, no tester). Applies only to phases whose claimed leaves were untouched by the redesign.
- **`preserved-requires-reverification`** — phase exists from a previous cycle with commits intact, but at least one claimed spec leaf was revised in place during the redesign. Impl-orch runs a tester-only re-verification pass against the existing code before executing any replanned or new phases. Outcome branches back into `preserved` (re-verification passes) or `partially-invalidated` (re-verification falsifies). Impl-orch is responsible for the promotion.
- **`partially-invalidated`** — phase exists from a previous cycle, marked as needing revision, will be revisited in this cycle. Reached either directly from the redesign brief (phase code explicitly scoped-out) or by promotion from `preserved-requires-reverification` when re-verification falsifies.
- **`replanned`** — phase from a previous cycle was fully invalidated; the new plan replaces it (possibly with a different number or shape).
- **`new`** — phase added in this cycle that did not exist before.
- **`not-started`** — phase exists in the current plan and has not yet been touched (the default for any phase that has not run).

The planner is required to seed `plan/status.md` with these values when a preservation-hint is present. Without a hint, all phases are seeded as `not-started` (the original behavior).

## How dev-orch produces the hint

After design-orch returns a revised design, dev-orch:

1. Reads the redesign brief's preservation section.
2. Reads the revised design docs — spec tree diff, architecture tree diff, updated `refactors.md` and `feasibility.md` — to confirm which phases are still valid and which are not.
3. For each entry in the preservation section, decides whether the design revision changed the assessment (e.g. design revision narrowed the change scope, so a partially-invalidated phase becomes preserved).
4. Enumerates the new and revised spec leaves introduced by the redesign cycle so the planner claims every affected leaf in `plan/leaf-ownership.md`.
5. Writes the preservation-hint.md file with the final preservation lists, the replan-from-phase anchor, and the leaf delta.
6. Spawns the next impl-orch with the revised design package and the preservation-hint attached via `-f`.

If dev-orch judges that the design revision invalidates more than the brief originally claimed, dev-orch updates the hint accordingly. The hint is dev-orch's decision, informed by both impl-orch's brief and design-orch's revised design.

## How impl-orch consumes the hint

Impl-orch's pre-planning step reads the hint first:

1. Loads the preserved-phase list. These commits are immutable starting state — no probing, no re-verification.
2. Loads the partially-invalidated list. Pre-planning notes scope to the runtime constraints that affect the invalidated parts (and only those parts).
3. Loads the fully-invalidated list and any new or revised spec leaves. These are the work the planner must replan.
4. Reads `replan-from-phase` to understand where the new plan starts.
5. Generates pre-planning notes scoped to the replan range, not the whole work item. This is what makes redesign cheap: pre-planning runtime work is proportional to the scope of the change, not to the total work item size.

The planner spawn then receives the design package + the hint + the scoped pre-planning notes. The planner produces a plan that respects the preservation anchor and renumbers or reorganizes only from `replan-from-phase` onward. The planner's new `plan/leaf-ownership.md` must contain **both** the preserved phases' leaf claims (copied from the hint's "Spec leaves satisfied" column for each preserved phase, verbatim) **and** the new or revised spec-leaf claims for replanned phases. Revised-in-place leaves carry the `revised: <reason>` annotation into the new ownership file so the phase blueprint re-verifies against the updated EARS statement even on preserved code. Omitting the preserved phases from the new ownership file makes impl-orch's completeness check falsely flag preserved leaves as unclaimed and wastes a planner re-spawn slot.

## Anti-patterns the contract is designed to prevent

- **Default-preserve as a verbal claim with no mechanism.** The hint makes preservation explicit and auditable.
- **Re-running pre-planning over the entire work item every redesign cycle.** Wasteful and erodes the cost benefit of incremental redesign. The replan-from-phase anchor scopes the work.
- **The planner forgetting which spec leaves are still claimed by preserved phases.** The hint replays leaf-to-phase ownership so the planner doesn't lose coverage.
- **Silent leaf revisions on preserved phases.** A spec leaf revised in place during a redesign cycle keeps its ID but its EARS statement changed; a naive preservation implementation skips the phase entirely and silently carries the old behavior forward under the new spec text. The `Revised leaves?` column above and the `preserved-requires-reverification` status value force impl-orch to run a tester-only re-verification pass against existing commits for any preserved phase with a `revised:` leaf. This is the exact spec-anchored failure mode the two-sub-category preserved design exists to close.
- **Drift between the brief's preservation section and the actual hint.** The hint is dev-orch's final call after reading the revised design, and dev-orch is allowed to update preservation status if the design changed the assessment. Decision rationale lands in `decisions.md` for audit.

## What the hint is not

- Not a plan. The planner still produces the plan; the hint anchors it.
- Not a substitute for the redesign brief. The brief is the historical record; the hint is the actionable instruction for the next cycle.
- Not a way to skip pre-planning. Impl-orch still runs pre-planning for the invalidated portion — the hint scopes it, does not eliminate it.
- Not consumed during normal (first-cycle) work. On the first impl-orch cycle, no hint exists. The hint is a redesign-cycle-only artifact.
