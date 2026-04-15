# Phase 3: Smoke Test

## Scope

Validate the artifacts from phases 1-2 locally before the first real release. No code changes — verification only.

## Verification Steps

### 1. JSON validity — all package.json files parse correctly

```bash
for f in npm/@mars-agents/*/package.json; do
  echo "Checking $f..."
  node -e "JSON.parse(require('fs').readFileSync('$f', 'utf8'))"
done
```

### 2. JS shim syntax check

```bash
node -c npm/@mars-agents/cli/bin/mars
```

### 3. Workflow YAML validity

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

### 4. Platform package os/cpu correctness

```bash
node -e "
  const checks = [
    ['npm/@mars-agents/linux-x64/package.json', 'linux', 'x64'],
    ['npm/@mars-agents/darwin-arm64/package.json', 'darwin', 'arm64'],
    ['npm/@mars-agents/darwin-x64/package.json', 'darwin', 'x64'],
  ];
  for (const [file, os, cpu] of checks) {
    const pkg = JSON.parse(require('fs').readFileSync(file, 'utf8'));
    console.assert(pkg.os[0] === os, file + ' os mismatch');
    console.assert(pkg.cpu[0] === cpu, file + ' cpu mismatch');
    console.log(file + ' ✓');
  }
"
```

### 5. CLI stub optionalDependencies match platform package names

```bash
node -e "
  const cli = JSON.parse(require('fs').readFileSync('npm/@mars-agents/cli/package.json', 'utf8'));
  const expected = ['@mars-agents/linux-x64', '@mars-agents/darwin-arm64', '@mars-agents/darwin-x64'];
  for (const dep of expected) {
    console.assert(dep in cli.optionalDependencies, 'Missing: ' + dep);
    console.log(dep + ' ✓');
  }
"
```

### 6. Shim resolves current platform (local test)

```bash
# Build mars locally
cargo build --release

# Create a fake node_modules structure to test resolution
mkdir -p /tmp/mars-npm-test/node_modules/@mars-agents/$(node -e "
  const map = {'darwin arm64':'darwin-arm64','darwin x64':'darwin-x64','linux x64':'linux-x64'};
  console.log(map[process.platform + ' ' + process.arch]);
")
cp target/release/mars /tmp/mars-npm-test/node_modules/@mars-agents/*/mars

# Run the shim with NODE_PATH set
NODE_PATH=/tmp/mars-npm-test/node_modules node npm/@mars-agents/cli/bin/mars --version

# Clean up
rm -rf /tmp/mars-npm-test
```

### 7. First real release checklist (manual, after setup steps)

- [ ] `@mars-agents` npm org exists
- [ ] `NPM_TOKEN` secret is set in GitHub repo settings
- [ ] GitHub Actions workflow permissions allow `contents: write`
- [ ] Push `v0.0.1` tag and monitor the Actions run
- [ ] Verify GitHub Release has 3 binary assets
- [ ] Verify `npm view @mars-agents/cli` shows published package
- [ ] Test `npm i -g @mars-agents/cli && mars --version` on a clean machine

## Dependencies

- **Requires**: Phase 1 (npm files) and Phase 2 (workflow file)
