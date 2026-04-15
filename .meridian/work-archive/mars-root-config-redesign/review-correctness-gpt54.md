**Findings**

1. Request changes: non-default managed roots are no longer recoverable once the generated directory is absent. [`init.rs:100`](/home/jimyao/gitrepos/mars-agents/src/cli/init.rs#L100) still lets callers choose any target, but that choice is never persisted in root config. Later, [`mod.rs:216`](/home/jimyao/gitrepos/mars-agents/src/cli/mod.rs#L216) re-derives `managed_root` purely from whatever generated directories currently exist and falls back to `.agents` at [`mod.rs:250`](/home/jimyao/gitrepos/mars-agents/src/cli/mod.rs#L250). That means `mars init custom-root`, followed by a clean checkout or deleting generated output, will silently switch subsequent `add/sync/link/doctor` calls to `/project/.agents`. It also makes `mars init` non-idempotent for custom targets: a later plain `mars init` creates `.agents` at [`init.rs:104`](/home/jimyao/gitrepos/mars-agents/src/cli/init.rs#L104), and discovery will then prefer that over the original custom root. Either persist the managed-root name in root config, or remove custom-target support.

2. Medium: `mars.local.toml` moved to project root, but `mars init` no longer makes it gitignored. The config type still documents local overrides as gitignored at [`config/mod.rs:87`](/home/jimyao/gitrepos/mars-agents/src/config/mod.rs#L87), and sync now writes them to the repo root at [`sync/mod.rs:227`](/home/jimyao/gitrepos/mars-agents/src/sync/mod.rs#L227). But initialization only updates the managed directory’s `.gitignore` for `.mars/` at [`init.rs:109`](/home/jimyao/gitrepos/mars-agents/src/cli/init.rs#L109) and [`init.rs:149`](/home/jimyao/gitrepos/mars-agents/src/cli/init.rs#L149). The first `mars override` now creates a machine-local file in tracked repo state. Add a root-level `.gitignore` entry for `mars.local.toml` or stop treating it as local-only state.

**Assessment**

Most of the direct config/lock callsites were correctly switched from `managed_root` to `project_root`, and the package-only manifest handling looks aligned with the design. The blocking issue is the missing persistence for custom managed roots.

`meridian report create --stdin` is unavailable in this environment (`Unknown command: report`), so the fallback report is inline here:

## What was done
Reviewed `/tmp/mars-root-config-diff.patch` against `/home/jimyao/gitrepos/mars-agents` with a correctness focus on root discovery, project-root vs managed-root usage, and moved config/lock behavior.

## Key decisions made
- Treated repo-root `mars.toml`/`mars.lock` as the intended source of truth.
- Prioritized end-to-end path behavior over compatibility or style concerns.

## Files inspected
- [`src/cli/mod.rs`](/home/jimyao/gitrepos/mars-agents/src/cli/mod.rs)
- [`src/cli/init.rs`](/home/jimyao/gitrepos/mars-agents/src/cli/init.rs)
- [`src/config/mod.rs`](/home/jimyao/gitrepos/mars-agents/src/config/mod.rs)
- [`src/sync/mod.rs`](/home/jimyao/gitrepos/mars-agents/src/sync/mod.rs)
- [`src/cli/link.rs`](/home/jimyao/gitrepos/mars-agents/src/cli/link.rs)
- [`src/cli/doctor.rs`](/home/jimyao/gitrepos/mars-agents/src/cli/doctor.rs)
- [`src/cli/repair.rs`](/home/jimyao/gitrepos/mars-agents/src/cli/repair.rs)
- [`tests/integration/mod.rs`](/home/jimyao/gitrepos/mars-agents/tests/integration/mod.rs)

## Verification
- Static callsite trace only.
- Did not run tests or builds because the workspace is read-only here.

## Verdict
Request changes.