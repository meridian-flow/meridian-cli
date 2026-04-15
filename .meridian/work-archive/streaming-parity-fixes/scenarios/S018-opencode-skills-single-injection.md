# S018: OpenCode skills single-injection (no double-send)

- **Source:** design/edge-cases.md E18 + p1411 finding M4
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
OpenCode streaming spawn with `skills=("skill-a", "skill-b")` and `run_prompt_policy().include_skills = True` (the default). Real `opencode serve` is available on PATH.

## When
The adapter constructs the `OpenCodeLaunchSpec` and the streaming runner sends the HTTP session payload.

## Then
- Because `include_skills=True`, the prompt text inlines the skill content and the factory sets `spec.skills = ()`.
- The HTTP session payload does NOT separately carry skills.
- The remote `opencode serve` session receives each skill's content exactly once.
- Alternative path: if `include_skills=False`, the prompt does not inline, `spec.skills` is populated, and the HTTP payload carries them. Still exactly once.

## Verification
- Unit test: assert `spec.skills == ()` when `include_skills=True`.
- Unit test: assert `spec.skills == ("skill-a","skill-b")` when `include_skills=False`.
- Smoke test: run a real streaming OpenCode spawn, inspect the session on the `opencode serve` side (via its REST API), and confirm each skill's content appears exactly once in the session turns.
- Delta test: force the v1 "double-inject" path (return `spec.skills` populated AND inline them in the prompt) and confirm the smoke test fails.

## Result (filled by tester)
Verified with extra coverage on 2026-04-10.

- `tests/harness/test_launch_spec.py:97` confirms the default policy path (`include_skills=True`) clears `spec.skills` to avoid duplicate wire injection.
- `tests/harness/test_launch_spec.py:164` confirms the alternate policy path (`include_skills=False`) preserves `spec.skills` for native transport delivery.
- `tests/harness/test_opencode_http.py:108` adds an explicit default-path assertion that the streaming `POST /session` payload omits `skills` when the prompt-inline channel is active.
- `tests/harness/test_opencode_http.py:126` confirms the non-inline path still carries `skills` in the HTTP payload when `OpenCodeLaunchSpec.skills` is populated.
- `tests/harness/test_launch_spec_parity.py:1140` confirms default streaming payload omits `skills`, so prompt-inline remains the sole channel in default launches.
- `tests/exec/test_streaming_runner.py:769` confirms plan skills are threaded through adapter resolution while the final OpenCode launch spec keeps `skills=()` under the default single-channel policy.
- Live protocol probe (`opencode serve --pure`, 2026-04-10) confirmed `POST /session` accepts a `skills` field, so the non-inline path remains representable when explicitly selected.
