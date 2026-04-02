---
name: tech-docs
description: Technical writing methodology — structure, clarity, and navigability for documents that humans and agents rely on. Use whenever writing technical documents, design docs, reference material, architecture specs, or any structured documentation. Also activate when reviewing or restructuring existing docs.
---

# Tech Docs

Good technical writing lets a reader — human or agent — find what they need, understand it without chasing context across five files, and trust that what they're reading reflects reality. Every doc you write either accelerates the next person or wastes their time.

## One Concept Per Document

A document that covers two concerns drifts twice as fast and gets read by people who only need half of it. Apply the same SRP discipline you'd apply to code:

- One component, one interface, one interaction pattern, one decision per file.
- When a doc starts covering two things, split it. The discomfort of having "too many files" is less than the cost of a doc that's half-relevant to every reader.
- Name files by what they describe, not by when they were written. `token-validation.md` ages better than `auth-redesign-notes.md`.

## Hierarchical Structure

Depth matches complexity. A simple topic gets a flat file. A complex subsystem gets nested directories. No artificial ceiling.

```
overview.md
<area>/
  overview.md
  <topic>.md
  <sub-area>/
    <topic>.md
```

The overview at each level orients the reader: what exists here, how the pieces relate, and where to go deeper. A reader who only reads the overview should still walk away oriented.

## Linked Web

Documents link to related docs using relative paths. A component doc links to the components it interacts with, the interfaces it implements, the tradeoffs that shaped it. Links serve two purposes: navigation and making dependency relationships explicit. Broken links are broken promises; maintain them as you'd maintain broken imports.

## Writing for Agents

Agents scan for structure, match keywords, and build context from whatever file they're handed. Write docs that work when read in isolation:

- **Self-contained.** Include enough inline context that a reader doesn't need three other docs first.
- **Scannable.** Use headers, bullet lists, and tables so an agent can jump to the relevant section. Bold key terms on first use.
- **Concrete.** Reference file paths, function names, and line numbers. "The auth module" is vague; "`src/auth/token.py:validate()`" is actionable.
- **State the invariants.** Agents don't infer constraints — they follow instructions. If a component assumes single-threaded access, say so explicitly.

## Writing Style

**Diagrams over words.** Prefer visual representations for flows, state machines, and dependency graphs. Tables for comparisons. A diagram that shows the relationship is worth more than three paragraphs describing it.

**Compress, don't narrate.** Every sentence earns its place. One sentence per concept. If a diagram says it, don't also say it in text.

**Reference, don't duplicate.** Point to source locations rather than pasting code. Snippets only for critical patterns — atomic operations, race guards, non-obvious invariants.

**WHAT and WHY, not HOW.** Code shows the how. Documentation captures what the code can't easily tell you: component relationships, dependency directions, data flows, and especially why the system ended up this way.

## Verification

After writing or restructuring linked docs, run the co-located link checker to catch broken internal links and anchors:

```bash
scripts/check-md-links.sh <doc-root>
```
