# Soften the "dial back aggressive language" principle in agent-creator and skill-creator

The `agent-creator` and `skill-creator` skills both carry a "Dial back aggressive language" principle (#4 in each) that reads as a blanket prohibition against ALL CAPS, "CRITICAL", "you MUST", and "NEVER". When a sweep coder loads these skills as authority and runs a rewrite pass, it applies the rule uniformly — stripping every occurrence of those words, including load-bearing standing principles where the firm language earns its place.

Evidence this is a real problem: a recent sweep (session p1561) removed legitimate standing principles like "Never write code or edit source files directly — it compromises your orchestration altitude" and "Always use meridian spawn for delegation — never use built-in Agent tools" because they matched the "NEVER" pattern. A separate restoration pass (p1562) had to put them back.

The fix: soften the principle so it distinguishes writing-new-prompts from rewriting-existing-prompts, and distinguishes belt-and-suspenders prohibitions from load-bearing standing principles. The principle should still guide toward positive framing by default, but it should make clear that some negatives earn their place.

## Files to edit

- `meridian-base/skills/agent-creator/SKILL.md` — principle #4 "Dial back aggressive language"
- `meridian-base/skills/skill-creator/SKILL.md` — principle #4 "Dial back aggressive language" (same content, same softening)

Edit the source submodules, not `.agents/` or `.claude/skills/` (those are generated outputs).

## What the current principle says

> ### 4. Dial back aggressive language
>
> Avoid ALL CAPS, "CRITICAL", "you MUST", "NEVER". Aggressive language was a reasonable defense against undertriggering on older models; on current models it pushes toward brittle, literal compliance and overtriggering — the instruction fires in contexts where it doesn't make sense. As models keep getting more responsive to system prompts, the threshold for this overtriggering drops. Use ordinary language. "Use `meridian spawn` to delegate work; the built-in Agent tool bypasses meridian's state tracking" is firmer in practice than "YOU MUST NEVER USE THE AGENT TOOL."

## What the softened principle should carry

The same core direction (positive framing is the default when writing new prompts), plus three clarifications the current version lacks:

1. **Writing vs rewriting.** The guidance applies to *writing* new prompts, not to mechanically stripping every negative from existing ones. A sweep pass that removes every "never" from an existing prompt will over-apply this principle.

2. **Belt-and-suspenders vs load-bearing.** Some negative framings are belt-and-suspenders on a behavior the prompt already describes positively ("the delegation chain already says planner is spawned by planning impl-orch; saying 'never spawn planner directly' on top is redundant and can be omitted"). Other negative framings *are* the load-bearing constraint, and removing them loses real information ("never write code or edit source files" is the orchestrator-coordinates-not-implements principle, not a loophole to close — the negative carries the constraint). The judgment is per-instance, not blanket.

3. **Reasoning earns the firmness.** A firm negative with explicit reasoning attached is much stronger than a bare prohibition. "Never write code or edit source files directly — dropping into implementation compromises your orchestration altitude" reads as a load-bearing principle; "NEVER EDIT SOURCE FILES" reads as a brittle rule. When the firm language is justified, keep the *reasoning* alongside it.

Add one positive example of a "never" that earns its place. The clearest example: the orchestrator-doesn't-edit principle. A decent alternative: the meridian-spawn-over-Agent-tool rule.

## What to keep

- The core observation that aggressive language on current models pushes toward brittle literal compliance and overtriggering — this is still true.
- The critique of ALL CAPS and CRITICAL as shouty writing — still useful.
- The default preference for positive framing when writing new prompts — still right.
- The example contrasting "YOU MUST NEVER USE THE AGENT TOOL" with the ordinary-language alternative — still valid as an illustration of the blanket-all-caps style the principle targets.

## What to change

- Reframe the principle's opening from "Avoid ALL CAPS, CRITICAL, you MUST, NEVER" to something that emphasizes positive framing as the default for new prompts, while acknowledging that firm negatives with reasoning have a place.
- Add the writing-vs-rewriting distinction.
- Add the belt-and-suspenders-vs-load-bearing distinction with a short example of each.
- Add a positive example of a firm negative that earns its place.

## What else to scan for

Both skills carry other principles that might have similar blanket-rule failure modes. Quick scan for language like "avoid X", "don't Y", "never Z" that could be misapplied by a sweep coder. Flag in the terminal report if you see candidates for softening beyond principle #4.

## Quality bar

After the edit:
- A future sweep coder loading agent-creator/skill-creator reads principle #4 and does not interpret it as "strip every negative from existing prompts."
- The principle still guides toward positive framing when writing new prompts.
- The example "never" that earns its place is concrete enough that a reader can apply the same judgment to other candidates.
- Both skills land the same softening — they share the principle body between them.

## Return

Terminal report listing:
- The before/after of each section touched, so the softening is visible at a glance
- Any other principles you flagged as candidates for similar softening
- Any judgment calls you made about what to keep vs change in the principle
