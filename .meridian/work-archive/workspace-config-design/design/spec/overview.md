# Workspace Config Spec Overview

## Purpose

This spec tree defines the behavioral contract for workspace-config. The design splits into two tiers: **runtime-home/state-boundary** (foundation) and **workspace topology** (builds on the foundation).

## Tier Structure

### Tier 1: Runtime Home and State Boundaries (HOME-1)

This is the foundation. It defines project identity via UUID, user-level state root with platform defaults, and clear ownership boundaries.

**Read HOME-1 first.** Everything else builds on it.

### Tier 2: Workspace Topology (CFG-1, WS-1, CTX-1, SURF-1, BOOT-1)

These specs build on the runtime-home foundation:
- CFG-1 — committed project config location
- WS-1 — local workspace topology file
- CTX-1 — context-root injection into harness launches
- SURF-1 — state surfacing in CLI
- BOOT-1 — bootstrap and opt-in file creation

## TOC

### Tier 1 (Foundation)

- **HOME-1** — Runtime home and state boundaries ([runtime-boundaries.md](runtime-boundaries.md)): Project UUID in `.meridian/id`, user state root with platform defaults (Unix/Windows), three-owner model, spawn-id keying. **Read this first.**

### Tier 2 (Workspace Topology)

- **CFG-1** — Project config location ([config-location.md](config-location.md)): `meridian.toml` in the same directory as the active `.meridian/` as the canonical committed project config.
- **WS-1** — Workspace topology file ([workspace-file.md](workspace-file.md)): `workspace.local.toml` naming, minimal schema, path resolution, unknown-key preservation, init behavior.
- **CTX-1** — Context-root injection ([context-root-injection.md](context-root-injection.md)): how enabled roots become harness arguments, precedence ordering, v1 harness support.
- **SURF-1** — State surfacing ([surfacing.md](surfacing.md)): how `config show`, `doctor`, and launch-time diagnostics report state.
- **BOOT-1** — Bootstrap and opt-in file creation ([bootstrap.md](bootstrap.md)): what first-run creates, what remains opt-in, init idempotency.

## Windows Compatibility Usage

The Windows compatibility design should:
1. **Import HOME-1 directly** — the runtime-home boundary model is the foundation
2. Focus on platform primitives, not Meridian state topology
3. Keep harness storage harness-owned per HOME-1.c1

Tier 2 specs (CFG-1 through BOOT-1) are workspace-specific and do not block Windows compatibility.

## Reading Order

1. **HOME-1** — the foundation everything builds on
2. **CFG-1** — root-vs-state boundary for committed config
3. **WS-1** — local topology file
4. **CTX-1** — launch behavior
5. **SURF-1** — diagnostics
6. **BOOT-1** — creation entrypoints
