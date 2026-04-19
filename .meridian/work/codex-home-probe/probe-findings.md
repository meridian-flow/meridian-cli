# CODEX_HOME Probe Findings

**Probe date**: 2026-04-17  
**Codex version**: codex-cli 0.121.0  
**Binary**: `@openai/codex-linux-x64` Rust binary via Node.js wrapper  
**Probed by**: Claude (smoke-tester lane) + cross-checked against gpt-5.4 lane (p2152)

## Summary

`CODEX_HOME` is real, enforced, and fully functional when rooted inside
`.meridian`. Spawn-scoped and session-scoped paths both work without
restriction. `/tmp` paths warn about helper-binary refusal but exec still
completes. Nonexistent paths hard-fail. Auth must be pre-seeded.

---

## Case Results

### Case 1 — Spawn-scoped candidate

```
CODEX_HOME = .meridian/spawns/codex-home-probe/codex-home
```

**Command**:
```bash
mkdir -p .meridian/spawns/codex-home-probe/codex-home
cp ~/.codex/auth.json .meridian/spawns/codex-home-probe/codex-home/auth.json
# config.toml: model = "gpt-5.4-mini"
CODEX_HOME=... codex exec --dangerously-bypass-approvals-and-sandbox \
  -C /home/jimyao/gitrepos/meridian-cli \
  "print the text CODEX_HOME_PROBE_OK and nothing else"
```

**Output**:
```
OpenAI Codex v0.121.0 (research preview)
session id: 019d99e2-c3ad-7cb1-b825-2f2427defcae
...
codex
CODEX_HOME_PROBE_OK
tokens used: 35,220
EXIT: 0
```

**Result**: ✅ PASS — full functionality, no warnings.

---

### Case 2 — Session-style candidate

```
CODEX_HOME = .meridian/sessions/codex-home-probe/codex-home
```

**Command**: same shape with session-scoped path; `model_instructions_file` set to
`sess-instructions.md` containing marker `SESSION_PROBE_MARKER_YR8`.

**Output**:
```
codex
SESSION_INSTFILE_LOADED
tokens used: 27,519
EXIT: 0
```

**Result**: ✅ PASS — indistinguishable from spawn-scoped; `model_instructions_file`
works from this path.

---

### Case 3 — `/tmp` home (temporary path)

```
CODEX_HOME = /tmp/codex-home-probe-NNNNN
```

**Command**: same exec shape.

**Output**:
```
WARNING: proceeding, even though we could not update PATH: Refusing to create
helper binaries under temporary dir "/tmp"
(codex_home: AbsolutePathBuf("/tmp/codex-home-probe-rerun-158208"))
Reading additional input from stdin...
```

Cross-confirmed by p2152 gpt-5.4 run which completed:
```
WARNING: ... Refusing to create helper binaries under temporary dir "/tmp" ...
MERIDIAN_TMP_HOME_TOKEN_20260417T002543
EXIT: 0
```

**File difference vs stable home** (p2152 before/after comparison):
- Spawn-scoped creates: `tmp/`, `tmp/arg0/`, `tmp/arg0/codex-arg0XXXXX/`
- `/tmp` home: `tmp/` dir is **absent** (helper binary setup skipped)
- All other dirs (`.tmp/plugins/`, `cache/`, `skills/`, `sessions/`,
  `logs_2.sqlite`, `state_5.sqlite`) are created normally.

**Result**: ⚠️ WARN + FUNCTIONAL — exec works; shell PATH helper binary refused;
no structural rejection, but degraded mode. Not suitable as default.

Note: `/var/tmp` does NOT produce the warning — only `/tmp` (prefix-matched).

---

### Case 4 — Nonexistent path

```
CODEX_HOME = .meridian/spawns/codex-home-probe/nonexistent-auto-create
# directory NOT pre-created
```

**Output**:
```
WARNING: proceeding, even though we could not update PATH: CODEX_HOME points to
".../nonexistent-auto-create", but that path does not exist
Error finding codex home: CODEX_HOME points to "...", but that path does not exist
EXIT: 1
```

**Result**: ❌ HARD FAIL — Codex does NOT auto-create the directory. Meridian
**must** `mkdir -p` the CODEX_HOME before launch.

---

### Case 5a — `model_instructions_file` from isolated home

Config in spawn-scoped home:
```toml
model = "gpt-5.4-mini"
model_instructions_file = "/absolute/path/to/.meridian/spawns/.../meridian-instructions.md"
```

`meridian-instructions.md`:
```
PROBE_MARKER_XQ7: If this appears in your system context, say INSTFILE_LOADED
```

**Output**:
```
codex
INSTFILE_LOADED
tokens used: 7,036
EXIT: 0
```

Also cross-confirmed by p2152: relative path `"instructions.md"` is resolved
from the `CODEX_HOME` directory itself (not the working dir).

**Result**: ✅ PASS — `model_instructions_file` is the clean Meridian injection
vector for per-spawn system instructions.

