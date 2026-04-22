# Config Init, Show, Set

This file validates the full config mutation loop in an isolated repo: scaffold defaults, inspect resolved values, set an override, and reset it back to builtin state.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-config.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_PROJECT_DIR="$SMOKE_REPO"
export MERIDIAN_RUNTIME_DIR="$SMOKE_REPO/.meridian"
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: config smoke repo ready" || echo "FAIL: config smoke repo setup failed"
```

### CFG-1. Config init creates `meridian.toml` [CRITICAL]

```bash
uv run meridian config init >/tmp/meridian-config-init.txt && \
test -f "$SMOKE_REPO/meridian.toml" && \
grep -q 'meridian.toml' /tmp/meridian-config-init.txt && \
echo "PASS: config init created meridian.toml" || echo "FAIL: config init did not create meridian.toml"
```

### CFG-2. Config show exposes resolved values [CRITICAL]

```bash
uv run meridian config show >/tmp/meridian-config-show.txt && \
grep -q '^defaults.model:' /tmp/meridian-config-show.txt && \
grep -q '^timeouts.wait_minutes:' /tmp/meridian-config-show.txt && \
grep -q '^harness.codex:' /tmp/meridian-config-show.txt && \
echo "PASS: config show includes the expected key families" || echo "FAIL: config show output was incomplete"
```

### CFG-3. Config get reads a single key [CRITICAL]

```bash
uv run meridian config get defaults.model >/tmp/meridian-config-get.txt && \
grep -q '^defaults.model:' /tmp/meridian-config-get.txt && \
grep -Eq '\[source: (builtin|file|env)\]' /tmp/meridian-config-get.txt && \
echo "PASS: config get returned a resolved key" || echo "FAIL: config get output was unexpected"
```

### CFG-4. Config set persists an override [IMPORTANT]

```bash
uv run meridian config set defaults.model smoke-model >/tmp/meridian-config-set.txt && \
uv run meridian config get defaults.model >/tmp/meridian-config-after-set.txt && \
grep -q 'smoke-model' /tmp/meridian-config-after-set.txt && \
grep -q '\[source: file\]' /tmp/meridian-config-after-set.txt && \
echo "PASS: config set persisted an override" || echo "FAIL: config set did not persist the override"
```

### CFG-5. Config reset removes the override [IMPORTANT]

```bash
uv run meridian config reset defaults.model >/tmp/meridian-config-reset.txt && \
uv run meridian config get defaults.model >/tmp/meridian-config-after-reset.txt && \
grep -q '\[source: builtin\]' /tmp/meridian-config-after-reset.txt && \
! grep -q 'smoke-model' /tmp/meridian-config-after-reset.txt && \
echo "PASS: config reset restored builtin resolution" || echo "FAIL: config reset did not restore builtin resolution"
```
