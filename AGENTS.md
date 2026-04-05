# Development Guide: meridian-channel

No real users, no real user data. No backwards compatibility needed — completely change the schema to get it right.

(if this is CLAUDE.md, it is symlink to AGENTS.md)

## Philosophy

**Meridian-Channel** is a coordination layer for multi-agent systems — not a file system, execution engine, or data warehouse.

### Design Principles

1. **Separate Policy from Mechanism** *(Raymond, Rule of Separation)*: Harness adapters are mechanism (how to launch Claude/Codex/OpenCode). CLI commands are policy (what to do, which model, what output). Policy changes fast; mechanism stays stable. Keep them apart.
2. **Extend, Don't Modify** *(Open/Closed)*: New harness = one adapter file + registration. New package source = one mars config entry. New CLI command = one module. If a feature requires editing 10 files, the abstraction is wrong.
3. **Knowledge in Data, Not Code** *(Raymond, Rule of Representation)*: Agent capabilities live in YAML profiles, not procedural code. State lives in JSONL events, not in-memory objects. This keeps the system inspectable and harness-agnostic.
4. **Crash-Only Design** *(Candea & Fox)*: Every write is atomic (tmp+rename). Every read tolerates truncation. There is no "graceful shutdown" — if meridian is killed mid-spawn, the next `meridian status` detects and reports the orphaned state. Recovery IS startup.
5. **Progressive Disclosure** *(clig.dev, Lengstorf)*: `meridian spawn "do the thing"` works with smart defaults. Power users override with `--model`, `--harness`, `--skills`. Don't force all-or-nothing configuration.
6. **Simplest Orchestration That Works** *(Google Cloud AI patterns)*: Stay a thin coordination layer. Centralized spawn-and-report is enough. Don't build complex agent choreography until the simple model breaks.

### Core Principles

1. **Harness-Agnostic**: One CLI, many runtimes. Meridian never assumes Claude, Codex, or any specific harness — adapters bridge the gap.
2. **Files as Authority**: All state is files under `.meridian/`. No databases, no services, no hidden state. If it's not on disk, it doesn't exist. `cat spawns.jsonl | jq` should tell you everything.
3. **Coordination, Not Control**: Meridian provides structure (spawns, sessions, skills, sync) but never dictates how agents do their work.
4. **Idempotent Operations**: `meridian sync` twice = same result. Re-running after a crash converges to correct state, never doubles side effects.

### Architecture

- **State Root**: `.meridian/` (flat layout, no nesting). JSONL event stores, per-spawn artifact dirs, shared filesystem.
- **Harness Adapters**: `src/meridian/lib/harness/` — per-harness command building, output extraction, materialization. Adding a harness = one adapter file + registration.
- **State Layer**: `src/meridian/lib/state/` — path resolution, spawn store, session store. Atomic writes via tmp+rename, `fcntl.flock` for concurrency.
- **Package Sync**: `meridian mars ...` — package resolution and `.agents/` materialization are delegated to mars.
- **Profiles & Skills**: Agent profiles (YAML markdown) define capabilities, model, and skills. Skills load fresh on launch/resume (survives compaction).

## Dev Workflow

Two orchestrators split the dev lifecycle: **dev-orchestrator** handles interactive design and planning with the user (spawns architects, reviewers, planners), then hands off approved plans to **dev-runner** for autonomous execution (code → test → review → fix loops, no human intervention needed).

Use `meridian spawn` (not `uv run meridian spawn`) to hand off tasks to subagents. `uv run meridian` runs from local source, so other agents editing meridian's own code in the same repo can leave it in a half-written state — use it only for smoke-testing local dev changes. The installed `meridian` binary is stable and isolated from in-progress source edits. Prefer gpt-5.3-codex as the main code implementer and opus as the primary documenter. For reviews, fan out across the strongest models — gpt-5.4, gpt-5.2, and opus — with different focus areas on each. Don't send all reviewers to the same model.

NEVER REVERT CHANGES — always assume it's someone else's work.

### Editing Agents & Skills

