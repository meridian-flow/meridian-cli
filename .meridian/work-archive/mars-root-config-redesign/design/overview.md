# Mars Root Config Redesign — Design Overview

## Problem

Mars v0.0.3 moved `mars.toml`/`mars.lock` from `.agents/` to the repo root (like Cargo.toml). The structural direction is right, but four reviewers identified blocking issues and we have new feature requirements. Since there are no real users, we can break anything — the goal is to get the design right before anyone adopts it.

## Scope

Four requirement groups, all in one release:

1. **R1: Reviewer fixes** — Kill init marker, gitignore `mars.local.toml`, canonicalize `project_root`, refuse to mutate package manifests, pass `&MarsContext` to sync
2. **R2: Persist managed root** — Add `[settings] managed_root` so custom targets survive clean checkouts
3. **R3: Local package symlinks** — When a project is both a package and a consumer, symlink its own agents/skills into `.agents/`
4. **R4: Test coverage** — Walk-up discovery with `.git` boundary tests

## Design Docs

| Doc | What it covers |
|---|---|
| [config-model.md](config-model.md) | `mars.toml` schema: consumer detection, `[settings]`, `[package]` + `[dependencies]` coexistence |
| [init-and-discovery.md](init-and-discovery.md) | `mars init` behavior, root walk-up, `.git` boundary, `--root` semantics |
| [local-package-sync.md](local-package-sync.md) | How local package items are symlinked into the managed dir during sync |
| [api-cleanup.md](api-cleanup.md) | `&MarsContext` threading, argument ordering, gitignore fixes |

## Key Decisions

1. **`[dependencies]` is the sole consumer marker** — no init comment, no heuristic. See [config-model.md](config-model.md).
2. **Persist managed root in `[settings]`** — `managed_root = ".claude"` survives clean checkouts. See [config-model.md](config-model.md).
3. **Local package items are a synthetic `_self` source** injected at sync time — not a user-visible config section. See [local-package-sync.md](local-package-sync.md).
4. **`mars init` defaults to git root, not cwd** — prevents orphaned configs in subdirectories. See [init-and-discovery.md](init-and-discovery.md).
5. **`[dependencies]` and `[dependencies]` remain separate** — they serve different roles (package deps vs consumer sources). See [config-model.md](config-model.md).
