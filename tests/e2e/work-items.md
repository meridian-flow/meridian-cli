# Work Items

Smoke checks for directory-as-authority work item storage.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-cli
export SMOKE_REPO="$(mktemp -d /tmp/meridian-work-items.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_PROJECT_DIR="$SMOKE_REPO"
export MERIDIAN_RUNTIME_DIR="$SMOKE_REPO/.meridian"
cd "$REPO_ROOT"
```

## 1. Migration From Legacy `work-items/*.json`

```bash
mkdir -p "$MERIDIAN_RUNTIME_DIR/work-items"
echo '{"name":"legacy-item","status":"open","description":"test","created_at":"2026-01-01T00:00:00Z"}' > "$MERIDIAN_RUNTIME_DIR/work-items/legacy-item.json"
mkdir -p "$MERIDIAN_RUNTIME_DIR/work/legacy-item"

uv run meridian work list

ls "$MERIDIAN_RUNTIME_DIR/work/legacy-item/__status.json"
```

## 2. Manually Created Work Dir Becomes Visible

```bash
mkdir -p "$MERIDIAN_RUNTIME_DIR/work/manual-item"
uv run meridian work list
```

## 3. Archive Crash-Recovery (heal on read)

```bash
uv run meridian work start crash-test
touch "$MERIDIAN_RUNTIME_DIR/work/crash-test/notes.md"

mkdir -p "$MERIDIAN_RUNTIME_DIR/archive/work"
mv "$MERIDIAN_RUNTIME_DIR/work/crash-test" "$MERIDIAN_RUNTIME_DIR/archive/work/"

uv run meridian work list --done
```

## 4. Rename Active And Archived Items

```bash
uv run meridian work start rename-test
uv run meridian work rename rename-test renamed-active
uv run meridian work done renamed-active
uv run meridian work rename renamed-active renamed-archived
uv run meridian work list --done
```

## 5. Delete Empty Item Vs Item With Artifacts

```bash
uv run meridian work start empty-item
uv run meridian work delete empty-item

uv run meridian work start artifact-item
touch "$MERIDIAN_RUNTIME_DIR/work/artifact-item/notes.md"
uv run meridian work delete artifact-item
uv run meridian work delete artifact-item --force
```

## 6. `work list --done -n` And `--all`

```bash
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  uv run meridian work start "done-item-$i"
  uv run meridian work done "done-item-$i"
done
uv run meridian work list --done
uv run meridian work list --done -n 5
uv run meridian work list --done --all
```