**NEVER edit `.agents/` directly** — it is generated output, overwritten by `meridian mars sync`. Edit the source submodules instead:

- **`meridian-base/`** — core agents, skills, and spawn infrastructure (e.g. `__meridian-spawn`, `__meridian-subagent`)
- **`meridian-dev-workflow/`** — dev orchestration agents and skills (e.g. `dev-orchestrator`, `reviewer`, `coder`, `agent-staffing`)

When writing or editing agent profiles and skills, follow the design principles in `resources/design-principles.md` under the `__meridian-spawn` skill (linked from `resources/creating-agents.md`). It covers prompt structure, tool restrictions, progressive disclosure, and common anti-patterns.

Canonical workflow:

1. Edit in the source submodule (e.g. `meridian-base/skills/__meridian-spawn/SKILL.md`)
2. Commit and push the source repo change
3. Update package refs if needed with `meridian mars add ...`
4. Run `meridian mars sync` to regenerate `.agents/`

### Upgrading from Legacy Sources State

Legacy meridian-managed source files are no longer used and are safe to delete:

- `.meridian/agents.toml`
- `.meridian/agents.local.toml`
- `.meridian/agents.lock`
- `.meridian/cache/agents/`

### Approval Modes

Spawns support 4 approval modes: `default` (harness decides), `confirm` (user approves each tool call), `auto` (auto-approve safe operations), `yolo` (approve everything). Set via `--approval` flag or profile YAML.

### Config Precedence

CLI flags > ENV vars > YAML profile > Project config > User config > harness default.

This applies to **every resolved field independently** — model, harness, approval, timeout, skills. Derived fields inherit the precedence level of their source: if the user overrides the model with `-m`, the harness must be derived from the overridden model, not from the profile's harness. A profile-level value must never win over a CLI override, even indirectly.

### Testing

**Prefer smoke tests over unit tests.** Too many unit tests is bad when you're constantly refactoring.

- **Smoke tests** (`tests/smoke/`): Organized markdown guides for manually testing CLI behavior. See the `_meridian-dev-smoke-test` skill for methodology. Run `uv run meridian` to test the CLI in its current state.
- **Unit tests** (focused): Only for logic that's hard to smoke test — signals, concurrency, security/env sanitization, sync engine algorithms, parsing edge cases. Run with `uv run pytest-llm`.
- **Linting**: `uv run ruff check .`
- **Type checking**: `uv run pyright` (must be 0 errors)

```bash
uv sync --extra dev      # Install from source
uv run ruff check .      # Lint
uv run pytest-llm        # Unit tests (token-efficient output)
uv run pyright            # Type check
uv run meridian           # Smoke test the CLI directly
uv add <package>          # Add a dependency (never use pip install)
```

### Versioning

The package version lives in `src/meridian/__init__.py` as `__version__`. Usually just bump patch:

```bash
scripts/release.sh patch          # 0.0.2 → 0.0.3 (default choice)
scripts/release.sh minor          # 0.0.3 → 0.1.0
scripts/release.sh 0.2.0 --push   # explicit version, push tag
```

### Always Use `uv`

This project uses `uv` exclusively for Python tooling. Never use `pip`, `pip install`, `python`, or `python -m` directly. Use `uv run`, `uv add`, and `uv sync` instead.

### Commit Checkpoints

Commit after each step that passes tests. Don't accumulate changes across multiple steps.

1. Implement the step
2. Verify tests pass
3. Commit with a descriptive message
4. Move to the next step

### Never Delete Untracked Files

**NEVER delete or remove untracked files without asking the user first.** Untracked files may be someone else's in-progress work.

1. Ask before deleting
2. If you must proceed, `git stash --include-untracked` first
3. When reverting agent changes, distinguish agent-created files from pre-existing untracked files

## Related Repos

- **mars-agents** (`../mars-agents/`): Standalone agent package manager for `.agents/`. Rust CLI, binary name `mars`. Meridian invokes it via `meridian mars ...` for project package setup and sync. Design spec in `.meridian/work/agent-package-management/design/`. Repo: `haowjy/mars-agents`.
