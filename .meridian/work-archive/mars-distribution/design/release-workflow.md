# Release Workflow — GitHub Actions

## Trigger

```yaml
on:
  push:
    tags: ["v*"]
```

The workflow runs when a version tag is pushed. Tags follow `v{major}.{minor}.{patch}` (e.g., `v0.0.1`). The existing CI workflow (`ci.yml`) continues to run on push/PR — the release workflow is additive.

## Jobs Overview

```
release workflow
  ├─ build (matrix: 3 targets)     — compile + upload artifacts
  ├─ github-release (needs: build) — create release + attach binaries
  └─ npm-publish (needs: build)    — publish all 4 npm packages
```

## Build Matrix

| Target Triple | Runner | Artifact Name | npm Package |
|---|---|---|---|
| `x86_64-unknown-linux-gnu` | `ubuntu-latest` | `mars-linux-x64` | `@mars-agents/linux-x64` |
| `aarch64-apple-darwin` | `macos-latest` (ARM) | `mars-darwin-arm64` | `@mars-agents/darwin-arm64` |
| `x86_64-apple-darwin` | `macos-15-intel` | `mars-darwin-x64` | `@mars-agents/darwin-x64` |

### Build Job

Each matrix entry:

1. Checks out the repo
2. Installs the Rust toolchain (stable) with the target triple
3. Builds with `cargo build --release --target $TARGET`
4. Strips the binary (`strip` on macOS, `strip` on Linux)
5. Renames to the artifact name (e.g., `mars-linux-x64`)
6. Uploads as a GitHub Actions artifact

```yaml
jobs:
  build:
    name: Build (${{ matrix.target }})
    runs-on: ${{ matrix.runner }}
    strategy:
      matrix:
        include:
          - target: x86_64-unknown-linux-gnu
            runner: ubuntu-latest
            artifact: mars-linux-x64
          - target: aarch64-apple-darwin
            runner: macos-latest
            artifact: mars-darwin-arm64
          - target: x86_64-apple-darwin
            runner: macos-15-intel
            artifact: mars-darwin-x64
    steps:
      - uses: actions/checkout@v4

      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - uses: Swatinem/rust-cache@v2
        with:
          key: ${{ matrix.target }}

      - name: Build
        run: cargo build --release --target ${{ matrix.target }}

      - name: Strip binary
        run: strip target/${{ matrix.target }}/release/mars

      - name: Rename binary
        run: cp target/${{ matrix.target }}/release/mars ${{ matrix.artifact }}

      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact }}
          path: ${{ matrix.artifact }}
```

### Notes on macOS Runners

- `macos-latest` resolves to Apple Silicon (ARM64) runners as of 2024
- `macos-15-intel` is the Intel runner label (replacing retired `macos-13`). Available until ~Aug 2027 when GitHub drops x86_64 macOS entirely
- No cross-compilation needed: each target builds natively on its platform

### Notes on Linux

- `ubuntu-latest` provides glibc. The binary links against glibc dynamically, which is fine for standard Linux distributions
- musl builds are **not** included — mars requires `git` on PATH anyway, which implies a standard Linux environment. If musl demand emerges later, add `x86_64-unknown-linux-musl` to the matrix

## GitHub Release Job

Downloads all artifacts, creates a GitHub Release from the tag, and attaches binaries.

```yaml
  github-release:
    name: GitHub Release
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          path: artifacts/
          merge-multiple: true

      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: artifacts/mars-*
```

Release notes are auto-generated from commits since the last tag. Manual release notes can be edited after the fact.

## npm Publish Job

See [npm-packages.md](npm-packages.md) for the package structure this job publishes.

```yaml
  npm-publish:
    name: Publish npm packages
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write  # npm provenance
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"

      - uses: actions/download-artifact@v4
        with:
          path: artifacts/
          merge-multiple: true

      - name: Extract version from tag
        id: version
        run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"

      - name: Verify tag matches Cargo.toml
        run: |
          CARGO_VERSION=$(grep '^version' Cargo.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
          TAG_VERSION=${{ steps.version.outputs.version }}
          if [ "$CARGO_VERSION" != "$TAG_VERSION" ]; then
            echo "::error::Tag version ($TAG_VERSION) does not match Cargo.toml ($CARGO_VERSION)"
            exit 1
          fi

      - name: Prepare and publish platform packages
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: |
          VERSION=${{ steps.version.outputs.version }}

          publish_platform() {
            local pkg_dir=$1
            local binary=$2
            local pkg_name
            pkg_name=$(node -e "console.log(require('./$pkg_dir/package.json').name)")

            # Skip if already published (idempotent on re-run)
            if npm view "$pkg_name@$VERSION" version >/dev/null 2>&1; then
              echo "Skipping $pkg_name@$VERSION — already published"
              return 0
            fi

            (
              cd "$pkg_dir"
              npm version "$VERSION" --no-git-tag-version --allow-same-version
              cp "../../artifacts/$binary" mars
              chmod +x mars
              npm publish --provenance --access public
            )
          }

          publish_platform npm/@mars-agents/linux-x64 mars-linux-x64
          publish_platform npm/@mars-agents/darwin-arm64 mars-darwin-arm64
          publish_platform npm/@mars-agents/darwin-x64 mars-darwin-x64

      - name: Publish CLI stub package
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
        run: |
          VERSION=${{ steps.version.outputs.version }}

          # Skip if already published
          if npm view "@mars-agents/cli@$VERSION" version >/dev/null 2>&1; then
            echo "Skipping @mars-agents/cli@$VERSION — already published"
            exit 0
          fi

          (
            cd npm/@mars-agents/cli
            node -e "
              const pkg = require('./package.json');
              pkg.version = '$VERSION';
              for (const dep of Object.keys(pkg.optionalDependencies || {})) {
                pkg.optionalDependencies[dep] = '$VERSION';
              }
              require('fs').writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');
            "
            npm publish --provenance --access public
          )
```

### Publish Order

Platform packages **must** publish before the CLI stub. The CLI stub declares them as `optionalDependencies` — if they don't exist on the registry when npm resolves the CLI package, installation fails. The script handles this sequentially: platform packages first, CLI stub last.

## Secrets & Setup

### Required Repository Secrets

| Secret | Purpose |
|---|---|
| `NPM_TOKEN` | npm automation token with publish access to `@mars-agents` scope |

### One-Time Setup

1. **Create the `@mars-agents` npm org** — `npm org create mars-agents` (or via npmjs.com)
2. **Create an npm automation token** — Settings → Access Tokens → Granular Access Token with publish permission to `@mars-agents/*`
3. **Add `NPM_TOKEN` to repo secrets** — Settings → Secrets → Actions → New repository secret
4. **Verify `GITHUB_TOKEN` permissions** — The default `GITHUB_TOKEN` needs `contents: write` for creating releases (declared in the job's `permissions`)

## Release Process

To cut a release:

```bash
# In the mars-agents repo
# 1. Update version in Cargo.toml
# 2. Commit
git add Cargo.toml
git commit -m "release: v0.0.2"

# 3. Tag and push
git tag v0.0.2
git push origin main v0.0.2
```

The tag push triggers the release workflow. GitHub Release + npm packages are published automatically. `cargo install mars-agents` picks up the new version from crates.io separately (if/when crates.io publishing is added).

### Version Synchronization

The tag determines the npm package version. CI verifies the tag matches `Cargo.toml` — if they disagree, the workflow fails before building. This prevents `mars --version` (compiled from Cargo.toml) from disagreeing with the npm package version (from the tag).
