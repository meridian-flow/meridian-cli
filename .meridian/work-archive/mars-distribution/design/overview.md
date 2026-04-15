# Mars Distribution — Design Overview

Mars is a single Rust binary (~6MB) with no runtime dependencies (except `git` on PATH for some operations). This design covers building and distributing pre-built binaries via GitHub Releases and npm.

## Distribution Channels

| Channel | Trigger | What Users Get |
|---|---|---|
| **GitHub Releases** | Push tag `v*` | Platform binaries as release assets |
| **npm** | Same CI run | `npm i -g @mars-agents/cli` installs platform binary |
| **cargo install** | Already works | No changes needed |

## Architecture

```
Tag push (v0.0.1)
  └─ GitHub Actions release workflow
       ├─ Build matrix (3 targets)
       │    ├─ x86_64-unknown-linux-gnu   → mars-linux-x64
       │    ├─ aarch64-apple-darwin       → mars-darwin-arm64
       │    └─ x86_64-apple-darwin        → mars-darwin-x64
       ├─ Upload binaries to GitHub Release
       └─ Publish npm packages
            ├─ @mars-agents/linux-x64     (platform pkg)
            ├─ @mars-agents/darwin-arm64  (platform pkg)
            ├─ @mars-agents/darwin-x64    (platform pkg)
            └─ @mars-agents/cli           (stub + resolver)
```

## Design Documents

- **[release-workflow.md](release-workflow.md)** — GitHub Actions workflow: build matrix, release asset upload, npm publish
- **[npm-packages.md](npm-packages.md)** — npm package structure: platform packages, CLI stub resolver, package.json files
- **[mars-passthrough.md](mars-passthrough.md)** — Meridian `mars` subcommand (pre-existing design)

**Note**: When design docs and phase blueprints (in `plan/`) diverge, the phase blueprints are authoritative for implementation. Design docs capture the rationale; blueprints capture the exact implementation spec.

## Key Decisions

See [../decisions.md](../decisions.md) for full decision log. Summary:

1. **Biome pattern over esbuild pattern** — no postinstall script, simpler resolution via `bin/mars` JS shim. Biome's approach is cleaner and avoids postinstall issues with `--ignore-scripts`.
2. **No WASM fallback** — mars is a CLI tool, not a library. If the platform binary isn't available, fail with clear instructions.
3. **Version extracted from Cargo.toml** — single source of truth, CI reads it to version npm packages.
