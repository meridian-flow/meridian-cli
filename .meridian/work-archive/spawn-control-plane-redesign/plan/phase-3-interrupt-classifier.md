# Phase 3 — Interrupt Classifier

## Scope and boundaries

This phase makes interrupt non-fatal at the runner layer. It is narrowly
scoped to event classification and follow-up turn viability; it does not
touch cancel semantics or HTTP endpoint shape.

## Touched files/modules

- `src/meridian/lib/launch/streaming_runner.py`

## Claimed EARS statement IDs

- `INT-001`
- `INT-002`
- `INT-003`
- `INT-004`

## Touched refactor IDs

- `R-04`

## Dependencies

- Phase 1 `foundation-primitives`

## Tester lanes

- `@verifier`: run focused runner tests and static checks.
- `@unit-tester`: cover `_terminal_event_outcome` for interrupted and
  completed turn payloads.
- `@smoke-tester`: verify `spawn inject --interrupt` keeps the spawn
  running and a follow-up inject succeeds on the same session.

## Exit criteria

- `_terminal_event_outcome` never treats per-turn interrupt/completion
  payloads as spawn-terminal.
- Interrupt while idle returns the noop shape expected by the spec.
- A post-interrupt follow-up turn works end-to-end against a live harness.
