# Two simplifications: approval walk and redesign brief

Two related simplifications that both collapse ceremony where a natural channel already exists.

## Simplification 1: approval walk

The dev-orchestrator approval walk currently names specific files (`design/spec/overview.md` and `design/architecture/overview.md`). That's more prescription than the agent needs — the dev-orch knows to walk the spec design and the architecture design with the user, and it can find the right entry points in the tree without a filename list.

Update `meridian-dev-workflow/agents/dev-orchestrator.md` so the approval walk reads at the category level: "walk the user through the spec design and the architecture design" or similar, without naming specific overview files. The intent is that the dev-orch trusts its judgment on where in each tree to start the walk based on what the user is reviewing.

`requirements.md` and `decisions.md` stay as specific filenames throughout the file — they're single-file per-work-item artifacts with stable names, so naming them is load-bearing. The simplification applies only to tree-shaped artifacts (spec tree, architecture tree, plan) where describing at the category level fits better than enumerating files.

While you're in the file, check the other places that enumerate specific filenames for tree-shaped artifacts and simplify where the category-level description reads cleaner without losing load-bearing information. Examples to check: plan review checkpoint (likely references `plan/overview.md`, phase blueprints, `plan/leaf-ownership.md`), spawning planning impl-orch (likely references design package paths), routing design-orch pushback. Apply judgment — if a specific filename is genuinely load-bearing because the agent needs to know exactly which file to touch or pass, keep it. If it's enumeration where "the plan" or "the design package" would read cleaner, simplify.

## Simplification 2: redesign brief into the terminal report

The v3 rewrite has impl-orchestrator write a separate `redesign-brief.md` file when its escape hatch fires, and dev-orchestrator reads the file to route the redesign. That's one more artifact than the flow needs — the impl-orch terminal report already reaches dev-orch, so the brief content can live as a section within that report instead of as a sibling file.

The brief's *content* stays the same (status, evidence, falsification case, design change scope, preservation, constraints, and the parallelism-blocking section for planning-time bail-outs). Only the delivery mechanism changes — from a file impl-orch writes to a structured section in impl-orch's terminal report.

Cross-cycle preservation is handled naturally by meridian spawn history: each redesign cycle has its own impl-orch spawn with its own terminal report, and those reports live in the spawn store indefinitely. The "append-only across cycles" semantic that the file version carried is implicit in the spawn history.

Update:

- `meridian-dev-workflow/agents/impl-orchestrator.md` — remove language about writing `redesign-brief.md` as a file. Replace with language about including the brief as a structured section in the terminal report when the escape hatch fires. Preserve the section contents (status, evidence, falsification case, design change scope, preservation, constraints, planning-time parallelism-blocking detail).
- `meridian-dev-workflow/agents/dev-orchestrator.md` — remove language about reading `redesign-brief.md` as a file. Replace with language about reading the impl-orch terminal report's redesign section when routing a bail-out.
- `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` — remove `redesign-brief.md` from the artifact list and remove any references to it as a first-class work-item artifact. The report structure lives in the impl-orchestrator body, not in dev-artifacts.
- Any other file in `meridian-dev-workflow/` that references `redesign-brief.md` — update or drop as appropriate.

The preservation-hint produced by dev-orch between cycles is a separate concern and stays as a file — it has a different producer (dev-orch, not impl-orch), a different consumer (the next cycle's planning impl-orch via `-f`), and it's load-bearing for the cross-cycle handoff. Don't touch it in this pass.

## Leave alone

- `requirements.md` and `decisions.md` references (single-file per-work-item artifacts)
- `preservation-hint.md` references (different producer/consumer than the redesign brief; stays as a file)
- Load-bearing file specifications — e.g., "write to `design/spec/`" or "pass `-f` with the approved plan" where the agent needs a specific target
- The dev-artifacts skill body's overall artifact convention description — only the `redesign-brief.md` listing gets removed from it per simplification 2; other entries stay

## Return

Terminal report with:
- Before/after for each simplification made
- Any tree-shaped-artifact references you chose to leave alone with a one-line reason
- Any similar patterns you noticed in other files that weren't in scope but could benefit from the same simplification (flag for follow-up)
