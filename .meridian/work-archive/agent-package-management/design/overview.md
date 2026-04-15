# mars-agents: Design Overview

## What It Is

**mars-agents** is a standalone package manager for the `.agents/` directory — the standard directory where AI coding assistants (Claude Code, Codex, Cursor, OpenCode, Gemini CLI, etc.) read agent profiles and skills from.

- **Project**: `haowjy/mars-agents`
- **Binary**: `mars`
- **Language**: Rust
- **Distribution**: cargo install, npm, Homebrew, curl, GitHub releases

## Why It Exists

The `.agents/` directory is an industry convention used by many AI coding tools, and several skill managers exist (Skills.sh, Skild, Tessl, Vett). They handle skill installation, discovery, and even dependency bundling — but they all avoid managing `.agents/` as a live working directory where users customize installed content alongside managed content.

Mars solves the **mixed-ownership problem**: multiple sources composing into one `.agents/` directory where local edits are expected, preserved via three-way merge, and collisions are resolved automatically with dependency-graph-aware frontmatter rewrites. No other tool manages agent profiles alongside skills as one install graph with cross-source constraint resolution.

**Security posture (v1)**: commit SHA pinning + checksums for integrity. Cryptographic signing and risk gating (as offered by Vett) are explicit non-goals for v1 — mars assumes trusted sources (team-internal repos, known publishers).

Meridian currently has a basic file copier (`meridian sources`). mars-agents replaces this with a proper package manager.

## Core Concepts

### All Mutations Resolve First

Every command that changes state proposes a new target state and resolves the full dependency graph before touching disk. Either the entire state is satisfiable or the command fails and nothing changes. No partial mutations — `add`, `remove`, `update`, `rename`, and `sync` all flow through the same resolve → validate → diff → plan → apply pipeline.

### `.agents/` Is Mixed, Not Generated

Unlike `node_modules/`, `.agents/` contains both managed and user-authored content. Users already have project-specific agents and skills alongside sourced content. mars respects this — it tracks what it installed via the lock file and never touches anything else.

### Ownership via Lock File

The lock file (`agents.lock`) is the ownership registry. If a file is in the lock, mars manages it. If not, mars ignores it. This drives all pruning, conflict detection, and update decisions.

### Git-Style Conflict Resolution

When mars detects conflicts between local modifications and upstream changes, it writes standard git conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) into the file. Users resolve in their editor with full IDE support (VS Code "Accept Current/Incoming/Both", etc.). No custom UI needed.

## Source Types

Three ways to add packages:

### Git Sources (Versioned)
Go modules model — URL is identity, git tags are versions.

```bash
mars add github.com/haowjy/meridian-base@v0.5.0
mars add github.com/haowjy/meridian-dev-workflow@v2.0
mars add github.com/someone/cool-agents@latest
```

Version resolution: `git ls-remote --tags` to discover available versions, pick one satisfying constraints, clone at that ref. No registry needed — git IS the registry.

### Local Path Sources (Unversioned)
For development and project-specific packages. Always syncs current state — no version, no tags.

```bash
mars add ./my-agents
mars add ../meridian-dev-workflow
```

First-class source type, not a workaround. A user who only uses local paths never needs git URLs, tags, or a registry.

### Registry Short Names (Future)
Discovery and convenience layer. Short name resolves to git URL via registry.

```bash
mars add meridian-dev-workflow    # registry resolves → git URL
```

Registry is optional — packages always work with just a git URL. `mars.dev` is the default registry, but configurable (company-internal registries, mirrors).

### Dev Overrides
For developing a package locally while the production config points at git:

```bash
mars override meridian-base --path ./meridian-base
```

This is a convenience command that edits `agents.local.toml` (gitignored) — equivalent to hand-editing the `[overrides]` section. Lock file keeps the git version for reproducibility. Override is local-only, not committed. Other contributors get the git version.

## CLI Semantics

uv-style: commands do the full operation, not just edit config.

- `mars add` → edits config + resolves + installs + updates lock
- `mars remove` → edits config + prunes + updates lock
- `mars sync` → resolves + installs (make reality match config)

Config files are a side effect of CLI commands. Users interact through the CLI, not by hand-editing TOML.

## Version Resolution

URL-based package identity (like Go modules) with constraint-based version resolution and lock file (like Cargo/uv). Git tags are versions:

- `@v0.5.0` — exact version
- `@v2` — latest v2.x.x
- `@latest` — newest tag
- `@branch` or `@commit` — pin to ref
- `>=0.5.0, <1.0` — range constraint in dependencies

Transitive resolution via topological sort with constraint intersection. Not SAT — the graph is small (sources depend on sources, agents declare skills). If constraints conflict, clear error showing the chain.

## Merge Mechanics

Four cases on sync, determined by comparing checksums against lock:

| Source changed? | Local changed? | Action |
|---|---|---|
| No | No | Skip |
| Yes | No | Overwrite (clean update) |
| No | Yes | Keep local |
| Yes | Yes | Three-way merge → conflict markers if needed |

Base for three-way diff = what mars installed last time (reconstructed from locked commit SHA if cache missing). Uses `git2::merge_file()` — libgit2's built-in three-way merge with conflict markers (no extra crate needed).

## Architecture

### File Layout

