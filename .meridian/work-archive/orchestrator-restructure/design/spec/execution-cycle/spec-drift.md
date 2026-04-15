# S05.3: Spec-drift enforcement

## Context

If impl-orch discovers during execution that runtime evidence contradicts a spec leaf — not just that the code does not yet satisfy it, but that the spec itself describes behavior the system cannot or should not have — the spec must be revised before code changes land. Quiet workarounds that leave the code satisfying unstated behavior while the spec says something else are exactly the drift Fowler warns about under spec-anchored SDD. The enforcement mechanism is the escape hatch (S05.4): a falsified spec leaf fires execution-time bail-out, impl-orch stops spawning fix coders, writes the redesign brief naming the falsified leaf IDs, and routes to dev-orch. Design-orch revises the affected leaves (and any architecture-tree nodes that realize them), dev-orch writes a preservation hint, and a fresh impl-orch resumes against the revised spec. There is no path where code lands satisfying behavior the spec does not describe.

**Realized by:** `../../architecture/verification/orchestrator-verification-contract.md` (A03.1).

## EARS requirements

### S05.3.u1 — Spec leaves are authoritative

`The execution impl-orchestrator shall treat every spec leaf as the authoritative contract for the behavior it describes, and shall not land code that satisfies behavior the spec does not describe.`

### S05.3.c2 — Spec revision precedes any code workaround

`While the execution impl-orchestrator is running the fix loop, when runtime evidence contradicts the trigger, precondition, or response of a claimed EARS statement (not merely that the code does not yet satisfy the statement), impl-orch shall halt the fix loop, not land a code workaround that contradicts the leaf, and route the falsification through the escape hatch per S05.4.`

### S05.3.s2 — "Code does not yet satisfy" is not falsification

`While impl-orch is evaluating runtime evidence against a spec leaf, "the code currently fails the assertion" shall not be treated as spec-leaf falsification — that is normal fix-loop territory — and shall not fire the escape hatch.`

**Reasoning.** Normal test failures are the coder's work to fix. Falsification is a different signal: runtime evidence shows the trigger/precondition/response triple described in the leaf cannot hold no matter what the code does, because the system's actual capability contradicts it.

### S05.3.e1 — Coder silently workarounds are forbidden

`When a coder catches itself reaching for a code workaround that papers over a spec-leaf contradiction (e.g. swallowing an error the spec says should propagate, inverting a condition the spec says should hold, adding a guard that skips the spec-described behavior), the coder shall halt, report the contradiction to impl-orch as a potential falsification signal, and not commit the workaround.`

### S05.3.e2 — Discovered edge cases route through appropriate channel

`When impl-orch discovers an edge case during execution that the spec leaves did not cover at all, impl-orch shall either add the edge case to the spec via a scoped design-orch revision cycle (for edge cases that are legitimately new requirements) or route it through the escape hatch (for edge cases that reveal a structural falsification of an existing leaf), and shall not silently extend the code's behavior beyond the spec's reach.`

### S05.3.w1 — Revised spec leaf triggers re-verification, not re-implementation by default

`Where a redesign cycle revises a spec leaf in place (EARS statement refined but ID preserved), the next impl-orch cycle shall run a tester-only re-verification pass on phases that previously satisfied the leaf, per S05.5, and shall not default to re-spawning the coder on those phases until re-verification falsifies the revised statement.`

### S05.3.s3 — Falsification evidence must be epistemic, not severity-based

`While impl-orch is deciding whether to fire the escape hatch on a spec-leaf contradiction, the decision shall be epistemic (the evidence shows the trigger/precondition/response cannot hold on the real system), and shall not be severity-based (a painful test failure is not by itself falsification).`

**Reasoning.** Severity-based triggers would fire bail-outs on normal friction and paralyze the execution loop. Epistemic triggers fire only when continuing would compound a contract error — the distinction is what the failure reveals about the spec, not how painful it was to hit.

## Non-requirement edge cases

- **Silent code workaround with post-hoc spec revision.** An alternative would let coders land workarounds and have impl-orch file a spec revision after the fact. Rejected because it collapses the authoritative ordering of spec-first, code-follows. A commit that contradicts the spec cannot be safely audited, and spec revision after the fact loses the "why did this code ship" audit trail. Flagged non-requirement because the spec-first discipline is the central v3 guarantee.
- **Coder rewrites the EARS statement directly.** An alternative would let the phase coder edit the spec leaf when the contradiction is obvious. Rejected because the coder does not hold convergence authority on spec leaves, and because cross-cutting spec edits need to route through the full design-orch revision cycle (spec reviewer, alignment reviewer, structural reviewer). Flagged non-requirement because the author boundary on spec leaves is load-bearing for convergence trust.
- **Severity-based bail-out trigger.** An alternative would fire the escape hatch on severe test failures regardless of whether they falsified a spec leaf. Rejected because severity-based triggers paralyze normal fix-loop operations. Flagged non-requirement because the epistemic trigger rule is load-bearing for loop ergonomics.
