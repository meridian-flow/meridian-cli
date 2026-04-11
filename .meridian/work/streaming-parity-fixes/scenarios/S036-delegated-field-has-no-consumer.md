# S036: Delegated field has no consumer

- **Source:** design/edge-cases.md E36 + design/transport-projections.md completeness-guard contract
- **Added by:** @design-orchestrator (revision pass 1)
- **Tester:** @unit-tester
- **Status:** pending

## Given
A field is marked delegated in one part of a transport path but is not present in any consumer `_ACCOUNTED_FIELDS` union.

## When
Transport-wide accounting guard executes.

## Then
- Import-time `ImportError` identifies unaccounted delegated field.
- Silent delegated-field drops are prevented.

## Verification
- Synthetic test where delegated field is removed from all consumer sets.
- Assert guard failure with field name in message.

## Result (filled by tester)
_pending_