```
.agents/
  agents.toml              # user config — declares sources + settings
  agents.lock              # generated — provenance, checksums, ownership
  .mars/
    cache/                 # content-addressed source cache
  agents/
    dev-orchestrator.md    # managed (from meridian-dev-workflow)
    my-custom-agent.md     # user-authored, mars doesn't touch
  skills/
    __meridian-spawn/      # managed (from meridian-base)
    my-project-skill/      # user-authored, mars doesn't touch
```

### Config: `agents.toml`

TOML format. Lives in `.agents/`. Primarily managed via CLI, not hand-edited. Tool-agnostic naming.

```toml
[sources.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"
agents = ["coder"]              # only this agent + its skill deps (resolved each sync)
skills = ["frontend-design"]    # explicitly requested skill

[sources.meridian-dev-workflow]
url = "github.com/haowjy/meridian-dev-workflow"
version = "^2.0"
exclude = ["agents/deprecated-agent"]  # everything except these

[sources.my-local-agents]
path = "./my-agents"
# no agents/skills/exclude = install everything
```

Filtering modes (pick one per source):
- **`agents`/`skills`**: Intent-based — install these + auto-resolve skill deps from frontmatter. If an agent adds a new skill dep, it comes in on next sync.
- **`exclude`**: Install everything except these.
- **Neither**: Install everything from the source (default).

`agents`/`skills` and `exclude` on the same source is an error — pick one mode.

### Name Collisions

When two sources provide the same item name, mars auto-renames both using `{name}__{owner}_{repo}`:

```
agents/coder__haowjy_meridian-base.md
agents/coder__someone_cool-agents.md
```

Name-first format groups items by name in autocomplete. Frontmatter `name:` is preserved, so agents are still reachable by original name. No implicit precedence — both get renamed.

Users can override: `mars rename` for custom names, or `exclude` in config to skip one entirely.

### `agents.local.toml` (Gitignored)

Dev overrides and local-only config. Merged on top of `agents.toml` at runtime. Not committed — each developer has their own.

```toml
[overrides]
meridian-base = { path = "../meridian-base" }  # use local checkout instead of git
```

### Lock: `agents.lock`

Tracks every managed file with provenance and integrity:

```toml
[agents."dev-orchestrator.md"]
source = "meridian-dev-workflow"
version = "2.1.0"
commit = "a1b2c3d4e5f6..."
source_checksum = "sha256:abc123..."
installed_checksum = "sha256:abc123..."

[skills."__meridian-spawn"]
source = "meridian-base"
version = "0.5.2"
commit = "9f8e7d6c5b4a..."
source_checksum = "sha256:def456..."
installed_checksum = "sha256:def456..."
```

### Manifest: `mars.toml` (Per Source/Package, Optional)

Lives in the package repo root. Named after the tool, following convention (`Cargo.toml`, `go.mod`, `package.json`). **Optional** — mars works without it by discovering items from filesystem convention (`agents/*.md`, `skills/*/SKILL.md`). Design for the case where nobody has a manifest.

When present, `mars.toml` adds: declared dependencies on other packages, package metadata (version, description). When absent, mars discovers everything in `agents/` and `skills/` directories, has no transitive dependency information, and uses the git tag as the version.

```toml
[package]
name = "meridian-dev-workflow"
version = "2.1.0"
description = "Opinionated dev workflow with review fan-out and decision tracking"

[dependencies.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"
items = ["skills/frontend-design"]  # only what we need from this package

[dependencies.meridian-core]
url = "github.com/haowjy/meridian-core"
version = ">=1.0.0"
# no items = install everything from this package
```

### Dependency Granularity

Dependencies are package-level by default — omit `items` and you get everything the package provides. Add `items` to cherry-pick specific agents/skills. This is the package author declaring "I only need these specific things," keeping installs lean without complicating the resolution algorithm.

Item-level filtering in `mars.toml` (package manifest) controls what a package *requires*. Intent-based filtering in `agents.toml` (consumer config via `agents`/`skills`/`exclude`) controls what a user *wants*. Both are optional.

Agent frontmatter stays clean — `skills: [X]` uses names only, no source URLs. Mars validates that referenced names exist after resolution. The frontmatter doesn't participate in dependency resolution.

Dependencies include the full URL — the URL IS the identity. No ambiguity about which package you mean.

### What the Manifest Is For

The manifest's purpose is declaring dependencies — "my package needs these things from other packages." Without `mars.toml`, mars discovers and installs what's in the repo. With `mars.toml`, mars also pulls in transitive dependencies.

What the repo provides is discovered from the filesystem (`agents/*.md`, `skills/*/SKILL.md`), not declared in the manifest. No `[provides]` section needed.

### Rust Tech Stack

- **`clap`** — CLI framework
- **`serde`** + **`toml`** — config/lock/manifest parsing
- **`serde_yaml`** — agent frontmatter parsing (for dependency validation)
- Three-way merge via **`git2::merge_file()`** (libgit2's built-in merge, no extra crate needed)
- **`git2`** — libgit2 bindings for git operations (clone, fetch, tag listing)
- **`sha2`** — checksum computation

## Meridian Integration

Meridian integrates mars as a passthrough command:

```bash
meridian mars sync          # → mars sync --root /path/to/project
meridian mars add ...       # → mars add ... --root /path/to/project
```

Meridian auto-detects `mars` on PATH, passes `--root` for project directory, execs mars with remaining args. Meridian's Python sync code (`lib/sync/`, `lib/install/`, the old `agents.toml`, `agents.lock`, flock) gets ripped out.

Meridian continues to read `.agents/` at spawn time for agent profiles and skills — it just stops being responsible for populating it.
