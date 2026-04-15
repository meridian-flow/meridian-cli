# Decisions

## 2026-04-14: Writer prompt propagated wrong `mark_finalizing` ordering

Orchestrator's initial writer prompts described `mark_finalizing` as running "after harness exit, before drain/report emission". Source actually places it *after* drain/extract/enrich_finalize and retry handling, immediately before `finalize_spawn`. Both writers (@code-documenter p1773 and @tech-writer p1774) faithfully propagated the error across fs/ and docs/.

Both reviewers (p1775 gpt-5.4 on fs/, p1776 gpt-5.2 on docs/) independently flagged the mismatch against source. Fixed in p1777/p1778 with updated prompts citing runner.py line numbers. Convergence reached after one additional pass (p1779/p1780 re-verify + p1781 for two residual items).

Lesson: writer prompts containing code-shaped claims must be sourced from the code, not from the caller's memory. The review/fix loop caught it, which is exactly what it's for — but writers would have had a cleaner first pass if the prompt had quoted runner.py directly.

## 2026-04-14: Kept orphan-investigation.md as archived context

`.meridian/fs/orphan-investigation.md` is a pre-refactor investigation note. Could have deleted it, but kept it because archival notes with a clear "archived / superseded by" header preserve historical reasoning cheap. Updated the Resolution section to match the shipped fix and flagged the file as archived context at the top.

## 2026-04-14: Reviewer fan-out across gpt-5.4 + gpt-5.2

Used different model families for first-pass review per CLAUDE.md guidance (gpt-5.4 on fs/, gpt-5.2 on docs/). Both caught the same core issue (mark_finalizing ordering), which is convergent signal — not redundant, because they independently verified different doc surfaces against the same underlying code. Re-verify pass used gpt-5.4 on both surfaces since the remaining checks were narrow and fast.
