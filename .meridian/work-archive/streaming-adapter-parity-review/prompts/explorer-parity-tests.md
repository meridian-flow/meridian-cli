# Explorer: Parity tests — do they actually exercise both paths?

You are an explorer. Do not make code changes. Report facts only.

## Task

Read `tests/harness/test_launch_spec.py` and `tests/harness/test_launch_spec_parity.py`. Determine whether the parity tests actually exercise both the subprocess path and the streaming path against the same `ResolvedLaunchSpec`, or whether they only test one side.

## Specific questions to answer

1. **Spec construction coverage.** How many test cases construct a `ResolvedLaunchSpec` (directly or via `adapter.resolve_launch_spec()`)? For each harness (Claude, Codex, OpenCode), list the scenarios covered: basic, with effort, with skills/agents, with permission modes, with resume/fork, with OpenCode model prefix, with Codex sandbox/approval, etc.

2. **Dual-path assertion.** For a given spec, do the tests assert that the subprocess projection (`build_command()` output) and the streaming projection (connection adapter's CLI args / JSON-RPC params / HTTP payload) are equivalent? Quote an example test. If they only check one projection, that is a gap — state it plainly.

3. **Claude-specific coverage.**
   - Does a test construct a spec with skills / `agents_payload` / `appended_system_prompt` and confirm both transports emit them? This is the headline bug from D1.
   - Does a test cover `--resume` + `--fork-session` on both transports (edge case 4)?

4. **Codex-specific coverage.**
   - Is there a test for the Codex `confirm`-mode approval rejection path (D14)? Where?
   - Does any test cover the sandbox / approval / effort fields reaching the JSON-RPC `newSession` request?

5. **OpenCode-specific coverage.**
   - Is there a test for the `opencode-` model prefix strip happening in the spec factory (edge case 5)?
   - Per D16, effort/fork are asymmetries on OpenCode. Do the tests acknowledge this as a known asymmetry rather than failing?

6. **Guard coverage.** Are there tests that directly verify the `_SPEC_HANDLED_FIELDS` completeness guard and any `_PROJECTED_FIELDS` guards fire when a field is missing? Or do the guards rely purely on import-time assertions?

7. **Smoke test.** Read `tests/smoke/streaming-adapter-parity.md`. Does the smoke test actually cover the child-spawn streaming case end to end, or is it a narrower check?

8. **Quantitative summary.** Count test functions, count harness coverage, call out any harness with noticeably fewer tests than the others. Note whether any tests are skipped or parameterized-off.

## Reference files
- `tests/harness/test_launch_spec.py`
- `tests/harness/test_launch_spec_parity.py`
- `tests/harness/test_claude_ws.py`
- `tests/harness/test_codex_ws.py`
- `tests/exec/test_streaming_runner.py`
- `tests/smoke/streaming-adapter-parity.md`
- `.meridian/work-archive/streaming-adapter-parity/design/parity-testing.md`
- `.meridian/work-archive/streaming-adapter-parity/decisions.md`

## Deliverable

A structured report answering questions 1–8 with quoted test examples, file paths, and line numbers. Be specific about gaps — "no coverage for X" is the most important finding.
