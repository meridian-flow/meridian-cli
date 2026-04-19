# Project Key

## Problem

Meridian needs a stable identifier for project-scoped runtime state that is:

- Independent of the current checkout path so repo moves/renames do not change the user-level runtime namespace
- Stable enough that other designs can reuse it without inventing their own project taxonomy
- Collision-resistant across projects on the same machine

The canonical use case is harness runtime isolation — each spawn needs its own state directory (for harness config, credentials, caches, and projected config) without polluting the user's actual home or interfering with other spawns. But `project_key` exists as a general-purpose stable project identity, not only for harness isolation.

## Design

### Identity Derivation

The `project_key` is derived from normalized project identity:

```text
project_key = hash(normalized_remote_url or canonical_repo_path)[:12]
```

Resolution order:

1. If `.git/config` exists and has a remote `origin`, use `normalize(remote_url)` as the input.
2. Otherwise, use `canonical(repo_root)` as the fallback.

Normalization strips protocol variations (`git@github.com:org/repo.git` → `github.com/org/repo`), trailing `.git`, and case-normalizes the host. Canonicalization uses `Path.resolve()` to eliminate symlinks and relative components.

The 12-hex-char hash (48 bits) provides more than enough space for local-machine use while staying short enough to remain readable in directory listings and logs.

### Where `project_key` Is Used

Project-scoped Meridian state lives under:

```text
~/.meridian/projects/<project_key>/
  spawns.jsonl
  spawns.jsonl.flock
  spawns/
    <spawn_id>/
      output.jsonl
      inbound.jsonl
      control.sock
      harness.pid
      heartbeat
      report.md
```

This is the canonical project-scoped Meridian runtime root. If another design needs project-scoped user-level state, it should extend this root rather than inventing a separate project namespace.

### Per-Spawn Homes and Config Projection

Harness-native home isolation and projected config live under the spawn directory:

```text
~/.meridian/projects/<project_key>/spawns/<spawn_id>/home/
~/.meridian/projects/<project_key>/spawns/<spawn_id>/config/
```

This keeps all native harness state under the same project/run namespace as the rest of Meridian's runtime files.

### What `project_key` Does NOT Cover

- **Session registry** — `~/.meridian/app/sessions.jsonl` remains user-level and keyed by `session_id`. Sessions are metadata/index, not runtime storage.
- **Server lockfile** — `~/.meridian/app/server.json` is machine-level, not project-scoped.
- **Workspace identity** — `repo_root` still tells Meridian and the harness which checkout to operate in. `project_key` is the runtime namespace, not a substitute for a real filesystem root.

## Why Not Session-Keyed or Chat-ID-Keyed Directories?

Sessions (`session_id`) and resumable harness sessions (`chat_id`) are metadata concepts, not runtime-home boundaries:

- **Sessions** are URL-addressable aliases for spawns. They exist for the app UI, not for filesystem organization.
- **Chat IDs** are harness-level resumable session identifiers. They're carried as spawn metadata for continuations, not as storage keys.

Runtime state is keyed by `spawn_id` because each spawn is a distinct execution with its own harness process, its own state, and its own lifecycle.

This means:

- `~/.meridian/projects/<project_key>/spawns/p123/` — YES
- `~/.meridian/projects/<project_key>/sessions/abc123/` — NO
- `~/.meridian/projects/<project_key>/chats/xyz789/` — NO

Primary sessions launched from the app also have Meridian `spawn_id`s. There is no separate "app session" runtime directory.

## Harness Workspace Shaping

How harnesses access project files is distinct from where harness state lives. `repo_root` shapes the workspace. `project_key` shapes Meridian-managed native state.

### Codex

- **Workspace access:** `--cd <repo_root>` sets the primary workspace. `--add-dir <path>` adds extra readable paths.
- **Home/state isolation:** `CODEX_HOME=~/.meridian/projects/<project_key>/spawns/<spawn_id>/home/`
- `CODEX_HOME` is only for native home/state isolation. It is not a substitute for `--add-dir`.

### OpenCode

- **Workspace access:** the launch root is the primary workspace. Additional paths come from projected config/permissions, especially `permission.external_directory`.
- **Home/state isolation:** use the same `home/` pattern or per-spawn config overlays when OpenCode supports it.
- There is no dedicated OpenCode `--add-dir` flag. Extra-path access is permission/config-based.

### Claude

- **Workspace access:** `--directory <repo_root>` sets the working directory.
- **Home/state isolation:** use the same `home/` pattern when needed.

## Future: Harness-Native Profile Projection

`project_key` enables project-specific harness configuration without modifying the user's global harness config:

```text
~/.meridian/projects/<project_key>/config/
  claude/
    settings.json
  codex/
    config.toml
  opencode/
    config.json
```

Spawns launched in this project can have their harness config path set to these projected files/directories via environment variables or harness-native config flags, so project-specific settings apply without polluting global config.

This is a future enhancement. The important contract for this design is simply that `project_key` is the reusable project-scoped namespace other designs can build on.
