NOTE: `meridian report create --stdin` failed with `error: Unknown command: report` (meridian `0.0.8`). Providing the report markdown inline for fallback persistence.

# Review: move mars consumer config to project root

## Summary
Reviewed `/tmp/mars-root-config-diff.patch` against `mars-agents` (`/home/jimyao/gitrepos/mars-agents`). The refactor largely achieves the intended separation:

- Consumer config now loads/saves from the **project root** (`mars.toml`, `mars.lock`, `mars.local.toml`).
- Managed output and mars internal state remain under the **managed dir** (default `.agents/`), with sync lock + cache at `.agents/.mars/` (`src/sync/mod.rs:101`, `src/sync/mod.rs:125`).
- Root discovery walks up looking for a **consumer** `mars.toml` and stops at the first `.git` boundary (`src/cli/mod.rs:274`).

There are still a few edge-case bugs and completeness gaps (notably around `mars.local.toml` gitignore, init/link robustness, and missing `.git`-boundary regression tests).

## Key Decisions (captured)
- Consumer-vs-manifest distinction: a `mars.toml` is treated as **consumer config** only if it contains `[sources]` or the init marker `# created by mars init` (`src/cli/mod.rs:253`).
- Config/lock/local live at project root; sync lock + cache live in managed dir (`src/sync/mod.rs:101`, `src/sync/mod.rs:125`).
- Discovery does not cross the nearest `.git` boundary (repo/submodule root) (`src/cli/mod.rs:303`).

## Goal/Question Check
- **Any code paths still assuming config in `managed_root`?** I didn’t find remaining call sites loading/saving config/lock/local from `managed_root`; CLI + sync consistently use `project_root` for config/lock/local and `managed_root` for installed paths/caches.
- **`mars.local.toml`: did it move too?** Yes (config loads/saves local overrides from `project_root`). But see *Blocking finding #1* re: gitignore.
- **Cache + sync lock locations consistent?** Yes: both are under `managed_root/.mars/` (`src/sync/mod.rs:106`, `src/sync/mod.rs:133`, `src/sync/mod.rs:136`). However, `mars link` currently assumes `managed_root/.mars` exists before acquiring the lock (see finding #4).
- **Tests cover package-only manifest case?** Yes: `package_manifest_without_sources_is_not_consumer` (`src/cli/mod.rs:337`) and init upgrade test (`src/cli/init.rs:217`).
- **Tests cover no-`.git`-root case?** Not explicitly; behavior is implicitly exercised via tempdirs, but there’s no targeted assertion about the “walk to /” behavior or messaging.
- **Tests cover nested submodules / `.git` boundary?** Not currently; needs an integration test that proves mars won’t pick up an outer repo’s config when invoked inside a submodule/nested repo.

## Findings

### Blocking / High Severity
1) `mars.local.toml` moved to project root but `mars init` does not ensure it’s gitignored.
- Evidence: `LocalConfig` explicitly documents “Gitignored” (`src/config/mod.rs:87`), but init only writes `.agents/.gitignore` for `.mars/` (`src/cli/init.rs:148`) and does not touch `<project>/.gitignore`.
- Impact: very easy to accidentally commit developer-local overrides now that the file is at the repo root.
- Fix: during `mars init`, add `mars.local.toml` to `<project-root>/.gitignore` (create if missing), or otherwise implement a clear “gitignore local overrides” flow.

2) `MarsContext::from_roots()` does not canonicalize `project_root`, causing false “managed root outside project” errors in common cases.
- Where: `src/cli/mod.rs:67` (canonicalizes `managed_root` only).
- Trigger: `mars init` calls `MarsContext::from_roots(project_root.clone(), managed_root.clone())` when `--link` is used (`src/cli/init.rs:124`).
- Impact:
  - `mars init --root <RELATIVE_PATH> --link ...` likely fails because `project_root` stays relative while `managed_root` canonicalizes to an absolute path, making `starts_with()` fail.
  - Similar failure when `project_root` contains symlinks.
