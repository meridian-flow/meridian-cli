# S05.2: Spec-leaf verification

## Context

Verification framing under v3 changes. A phase's success criterion is not "the code works" or "the tests pass" — it is "does this phase satisfy the spec leaves it claims?" Each phase blueprint names specific spec-leaf IDs (e.g. `S03.1.e1, S03.1.e2, S05.2.e1`) pulled from `design/spec/`. Testers read those leaves, parse the EARS statements into trigger/precondition/response triples per the mechanical parsing rule, and execute smoke tests that exercise each triple. A phase passes when every claimed EARS statement has at least one verified test and none are falsified. Smoke tests remain the default per the project's existing "prefer smoke tests over unit tests" rule. There is no TDD mandate — coders do not write tests before implementing.

**Realized by:** `../../architecture/verification/orchestrator-verification-contract.md` (A03.1), `../../architecture/verification/leaf-ownership-and-tester-flow.md` (A03.2), and `../../architecture/verification/ears-parsing.md` (A03.3).

## EARS requirements

### S05.2.u1 — Spec leaves are the verification contract

`Every phase verification in the execution cycle shall be rooted in the spec-leaf IDs the phase blueprint claims, and not in free-floating test cases outside the leaf-claim contract.`

### S05.2.u2 — Smoke tests are the default execution mode

`Every tester spawn run during phase verification shall execute smoke tests by default, in alignment with the project's "prefer smoke tests over unit tests" rule, and shall not require unit-test coverage before declaring a leaf verified.`

### S05.2.e1 — Tester parses EARS into trigger/precondition/response triple

`When a tester reads a claimed spec leaf, the tester shall parse each EARS statement into a trigger/precondition/response triple using the per-pattern parsing rule in the architecture tree's ears-parsing.md (A03.3), and shall apply the row matching the leaf's EARS pattern letter (u/s/e/w/c).`

### S05.2.e2 — Trigger becomes test setup, precondition becomes fixture, response becomes assertion

`When a tester derives a smoke test from an EARS triple, the trigger shall become the test setup, the precondition shall become the test fixture, and the response shall become the assertion, per the direct mapping in the architecture tree's ears-parsing.md.`

### S05.2.e3 — Unparseable leaf reports as "cannot mechanically parse"

`When a tester cannot derive a trigger/precondition/response triple from an EARS statement using the mechanical parsing rule, the tester shall report the leaf as "cannot mechanically parse — requires design clarification" and shall not fabricate an interpretation or silently skip the leaf.`

**Reasoning.** The mechanical parsing rule exists to surface ambiguity, not to paper over it. A tester that synthesizes a reading in the absence of a clean parse hides the convergence problem the rule was designed to expose.

### S05.2.e4 — Tester reports per EARS statement, not per leaf file

`When a tester reports verification results, the report shall list each claimed EARS statement ID separately with status (verified, falsified, not-covered, cannot mechanically parse), and shall not collapse multiple EARS statements inside a single leaf into a single leaf-level status.`

**Reasoning.** Ownership under D26 is at EARS-statement granularity; verification must match that granularity or the system cannot tell whether a leaf with multiple statements is partially verified.

### S05.2.s1 — Tester may execute additional edge-case tests beyond the claimed leaves

`While a tester is verifying a phase's claimed spec leaves, the tester may execute additional edge-case tests beyond the EARS statements as long as the claimed leaves are covered, and shall not substitute edge-case coverage for missing leaf coverage.`

**Reasoning.** Edge-case coverage is welcome additional signal, but it is additive, not substitutive. Covering edge cases but not the claimed leaves is incomplete verification under the leaf-claim contract.

### S05.2.s2 — Phase passes when every claimed EARS statement verifies

`While a phase's testers are reporting, the phase shall pass verification only when every claimed EARS statement reports verified and none report falsified, not when the tester declares "the code works" informally.`

### S05.2.s3 — No TDD — coders do not write tests before implementing

`While the execution cycle is running, the coder role shall not be required to write tests before implementing a phase, and the tester role shall run tests after the phase lands and report verification results on committed code; this is an explicit rejection of the test-first (TDD) flow and follows Kiro's spec-anchored-without-TDD discipline.`

### S05.2.w1 — Tester-generated edge cases are mandatory at the test layer

`Where a tester is verifying a phase, the tester shall generate and execute edge cases of their own — not just the happy-path scenarios the coder describes — because edge-case coverage is a first-class tester responsibility per dev-principles and "works on happy path" is an incomplete result, not a passing result.`

### S05.2.c1 — Unparseable leaves route back to design-orch

`While a tester is reporting unparseable leaves to the execution impl-orch, when the impl-orch receives the report, the impl-orch shall route the unparseable leaf back to design-orch via a scoped design revision cycle rather than letting the tester synthesize a reading, and shall not mark the phase complete until the leaf has been refined and re-verified.`

## Non-requirement edge cases

- **TDD flow (test-first).** An alternative would mandate that coders write tests before implementing each phase. Rejected per D21 and Kiro's spec-anchored-without-TDD discipline; also rejected because the project's "prefer smoke tests over unit tests" rule would make mandatory pre-implementation tests thrash against the tester-after-commit discipline. Flagged non-requirement to document the rejection.
- **Unit-test-first verification.** An alternative would default to unit tests for phase verification. Rejected because the project's smoke-test preference makes unit tests a special case, not the default. Flagged non-requirement because the smoke-test default is load-bearing for the test-layer discipline.
- **Tester interprets ambiguous leaves silently.** An alternative would let testers synthesize a reading of an unparseable leaf to keep execution moving. Rejected because it hides the convergence gap and produces unreliable verification. Flagged non-requirement because the "cannot mechanically parse" escape valve is load-bearing for spec quality.
