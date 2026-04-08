# Cross-Layer Leak Policy and Fix List

## The Problem

meridian-base is the lower layer. It must not assume any specific upper layer (dev-workflow, docs-workflow, or any future workflow) exists. When a base skill or agent says `@reviewer` or `@explorer` as if it's a real role the agent should expect to find, it has leaked layering — the skill becomes broken if loaded in a project that uses base without dev-workflow.

The earlier `@`-syntax sweep surfaced nine sites in meridian-base referencing dev-workflow agents. They split into two clean categories with different fixes.

## Policy: Examples vs Generic Guidance

**Generic-guidance references — must be fixed.** When a skill says "fan out @reviewers for high-risk work" as a *prescription* the reader is expected to follow, it asserts that `@reviewer` exists. That assertion is wrong in any project that doesn't ship dev-workflow. Fix by rewriting in layer-zero terms ("fan out additional reviewing spawns", "delegate bulk reading to a cheap exploration spawn", etc.).

**Pure example references — keep.** When a skill teaches a *concept* and uses `@reviewer` to make the example concrete (e.g., "agent profiles like @reviewer scope tools narrowly"), the agent name is illustrative, not prescriptive. Removing the name would make the example abstract and worse. The example is still correct in a project that doesn't ship dev-workflow — the reader just doesn't have that specific profile to look at, but the concept stands.

The test: **delete the agent name from the sentence and read it back.** If the sentence becomes meaningless or loses its instructional value, it was an example — keep it. If the sentence still makes sense and was telling the reader to *do something*, it was generic guidance — rewrite it without the agent name.

This policy is captured here once and referenced from `agent-creator` / `skill-creator`'s anti-patterns docs as the canonical rule.

## Fix List

| File | Line | Current text (excerpt) | Category | Fix |
|---|---|---|---|---|
| `meridian-base/agents/__meridian-orchestrator.md` | 29 | "fan out @reviewers with different focus areas" | **Generic** | Rewrite: "fan out additional reviewing spawns with different focus areas — different models catch different things." |
| `meridian-base/skills/__meridian-session-context/SKILL.md` | 62 | "delegate to @explorers rather than reading everything yourself" | **Generic** | N/A — file is being deleted (split into `__meridian-cli` + new dev-workflow skill). The replacement guidance lives in the new dev-workflow skill, where `@explorer` is in-layer. |
| `meridian-base/skills/__meridian-session-context/SKILL.md` | 65 | `meridian spawn -a explorer --skills __meridian-session-context` | **Generic** | Same — file deleted. |
| `meridian-base/skills/__meridian-session-context/SKILL.md` | 69 | "If you are an @explorer yourself…" | **Generic** | Same — file deleted. |
| `meridian-base/skills/agent-creator/SKILL.md` | 236 | "A @reviewer that only needs `git diff` and…" | **Example** | **Keep.** Illustrating tool-scoping principle with a concrete profile name. |
| `meridian-base/skills/agent-creator/SKILL.md` | 257 | "the @dev-orchestrator spawns you with `--from`" inside a quoted anti-pattern | **Example** | **Keep.** The phrase appears *inside* a quoted anti-pattern showing what NOT to write — so naming the agent is essential to the example, not incidental. Removing the name would defeat the anti-pattern. |
| `meridian-base/skills/agent-creator/SKILL.md` | 261 | "the same @reviewer can be called from a dev orchestrator, a CI pipeline, or a…" | **Example** | **Keep.** Illustrating profile reuse across contexts. |
| `meridian-base/skills/agent-creator/SKILL.md` | 297 | "canonical examples (minimal utility agent, @reviewer, orchestrator)" | **Example** | **Keep.** Literally enumerating example profiles. |
| `meridian-base/skills/agent-creator/resources/example-profiles.md` | 45, 92 | Walkthrough of an example reviewer profile | **Example** | **Keep.** The whole resource file is example profiles. |
| `meridian-base/skills/agent-creator/resources/anti-patterns.md` | 149 | "hardcoding a specific parent (@dev-orchestrator)" | **Example** | **Keep.** Naming the agent makes the anti-pattern concrete. |
| `meridian-base/skills/skill-creator/SKILL.md` | 290 | "'refactor the @reviewer'" inside a quoted trigger phrase | **Example** | **Keep.** Quoted illustrative trigger phrase, not a prescription. |
| `meridian-base/skills/skill-creator/resources/example-skills.md` | 140 | "@reviewers can read it once" | **Example (borderline)** | **Keep.** The weakest "Keep" — delete-test gives a still-meaningful sentence ("agents can read it once"). Lives in an example walkthrough where the agent name keeps it tactile. Borderline but not worth changing. |
| `meridian-base/skills/skill-creator/resources/anti-patterns.md` | 55 | `@reviewer` in an anti-pattern walkthrough | **Example** | **Keep.** Same logic as agent-creator anti-patterns. |

## Net Result

- **One real generic-guidance fix** in base after the consolidation: `__meridian-orchestrator.md` line 29.
- All four `__meridian-session-context` references vanish naturally because the file is deleted.
- All `agent-creator` and `skill-creator` references are examples and stay as-is per the policy above.

## Codifying the Policy

After the consolidation lands, add a one-paragraph note to both `agent-creator/resources/anti-patterns.md` and `skill-creator/resources/anti-patterns.md` stating the example-vs-generic rule explicitly. This prevents the next `@`-syntax sweep from "fixing" the legitimate examples by accident. The wording can be a single paragraph, ~5 lines, referenced from this design doc as the source of truth.

That codification is part of the consolidation work, not a follow-up. The planner should include it in the same phase as the orchestrator-line-29 fix.
