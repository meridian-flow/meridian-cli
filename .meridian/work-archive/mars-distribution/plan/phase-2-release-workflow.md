# Phase 2: Release Workflow

## Scope

Create `.github/workflows/release.yml` in the mars-agents repo — the complete CI pipeline triggered on `v*` tags that builds binaries, creates a GitHub Release, and publishes npm packages.

## Files to Create

### `.github/workflows/release.yml`

Full workflow with three jobs:

```yaml
name: Release

on:
  push:
    tags: ["v*"]

env:
  CARGO_TERM_COLOR: always

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

  npm-publish:
    name: Publish npm packages
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
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

## Design References

- Build matrix targets and runners: [release-workflow.md](../design/release-workflow.md) § "Build Matrix"
- npm publish order and logic: [release-workflow.md](../design/release-workflow.md) § "npm Publish Job"
- Package structure being published: [npm-packages.md](../design/npm-packages.md)

## Verification Criteria

- [ ] `yamllint .github/workflows/release.yml` or `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` passes
- [ ] Workflow triggers only on `v*` tags (not branches)
- [ ] Build matrix covers all 3 targets with correct runners
- [ ] `github-release` and `npm-publish` jobs both `needs: build`
- [ ] Platform packages publish before CLI stub
- [ ] `NPM_TOKEN` secret is referenced (not hardcoded)
- [ ] `permissions` are declared at job level (least privilege)
- [ ] Version mismatch check exists before build
- [ ] Publish steps are idempotent (skip if version already exists on registry)

## Dependencies

- **Requires**: Phase 1 npm package files (the workflow references `npm/@mars-agents/*/package.json`)
