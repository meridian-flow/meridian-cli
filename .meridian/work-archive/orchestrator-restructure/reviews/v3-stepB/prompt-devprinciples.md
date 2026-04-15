# Review brief — v3 step B two-tree instantiation, dev-principles framing lane

You are reviewing the design package at `/home/jimyao/gitrepos/meridian-channel/.meridian/work/orchestrator-restructure/design/`. Step B just finished materializing the two-tree layout. Your job is **verifying that `dev-principles` is framed correctly throughout the package** — D24 went through multiple revisions and step B should have swept the last of the stale gate-framing out.

## Context you need

- `decisions.md` D24 (revised this cycle). The current framing is: `dev-principles` is universal shared guidance loaded by every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns, and it is **never a binary pass/fail gate at any altitude** — not at design-orch convergence, not at impl-orch final review, not at any intermediate phase. Principle violations surface as reviewer findings that flow through the normal convergence / review / phase loops alongside any other finding. The correction source is an in-session user override in parent chat `c1135` and is recorded in the revision note at the top of D24.
- Earlier D24 drafts (reflected in some historical artifacts) described `dev-principles` as a hard gate at impl-orch altitude (v2 framing) or as a design-orch-only gate (v3-r1 framing). Both are now superseded.
- `design/architecture/principles/dev-principles-application.md` is the R07 anchor and should carry the canonical post-correction framing with a per-agent application table and a "why not a gate" section.
- `design/spec/root-invariants.md` §S00.w1 should encode the universal-loading rule as a ubiquitous EARS statement.
- `design/spec/design-production/convergence.md` §S02.4.w1 should encode the "during convergence apply as shared lens" rule as a where/optional-feature EARS statement.
- `design/spec/execution-cycle/phase-loop.md` §S05.1.s4 should encode the "across every final-review-loop reviewer" rule as a complex EARS statement.
- `design/feasibility.md` P05 and F04 were swept this step — they should no longer describe any binary gate at any altitude.

## What to check

1. **No binary gate framing anywhere.** Walk every leaf in `design/spec/` and `design/architecture/`, plus the 6 surviving flat docs. Flag any prose that describes `dev-principles` as a gate, checkpoint, pass/fail rule, separate convergence criterion, or mandatory blocking check at any altitude.
2. **Universal loading is explicit.** Verify the universal-loading rule is stated clearly in at least one spec leaf (expected: `S00.w1`) and restated in at least one architecture leaf (expected: `A05.1`). The list of agents that load the skill should include @coder, @reviewer, @refactor-reviewer, @planner, @architect, @design-orchestrator, @impl-orchestrator, @dev-orchestrator — and should **exclude** research-only agents like @internet-researcher and @explorer.
3. **Application table.** `design/architecture/principles/dev-principles-application.md` should carry a per-agent table that says what each agent loads and how each agent applies the skill. Verify every listed agent has a row, and that no row describes "runs a gate" or equivalent.
4. **Why-not-a-gate rationale.** Verify `dev-principles-application.md` includes a section explaining *why* the shared-context model is preferred over a gate at any altitude, naming the failure modes (gate gaming, altitude mismatch, bureaucratic drift). The revised D24 should match.
5. **feasibility.md P05 + F04 sweep.** Verify the two entries in `design/feasibility.md` describe `dev-principles` as universal shared guidance with no binary gate at any altitude — not "design-time only gate," not "impl-orch gate," not "interim fix." Cross-check the `Constraint` field of each against the A05.1 framing.
6. **Cross-reference to correction source.** Verify at least one artifact (decision log, principles leaf, or feasibility entry) names the in-session correction in parent session `c1135` as the source of the revised framing, so a resuming agent can trace the decision chain.
7. **No retirement surface leftovers.** The `Retirement surface` section in `A05.1` enumerates every `meridian-dev-workflow/agents/*.md` file that must stop carrying gate framing after the coordinated skill edit lands. Verify that section exists and lists @design-orchestrator, @impl-orchestrator, @planner, @coder, @reviewer, and the feasibility sweep target.

## What NOT to check in this lane

- Whether every non-dev-principles claim is structurally sound (alignment lane).
- URL-level link integrity (cross-link lane).
- Whether the tree shape itself is well-factored (refactor-reviewer lane).

## How to report

Start with a one-line verdict: `FRAMING CONVERGED` or `FRAMING HAS GAPS`. Then for each gap: location, exact phrase or sentence that carries wrong framing, which sub-check caught it, and the correct replacement. Close with a summary of which sub-checks passed and which found issues.
