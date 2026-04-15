# S06.2: Preservation hint production

## Context

After design-orch returns a revised design package on a design-problem redesign cycle, dev-orch produces the **preservation hint** before spawning the next planning impl-orch. The hint scopes what the planner needs to re-decompose — without it, default-preserve (D8) degrades into ad-hoc handling and the planner re-decomposes work that is already valid. The hint format is specified in `preservation-hint.md` (the flat-doc artifact that this restructure preserves). Production steps are a six-step sequence dev-orch runs deterministically. The hint is overwritten on each redesign cycle, not appended — cycle history lives in the brief and decisions.md.

**Realized by:** `../../architecture/artifact-contracts/preservation-and-brief.md` (A02.3).

## EARS requirements

### S06.2.u1 — Dev-orch is the sole author of the preservation hint

`The preservation hint at plan/preservation-hint.md shall be authored exclusively by dev-orch, and neither impl-orch nor design-orch nor @planner shall write to this file.`

### S06.2.u2 — Hint is overwritten, not appended

`Every dev-orch preservation-hint production pass shall overwrite plan/preservation-hint.md with the current cycle's hint, and shall not append to or merge with prior cycle hints, because cycle history lives in the redesign brief and decisions.md.`

### S06.2.e1 — Six-step production sequence

`When dev-orch produces a preservation hint after a design-orch revision cycle, dev-orch shall execute the following six steps in order: read the redesign brief's preservation section (what impl-orch claimed could be preserved, what was partially invalidated, what was fully invalidated), read the revised design docs to confirm or revise that assessment, decide the replan-from-phase anchor, replay the constraints-that-still-hold from the brief into the hint, list any new or revised spec leaves the planner must claim in the new plan, and write plan/preservation-hint.md.`

### S06.2.e2 — Revised-leaf annotation preserves stable ID

`When dev-orch lists a spec leaf that was revised in-place during the redesign cycle (EARS statement refined, same ID per S02.1.e2), the hint shall list the leaf with a "revised: <reason>" annotation, and shall not renumber or renaming the leaf.`

### S06.2.e3 — Newly introduced leaves get fresh IDs

`When dev-orch lists a spec leaf that did not exist in the prior cycle and was introduced during the redesign, the hint shall list the leaf with a fresh ID in the appropriate S<subsystem>.<section>.<letter><number> namespace, and shall not reuse any retired ID.`

### S06.2.c2 — Dev-orch may revise impl-orch's preservation claims

`While dev-orch is producing a preservation hint, when dev-orch disagrees with impl-orch's preservation-section claim in the brief (e.g. impl-orch marked a phase "partially invalidated" but dev-orch decides after reading the revised design that it is actually fully preserved), dev-orch shall update the hint with the revised classification and record the rationale in decisions.md, because the hint is dev-orch's final call.`

### S06.2.s2 — Replan-from-phase anchor scopes planning work

`While dev-orch is deciding the replan-from-phase anchor, the anchor shall name the first phase number that must be replanned in the next cycle, and all phases before the anchor shall remain preserved (including "partially invalidated" phases that get tester-only re-verification per S05.5).`

### S06.2.s3 — Constraints-that-still-hold land in direct context

`While dev-orch is producing a preservation hint, constraints-that-still-hold from the brief shall be replayed into the hint as direct context, so that impl-orch and @planner have them without needing to re-read the brief.`

**Reasoning.** The hint is attached to the next planning impl-orch via -f. Forcing @planner to read the full brief for constraint replay would burn planner context on content that could be in the hint directly.

### S06.2.w1 — Absent hint on first cycle and on scope-problem paths

`Where dev-orch is running a first cycle (no prior bail-out) or a scope-problem path (S06.1.s4), plan/preservation-hint.md shall not exist, and planning impl-orch shall read the hint only when it is present on disk.`

### S06.2.c1 — Decision log records every preservation revision

`While dev-orch is producing a preservation hint, when dev-orch revises a preservation claim from the brief's original classification, dev-orch shall record the rationale in decisions.md for audit, and shall not rely on the brief's original claim as the final state.`

## Non-requirement edge cases

- **Append preservation hints across cycles.** An alternative would append each cycle's hint to the prior one for a full cycle history. Rejected because cycle history already lives in decisions.md and the brief, and a cumulative hint would grow uncontrollably while only the current cycle's scope matters. Flagged non-requirement because the overwrite-on-cycle rule is load-bearing for hint clarity.
- **Impl-orch produces the preservation hint instead of dev-orch.** An alternative would have impl-orch produce the hint since it has the richer runtime context. Rejected because dev-orch is the routing authority for redesign cycles and must own the final preservation call — impl-orch's brief is the raw input, dev-orch's hint is the final classification after reading the revised design. Flagged non-requirement because the single-author rule on the hint is load-bearing for loop accountability.
- **Planner produces the hint.** An alternative would fold hint production into @planner's inputs. Rejected because the planner runs inside a planning impl-orch cycle and needs the hint as an input, not an output. Flagged non-requirement to document the rejected ordering.
