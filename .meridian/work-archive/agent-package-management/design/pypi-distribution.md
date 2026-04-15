# Distributing a Rust Binary (mars-agents) via PyPI

## Question

Can `mars-agents` (a Rust CLI binary) be bundled with `meridian-channel` (a Python package) so that `uv tool install meridian-channel` gives users both `meridian` and `mars`?

## Answer: Yes, Multiple Proven Patterns Exist

### Pattern 1: Maturin `bindings = "bin"` (Recommended for mars-agents)

This is how **ruff**, **uv**, and other Astral tools ship Rust binaries via PyPI.

**How it works:**
- Maturin compiles the Rust binary and packages it into platform-specific wheels
- The binary goes into the wheel's `scripts` directory, landing on `PATH` when installed
- PyPI hosts separate wheels per platform (linux-x86_64, macos-arm64, windows-x86_64, etc.)
- `pip install` / `uv pip install` selects the correct wheel automatically

**pyproject.toml for mars-agents:**
```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[project]
name = "mars-agents"
version = "0.1.0"

[tool.maturin]
bindings = "bin"
strip = true
```

**CI builds** use maturin's cross-compilation support or platform-specific runners to produce wheels for ~10+ targets. Maturin handles manylinux compliance automatically via its built-in auditwheel reimplementation.

### Pattern 2: meridian-channel depends on mars-agents

Once mars-agents publishes its own wheels to PyPI:

```toml
# meridian-channel's pyproject.toml
[project]
dependencies = [
    "mars-agents>=0.1.0",
    # ... other deps
]
```

Then `uv tool install meridian-channel` installs both. The `mars` binary lands in the venv's `bin/` alongside `meridian`. This is exactly how any Python package can pull in a native binary dependency -- the wheel format handles it transparently.

### Pattern 3: Wrapper package (how pyright does it)

Pyright on PyPI is a pure-Python wrapper that downloads the real Node.js binary at runtime. This avoids building platform wheels but adds runtime download complexity. **Not recommended** -- maturin is strictly better for Rust.

## Concrete Plan for mars-agents

1. **mars-agents repo** adds a `pyproject.toml` with maturin `bindings = "bin"`
2. **CI** (GitHub Actions) builds platform wheels using `maturin build --release` on matrix runners (linux x86_64/aarch64, macos x86_64/arm64, windows x86_64)
3. **Publish** wheels to PyPI with `uv publish` or `maturin publish`
4. **meridian-channel** adds `mars-agents` as a dependency in its `pyproject.toml`
5. `uv tool install meridian-channel` now installs both binaries

## Precedent

| Tool | Language | Build Tool | PyPI Package | Binary on PATH |
|------|----------|------------|--------------|----------------|
| ruff | Rust | maturin | `ruff` | `ruff` |
| uv | Rust | maturin | `uv` | `uv` |
| pyright | TypeScript | runtime download | `pyright` | `pyright` |
| orjson | Rust | maturin | `orjson` | (library, not CLI) |

## Key Considerations

- **Wheel size**: Rust binaries are typically 10-30MB per platform. `strip = true` helps.
- **Platform coverage**: Must build wheels for every platform you want to support. No wheel = no install. Maturin + GitHub Actions matrix covers the common ones easily.
- **Version coupling**: mars-agents and meridian-channel can version independently. meridian-channel pins a minimum mars-agents version.
- **Fallback**: Users with unsupported platforms can `cargo install mars-agents` directly and meridian can detect `mars` on PATH regardless of how it was installed.
