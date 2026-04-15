# Mars Distribution & Meridian Integration

## Context

Mars (`mars-agents`) is a standalone Rust agent package manager for `.agents/` directories. It needs a distribution story for two audiences, plus integration into the meridian CLI.

## Goals

### 1. Mars Binary Distribution (mars-agents repo)

Build and publish pre-built mars binaries for three platforms:
- linux-x86_64
- darwin-arm64 (Apple Silicon)
- darwin-x86_64 (Intel Mac)

No Windows — WSL users use the Linux binary.

Distribution channels, all fed from the same CI build matrix on tagged releases:
- **GitHub Releases** — binary assets per platform
- **npm** — platform-specific optional dependency pattern (like esbuild/biome/turbo)
  - `@mars-agents/cli` — stub that resolves the right platform package
  - `@mars-agents/linux-x64`, `@mars-agents/darwin-arm64`, `@mars-agents/darwin-x64`
- **cargo install** — already works, no changes needed

### 2. Meridian `mars` Subcommand (meridian-channel repo)

`meridian mars <args>` is a transparent passthrough to the `mars` binary on PATH.

Behavior:
- All args after `meridian mars` are forwarded verbatim to `mars`
- `meridian mars -h` shows mars's help, not meridian's
- `meridian mars --version` shows mars's version
- If mars is not on PATH, print an error with install instructions (npm + cargo)
- `meridian -h` lists `mars` as a subcommand with a brief description

No managed binary / auto-download. No version checking. Mars on PATH or helpful error. Keep it simple.

## Non-Goals

- Windows support
- Auto-downloading / managed mars binary from meridian
- Version coupling between meridian and mars
- Mars self-update mechanism
- Meridian Rust rewrite (separate future effort)

## Success Criteria

- `npm i -g @mars-agents/cli && mars --version` works on all 3 platforms
- GitHub Release for a mars tag contains 3 platform binaries
- `meridian mars sync` passes through to mars correctly
- `meridian mars` with no mars installed gives clear install instructions
