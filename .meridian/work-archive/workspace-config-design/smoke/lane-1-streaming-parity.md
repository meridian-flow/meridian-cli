## Verdict
clean

## Harness coverage
- claude: exercised
- codex: exercised
- opencode: exercised

## Scenarios passed
- Setup: `uv run meridian --help >/dev/null && echo 'PASS: meridian CLI is runnable'` -> `PASS: meridian CLI is runnable`
- SAP-1 dry-run projection: `uv run meridian --json spawn -m claude-sonnet-4-6 -a coder -s verification --effort xhigh --dry-run -p "Claude parity smoke" >/tmp/meridian-parity-claude-dry.json && uv run python - <<'PY' ...` -> `PASS: Claude subprocess projection includes model/effort/agent/skills`
- SAP-1 streaming parity: `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude_cross_transport_parity_on_semantic_fields -q` -> `.` / `[100%]`
- SAP-2 dry-run projection: `uv run meridian --json spawn -m gpt-5.3-codex --effort high --approval confirm --dry-run -p "Codex parity smoke" >/tmp/meridian-parity-codex-dry.json && uv run python - <<'PY' ...` -> `PASS: Codex subprocess projection includes model + effort`
- SAP-2 streaming parity: `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k codex_cross_transport_parity_on_semantic_fields -q` -> `.` / `[100%]`
- SAP-2 approval behavior: `uv run pytest-llm tests/harness/test_codex_ws.py -k "auto_accepts_command_execution_approval_requests or rejects_approval_requests_in_confirm_mode" -q` -> `..` / `[100%]`
- SAP-3 dry-run projection: `uv run meridian --json spawn -m opencode-gpt-5.3-codex --effort medium --dry-run -p "OpenCode parity smoke" >/tmp/meridian-parity-opencode-dry.json && uv run python - <<'PY' ...` -> `PASS: OpenCode subprocess projection includes normalized model + effort variant`
- SAP-3 streaming parity: `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k opencode_cross_transport_parity_with_known_streaming_asymmetries -q` -> `.` / `[100%]`
- Fix A 60 KiB codex spot-check: `PROMPT="$(uv run python - <<'PY' ; print('A' * (60 * 1024)) ; PY )"; uv run meridian --json spawn -a coder --harness codex --dry-run -p "$PROMPT" >/tmp/meridian-codex-60k.json && uv run python - <<'PY' ...` -> `PASS: codex 60KiB dry-run preserved full prompt tail (61440 bytes input; 75088 bytes composed)` and no `warning/promptTruncated` marker in the dry-run JSON
- Fix A >10 MiB guard: `uv run python - <<'PY' ... validate_prompt_size(...) ... PY` -> `PASS: codex: initial prompt is 10485761 bytes, exceeds limit of 10485760 bytes`

## Scenarios failed
- none

## Surprises
- The 60 KiB codex dry-run emitted two stderr warnings before the PASS line:
  - `Codex does not support disallowed-tools resolver flags; dropping resolver-emitted --disallowedTools tokens`
  - `Codex does not support allowed-tools resolver flags; dropping resolver-emitted --allowedTools tokens`
- Those warnings did not affect the dry-run JSON result or truncate the prompt, so I treated them as non-blocking noise rather than a lane regression.
- This lane prompt did not provide claimed EARS statement IDs, so coverage was executed against the named smoke scenarios (`SAP-1` through `SAP-3`) and the two Fix A spot-checks directly.
