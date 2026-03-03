# Primary CLI Redesign Plan

Status: in progress
Date: 2026-03-03

## Execution Board

1. Slice A: Delete unused primary flags (`timeout/budget/guardrail/secret`) - done
- Commit: `ec5f806`
- Verification: `uv run meridian start --help`, explicit unknown-flag failure smoke, targeted pytest, `uv run pytest-llm`
2. Slice B: Root entry unification (`meridian` as primary entrypoint, remove `start`) - done
- Commit: `76d9678`
- Verification: `uv run meridian --help`, `uv run meridian --dry-run`, non-dry-run with mock harness, `uv run meridian start --dry-run` unknown command, targeted pytest, `uv run pytest-llm`
3. Slice C: Continue contract (`--continue <session-ref>` string, not bool) - done
- Commit: `248b97d`
- Verification: `uv run meridian --help`, `uv run meridian --json --continue <ref> --dry-run`, ambiguity/mismatch error smokes, targeted pytest, `uv run pytest-llm`
4. Slice D: Primary harness refactor (remove hardcoded Claude path) - done
- Commit: `2950a8b`
- Verification: `uv run meridian --help`, `uv run meridian --json --model <model> --harness <id> --dry-run`, incompatibility error smoke, targeted pytest, `uv run pytest-llm`
5. Slice E: Session identity + resume UX output - done
- Commit: TBD
- Verification: non-dry-run root output includes resume hint, JSON includes `session_id` and `resume_command`, continue resolution accepts session ids, targeted pytest, `uv run pytest-llm`
6. Slice F: Docs/help/smoke hardening - pending

## Current Implementation Snapshot (2026-03-03)

- `meridian start` is still the primary entrypoint.
- Root `meridian` does not launch a primary session.
- `--continue` on `start` is still stubbed.
- This plan remains active and not yet implemented.

## Goal

Make primary session UX explicit and consistent:
- `meridian` is the primary entrypoint
- `meridian start` is removed
- `--continue <session-ref>` is real (not stubbed)
- model and harness selection are predictable
- human space commands remain convenience/admin only

## Agreed Product Decisions

1. Remove `meridian start`.
2. Root command (`meridian`) launches primary harness session.
3. Continue API:
- `--continue <session-ref>` where session-ref can be Meridian session id or harness session id.
- `--continue` auto-resolves space from session.
- optional `--space` is validation/disambiguation only.
4. Space commands remain for humans:
- `meridian space list|show|close`
- `space start|resume` should be wrappers or removed later, but not introduce unique behavior.
5. Primary launch flags:
- keep: `--new`, `--space`, `--continue`, `-m/--model`, `--harness`, `-a/--agent`, `--permission`, `--unsafe`, `--autocompact`, `--dry-run`, passthrough via `--`.
- remove from primary surface now: `--budget-per-spawn-usd`, `--budget-per-space-usd`, `--guardrail`, `--secret`, `--timeout-secs`.
6. No implicit passthrough for unknown flags.
- unknown Meridian flags error.
- harness passthrough is explicit via `--`.

## Current Reality (Important)

1. Primary launch currently hardcodes Claude command construction.
2. Primary launch dataclass contains budget/guardrail/secret/timeout fields marked as future parity fields and they are not enforced in primary path.
3. Budget + guardrail enforcement exists in spawn execution path, not primary launch path.
4. `--continue` at root is currently stubbed.

## CLI Spec (Target)

Primary:
- `meridian [primary flags] [-- <harness-args...>]`

Primary flags:
- `--new`
- `--space <space-id>`
- `--continue <session-ref>`
- `-m, --model <model>`
- `--harness <claude|codex|opencode>`
- `-a, --agent <agent>`
- `--permission <tier>`
- `--unsafe`
- `--autocompact <lvl>`
- `--dry-run`

Rules:
1. Fresh mode (no `--continue`):
- default: latest active space, else create new.
- `--space`: fresh session in explicit space.
- `--new`: force new space.
2. Continue mode:
- `--continue` requires value.
- auto-resolve space by session ref.
- if `--space` provided and mismatch, hard error.
- disallow `--new`, `--model`, `--harness`, `--agent`.
3. Harness/model compatibility:
- `--harness` forces harness.
- if model conflicts with forced harness, hard error.

## Output Contract

1. Non-dry-run primary command:
- do not print full launch command.
- print session-essential fields only.
- print resume hint:
  `Resume this session with: meridian --continue <session-id>`
2. Dry-run:
- include fully resolved command.
3. JSON output:
- include `space_id`, `session_id`, `exit_code`, `resume_command`.
- include `command` only for dry-run.

## Implementation Slices

1. Root Entry Unification
- Make bare `meridian` execute primary launch flow.
- Remove `start` subcommand registration and help text.
- Keep behavior parity for current `start` defaults.

2. Flag Surface Cleanup
- Remove root primary flags that are not enforced:
  `--timeout-secs`, `--budget-per-spawn-usd`, `--budget-per-space-usd`, `--guardrail`, `--secret`.
- Add `--harness` on primary.
- Change `--continue` from bool to `str`.

3. Session-First Continue
- Implement resolver for `--continue <session-ref>`.
- Space auto-resolution from session.
- `--space` mismatch detection.
- Clear error messages for ambiguous/missing refs.

4. Primary Harness Refactor
- Replace hardcoded Claude primary command assembly with harness adapter path.
- Enforce model/harness compatibility in one place.

5. Resume UX
- Capture and persist stable Meridian session id for primary sessions.
- Emit resume command on primary exit.
- Ensure no command leakage outside dry-run.

6. Docs + Smoke Coverage
- Update CLI docs/help examples.
- Add smoke tests that exercise real CLI entry:
  `uv run meridian`
  `uv run meridian --dry-run`
  `uv run meridian --continue <session>`
  `uv run meridian --space <space>`

## Verification Checklist (Per Slice)

1. Unit tests for parser/validation and operation logic.
2. `uv run pytest-llm` passes.
3. CLI smoke run(s) with `uv run meridian` (not unit-tests only).
4. If anomalies occur, append to `plans/backlog-execution-anomalies.md`.
