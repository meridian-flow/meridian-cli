# External Validation: Workspace-Config Design

You are validating specific design decisions against external prior art, not doing a generic survey. For each question below, report what similar projects actually do, with citations (URLs or project names + file paths). Flag decisions that diverge from consensus, but only when the divergence has a real downside — unusual-but-principled choices are fine.

## Context

Meridian is a CLI that coordinates multi-agent AI harnesses (Claude Code, OpenAI Codex CLI, OpenCode). It has a local state dir `.meridian/`. This design adds:

1. Canonical committed project config at `meridian.toml` in the same directory as `.meridian/` (replacing `.meridian/config.toml`).
2. Optional local workspace topology file `workspace.local.toml` declaring extra directories to inject into harness launches as multi-root context.
3. Env override `MERIDIAN_WORKSPACE=<abs path>` that points at a workspace file anywhere on disk.
4. Per-harness projection of workspace roots: Claude/Codex get `--add-dir`, OpenCode gets `permission.external_directory` overlay via `OPENCODE_CONFIG_CONTENT` env var.

**Breaking change stance:** this project has no real users yet. Design explicitly rejects migration code — one release moves config from `.meridian/config.toml` to `meridian.toml` with no fallback reader, no `config migrate` command.

## Questions

### Q1: Is `workspace.local.toml` the right name for a gitignored local topology file?

Claim in design: across pnpm / npm / Yarn / Rush / Nx / Bazel / Go / Cargo / Bun / Deno, an unsuffixed `workspace.*` name means "committed team topology." A gitignored file under an unsuffixed name would mis-signal intent. The `.local.` suffix precedent comes from `.env.local`, `mars.local.toml`, `compose.override.yaml`-adjacent patterns.

- Verify: does every tool listed use `workspace.*` as committed team topology?
- Verify: is `.local.` suffix an established convention for gitignored local overrides, and in which projects?
- Any counter-examples where `workspace.toml` or similar is idiomatically local?
- Any stronger naming precedent we should consider (`.user.toml`, `.private.toml`, etc.)?

### Q2: Is "parent directory of the state dir" a sensible workspace anchor?

Meridian has `.meridian/` (state dir, like `.git/`). The design treats the *parent of `.meridian/`* as the one effective working directory — workspace file default location, config file location, spawn cwd, all anchor there. Users never see a named "repo root" concept.

- How do similar tools handle this? Git uses `.git/` walk-up. What about Cargo, pnpm, Nx, direnv, mise, devbox?
- Is walk-up discovery (parent-scanning) a liability in practice, or the expected ergonomic?
- Any tool that explicitly names and exposes "project root" as user-facing vocabulary, and does it help or hurt?

### Q3: Paths inside the workspace file — relative to what?

Design says: paths inside `workspace.local.toml` are resolved relative to the workspace file itself (VS Code `.code-workspace` convention). This makes the file portable — move it, paths follow.

- Confirm `.code-workspace` does this.
- What do Cargo workspace (`members = [...]` in `Cargo.toml`), pnpm workspace (`packages:` in `pnpm-workspace.yaml`), Nx (`workspace.json`), Bazel (`WORKSPACE`), Deno (`deno.json`), Bun workspaces do? All relative-to-file?
- Any workspace-adjacent tools that resolve relative to shell cwd or a different anchor? If so, what went wrong?

### Q4: Env var override for absolute-paths-only

Design: `MERIDIAN_WORKSPACE=/abs/path/to/workspace.toml` is absolute-only in v1. Relative-path resolution is deferred because shell cwd and the meridian effective cwd both have surprising behaviors.

- What do established env var conventions do? `GIT_DIR`, `CARGO_HOME`, `PYTHONPATH`, `VIRTUAL_ENV`, `NODE_PATH`, `KUBECONFIG`, `DOCKER_CONFIG`?
- Is absolute-only reasonable for v1, or does it break common usage (e.g., scripts that set relative paths)?
- Any env var overrides that explicitly document "relative resolved against X" behavior worth borrowing?

### Q5: OpenCode `permission.external_directory` and `OPENCODE_CONFIG_CONTENT` for multi-root injection

Our 2026-04-14 probe showed OpenCode has no native `--add-dir` parity with Claude/Codex. We use `permission.external_directory` (config field) delivered via the `OPENCODE_CONFIG_CONTENT` env var (inline JSON config).

- Has OpenCode shipped first-class multi-root support since 2026-04-14? PR #2921 was closed unmerged at that time; check current state.
- Is `permission.external_directory` still the documented native path for extra-directory access?
- Is `OPENCODE_CONFIG_CONTENT` still the right inline-config mechanism, or has something else replaced it?
- Any community guidance on the right way to do multi-root in OpenCode today?

### Q6: Breaking config-location changes without migration

Our stance: one release moves `config.toml` from `.meridian/` to project root. No dual-read, no `config migrate`, no deprecation phases. Users re-run `config init` or copy by hand. Justification: no real users yet.

- How have similar early-stage tools handled config-location moves? (pre-1.0 Cargo, early Docker, early Kubernetes, etc.)
- When does "no migration, break hard" succeed, and when does it backfire even for pre-1.0 projects?
- Are there low-cost patterns we're leaving on the table (e.g., detect legacy location, exit with clear error message rather than silently ignore)?

### Q7: Honest "this feature is inert in your current mode" reporting

Codex has a read-only sandbox mode where `--add-dir` is silently inert (still accepted, has no effect). Our design surfaces this as `applicability = ignored:read_only_sandbox` with an explicit diagnostic rather than pretending the roots were applied.

- Do any dev tools do this honestly-report-inert-features pattern? Examples?
- Is the alternative (refuse to launch in incompatible modes) more common? Less?
- Any vocabulary precedent for the applicability states (active / ignored / unsupported)?

### Q8: Schema choice — `[[context-roots]]` vs alternatives

We use `[[context-roots]]` with `path` and `enabled` fields. Low priority but want to validate.

- Prior art for "extra directories to include" schemas: VS Code `.code-workspace` has `folders: [{path, name}]`. Cargo has `members = [...]` as plain array. pnpm uses `packages: [...]`.
- Is a table-of-tables shape justified for v1 with only two fields (`path`, `enabled`)? Or would a simple array `enabled_roots = ["./foo", "./bar"]` be less ceremony?
- Any prior art on the `enabled: bool` pattern vs "presence means enabled, comment out to disable"?

### Q9 (optional): Multi-root dev-env tool competitive landscape

We're in the rough category of "tool that coordinates multiple repos for a dev environment." Peers: direnv, mise, devbox, devpod, tea.xyz, Nix flakes, devenv.sh, Dev Containers. Plus the AI-harness space directly: Claude Code, Codex CLI, OpenCode, Cursor, Aider, Cline.

- Skim the ones that have any multi-root story. What's the idiomatic UX?
- Anything we should steal or be warned about?

## Output shape

For each question: one paragraph of findings with citations, then one of `confirmed` / `divergent-but-defensible` / `divergent-and-problematic` / `new-info-requires-redesign`. End with a short summary block listing any decisions that need reconsideration.

Keep it tight — the goal is validation, not a literature review. If a question's answer is "this is totally standard, here are three projects that do it," that's a good short answer.
