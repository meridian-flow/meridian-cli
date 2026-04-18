# Workspace Config Architecture Overview

## Summary

The architecture splits into two tiers: **runtime-home/state-boundary** (foundation) and **workspace topology** (builds on the foundation). This reflects the design's primary goal: establish a simple, UUID-based project identity model with clear state boundaries.

## Tier Structure

### Tier 1: Runtime Home and State Boundaries (A00)

The foundation. It defines:
- Project UUID stored in `.meridian/id`
- User-level state root with platform defaults (Unix: `~/.meridian/`, Windows: `%LOCALAPPDATA%\meridian\`)
- Three-owner model (repo `.meridian/`, user state root, harness adapters)
- Spawn-id keying for all runtime state

**A00 is the first leaf to read.** Everything else builds on it.

### Tier 2: Workspace Topology (A01–A05)

These leaves build on the runtime-home foundation:
- A01 — paths-layer: file-ownership boundary for repo-root policy
- A02 — config-loader: project-config state machine
- A03 — workspace-model: workspace file parsing and evaluation
- A04 — harness-integration: workspace projection into harness launches
- A05 — surfacing-layer: config/workspace reporting in CLI

## External Dependencies

This work item depends on the **launch-core-refactor** work item completing first. A04's workspace projection plugs into the launch-domain core's `apply_workspace_projection()` pipeline stage.

## TOC

- **A00** — [runtime-home.md](runtime-home.md): Project UUID, user state root, platform defaults, ownership model, spawn-id keying. **Read this first.**
- **A01** — [paths-layer.md](paths-layer.md): `UserStatePaths` and `StatePaths` boundary.
- **A02** — [config-loader.md](config-loader.md): project-config state machine (`absent | present`), read/write resolution, command-family consistency.
- **A03** — [workspace-model.md](workspace-model.md): parsed workspace representation, validation tiers, unknown-key handling.
- **A04** — [harness-integration.md](harness-integration.md): harness-owned `HarnessWorkspaceProjection`, launch ordering, per-harness mechanism mapping.
- **A05** — [surfacing-layer.md](surfacing-layer.md): `config show`, `doctor`, and launch-diagnostic shapes.

## Cross-Cutting Decisions

### Tier 1 Decisions (Foundation)

- **UUID-based project identity per D28.** Project UUID stored in `.meridian/id`, generated once, moves with the project folder. No derivation algorithm.

- **Three-owner model per D28.** Repo `.meridian/` holds UUID and committed artifacts. User state root (`~/.meridian/projects/<UUID>/`) holds runtime state. Harness adapters own harness-native storage. No cross-owner writes.

- **Spawn-ID universal keying per D28.** Runtime homes keyed by `spawn_id` exclusively. Primary sessions also receive spawn-ids. Sessions (`chat_id`, app `session_id`) are metadata only, not storage keys.

### Tier 2 Decisions (Workspace Topology)

- **One state snapshot, many consumers.** Loader logic, config commands, `doctor`, and harness launch paths consume the same observed config/workspace state.

- **Structured internal workspace roots.** User-facing TOML stays minimal; internal model carries ordering and provenance.

- **Projection interface, not mechanism branches.** Launch code computes ordered roots once, then adapters translate them into `HarnessWorkspaceProjection` objects.

## Reading Order

1. **A00 (runtime-home)** — the foundation everything builds on
2. **A01 (paths-layer)** — file-ownership boundary
3. **A02 (config-loader)** and **A03 (workspace-model)** — the two read models
4. **A04 (harness-integration)** — launch behavior
5. **A05 (surfacing-layer)** — user-visible state
