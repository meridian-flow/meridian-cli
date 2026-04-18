# Prior Round Feedback

A previous design round for this work item was rejected by a 5-reviewer fanout (alignment/opus, correctness/gpt-5.4, UX/gpt-5.2, refactor/gpt-5.4, prior-art/codex). Verdict unanimous: **revise**. The rejected design was removed; `requirements.md` is unchanged and authoritative. This file consolidates what the reviewers flagged so you can start fresh without reintroducing known bugs.

Full reviewer reports are in `.meridian/spawns/p1705..p1710/report.md` and accessible via `meridian spawn show`.

## Factual corrections to the prior design's assumptions

1. **Codex CLI has `codex exec --add-dir`.** The prior design's Feasibility Probe 4 claimed Codex has no directory-inclusion mechanism. This is wrong. `codex exec --add-dir DIR` exists as "additional directories writable alongside the primary workspace" (see `openai/codex/codex-rs/exec/src/cli.rs`). Gotcha: `--add-dir` is ignored when the effective sandbox mode is read-only — codex emits an explicit warning in that case. Re-run this probe against the installed codex version before relying on any mechanism claim.

2. **Mars owns model-alias resolution.** The prior design added `OWN-1.5` / `RF-4` to "migrate `.meridian/models.toml` to repo root." But Meridian has no central `.meridian/models.toml` loader — model aliases are resolved via `mars models list/resolve` + `.mars/models-merged.json`. A migration of that file does not touch Meridian's read path. Either drop this from the design or first write a separate ownership decision (does Meridian grow its own root `models.toml`? how does it compose with Mars?) before attempting to migrate anything.

3. **Meridian config commands bypass the loader's resolver.** `meridian config show/get/set/reset/init` do not go through `_resolve_project_toml()` — they operate on a single `_config_path` in `ops/config.py`. Any design that migrates the canonical config location must redesign the config command family end-to-end, not just the resolver. Conflict rules for divergent-file cases (legacy and root both exist with different content) must be explicit: what counts as byte-equal vs. divergent, who wins, abort vs. overwrite.

## Structural flaws in the prior design

4. **Dedupe ordering inverted last-wins semantics.** The prior spec asserted workspace dirs go *before* user passthrough so passthrough wins "last-wins," but `dedupe_nonempty` preserves the first occurrence. Result: workspace dirs win, user passthrough gets silently dropped. Pin dedupe semantics precisely or restructure the merge.

5. **`context_directories() → list[Path]` is a premature and fragile abstraction.** Only one real consumer today (Claude preflight). The flat-list shape loses the ordering relationships the spec depends on. External evidence matches: harness-agnostic context-root abstractions survive a second consumer only with structured entries — `{path, enabled, access_mode, source, order, tags}`. Keep v1 minimal in user-facing schema, but shape the internal model to grow.

6. **Silent harness no-op is a footgun.** The prior spec said unsupported harnesses silently skip workspace roots, but codex is the *default* harness. Even after correction #1, some harnesses or sandbox modes will still be unsupported. `config show` and `doctor` must explicitly report per-harness applicability (`claude: active`, `codex: active`, `codex (read-only sandbox): ignored`, etc.).

7. **RF-1 was drastically under-scoped.** "One function change in `settings.py`" does not cover the true blast radius of moving committed config: `ops/config.py`, `ops/runtime.py`, `main.py`, smoke tests, bootstrap, CLI help text, command-description strings all hard-reference `.meridian/config.toml` or the single `_config_path`. Any migration must be planned as a coordinated read/write/bootstrap/CLI/test change, not a resolver tweak.

8. **Root-file policy doesn't belong in `state/paths.py`.** `StatePaths` is `.meridian`-scoped. Pushing `root_config_path`, `workspace.toml` discovery, `MERIDIAN_WORKSPACE` env override handling, and root `.gitignore` mutation into that module mixes repo-policy concerns with state-root concerns. Consider a separate `ProjectPaths`/`RepoFiles` abstraction.

## UX / progressive-disclosure issues

9. **Auto-creating `meridian.toml` on first invocation violates the "invisible by default" promise.** The prior `CFG-1.5` said new projects create `meridian.toml` at root on first `meridian` invocation. That's a surprise untracked file in `git status` for users who never opted in. File creation must be opt-in via `config init`/`config migrate`/`workspace init`. Advisory messages are fine; silent file creation is not.

10. **"Fatal on parse error" is too blunt for inspection commands.** The prior architecture said invalid `workspace.toml` causes fatal exit. That would mean a typo in `workspace.toml` crashes `meridian spawn ls` and other unrelated commands. Scope fatal behavior to commands that *need* workspace-derived directories (spawns, `workspace *` commands). Inspection commands should surface `workspace.status = invalid` and continue.

