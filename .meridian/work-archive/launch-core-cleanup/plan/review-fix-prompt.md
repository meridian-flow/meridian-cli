# Review Fix Loop

Address the open reviewer findings from `p2015`, `p2016`, and `p2017`.

You are not alone in repo. Do not revert others' work. Keep scope tight to the review findings and directly-required tests.

Must fix:

1. Primary launch still composes outside factory.
- `plan.py` / `process.py` must stop acting as a second composition system.
- `build_launch_argv()` must not retain a hidden composition fallback when `projected_spec` is omitted if that undermines factory ownership.
- Reviewer references: `p2016`.

2. `autocompact` still has split ownership and weak typing.
- Execution should consume `request.autocompact` directly, not shadow metadata.
- Reject bool-shaped input for `SpawnRequest.autocompact`; update tests to use real integer percentage values.
- Reviewer references: `p2015`.

3. Harness extension documentation is incomplete.
- Either make `HARNESS_EXTENSION_TOUCHPOINTS` fully authoritative, including projection/extractor/bootstrap seams, or move to a less overclaiming inline documentation approach.
- Reviewer references: `p2015`, `p2017`.

4. Dry-run preview command leaks fake artifact paths.
- `spawn --dry-run` should not preview a bogus `.meridian/spawns/preview/...` output path as if real.
- Use an obvious placeholder or omit artifact path from preview if that matches harness semantics better.
- Reviewer reference: `p2017`.

Constraints:
- Preserve green verifier bar: `ruff`, `pyright`, `pytest`.
- Do not broaden into unrelated launch redesign.
- If a reviewer finding is rejected, log concrete reasoning in work artifacts; do not silently leave it unresolved.

Report back:
- what changed
- files changed
- exact tests/checks run
- whether each reviewer finding is fixed
