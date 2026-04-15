# Decisions — Mars Distribution

## 1. Biome pattern over esbuild pattern for npm distribution

**Decision**: Follow biome's approach (no postinstall, JS shim resolver) rather than esbuild's (postinstall `install.js`).

**Reasoning**: esbuild uses `postinstall: "node install.js"` to verify the binary and optimize the bin path. Biome skips postinstall entirely — the `os`/`cpu` fields handle platform selection at npm install time, and a bin shim resolves the binary at runtime. The biome approach is:
- Simpler (no install.js to maintain)
- Works with `--ignore-scripts` (common in CI and security-conscious environments)
- Fewer moving parts to debug

**Rejected**: esbuild's postinstall approach. The install.js does useful things (verifies binary version, optimizes the bin symlink to skip the JS shim), but these are optimizations mars doesn't need. Mars is a CLI tool invoked occasionally, not a build tool called thousands of times per build — the ~5ms JS shim overhead is irrelevant.

## 2. No WASM fallback

**Decision**: If the platform binary isn't found, fail with clear error and instructions.

**Reasoning**: Mars is a CLI tool that manages `.agents/` directories and runs git operations. There's no meaningful WASM fallback — it needs filesystem access and git on PATH. Users on unsupported platforms can use `cargo install mars-agents`.

**Rejected**: WASM build for universal fallback (like esbuild-wasm). Not worth the complexity for a CLI tool with 3 well-covered platforms.

## 3. Tag as version source of truth for npm

**Decision**: The git tag (`v0.0.1` → `0.0.1`) determines the npm package version. CI extracts it from `GITHUB_REF_NAME` and asserts it matches `Cargo.toml` before building.

**Reasoning**: The tag is the explicit release intent — it's what triggers the workflow. The version assertion prevents `mars --version` (from Cargo.toml) from disagreeing with the npm package version (from the tag). Both must agree for the release to proceed.

**Rejected**: Using Cargo.toml as the sole source (requires parsing in CI, tag still needed for trigger). Also rejected: no assertion at all (allows silent version drift).

## 4. No `bin` field in platform packages

**Decision**: Platform packages (`@mars-agents/linux-x64` etc.) declare `files` but not `bin`. Only `@mars-agents/cli` declares `bin: { "mars": "bin/mars" }`.

**Reasoning**: If platform packages declared `bin`, npm might create conflicting command entries. The CLI stub owns the command name — platform packages are implementation details. This matches biome's approach (biome platform packages don't declare bin either).

**Rejected**: Declaring `bin` in platform packages (like esbuild does). Adds confusion and potential conflicts.

## 5. Native builds only, no cross-compilation

**Decision**: Each target builds on its native platform (Linux on ubuntu-latest, macOS ARM on macos-latest, macOS Intel on macos-13). No cross-compilation.

**Reasoning**: GitHub Actions provides all three runner types natively. Cross-compilation for macOS from Linux would require additional toolchain setup and is fragile. Native builds are simpler and more reliable.

**Rejected**: Cross-compiling all targets from a single Linux runner (using cross-rs or cargo-zigbuild). Adds toolchain complexity without benefit since GitHub provides native runners.

## 6. No musl Linux build

**Decision**: Only glibc Linux build (`x86_64-unknown-linux-gnu`). No musl variant.

**Reasoning**: Mars requires `git` on PATH for some operations, implying a standard Linux environment with glibc. Alpine/musl users are a small minority for this tool. Can be added later as an additional matrix entry if demand emerges.

**Rejected**: Including `x86_64-unknown-linux-musl` in the initial matrix. Low demand, easy to add later.

## 7. npm packages live in the mars-agents repo

**Decision**: The `npm/` directory containing all package.json files and the bin shim lives in the mars-agents repo alongside the Rust source.

**Reasoning**: Keeps the release workflow self-contained — one repo, one CI workflow, one tag triggers everything. No cross-repo coordination needed.

**Rejected**: Separate npm repo. Adds release coordination complexity for no benefit.

## 8. Idempotent npm publish (added post-review)

**Decision**: Each `npm publish` step checks if the version already exists on the registry and skips if so. This makes the workflow safe to re-run after partial failures.

**Reasoning**: Reviewer (gpt-5.4) flagged that if platform package 2 of 3 fails, re-running the workflow would fail on the already-published package 1 before reaching the failed package 2. `npm view "$pkg@$VERSION" version` checks existence before publish.

## 9. Tag-Cargo.toml version assertion (added post-review)

**Decision**: CI verifies the tag version matches `Cargo.toml` before building. Mismatch fails the workflow.

**Reasoning**: Reviewer (gpt-5.4) flagged that without this check, `mars --version` (compiled from Cargo.toml) could disagree with the npm package version (from the tag). The assertion prevents this drift.

## 10. `libc: ["glibc"]` on Linux package (added post-review)

**Decision**: The `@mars-agents/linux-x64` package declares `libc: ["glibc"]` alongside `os` and `cpu`.

**Reasoning**: Reviewer (gpt-5.4) flagged that without the `libc` field, npm on musl-based systems (Alpine Linux) would install the glibc binary, which can't run there. Biome uses this same field for their glibc packages. This prevents silent failures on Alpine.

## 11. `macos-15-intel` runner (added post-review)

**Decision**: Use `macos-15-intel` for x86_64 macOS builds, not `macos-13`.

**Reasoning**: Reviewer (gpt-5.4) flagged that GitHub retired `macos-13` runners in Dec 2025. `macos-15-intel` is the replacement, available until ~Aug 2027. After that, x86_64 macOS builds will require cross-compilation or a self-hosted runner.
