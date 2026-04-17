# Workspace Init and Inspection

Validate workspace file bootstrap, inspection surfacing, and invalid-workspace
launch gating.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-workspace.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: workspace smoke repo ready" || echo "FAIL: setup failed"
```

### WS-1. `workspace init` creates local workspace file [CRITICAL]

```bash
uv run meridian workspace init >/tmp/meridian-workspace-init.txt && \
test -f "$SMOKE_REPO/workspace.local.toml" && \
grep -q 'workspace.local.toml' "$SMOKE_REPO/.git/info/exclude" && \
grep -q '^created:' /tmp/meridian-workspace-init.txt && \
echo "PASS: workspace init created local file and local gitignore coverage" || echo "FAIL: workspace init did not scaffold correctly"
```

### WS-2. `workspace init` is idempotent [IMPORTANT]

```bash
uv run meridian workspace init >/tmp/meridian-workspace-init-2.txt && \
grep -q '^exists:' /tmp/meridian-workspace-init-2.txt && \
[ "$(grep -c '^workspace.local.toml$' "$SMOKE_REPO/.git/info/exclude")" -eq 1 ] && \
echo "PASS: workspace init is idempotent" || echo "FAIL: workspace init idempotency failed"
```

### WS-3. `config show` and `doctor` surface workspace findings [CRITICAL]

```bash
cat > "$SMOKE_REPO/workspace.local.toml" <<'EOF'
future = "value"
[[context-roots]]
path = "./missing-root"
extra = "kept"
EOF
uv run meridian config show >/tmp/meridian-workspace-config-show.txt && \
uv run meridian doctor >/tmp/meridian-workspace-doctor.txt && \
grep -q '^workspace.status = present' /tmp/meridian-workspace-config-show.txt && \
grep -q 'workspace.roots.missing = 1' /tmp/meridian-workspace-config-show.txt && \
grep -q 'workspace_unknown_key' /tmp/meridian-workspace-config-show.txt && \
grep -q 'workspace_missing_root' /tmp/meridian-workspace-doctor.txt && \
echo "PASS: workspace findings surfaced in config show and doctor" || echo "FAIL: workspace findings were not surfaced"
```

### WS-4. Invalid workspace is fatal for launch-dependent commands [CRITICAL]

```bash
cat > "$SMOKE_REPO/workspace.local.toml" <<'EOF'
[[context-roots]]
EOF
if uv run meridian --json spawn -p "workspace invalid gate probe" --dry-run >/tmp/meridian-workspace-gate.out 2>&1; then
  echo "FAIL: spawn dry-run unexpectedly succeeded with invalid workspace"
elif grep -q 'Invalid workspace file' /tmp/meridian-workspace-gate.out; then
  echo "PASS: invalid workspace gated launch-dependent command"
else
  echo "FAIL: invalid workspace error message missing"
fi
```