11. **Warn-on-every-missing-path becomes spawn noise.** Multi-root workspaces routinely include sometimes-present roots (alternate checkouts, VPN mounts). Warning on every spawn trains users to ignore warnings. Surface in `doctor`/`config show`; for spawns, either warn once per session or keep at debug level.

12. **Unknown-keys "debug only" hides config typos.** `workspace.toml` exists to affect harness launches. Silent misconfig is expensive. Preserve unknown keys (forward-compatibility) but surface them in `doctor`/`config show` as warnings.

13. **`workspace init --from mars.toml` risks broken-by-default state.** Most mars deps won't have reliable local paths without auto-detection (a non-goal). Default init should produce a minimal file with commented examples, or emit entries as `enabled=false` pending user edit.

14. **`config show` needs a crisp minimal answer set.** Adding a workspace section risks cluttering an already grep-friendly command. Propose explicit JSON shape: `workspace: {status: absent|active|invalid, path, roots: {count, enabled, missing}, harness_support: {claude: ..., codex: ...}}`. Text output stays flat.

## Naming and convention issues

15. **Gitignored `workspace.toml` violates monorepo convention.** Across pnpm, npm, Yarn, Rush, Nx, Bazel, Go, Cargo, Bun, Deno — workspace files are committed team topology. A gitignored file named `workspace.toml` reads as a team file but behaves as a personal file. Prior art (`.env.local`, `mars.local.toml`, `compose.override.yaml`) consistently uses a `.local` or `.override` suffix for local overrides. Rename to `workspace.local.toml` (or equivalent) so the filename encodes locality.

16. **`[context-roots]` naming is accurate but jargon-heavy.** `[include-dirs]` or `[extra-dirs]` may be clearer. Low priority.

## Migration policy gaps

17. **No sunset trigger for the `.meridian/config.toml` dual-read fallback.** Prior art (ESLint flat-config rollout, Bazel WORKSPACE → MODULE.bazel) shows that migrations without an explicit end-state linger for years. Design a staged deprecation: Phase A dual-read + advisory, Phase B warning + remediation command, Phase C fallback removed. Pin the transition triggers (version bumps, time, or explicit opt-in).

18. **"Emit a one-time advisory" is not implementable as specified.** "One-time" could mean per-process, per-invocation, or per-repo. Each requires different state. Pick one explicitly. Per-invocation is simplest and requires no new local suppression state.

19. **`meridian config migrate` idempotency underspecified for divergent files.** If both `.meridian/config.toml` and `meridian.toml` exist with different content, naive "copy legacy to root" destroys root edits; naive "root wins, delete legacy" strands legacy edits. Specify: byte-equal → delete legacy; legacy-only → move; root-only → no-op; divergent → abort with explicit "pick a winner" error.

## What should carry forward from the prior design

The *framing* was sound — don't throw this out:

- **Boundary-first reframing.** The core insight that committed project policy belongs at repo root (alongside `mars.toml`) and `.meridian/` should trend fully local/runtime/gitignored is correct and endorsed by every reviewer.
- **Mars / Meridian separability.** Mars-owned state and config never live under `.meridian/`; Meridian-owned state and config never live under `.mars/`.
- **`org/repo` canonical identifiers** for AGENTS.md and workspace config.
- **Workspace orthogonal to MeridianConfig precedence.** Workspace answers "which directories participate?" — a topology question, not an operational-config question.
- **Workspace is purely topology, no `[settings]` table.** Settings belong in `meridian.toml`, not `workspace.toml`. Avoid scope creep.
- **Single-repo users experience zero new complexity.** Progressive disclosure: no workspace file → no workspace behavior, no warnings, no prompts.
- **TOML format** for all config.
- **Non-goals held firm** were correctly scoped: no per-harness subsets in v1, no shareable team workspace in v1, no auto-detection, no cloud-backed work/fs, no replacement of `mars.local.toml`.

## Probes to re-run before the next design round

- Verify `codex exec --add-dir` behavior against the installed codex version. Document the read-only-sandbox nullification warning explicitly.
- Enumerate every call site that references `.meridian/config.toml` or `_config_path` (grep `_config_path`, `.meridian/config.toml`, `state/paths.py::config_path`). The full list should drive RF-1 scope.
- Verify whether `.meridian/models.toml` is read anywhere in the Meridian codebase or whether it's strictly a Mars input. If Meridian reads it anywhere, document those call sites; otherwise remove models migration from this design's scope entirely.
- Re-check `dedupe_nonempty` semantics (first-seen vs. last-seen) and whether the existing call sites in `claude_preflight.py` rely on first-seen.