- Fix: canonicalize `project_root` inside `from_roots()` the same way `MarsContext::new()` does.

3) `mars init --root .agents` (old mental model) becomes a dangerous footgun that creates nested `.agents/.agents`.
- Where: `src/cli/init.rs:96` treats `--root` as **project root**, then appends default target `.agents` (`src/cli/init.rs:102`).
- Impact: silently scaffolds into an unexpected tree and can strand config/lock in the wrong place.
- Fix: in `init.rs`, reject `--root` paths that look like a managed output dir (basename in `{.agents,.claude,.cursor}` or equals `TARGET`), with a clear error suggesting `--root <project-root>`.

### Medium Severity
4) `mars link` acquires `.agents/.mars/sync.lock` without ensuring `.agents/.mars` exists, which becomes more likely now that `.agents/` is “purely generated output”.
- Where: `src/cli/link.rs:110` acquires lock at `ctx.managed_root/.mars/sync.lock` before creating any `.mars` directory.
- Impact: if a user deletes `.agents/` (reasonable under the new model) and then runs `mars link`, it can fail before it gets a chance to recreate structure.
- Fix: `create_dir_all(ctx.managed_root.join(\".mars\"))` before lock acquisition (similar to `sync::execute` creating `.mars/cache` pre-lock at `src/sync/mod.rs:133`).

5) `mars init` defaults `project_root` to the current working directory, not the git root; this undermines “repo-root config” expectations and interacts badly with `.git`-bounded discovery.
- Where: `src/cli/init.rs:96`.
- Impact: running `mars init` from a subdirectory creates `mars.toml` there; later running mars from a different subdir won’t find it because discovery only checks ancestors up to the `.git` boundary (`src/cli/mod.rs:297`–`src/cli/mod.rs:306`).
- Fix: consider defaulting `project_root` to the nearest git root when `--root` is omitted (or at least warn when `.git` is in an ancestor but not in `cwd`).

6) README is inconsistent with the new layout and `--root` semantics.
- Where: `README.md:101` claims `--root` is an “explicit managed root”; `README.md:104` shows `mars.toml`/`mars.lock`/`mars.local.toml` under `.agents/`.
- Impact: docs currently direct users into the `init --root .agents` footgun and contradict actual behavior.
- Fix: update the layout diagram and `--root` description to reflect:
  - `<project-root>/mars.toml`, `<project-root>/mars.lock`, `<project-root>/mars.local.toml`
  - `<project-root>/.agents/.mars/`, `.agents/agents/`, `.agents/skills/`.

7) Missing regression tests for the `.git` boundary requirement (nested repo/submodule).
- Where: logic in `src/cli/mod.rs:303`.
- Suggested integration tests (use `current_dir()` like existing `root_discovery_from_subdir` in `tests/integration/mod.rs:528`):
  - Outer dir has `.git/` + consumer `mars.toml`. Inner dir has its own `.git/` but no consumer config. Running `mars list` from inner should fail (must not pick outer config).
  - Inner has consumer config too; ensure inner config is selected.

### Low Severity
8) Error messaging says “up to repository root” even when there is no `.git` boundary (walks to `/`).
- Where: `src/cli/mod.rs:314`.
- Not functionally wrong, but slightly misleading in non-git directories.

## Verification
- No automated tests executed in this environment.
- Review based on static inspection of the patch + current `mars-agents` tree.

## Verdict
Request changes.

Blocking issues: `mars.local.toml` gitignore gap (`src/config/mod.rs:87` vs `src/cli/init.rs:148`), `from_roots()` canonicalization bug (`src/cli/mod.rs:67`), and the `init --root .agents` footgun (`src/cli/init.rs:96`). Docs and missing `.git`-boundary tests should be addressed to make the refactor complete and resistant to the edge cases you called out (package-only manifests, `.git` boundaries, and generated `.agents/` deletion).