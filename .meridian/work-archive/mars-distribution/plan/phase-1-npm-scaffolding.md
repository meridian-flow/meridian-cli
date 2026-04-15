# Phase 1: npm Package Scaffolding

## Scope

Create the `npm/` directory in the mars-agents repo with all four package.json files and the bin/mars resolver shim. No publishing — just the files that CI will use.

## Files to Create

All paths relative to the mars-agents repo root.

### `npm/@mars-agents/linux-x64/package.json`

```json
{
  "name": "@mars-agents/linux-x64",
  "version": "0.0.1",
  "description": "mars binary for Linux x64",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/haowjy/mars-agents.git"
  },
  "os": ["linux"],
  "cpu": ["x64"],
  "libc": ["glibc"],
  "files": ["mars"]
}
```

### `npm/@mars-agents/darwin-arm64/package.json`

```json
{
  "name": "@mars-agents/darwin-arm64",
  "version": "0.0.1",
  "description": "mars binary for macOS ARM64 (Apple Silicon)",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/haowjy/mars-agents.git"
  },
  "os": ["darwin"],
  "cpu": ["arm64"],
  "files": ["mars"]
}
```

### `npm/@mars-agents/darwin-x64/package.json`

```json
{
  "name": "@mars-agents/darwin-x64",
  "version": "0.0.1",
  "description": "mars binary for macOS x64 (Intel)",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/haowjy/mars-agents.git"
  },
  "os": ["darwin"],
  "cpu": ["x64"],
  "files": ["mars"]
}
```

### `npm/@mars-agents/cli/package.json`

```json
{
  "name": "@mars-agents/cli",
  "version": "0.0.1",
  "description": "Mars — agent package manager for .agents/ directories",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/haowjy/mars-agents.git"
  },
  "bin": {
    "mars": "bin/mars"
  },
  "files": ["bin/mars"],
  "engines": {
    "node": ">=16"
  },
  "optionalDependencies": {
    "@mars-agents/linux-x64": "0.0.1",
    "@mars-agents/darwin-arm64": "0.0.1",
    "@mars-agents/darwin-x64": "0.0.1"
  }
}
```

### `npm/@mars-agents/cli/bin/mars`

The JS shim from [npm-packages.md](../design/npm-packages.md) § "Platform Resolver". Must be executable (`chmod +x`).

### `npm/.gitignore`

```
# Platform binaries are added at publish time, not checked in
@mars-agents/linux-x64/mars
@mars-agents/darwin-arm64/mars
@mars-agents/darwin-x64/mars
```

## Verification Criteria

- [ ] All 4 `package.json` files pass `node -e "JSON.parse(require('fs').readFileSync('package.json'))"` 
- [ ] `bin/mars` has `#!/usr/bin/env node` shebang and is executable
- [ ] `node -c npm/@mars-agents/cli/bin/mars` passes syntax check
- [ ] Platform packages have correct `os`/`cpu` values matching their names
- [ ] `.gitignore` prevents binary files from being committed

## Dependencies

None — this is the foundation phase.