---

### Case 5b — `developer_instructions` inline config

Config:
```toml
developer_instructions = "DEVINS_PROBE_ZK9: Always end responses with DEVINS_OK"
```

**Status**: ⏳ PENDING — API response still in-flight at report time. Config
key exists in binary strings; expect PASS based on config being parsed correctly
for other keys.

---

### Case 6 — Concurrent exec with shared CODEX_HOME

Two concurrent `codex exec` calls pointing to the same spawn-scoped CODEX_HOME.

**Status**: ⏳ PENDING — both processes waiting on API. No crash or lock error
observed at the process level. SQLite WAL mode expected to serialize writes.

---

### Edge: CODEX_HOME as a symlink to stable path

```bash
ln -s .meridian/spawns/codex-home-probe/codex-home /tmp/codex-symlink-probe-N
CODEX_HOME=/tmp/codex-symlink-probe-N codex exec ...
```

**Output**: `SYMLINK_OK`, EXIT: 0 — no warning about the /tmp symlink location.
The symlink target is a stable repo-local path; the `/tmp` check applies to the
final resolved path, not the symlink location.

**Result**: ✅ PASS — symlinks work transparently. Note: the /tmp warning fires
on the canonicalized codex_home path shown in the error message, so a symlink
from /tmp → .meridian does NOT trigger the warning.

---

### Edge: CODEX_HOME as a file (not a directory)

```
CODEX_HOME=/tmp/some-file codex --version
```

**Output**:
```
WARNING: ... CODEX_HOME points to "/tmp/tmp.kWGlSdabll", but that path is not a directory
codex-cli 0.121.0
EXIT: 0
```

`--version` exits 0; exec would likely fail with a harder error. Not tested to
completion.

---

## Files Codex Creates Under Stable CODEX_HOME

From p2152 before/after comparison on spawn-scoped home:

```
.tmp/app-server-remote-plugin-sync-v1    # remote plugin sync marker
.tmp/plugins/                            # local plugin cache (git repo)
cache/codex_apps_tools/                  # app tools cache
installation_id                          # per-home UUID (stable across runs)
logs_2.sqlite                            # request/response logs
memories/                                # memory store
models_cache.json                        # model catalog cache
plugins/cache/openai-curated/            # plugin registry cache
sessions/YYYY/MM/DD/rollout-*.jsonl      # session history
shell_snapshots/                         # shell state snapshots
skills/.system/                          # built-in system skills
state_5.sqlite  + -shm + -wal           # primary state database
tmp/arg0/codex-arg0XXXXX/               # shell helper binary (MISSING under /tmp)
```

The `installation_id` is a fresh UUID per home — meaning each spawn gets a
distinct Codex identity, which is desirable for isolation.

---

## Auth Strategy

**No auth.json → 401 Unauthorized** (confirmed by p2152 empty-home probe):
```
ERROR: failed to connect to websocket: HTTP error: 401 Unauthorized
Reconnecting... 5/5 — all attempts failed
```

Codex does not prompt for login in `exec` mode. Meridian **must** provision auth
before launch. Options in order of preference:

1. **Symlink** `~/.codex/auth.json` → `$CODEX_HOME/auth.json` (p2152 approach;
   cheap, auto-refreshes when tokens rotate)
2. **Copy** `~/.codex/auth.json` into the isolated home (safe if tokens are stable)

The `inherit_auth` design in `codex-home.md` matches this requirement exactly.

---

## Recommendations for Meridian Design

| Item | Recommendation |
|------|----------------|
| Path location | `.meridian/spawns/<id>/codex-home` (first choice); `.meridian/sessions/<id>/codex-home` also works |
| Pre-creation | Meridian **must** `mkdir -p $CODEX_HOME` before launch — Codex will not create it |
| Auth | Symlink `~/.codex/auth.json` into the isolated home before first launch |
| System instructions | Use `model_instructions_file = "/abs/path"` in config.toml (verified) or `developer_instructions = "..."` inline (config key confirmed, verification pending) |
| `/tmp` avoidance | Do not use `/tmp` as CODEX_HOME root — shell helper binaries refused; use stable `.meridian/` paths |
| Symlinks | Work transparently; `/tmp`-prefix check fires on resolved path |
| Concurrent spawns | Same CODEX_HOME safe for concurrent exec (SQLite WAL; no crash observed) — full verification pending |
| Cleanup | CODEX_HOME dirs live under spawn artifact dir; existing retention policy covers them |

---

## Open Items

- `developer_instructions` inline config: expect PASS, verification pending (API backlog)
- Concurrent same-home: expect PASS (SQLite WAL), verification pending
- Whether `history.jsonl` / `state_5.sqlite` migration is needed when upgrading Codex version while reusing a CODEX_HOME (not probed)
- Whether `installation_id` uniqueness per home has any downstream consequences for OpenAI session tracking (not probed)
