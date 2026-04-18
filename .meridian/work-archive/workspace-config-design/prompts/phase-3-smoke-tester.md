# Phase 3 Smoke Test: User-Level State Root

## Test Objectives

Verify the UUID-based user-level state model works end-to-end:

1. **Default spawn state location** — spawn creates state under `~/.meridian/projects/<UUID>/`
2. **UUID generation** — first spawn creates `.meridian/id` with a valid UUID
3. **Project move continuity** — moving the project folder preserves UUID and finds existing state
4. **MERIDIAN_HOME override** — setting MERIDIAN_HOME redirects the user state root
5. **MERIDIAN_STATE_ROOT override** — explicit state root override still works
6. **Repo paths stay repo-scoped** — fs/ and work/ still go to repo `.meridian/`

## Test Procedure

### Test 1: Default spawn creates user-level state

```bash
# Create a temp directory as a test project
cd /tmp
rm -rf test-uuid-state
mkdir test-uuid-state
cd test-uuid-state
git init

# Run a simple spawn (use a fast model)
uv run meridian spawn -m gpt-5.4-mini -p "echo hello" --desc "test spawn"

# Verify:
# 1. .meridian/id exists and contains a valid UUID
cat .meridian/id

# 2. Check user state location
ls -la ~/.meridian/projects/$(cat .meridian/id)/
# Should see spawns.jsonl, sessions.jsonl, spawns/

# 3. Verify repo .meridian/ does NOT have spawns.jsonl
ls .meridian/spawns.jsonl 2>&1 || echo "Good: no repo-level spawns.jsonl"
```

### Test 2: MERIDIAN_HOME override

```bash
cd /tmp/test-uuid-state

# Create custom home
rm -rf /tmp/custom-meridian-home
mkdir -p /tmp/custom-meridian-home

# Run with MERIDIAN_HOME set
MERIDIAN_HOME=/tmp/custom-meridian-home uv run meridian spawn -m gpt-5.4-mini -p "echo test" --desc "home override test"

# Verify state went to custom location
ls -la /tmp/custom-meridian-home/projects/$(cat .meridian/id)/
```

### Test 3: Project move preserves UUID

```bash
# Move the project
cd /tmp
mv test-uuid-state test-uuid-state-moved
cd test-uuid-state-moved

# Run another spawn
uv run meridian spawn -m gpt-5.4-mini -p "echo moved" --desc "after move"

# Verify same UUID was used
cat .meridian/id

# Verify state is accessible
uv run meridian spawn list
```

### Test 4: MERIDIAN_FS_DIR and MERIDIAN_WORK_DIR stay repo-scoped

```bash
cd /tmp/test-uuid-state-moved

# Check that MERIDIAN_FS_DIR points to repo .meridian/fs
uv run meridian spawn -m gpt-5.4-mini -p 'echo $MERIDIAN_FS_DIR' --desc "fs dir test"

# The value should contain the repo path, not ~/.meridian/
```

## Expected Results

- UUID is a valid 36-character UUID v4 string
- User state (`spawns.jsonl`, `sessions.jsonl`, `spawns/`) lives under `~/.meridian/projects/<UUID>/`
- Repo `.meridian/` only contains `id`, `work/`, `fs/`, `.gitignore` — no runtime state
- MERIDIAN_HOME override redirects user state root
- MERIDIAN_STATE_ROOT override short-circuits UUID resolution

Report verification results for each test.
