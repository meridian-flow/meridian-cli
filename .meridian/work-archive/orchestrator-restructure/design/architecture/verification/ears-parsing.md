# A03.3: EARS per-pattern parsing

## Summary

Testers turn EARS statements into executable tests by applying a per-pattern parsing rule that maps the five EARS patterns (Ubiquitous, State-driven, Event-driven, Optional-feature, Complex) onto a test triple: trigger (setup), precondition (fixture), and response (assertion). When a pattern clause is absent, the tester synthesizes the missing role from the system's default running state or from sibling leaves. When neither works, the tester reports the statement as `cannot mechanically parse — requires design clarification` and the statement routes back to design-orch. This leaf captures the parsing rule as a reference the tester agents load via the verification contract.

## Realizes

- `../../spec/root-invariants.md` — S00.u6 (EARS shape mandated with stable IDs).
- `../../spec/design-production/spec-tree.md` — S02.1.u2 (EARS is the notation for every spec leaf), S02.1.e2 (statement-letter encodes pattern).
- `../../spec/execution-cycle/spec-leaf-verification.md` — S05.2.e1 (tester parses EARS per this rule), S05.2.e2 (trigger/precondition/response mapping), S05.2.e3 (unparseable escape valve), S05.2.c1 (unparseable routes back to design-orch).

## Current state

- v2 lacks a mechanical EARS parsing rule. Tester prompts rely on ad-hoc judgment to turn a scenario description into a test, and edge cases between Ubiquitous and Optional-feature patterns often get skipped entirely because the tester cannot find a clause to parse.
- The per-pattern rule lived as narrative guidance inside `design/design-orchestrator.md` §"Per-pattern parsing guide" in the v2 flat design package — one of the docs absorbed by this subtree under R01.

## Target state

### Five EARS patterns with stable ID letters

Each EARS pattern has a letter that appears in the statement ID. The ID format is `S<subsystem>.<section>.<letter><number>` (spec leaves) or `A<subsystem>.<section>.<letter><number>` (architecture leaves where applicable). The letter encodes the pattern so any tester reading the ID knows which parsing row to apply:

| Letter | Pattern | Template |
|---|---|---|
| `u` | Ubiquitous | `The <system> shall <response>` |
| `s` | State-driven | `While <precondition>, the <system> shall <response>` |
| `e` | Event-driven | `When <trigger>, the <system> shall <response>` |
| `w` | Optional-feature (Where) | `Where <feature>, the <system> shall <response>` |
| `c` | Complex | `While <precondition>, when <trigger>, the <system> shall <response>` |

### Per-pattern parsing table

Testers apply this table mechanically. Each row says how to derive the test triple (trigger, precondition, response) from the EARS text.

| Pattern | Trigger (test setup) | Precondition (fixture) | Response (assertion) |
|---|---|---|---|
| **Ubiquitous** (`The <system> shall <response>`) | The act of bringing the system up in its normal operating mode. No external event is required; the tester runs the system and observes whether the response holds as an invariant. | The system is in its default running state — whatever "the system runs" means for the subsystem under test (`spawn runner is live`, `harness is initialized`). | The observable outcome named in the `shall` clause. For continuous invariants ("shall emit one heartbeat every 30s") the assertion is a sampled observation over a bounded window. |
| **State-driven** (`While <precondition>, the <system> shall <response>`) | The act of entering the named state (or, for invariants that hold across the whole state, running any legal operation while the state is active). For negative assertions ("shall not"), the trigger is any operation that would produce the forbidden response if the rule were violated — the test exercises the rule by attempting the forbidden path. | The `while` clause, verbatim, becomes the fixture the test sets up before the trigger fires. | The `shall`/`shall not` clause. |
| **Event-driven** (`When <trigger>, the <system> shall <response>`) | The `when` clause, verbatim. This is the most direct mapping. | Implicit preconditions named in surrounding prose, or "system in default running state" if none are named. | The `shall` clause. |
| **Optional-feature** (`Where <feature>, the <system> shall <response>`) | Whatever operation exercises the feature once it is enabled (typically stated in surrounding prose or in a sibling event-driven leaf). If the leaf describes a passive effect, the trigger is "run any legal operation that would produce the response if the feature were active." | The `where` clause becomes a fixture: the feature flag, config, or capability must be enabled before the trigger fires. Testing the feature with the flag **off** is a complementary negative test. | The `shall` clause. |
| **Complex** (`While <precondition>, when <trigger>, the <system> shall <response>`) | The `when` clause. | The `while` clause. | The `shall` clause. This pattern is the full triple in one sentence. |

**Rule the table encodes:** when a clause is present, it maps directly; when a clause is absent, the tester synthesizes the missing role from the system's default running state (for Ubiquitous, no external event needed) or from the sibling leaves that name the triggering operation.

### Escape valve — "cannot mechanically parse"

If neither the explicit clause nor the synthesized default works, the tester reports the statement as `cannot mechanically parse — requires design clarification` per S05.2.e3. This is the deliberate escape valve that keeps unparseable statements visible instead of letting the tester paper over ambiguity.

When the escape valve fires:

1. The tester writes the outcome against the EARS statement ID in its report as `unparseable`.
2. Execution impl-orch updates `plan/leaf-ownership.md` row status to `blocked` with the tester report as evidence.
3. Execution impl-orch routes the falsification to design-orch via the spec-drift channel (S05.3.s3) so the leaf is clarified in a scoped revision cycle.
4. The phase pauses until the leaf is clarified; no other parts of the phase block on unrelated statements, so coder work on still-parseable statements can continue in parallel.

The escape valve is not a workaround for lazy parsing. It is a convergence signal: if a leaf surfaces `unparseable` reports repeatedly, the leaf is structurally broken and the spec author needs to rewrite it. A tester that cannot parse an EARS statement has discovered that the design does not know when or under what state the response fires, and that gap has to be closed at the design altitude, not patched at the tester altitude.

### EARS does not imply TDD

The parsing rule turns EARS statements into tests that testers run *after* the phase code lands. Coders do not write tests before implementing — Kiro uses EARS without TDD, and v3 follows Kiro. Pre-commit TDD cycles are explicitly out of scope for the verification contract (S05.2.s3). Smoke tests are the default verification lane because the project rule "prefer smoke tests over unit tests" makes them the most load-bearing coverage surface (S05.2.u2).

## Interfaces

- **Tester skill body** — `meridian-dev-workflow/skills/smoke-test/SKILL.md` and `skills/unit-test/SKILL.md` carry this parsing rule in their body so every tester has it loaded on spawn.
- **Spec-leaf ID letter** — every spec-leaf EARS statement ID carries the pattern letter, so testers know which row of the parsing table to apply without reading the statement text.
- **Tester report outcome** — `verified` / `falsified` / `unparseable` / `blocked`, cited per EARS statement ID.

## Dependencies

- `./orchestrator-verification-contract.md` — the shared contract that mandates EARS as the acceptance notation.
- `./leaf-ownership-and-tester-flow.md` — the ledger where parsed outcomes land.

## Open questions

None at the architecture level.
