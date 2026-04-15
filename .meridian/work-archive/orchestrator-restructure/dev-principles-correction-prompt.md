# Narrow correction: dev-principles is universal, not a design-orch gate

D24 as currently landed in `$MERIDIAN_WORK_DIR/decisions.md` scopes `dev-principles` too narrowly — it says the skill is a design-orch convergence gate and downstream agents "carry it as context." User feedback: design principles should be generic for everyone. `dev-principles` is a shared behavioral lens that every relevant agent loads, not a gate at one orchestration point.

This is a surgical patch across four files.

## Files to touch

1. `$MERIDIAN_WORK_DIR/decisions.md` — revise D24
2. `$MERIDIAN_WORK_DIR/design/design-orchestrator.md` — drop "convergence gate" framing
3. `$MERIDIAN_WORK_DIR/design/impl-orchestrator.md` — adjust reasoning for why impl-orch doesn't gate
4. `$MERIDIAN_WORK_DIR/design/planner.md` — confirm dev-principles framing is consistent with universal loading

## What "generic for everyone" means

`dev-principles` is a skill — reference material loaded by whatever agent needs it. Multiple agent types load it and apply it continuously across the lifecycle:

- `@coder` loads it because refactor discipline, edge-case thinking, abstraction judgment, deletion courage, pattern-following, and integration-boundary probing shape the code they write.
- `@reviewer` loads it because it's the evaluation lens. Refactor reviewer, structural reviewer, and correctness reviewer all read it as their rubric for findings.
- `@architect` loads it because abstraction judgment, modularity, and structural hygiene are design-time concerns during exploration.
- `@design-orchestrator` loads it to shape convergence — convergence is judged on whether the design honors the principles, with reviewers using them as part of their evaluation rubric. There is no binary pass/fail gate mechanism.
- `@planner` loads it because refactor sequencing and foundational-prep ordering are principle-driven judgment calls.
- `@impl-orchestrator` coordinates and doesn't apply the principles directly itself, but the coders and reviewers it spawns already carry them.

The wrong mental model is "dev-principles is a checkpoint." The right one is "dev-principles is operating guidance that every agent whose work touches structure, abstraction, or correctness loads and applies continuously."

## D24 revision

Replace the current D24 body with content that reflects the universal framing. Keep the decision ID (D24), the `## D24:` heading, and the revision-history pattern (mark this as a revision of the prior D24, not a new decision — the prior D24 was a first-pass correction that landed too narrow).

Key points for the revised D24 body:
- The decision: `dev-principles` is a shared skill loaded by every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns.
- Not a gate — behavioral guidance that shapes work as it happens.
- Design-orch loads it during convergence as one of several lenses; convergence is judged on whether the design honors the principles, not on a pass/fail mechanism.
- Coders, reviewers, architects, and planner all load it in their own work.
- Impl-orch doesn't load the skill directly because it's a coordinator, not an evaluator — but every agent it spawns that touches code or structure already has the skill loaded.
- Final review at implementation time doesn't need a separate dev-principles reviewer lens — all reviewers already apply the principles as their rubric.
- Reasoning: principles are universal by definition. Gating them at one orchestration point creates a false binary; loading them as a shared skill makes them operational across every surface where they apply.
- Alternatives considered: (a) dev-principles as a design-orch-only gate — rejected because principles don't stop applying at handoff; (b) dev-principles inlined into each agent body — rejected because duplication drifts and the shared skill is the right pattern; (c) dev-principles as a hard pass/fail gate anywhere — rejected because principles are behavioral guidance, not checklists.

## design-orchestrator.md revision

Scan for "convergence gate" language around dev-principles and replace with "shared behavioral lens" framing. Specific shifts:
- "Load `dev-principles` as a hard gate during convergence" → "Load `dev-principles` as a shared behavioral lens; convergence is judged on whether the design honors the principles, with reviewers using them as part of their evaluation rubric."
- "blocks convergence if the answer is no" → replace with language that makes review findings the enforcement mechanism (a reviewer flags a principle violation, convergence continues once addressed).
- Any other language that treats dev-principles as a binary check.

Preserve the rest of the doc's content. This is a framing correction, not a restructure.

## impl-orchestrator.md revision

Scan for dev-principles language. Current framing (post-p1535): "impl-orch does **not** run a pass/fail gate itself. Instead, impl-orch spawns one reviewer in the final fan-out whose brief names `dev-principles` as the review lens."

Update: impl-orch doesn't need a dedicated dev-principles reviewer lens because all reviewers it spawns already load `dev-principles` as part of their skill set. The final review fan-out applies the principles across every reviewer, not as a special lens. Impl-orch's role remains coordination; principle application happens at the agents it spawns.

## planner.md revision

Scan for dev-principles language. Current framing (post-p1535): "`dev-principles` skill load framed as context-for-sequencing-judgment, not a gate."

This is already close to right — just confirm the framing is consistent with "loaded because refactor sequencing is principle-driven" rather than "loaded as a design-orch exception." The planner loads the skill because planner is one of the agents that applies the principles in its own work, same pattern as coders and reviewers.

## Scope

This patch touches four files. It does not:
- Restructure any doc layout (that's the main two-tree pass running separately)
- Add new content beyond the corrections
- Modify any decision beyond D24
- Touch agent profiles in `meridian-dev-workflow` (that's a coordinated follow-up tracked separately)

## Return

Terminal report naming:
- The four files touched with a one-line summary of the change in each
- The revised D24 body (copy-pasted into the report so it's inspectable)
- Any place you found dev-principles language that was already correct and didn't need touching
- Any place you found dev-principles language that looked wrong but didn't fit the patch scope (flag for follow-up)
