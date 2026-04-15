# Round 2 review: verify convergence on agent-shell-mvp design tree

## Context

Round 1 reviewers (p1163 gpt-5.4 design alignment, p1164 opus contract fidelity, p1165 gpt-5.2 refactor) converged on three blockers and six concerns. Fix-pass architect p1166 (opus) edited seven design docs to resolve them. Your job is to verify the fix-pass actually resolved each finding and did not introduce new contradictions.

This is a **convergence check**, not a fresh review. Be focused and decisive — either the fix landed cleanly (close the finding) or it didn't (reopen with specific text that still needs changing).

## What you must read

1. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 — basis
2. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness authority
3. **The three round-1 reviewer reports** — your starting checklist:
   - `.meridian/spawns/p1163/report.md`
   - `.meridian/spawns/p1164/report.md`
   - `.meridian/spawns/p1165/report.md`
4. **The fix-pass architect report**, which says what was changed and how:
   - `.meridian/spawns/p1166/report.md`
5. The **current state** of the design tree (post-fix):
   - `$MERIDIAN_WORK_DIR/design/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/{overview,abstraction,adapters,mid-turn-steering}.md`
   - `$MERIDIAN_WORK_DIR/design/events/{overview,flow,harness-translation}.md`
6. The canonical meridian-flow contract for cross-check:
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md` (ToolDisplayConfig definition at §"Per-Tool Display Config")
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md`

## What to verify

Walk through each round-1 finding and check whether the current state of the design tree actually resolves it. Specifically:

### Blockers

- **B1 (all reviewers)** — Did `CAPABILITY`, `CONTROL_RECEIVED`, `CONTROL_ERROR` actually get removed from the on-wire AG-UI event stream? Grep across the eight design docs. Surviving mentions should be either (a) "there is no on-wire X event" negative form, or (b) explicit future-migration notes gated on meridian-flow agreement. Any positive emission of these events remaining = unresolved.
- **B2 (p1164)** — Does `TOOL_CALL_START` payload now carry only `{toolName, toolCallId}` (plus arguments in a later event)? Is the `config: {input, stdout, stderr}` payload field gone? Are the per-harness "render config" tables replaced with a "tool naming coordination checklist" that names the tools each adapter exposes without inventing config values?
- **B3 (p1165)** — Is FIFO declared the single authoritative control ingress? Is the streaming spawn clearly NOT reading its own stdin as a control channel? Does `overview.md`'s "stdin control protocol" wording still linger or has it been updated?

### Concerns

- **C1** — Is the `HarnessCapabilities` shape unified across all docs (flat, no `supports_` prefix, same field names)?
- **C2** — Is `supports_interrupt` fully removed? Does the Claude V0 story say `mid_turn_injection: "queue"` without claiming interrupt support? Is Codex structured reasoning consistently `false in V0, future upgrade`?
- **C3** — Does `harness/mid-turn-steering.md` now contain an explicit "failure modes and edge cases" section covering harness death, consumer disconnect, inject races, `--from`/`--fork` interaction, FIFO missing, FIFO with no reader, and frame-arrives-mid-tool-call?
- **C4** — Do the relative `..` path counts resolve to the correct files when followed from each doc's location? Spot-check at least three links per file.
- **C5** — Is the streaming CLI flag renamed to `--ag-ui-stream`? Does the design acknowledge the existing hidden `--stream` debug flag at `cli/spawn.py:211`?
- **C6** — Is the Codex `item/*/start|delta|end` notation either grounded in a citation or reframed as adapter-detected boundaries?

### Check for new contradictions

The fix-pass edited seven files. New contradictions can emerge when coordinated edits don't quite land in sync. Specifically look for:

- A stale mention of the old capability shape (`supports_*` prefix) in any doc
- A stale mention of `TOOL_CALL_START.config` payload in any doc
- A stale mention of stdin-as-control-channel in any doc
- A stale relative path count (5 segments where 6 are needed, or vice versa)
- An inconsistency between how `params.json` is described as the capability carrier and how capability reporting is described on the adapter side
- An inconsistency between how `control.log` is described as the control-error sink and how control-error semantics are described in the adapter or the CLI

## What NOT to do

- Do NOT re-litigate decisions the fix-pass deliberately made (e.g., "FIFO is the single ingress" — that's a decision, not a finding to reopen)
- Do NOT propose new structural changes beyond what round 1 flagged
- Do NOT demand exhaustive implementation detail; this remains a design tree
- Do NOT repeat round-1 findings that were explicitly deferred (ag_ui_events.py sprawl risk, codex.py growth risk) — those are documented as implementation-time concerns with concrete thresholds

## Report format

For each round-1 finding (B1, B2, B3, C1–C6) and any new contradiction you discover, report:

```
[Finding ID or new-contradiction label]: [RESOLVED | PARTIALLY RESOLVED | NOT RESOLVED | NEW CONTRADICTION]
Evidence: file path + section + specific quote
If not resolved: what concrete change still needs to happen
```

Then a **verdict** line:

- **CONVERGED** — all blockers resolved, remaining nits are non-blocking
- **BLOCKED** — at least one blocker is unresolved or a new blocker appeared

Finally, list any nits you spotted along the way (wording, typos, minor inconsistencies) as a short bulleted addendum. Nits do not affect the verdict.
