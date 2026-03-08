# Migration Gotchas (Reference)

Non-actionable historical notes from the `run` → `spawn` migration. Kept for context when debugging unexpected behavior.

## Mechanical Rename Pitfalls

- `run` → `spawn` replacement touched non-domain usages (`uv run`, `subprocess.run`) and required manual restoration.
- Pre-existing dirty worktree included docs partially migrated to `spawn` while code paths still had legacy `run` naming.

## Pre-existing Docs

- `_docs/cli-spec-agent.md` and `_docs/cli-spec-human.md` existed before migration; verify against current plan instead of regenerating.

## Type Checking

- `uv run pyright` reports strict-type diagnostics not scoped to migration; full pytest suite was green in that context.

## Dogfood Session Notes

- Blocking spawn `p5` failed at timeout (`exit 3`) with empty `stderr.log` and `output.jsonl`; no extracted report. Failure diagnostics are opaque without structured failure artifacts.
- Background spawn `p4` remained `running` until manually interrupted; `output.jsonl` stayed empty, `stderr.log` captured high-volume raw harness chatter.
- Background spawn `r2` stayed running during await, creating workspace concurrency risk; required manual SIGINT.
- Spawn `r1` returned thin auto-extracted report with pseudo-paths (`scope/terminology`, `scope/problem/target`) in `files_touched`.
