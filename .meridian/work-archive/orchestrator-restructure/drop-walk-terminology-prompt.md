# Drop "walk" terminology from the design approval section

The current `meridian-dev-workflow/agents/dev-orchestrator.md` has a "Design Approval Walk" section that uses "walk" language — implying the dev-orchestrator narrates or summarizes design content to the user. That's ceremony the user doesn't need. The actual flow is simpler: design is produced, the user reads it directly, the user responds, dev-orch routes the response. Dev-orch's role at approval time is "make the content available and wait for feedback."

## What to change

In `meridian-dev-workflow/agents/dev-orchestrator.md`:

- Rename the section heading from `## Design Approval Walk` to `## Design Approval` (or similar — whatever reads cleaner, without "Walk").
- Drop the "Default walk order:" language and the "walk" framing throughout.
- Reframe the section to describe the actual flow: when design-orch terminates with a converged design, the user reads it and decides; dev-orch waits for feedback; on approval, spawn planning impl-orch; on pushback, spawn a fresh design-orch with feedback attached.
- Keep the spec / architecture tree distinction if it helps orient the reader on what's in the design package, but describe it as what exists, not as what gets "walked."

Also scan the file for any other "walk" language used in the same sense (the dev-orch presenting/narrating content to the user). If you find any, apply the same reframing. Leave alone any uses of "walk" that are actually appropriate English (e.g. "walk the git history" or idiomatic uses that don't imply dev-orch narrating content).

## Quality bar

- No remaining "walk" language in the design approval section.
- The section describes the flow: user reads, dev-orch waits, dev-orch routes the response.
- Pushback routing still points to a fresh design-orch spawn.
- Approval routing still points to the planning impl-orch spawn.

## Return

Terminal report with:
- Before/after of the section
- Any other "walk" instances you found and touched (or explicitly left alone)
