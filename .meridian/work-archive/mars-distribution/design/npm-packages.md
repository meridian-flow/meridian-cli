# npm Package Structure

Four packages under the `@mars-agents` scope, following the same pattern as biome (`@biomejs/biome` + `@biomejs/cli-*`).

## Package Hierarchy

```
@mars-agents/cli              ← user installs this
  ├── optionalDependencies:
  │   ├── @mars-agents/linux-x64
  │   ├── @mars-agents/darwin-arm64
  │   └── @mars-agents/darwin-x64
  └── bin/mars                ← JS shim that resolves platform binary
```

npm installs `@mars-agents/cli`, which declares the three platform packages as `optionalDependencies`. npm only installs the one matching the current `os` + `cpu`. The `bin/mars` shim finds and executes it.

## Platform Packages

Each platform package contains a single binary and declares `os`/`cpu` constraints so npm skips it on non-matching platforms. The Linux package also declares `libc: ["glibc"]` so npm skips it on musl-based systems (e.g., Alpine) where the glibc binary won't run.

### Directory Layout (in repo)

```
npm/
  @mars-agents/
    cli/
      package.json
      bin/
        mars           ← JS shim (checked in)
    linux-x64/
      package.json     ← checked in (binary added at publish time)
    darwin-arm64/
      package.json
    darwin-x64/
      package.json
```

The `mars` binary itself is **not** checked into the repo — CI copies the built binary into each platform package directory before `npm publish`.

### `@mars-agents/linux-x64/package.json`

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

### `@mars-agents/darwin-arm64/package.json`

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

### `@mars-agents/darwin-x64/package.json`

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

### Why No `bin` in Platform Packages

Unlike esbuild, the platform packages don't declare `bin`. The CLI stub package owns the `mars` command — its `bin/mars` shim resolves the correct platform binary. This avoids conflicts if multiple platform packages somehow get installed and avoids exposing internal package names as commands.

## CLI Stub Package

### `@mars-agents/cli/package.json`

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

### `@mars-agents/cli/bin/mars` — Platform Resolver

```javascript
#!/usr/bin/env node

const { execFileSync } = require("child_process");
const path = require("path");

const PLATFORMS = {
  "darwin arm64": "@mars-agents/darwin-arm64",
  "darwin x64": "@mars-agents/darwin-x64",
  "linux x64": "@mars-agents/linux-x64",
};

const key = `${process.platform} ${process.arch}`;
const pkg = PLATFORMS[key];

if (!pkg) {
  console.error(
    `mars: unsupported platform ${process.platform} ${process.arch}\n` +
    `Supported: linux-x64, darwin-arm64, darwin-x64\n` +
    `Try: cargo install mars-agents`
  );
  process.exit(1);
}

let binaryPath;
try {
  binaryPath = require.resolve(`${pkg}/mars`);
} catch {
  console.error(
    `mars: could not find binary package ${pkg}\n` +
    `This usually means the optional dependency was not installed.\n` +
    `Try reinstalling: npm i -g @mars-agents/cli\n` +
    `Or install from source: cargo install mars-agents`
  );
  process.exit(1);
}

try {
  const result = execFileSync(binaryPath, process.argv.slice(2), {
    stdio: "inherit",
    env: process.env,
  });
} catch (e) {
  // execFileSync throws on non-zero exit — forward the exit code
  process.exit(e.status ?? 1);
}
```

### Why `execFileSync` Instead of `spawnSync`

`execFileSync` with `stdio: "inherit"` transparently forwards stdin/stdout/stderr, and throws on non-zero exit (which we catch and forward). `spawnSync` would also work but requires manually reading `.status`. Either is fine — biome uses `spawnSync`, we use `execFileSync` for slightly simpler error handling.

### Why No `postinstall`

Biome doesn't use `postinstall` and neither do we. The `os`/`cpu` fields in platform packages handle platform selection at install time — npm only downloads the matching package. The `bin/mars` shim handles resolution at runtime. This avoids:

- Breakage when users run `npm install --ignore-scripts`
- Lifecycle script security warnings
- Extra complexity in CI

## Resolution Flow

```
User runs: npm i -g @mars-agents/cli
  │
  ├─ npm reads @mars-agents/cli/package.json
  ├─ npm installs optionalDependencies
  │    ├─ @mars-agents/linux-x64    → skipped (os mismatch) or installed
  │    ├─ @mars-agents/darwin-arm64 → skipped (os/cpu mismatch) or installed
  │    └─ @mars-agents/darwin-x64   → skipped (os/cpu mismatch) or installed
  ├─ npm links bin/mars to PATH
  │
User runs: mars --version
  │
  ├─ Node executes bin/mars
  ├─ Shim checks process.platform + process.arch
  ├─ require.resolve("@mars-agents/darwin-arm64/mars")
  └─ execFileSync(binaryPath, args)
```

## Package Manager Compatibility

| Manager | `optionalDependencies` + `os`/`cpu` | Status |
|---|---|---|
| npm ≥7 | ✅ native support | Works |
| yarn (classic) | ✅ native support | Works |
| yarn (berry/PnP) | ⚠️ needs `supportedArchitectures` in `.yarnrc.yml` | Works with config |
| pnpm | ✅ native support | Works |
| bun | ✅ native support | Works |

This is the same compatibility profile as esbuild and biome — it's a well-trodden pattern.
