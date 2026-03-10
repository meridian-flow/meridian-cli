# Sync Install Cycle

This is the full scratch-repo round trip for sync: install a source, verify materialization, update it, and remove it cleanly. Always override both `MERIDIAN_REPO_ROOT` and `MERIDIAN_STATE_ROOT` here.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
rm -rf /tmp/meridian-sync-src /tmp/meridian-sync-repo
mkdir -p /tmp/meridian-sync-src/skills/demo /tmp/meridian-sync-src/agents /tmp/meridian-sync-repo
git -C /tmp/meridian-sync-repo init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT=/tmp/meridian-sync-repo
export MERIDIAN_STATE_ROOT=/tmp/meridian-sync-repo/.meridian
export UV_CACHE_DIR=/tmp/uv-cache
mkdir -p "$UV_CACHE_DIR"
cat > /tmp/meridian-sync-src/skills/demo/SKILL.md <<'EOF'
# Demo Skill

Body content.
EOF
cat > /tmp/meridian-sync-src/agents/helper.md <<'EOF'
# Helper Agent

Does things.
EOF
cd "$REPO_ROOT"
test "$MERIDIAN_STATE_ROOT" = "/tmp/meridian-sync-repo/.meridian" && echo "PASS: sync setup isolated both env vars" || echo "FAIL: sync setup leaked env vars"
```

### SYNC-1. Install materializes skills and agents [CRITICAL]

```bash
uv run meridian sync install /tmp/meridian-sync-src --name smoke-source >/tmp/meridian-sync-install.out 2>&1 && \
test -f /tmp/meridian-sync-repo/.agents/skills/demo/SKILL.md && \
test -f /tmp/meridian-sync-repo/.agents/agents/helper.md && \
test -f /tmp/meridian-sync-repo/.meridian/config.toml && \
test -f /tmp/meridian-sync-repo/.meridian/sync.lock && \
echo "PASS: sync install materialized expected files" || echo "FAIL: sync install did not materialize expected files"
```

### SYNC-2. Status reports the repo as in sync [IMPORTANT]

```bash
uv run meridian sync status >/tmp/meridian-sync-status.out 2>&1 && \
grep -Eiq 'in sync|ok|clean' /tmp/meridian-sync-status.out && \
echo "PASS: sync status reported a healthy state" || echo "FAIL: sync status output was unexpected"
```

### SYNC-3. Update pulls source changes into managed files [IMPORTANT]

```bash
printf '\n## Updated upstream\n' >> /tmp/meridian-sync-src/agents/helper.md && \
uv run meridian sync update >/tmp/meridian-sync-update.out 2>&1 && \
grep -q 'Updated upstream' /tmp/meridian-sync-repo/.agents/agents/helper.md && \
echo "PASS: sync update refreshed managed content" || echo "FAIL: sync update missed source changes"
```

### SYNC-4. Remove cleans up the managed source [IMPORTANT]

```bash
uv run meridian sync remove smoke-source >/tmp/meridian-sync-remove.out 2>&1 && \
test ! -e /tmp/meridian-sync-repo/.agents/skills/demo && \
test ! -e /tmp/meridian-sync-repo/.agents/agents/helper.md && \
echo "PASS: sync remove cleaned managed artifacts" || echo "FAIL: sync remove left managed artifacts behind"
```

### SYNC-5. Remote GitHub install works for a real repo [IMPORTANT]

Run this when you changed remote source resolution, lock semantics, or `.claude/` materialization. This complements the local-path round trip above.

```bash
rm -rf /tmp/meridian-sync-gh-repo
mkdir -p /tmp/meridian-sync-gh-repo
git -C /tmp/meridian-sync-gh-repo init --quiet
export MERIDIAN_REPO_ROOT=/tmp/meridian-sync-gh-repo
export MERIDIAN_STATE_ROOT=/tmp/meridian-sync-gh-repo/.meridian
export UV_CACHE_DIR=/tmp/uv-cache
uv run meridian sync install haowjy/orchestrate --name orchestrate >/tmp/meridian-sync-gh-install.out 2>&1 && \
uv run meridian sync status >/tmp/meridian-sync-gh-status.out 2>&1 && \
grep -q '"source_value": "haowjy/orchestrate"' /tmp/meridian-sync-gh-repo/.meridian/sync.lock && \
grep -q '"status": "in-sync"' /tmp/meridian-sync-gh-status.out && \
test -L /tmp/meridian-sync-gh-repo/.claude/skills/orchestrate && \
echo "PASS: remote GitHub sync installed and locked a real source" || echo "FAIL: remote GitHub sync did not behave as expected"
```
