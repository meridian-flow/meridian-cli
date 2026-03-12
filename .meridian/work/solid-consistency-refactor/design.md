# Design: Consistency, Frontend-Readiness, and Legibility Refactor

This revision replaces the prior SOLID & Consistency Refactor design. It incorporates findings from all previous reviews (`review-risk.md`, `review-design-quality.md`, `review-fresh-eyes.md`, `review-correctness.md`, and the source reviews they cite), a full codebase exploration, and an architectural reassessment against three explicit goals.

All code snippets below are illustrative, not final.

## Goals

1. **Squash bugs, be consistent.** Fix crash-causing defects, concurrency races, and inconsistencies that have produced or will produce incorrect behavior.
2. **Frontend-ready architecture.** Build the state infrastructure so a future `meridian view` web UI can read state efficiently, receive real-time updates, and display conversation history — without re-architecting the core.
3. **Codebase legibility for AI agents.** Meridian's primary users are AI agents. The agents it orchestrates are also the agents that read, modify, and extend its code. Single sources of truth, focused protocols, and predictable patterns directly reduce friction for agent exploration and implementation.

## Architecture Context

Meridian already has infrastructure that supports multiple surfaces:

- **Operation manifest** — typed operations with declared surfaces (`cli`, `mcp`), input/output models with `.to_wire()` serialization
- **MCP server** — persistent process exposing all manifest operations as tools via FastMCP
- **OutputSink protocol** — pluggable output routing (TextSink, JsonSink, AgentSink, NullSink)
- **Stream event observer** — `event_observer` callback in spawn execution for real-time stream parsing

What's missing for a frontend:

- **Observable state** — state changes are silent; no notification when a spawn finishes or a session starts
- **Queryable state** — every read re-scans the full JSONL file; no indexing or caching
- **Conversation model** — no unified representation of harness conversation history
- **Sink fan-out** — only one sink active at a time; no composite routing

What creates friction for agents exploring the codebase:

- **Duplicated JSONL mechanics** across spawn_store and session_store (locking, reading, timestamps, error handling — already drifted once, producing the Phase 1 bug)
- **Duplicated ops helpers** across spawn/execute.py, spawn/api.py, and work.py (`_runtime_context()`, `_state_root()`, `_resolve_chat_id()` with subtly different defaults)
- **Duplicated policy resolution** in primary launch (`prepare_launch_context()` and `build_harness_context()` both resolve model/harness/agent/skills independently)
- **Kitchen-sink harness protocol** (17 methods, DirectAdapter stubs 12 of them via base class defaults)
- **Wide function signatures** (`execute_with_finalization` takes 15+ parameters instead of a structured plan)
- **Inconsistent error semantics** (work-store rename raises ValueError, update raises KeyError, get returns None)

## Ship Order

Safety fixes ship first. Infrastructure phases build on each other. Legibility phases land alongside the infrastructure they clarify.

### Tier 1: Immediate Safety

1. Phase `10b` — primary-launch flock mutex
2. Phase `1` — malformed-event guard + dead code removal
3. Phase `12a.1` — heartbeat lifecycle wiring
4. Phase `12a.2` — stale-policy flip

### Tier 2: Consistent Foundations

5. Phase `2a` — shared JSONL event store mechanics
6. Phase `2b` — observable event store (observer hooks)
7. Phase `4` — ops helper consolidation
8. Phase `5` — async wrapper consistency
9. Phase `3b` — work-store mutation safety
10. Phase `3` — work-store error semantics

### Tier 3: Session Safety

11. Phase `6` — session lifecycle extraction
12. Phase `9a+9b` — session start lock ordering + generation-safe stale-session cleanup (shipped as one atomic commit — the window between them is unsafe because stale-session cleanup runs on every CLI startup)

### Tier 4: Legibility

13. Phase `6a` — resolved primary launch plan
14. Phase `6b` — prepared spawn plan DTO
15. Phase `7` — harness adapter protocol split (narrowed)
16. Phase `8` — CLI registration consolidation
17. Phase `11a` — spawn transition model

### Tier 5: Frontend-Ready Infrastructure

18. State projections (SpawnIndex, SessionIndex, WorkIndex; absorbs Phase `11b`)
19. Conversation model + per-adapter extractors
20. Sink fan-out (CompositeSink)

## Verification Gates

Each risky phase carries targeted verification. This closes the test-planning gap called out in `review-risk.md` §3.

- Phase `1`: confirm `list_spawns()` and `get_spawn()` survive a malformed JSONL row without crashing.
- Phase `2a`: unit tests for truncated trailing lines, mid-file malformed JSON, `ValidationError` skips, concurrent append serialization. CLI smoke for `spawn create/show/wait`.
- Phase `2b`: observer notification delivery tests. Test that observer exceptions do not propagate to callers.
- Phase `3b`: store tests for rename/update races and crash recovery from an in-progress rename intent.
- Phase `9a+9b` (atomic): multiprocessing tests for concurrent `start_session()`, `stop_session()`, and stale cleanup on reused chat IDs with generation tokens. Including verification that stale-session cleanup during the implementation window does not stop live sessions.
- Phase `10b`: mutex tests that probe `flock`, not only JSON payloads. Process-lifetime gate: flock ownership held across full primary launch lifetime. Real two-process concurrent launch smoke test. Crash/restart cleanup smoke test. Verification that startup cleanup cannot remove a live flock-held lock.
- Phase `6a` / `6b`: smoke tests proving primary launch and background/resume execution consume one resolved plan each.
- Phase `7`: registry/type-routing tests proving direct mode never enters subprocess-only code.
- Phase `11a`: transition-table tests and store-mutation tests that validate inside the locked append path.
- Phase `12a.1`: heartbeat start/cancel/await tests proving heartbeat files are written in all execution paths (background spawn, primary launch, foreground).
- Phase `12a.2`: regression test showing a quiet but live PID is not finalized as stale. Test that observer exceptions do not fail the append path. Smoke test for spawn wait on a long-running quiet spawn.
- State projections: tests verifying projection consistency with raw JSONL reads after concurrent appends.

## Known Limitations Kept Explicit

These are acknowledged but not solved in this refactor:

- JSONL stores still append without compaction. State projections solve the read-performance problem; compaction remains future work.
- `flock` remains a local-filesystem assumption. Meridian does not claim correctness on NFS/shared storage.
- Primary launch still has an ambiguous post-fork/pre-registration window. Phase `10b` makes the reaper conservative in that window instead of claiming certainty it does not have.
- Phase `2b` observers are process-local. A persistent frontend server in a separate process would not receive callbacks from CLI invocations or harness workers writing to JSONL on disk. Cross-process state notification (file-tailing, inotify, append broker) is future work needed before a web UI can receive real-time updates.
- Read operations still perform reconciliation side effects. The reaper runs from query paths (spawn list, work show, etc.) and can append finalize events or send SIGTERM. Separating query from repair is future work.
- Cross-store work reference integrity is not transactional. Work rename/start can leave dangling `work_id` references in `spawns.jsonl` or `sessions.jsonl` if a crash occurs between the work-store mutation and the cross-store reference update. Full cross-store repair is future work.
- The conversation model provides extraction, not mutation. Injecting messages into a running harness session requires a new execution mode beyond the scope of this refactor.

---

## Phase 10b: Primary-Launch Flock Mutex

**Goal:** Bug fix (Goal 1)

**Addresses:** `review-state-safety.md` finding 1, `review-correctness.md` Phase 10, `review-risk.md` §4 and §6.

### Problem

`active-primary.lock` is a JSON marker file written with `atomic_write_text`, not an actual mutex. Two concurrent `meridian` launches both proceed, both write state, and corruption follows. The prior design also opened the file with `"w"`, which truncates before the lock is acquired.

### Solution

Make `active-primary.lock` an `flock`-backed mutex:

- Open with `a+` (no truncation before lock)
- Acquire `LOCK_EX | LOCK_NB` (fail immediately if contended)
- Rewrite the JSON payload only after acquiring the lock
- `cleanup_orphaned_locks()` probes the flock itself, not just the JSON payload

IMPORTANT: The flock must be held for the ENTIRE primary launch lifetime, not just during the lock file write. This requires structural changes to `launch_primary()` and `run_harness_process()` to thread the flocked file descriptor through the full execution path. The current code writes a JSON marker with `_write_lock()` and unlinks the path at the end — both of those operations must be replaced by the flock context manager wrapping the entire launch.

```python
# src/meridian/lib/launch/process.py
@contextmanager
def primary_launch_lock(lock_path: Path, payload: dict[str, object]) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A primary launch is already active.")

        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
```

```python
def cleanup_orphaned_locks(repo_root: Path) -> bool:
    lock_path = active_primary_lock_path(repo_root)
    if not lock_path.is_file():
        return False

    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False  # Lock is held — primary is active
        payload = _read_lock_payload(handle)
        if _lock_payload_is_live(payload):
            return False
        lock_path.unlink(missing_ok=True)
        return True
```

Phase 10b also requires coordinating with the reaper. `cleanup_orphaned_locks()` currently probes the JSON payload; it must switch to probing the flock. The reaper in `src/meridian/lib/state/reaper.py` must also be updated: foreground reconciliation that fails a queued run on `missing_worker_pid`/`orphan_run` needs to respect the flock-held window.

---

## Phase 1: Malformed-Event Guard + Dead Code Removal

**Goal:** Bug fix (Goal 1)

**Addresses:** `review-consistency.md` HIGH finding 1, `review-correctness.md` gap 4, `review-design-quality.md` finding 5, `review-fresh-eyes.md` §7.1.

### Problem

- `spawn_store._parse_event()` propagates `ValidationError` and crashes all read paths (`list_spawns()`, `get_spawn()`, `spawn show`, `spawn wait`, the dashboard) on one malformed JSONL row. `session_store._parse_event()` already catches this — the inconsistency is a confirmed drift bug.
- Dead code remains: `SpawnListFilters`, `reconcile_running_spawn()`.
- The prior design contradicted itself by deleting `resolve_state_root()` in Phase 1 and recreating it in Phase 4.
- `spawn_continue_sync()` in `spawn/api.py` drops the provided `RuntimeContext` — it ignores the `ctx` parameter and calls `spawn_create_sync()` without passing it, potentially losing explicit RuntimeContext state for depth/work/chat inheritance.

### Solution

1. Guard `ValidationError` in `spawn_store._parse_event()`, matching session_store's existing behavior.
2. Remove confirmed dead code: `SpawnListFilters`, `reconcile_running_spawn()`.
3. Do **not** remove `resolve_state_root()`. Phase `4` standardizes it.
4. Fix `spawn_continue_sync()` to pass the RuntimeContext through to `spawn_create_sync()`.

### Snippet

```python
# src/meridian/lib/state/spawn_store.py
from pydantic import ValidationError


def _parse_event(payload: dict[str, Any]) -> SpawnEvent | None:
    event_type = payload.get("event")
    try:
        if event_type == "start":
            return SpawnStartEvent.model_validate(payload)
        if event_type == "update":
            return SpawnUpdateEvent.model_validate(payload)
        if event_type == "finalize":
            return SpawnFinalizeEvent.model_validate(payload)
    except ValidationError:
        return None
    return None
```

---

## Phase 12a.1: Heartbeat Lifecycle Wiring

**Goal:** Bug fix (Goal 1) — mechanism; reported as `bug-spawn-wait-false-failure.md`

**Addresses:** `review-state-safety.md` finding 7, `review-risk.md` §3, `review-correctness.md` Phase 12, `review-fresh-eyes.md` §5d.

### Problem

A quiet but healthy spawn (model thinking for 6+ minutes) gets reaped as "stale" because the hardcoded 5-minute threshold fires. The user sees a false failure. Additionally:

- `_heartbeat_loop()` is not integrated into any lifecycle
- Config bounds for stale threshold are unspecified

### Solution

Wire heartbeat into every execution lifecycle the reaper depends on: background spawn execution (`runner.py`), primary launch (`process.py`), and foreground execution. The heartbeat file must be written before the reaper's stale-threshold window opens.

1. Validated reaper timing config with bounds:

```python
# src/meridian/lib/state/reaper_config.py
def validate_stale_threshold_secs(value: object) -> int:
    parsed = int(value)
    if parsed < 60 or parsed > 86_400:
        raise ValueError("stale_threshold_secs must be between 60 and 86400")
    return parsed
```

2. Heartbeat writers integrated into actual execution lifecycles:

```python
# src/meridian/lib/launch/heartbeat.py
@asynccontextmanager
async def heartbeat_scope(path: Path, *, interval_secs: int) -> AsyncIterator[None]:
    task = asyncio.create_task(_heartbeat_loop(path, interval_secs))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
```

The heartbeat helper is async but primary launch is synchronous — the primary launch path needs a threaded heartbeat writer or the heartbeat must be started from the async wrapper layer.

---

## Phase 12a.2: Stale-Policy Flip

**Goal:** Bug fix (Goal 1) — policy; reported as `bug-spawn-wait-false-failure.md`

**Addresses:** `review-state-safety.md` finding 7, `review-risk.md` §3, `review-correctness.md` Phase 12, `review-fresh-eyes.md` §5d.

### Problem

Before this flip, "PID alive but quiet" falls through to failure.

### Solution

Only safe to land after 12a.1 confirms heartbeat evidence exists in all execution paths. If the policy flips before heartbeat is wired, dead spawns stop getting finalized and remain stuck in queued/running.

Also addresses hung-but-alive processes: a live wrapper/harness that stops producing output is now preserved rather than falsely failed, but this means genuinely wedged processes can persist indefinitely. A future health-check rule (e.g., heartbeat age threshold) can address this without reverting to the stale-only heuristic.

```python
# src/meridian/lib/state/reaper.py
def _should_finalize_stale(inspection: _SpawnInspection) -> bool:
    if inspection.harness_alive or inspection.wrapper_alive:
        return False  # Live but quiet → suspect, not terminal
    return inspection.stale and inspection.grace_elapsed
```

---

## Phase 2a: Shared JSONL Event Store Mechanics

**Goal:** Consistency (Goal 1) + Legibility (Goal 3)

**Addresses:** `review-consistency.md` HIGH finding 1 and cross-file note 1, `review-solid.md` LOW finding, `review-correctness.md` Phase 2, `review-fresh-eyes.md` §3c, §3d, §4a, §6a, `review-design-quality.md` SRP/DIP notes.

### Problem

- `spawn_store.py` and `session_store.py` duplicate JSONL mechanics (locking, reading, appending, timestamp generation). The error-handling drift already produced the Phase 1 bug.
- `_utc_now_iso()` is defined identically in three files.

### Solution

Extract `event_store.py` with shared mechanics:

```python
# src/meridian/lib/state/event_store.py
from collections.abc import Callable, Iterator


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_event(
    data_path: Path,
    lock_path: Path,
    event: BaseModel,
    *,
    store_name: str,
    exclude_none: bool = False,
) -> None:
    payload = event.model_dump(mode="json", exclude_none=exclude_none)
    line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    with lock_file(lock_path):
        append_text_line(data_path, line + chr(10))  # append_text_line does not add newline; callers must include it


def read_events(
    data_path: Path,
    parse_event: Callable[[dict[str, Any]], T | None],
) -> list[T]:
    if not data_path.is_file():
        return []

    rows: list[T] = []
    with data_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                parsed = parse_event(cast("dict[str, Any]", payload))
            except ValidationError:
                continue
            if parsed is not None:
                rows.append(parsed)
    return rows
```

Key design decisions:

- `read_events()` catches `ValidationError` around the parser callback. The guarantee belongs in the shared helper, not in every domain store.
- `append_event()` keeps `exclude_none` explicit so stores preserve current JSON shape.
- `read_events()` uses line-streaming, not `read_text().splitlines()`, to avoid memory spikes.

### Impact

Spawn and session stores stop drifting on crash-tolerance behavior. `_utc_now_iso()` is deduplicated. An agent exploring the codebase finds one file for how JSONL works instead of two divergent copies.

---

## Phase 2b: Observable Event Store (Observer Hooks)

**Goal:** Frontend-ready (Goal 2)

**Addresses:** `review-consistency.md` HIGH finding 1 and cross-file note 1, `review-solid.md` LOW finding, `review-correctness.md` Phase 2, `review-fresh-eyes.md` §3c, §3d, §4a, §6a, `review-design-quality.md` SRP/DIP notes.

### Problem

State changes are silent — no notification when events are appended. A future frontend would need to poll files.

### Solution

Move observer hooks into the event store layer:

```python
# src/meridian/lib/state/event_store.py
from collections.abc import Callable

EventObserver = Callable[[str, dict[str, Any]], None]  # (store_name, event_payload)
_observers: list[EventObserver] = []


def register_observer(observer: EventObserver) -> None:
    _observers.append(observer)


def append_event(...) -> None:
    payload = event.model_dump(mode="json", exclude_none=exclude_none)
    line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    with lock_file(lock_path):
        append_text_line(data_path, line + chr(10))
    for observer in _observers:
        try:
            observer(store_name, payload)
        except Exception:
            pass  # Log but do not fail the append path
```

Observer callbacks are invoked after the durable write completes and outside the lock. If an observer raises, the event is already committed — observer failures must not propagate to the caller. Wrap each observer call in a try/except that logs but does not re-raise.

### Impact

State changes become observable — the foundation for projections. Note: observers are process-local. A persistent frontend server in a separate process would not receive these callbacks. Cross-process state notification (file-tailing, inotify, append broker) is future work.

---

## Phase 4: Ops Helper Consolidation

**Goal:** Legibility (Goal 3)

**Addresses:** `review-consistency.md` MEDIUM finding 5, `review-correctness.md` Phase 4, `review-fresh-eyes.md` §3b.

### Problem

`_runtime_context()`, `_state_root()`, `_resolve_roots()`, and `_resolve_chat_id()` are duplicated across spawn/execute.py, spawn/api.py, and work.py. Defaults disagree (`""` versus `"c0"`). An agent reading the codebase encounters the same helper in three files and has to verify they're equivalent.

### Solution

Consolidate into `src/meridian/lib/ops/runtime.py`:

```python
@dataclass(frozen=True)
class ResolvedRoots:
    repo_root: Path
    state_root: Path


def resolve_roots(repo_root: str | None) -> ResolvedRoots:
    resolved_repo, _ = resolve_runtime_root_and_config(repo_root)
    return ResolvedRoots(
        repo_root=resolved_repo,
        state_root=resolve_state_paths(resolved_repo).root_dir,
    )


def resolve_state_root(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).root_dir


def resolve_chat_id(
    *,
    payload_chat_id: str = "",
    ctx: RuntimeContext | None = None,
    fallback: str = "",
) -> str:
    if payload_chat_id.strip():
        return payload_chat_id.strip()
    if ctx is not None and ctx.chat_id:
        return ctx.chat_id.strip()
    return fallback
```

All ops modules import from one place. One default policy. One place for an agent to read.

---

## Phase 5: Async Wrapper Consistency

**Goal:** Consistency (Goal 1) + Frontend-ready (Goal 2)

**Addresses:** `review-consistency.md` HIGH finding 2, `review-risk.md` §3, `review-correctness.md` Phase 5.

### Problem

Some MCP-facing async operations use `asyncio.to_thread()` while others call sync implementations directly and block the event loop. If the MCP server becomes the backend for a web UI, blocking calls break concurrent tool execution.

### Solution

One decorator, mechanical application:

```python
# src/meridian/lib/ops/runtime.py
P = ParamSpec("P")
T = TypeVar("T")


def async_from_sync(sync_fn: Callable[P, T]) -> Callable[P, Coroutine[Any, Any, T]]:
    @functools.wraps(sync_fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await asyncio.to_thread(sync_fn, *args, **kwargs)
    return wrapper
```

```python
# src/meridian/lib/ops/report.py
report_create = async_from_sync(report_create_sync)
report_show = async_from_sync(report_show_sync)
```

Applied to all `report.*`, `work.*`, and `catalog.*` operations.

---

## Phase 3b: Work-Store Mutation Safety

**Goal:** Bug fix (Goal 1)

**Addresses:** `review-state-safety.md` findings 5 and 6, `review-correctness.md` gap 1, `review-risk.md` §5.

### Problem

`work_store.py` has no file-level locking. A concurrent `rename` + `update` can recreate the old directory. A crash between directory rename and `work.json` rewrite leaves inconsistent state.

### Solution

1. All work mutations under a shared `work.lock`.
2. Rename uses a `work-rename.intent.json` journal for crash recovery.
3. `reconcile_work_store()` runs on every mutating entry point and before `list_work_items()`.
4. State is re-read after acquiring the lock, never before.

```python
# src/meridian/lib/state/work_store.py
class WorkRenameIntent(BaseModel):
    old_work_id: str
    new_work_id: str
    started_at: str


def rename_work_item(state_root: Path, old_work_id: str, new_name: str) -> WorkItem:
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
        reconcile_work_store(state_root)

        old_item = _get_work_item_unlocked(state_root, old_work_id)
        if old_item is None:
            raise ValueError(f"Work item '{old_work_id}' not found")

        normalized = _validate_new_slug(new_name)
        old_dir = paths.work_dir / old_work_id
        new_dir = paths.work_dir / normalized
        if new_dir.exists():
            raise ValueError(f"Work item '{normalized}' already exists.")

        intent = WorkRenameIntent(
            old_work_id=old_work_id,
            new_work_id=normalized,
            started_at=utc_now_iso(),
        )
        atomic_write_text(paths.work_rename_intent, intent.model_dump_json(indent=2) + "\n")

        old_dir.rename(new_dir)
        updated = old_item.model_copy(update={"name": normalized})
        atomic_write_text(new_dir / "work.json", _serialize_work_item(updated))
        paths.work_rename_intent.unlink(missing_ok=True)
        return updated
```

The visible work directory layout and `MERIDIAN_WORK_DIR` remain unchanged.

---

## Phase 3: Work-Store Error Semantics

**Goal:** Consistency (Goal 1) + Legibility (Goal 3)

**Addresses:** `review-consistency.md` MEDIUM finding 4, `review-correctness.md` Phase 3.

### Problem

- `get_work_item()` returns `None`
- `rename_work_item()` raises `ValueError`
- `update_work_item()` raises `KeyError`

An agent encountering work-store code has to check each function to know which error to expect.

### Solution

Getters return `None`. All mutations raise `ValueError` on not-found.

```python
def update_work_item(...) -> WorkItem:
    ...
    if current is None:
        raise ValueError(f"Work item '{work_id}' not found")
```

```python
# src/meridian/cli/main.py
except ValueError as exc:
    emit_error(str(exc))
```

---

## Phase 6: Session Lifecycle Extraction

**Goal:** Legibility (Goal 3) + Risk reduction for Phase 9a

**Addresses:** `review-solid.md` HIGH finding 2, `review-design-quality.md` finding 3, `review-risk.md` §1 and §7, `review-correctness.md` Phase 6.

### Problem

Session start/stop orchestration is duplicated between primary launch (`process.py`) and spawn execution (`spawn/execute.py`). Phase 9a changes session start semantics significantly — lock ordering, chat-ID reservation, instance IDs. With the orchestration in two places, Phase 9a must make coordinated changes in both, increasing the risk of inconsistency.

### Solution

Extract shared session lifetime to `launch/session_scope.py`. Keep it narrowly scoped to session lifetime only:

```python
# src/meridian/lib/launch/session_scope.py
@dataclass(frozen=True)
class ManagedSession:
    chat_id: str
    record_harness_session_id: Callable[[str], None]


@contextmanager
def session_scope(...) -> Iterator[ManagedSession]:
    resolved_chat_id = start_session(...)
    try:
        yield ManagedSession(
            chat_id=resolved_chat_id,
            record_harness_session_id=lambda session_id: update_session_harness_id(
                state_root, resolved_chat_id, session_id,
            ),
        )
    finally:
        stop_session(state_root, resolved_chat_id)
```

Auto-work-item creation is NOT part of session scope — it's explicit policy in a separate helper:

```python
# src/meridian/lib/ops/session_policy.py
def ensure_session_work_item(state_root: Path, chat_id: str) -> str:
    existing = get_session_active_work_id(state_root, chat_id)
    if existing:
        return existing
    auto_item = work_store.create_auto_work_item(state_root)
    update_session_work_id(state_root, chat_id, auto_item.name)
    return auto_item.name
```

### Impact

- One place for session lifetime logic — Phase 9a changes land once.
- An agent reading "how does a session start?" finds one file.
- Policy (auto-work creation) stays out of mechanism (session lifetime).

---

## Phase 9a+9b: Session Start Lock Ordering and Generation-Safe Stale-Session Cleanup

**Goal:** Bug fix (Goal 1)

**Addresses:** `review-state-safety.md` findings 3 and 4, `review-risk.md` §6, `review-correctness.md` Phase 9, `review-fresh-eyes.md` §4b.

### Problem

- `next_chat_id()` counts start events without any lock on the counter — concurrent session starts can allocate the same `c7`.
- `start_session()` appends the start event before acquiring the lifetime lock. If the lock fails, the session is recorded but unowned.
- No generation identity to distinguish an old dead session from a newly restarted one.
- Cleanup can mark `c7` stale, then a new process restarts `c7`, then cleanup appends `stop(c7)` against the new live session.

### Solution

Ship 9a+9b atomically. Stale-session cleanup runs on every CLI startup, so landing lock-order fixes and generation-safe cleanup in separate commits introduces an unsafe window.

1. Reserve chat IDs through a dedicated counter file under its own lock.
2. Add `session_instance_id` (ULID) to start/stop/update events.
3. Acquire the per-session lifetime lock before appending the start event.
4. Release the lock in an `except` path if the append fails.
5. Write a per-session lease file for stale-cleanup validation.
6. In stale cleanup: append stop only when lease generation matches the current record, then finalize stale files.

```python
# src/meridian/lib/state/session_store.py
def reserve_chat_id(state_root: Path) -> str:
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.session_id_counter_lock):
        next_value = _read_session_counter(paths) + 1
        atomic_write_text(paths.session_id_counter, f"{next_value}\n")
        return f"c{next_value}"


def start_session(...) -> str:
    paths = StateRootPaths.from_root_dir(state_root)
    resolved_chat_id = chat_id.strip() if chat_id else reserve_chat_id(state_root)
    lock_path = paths.sessions_dir / f"{resolved_chat_id}.lock"
    handle = _acquire_session_lock(lock_path)
    session_instance_id = ulid.new().str

    try:
        with lock_file(paths.sessions_lock):
            _append_session_event(
                state_root,
                SessionStartEvent(
                    chat_id=resolved_chat_id,
                    session_instance_id=session_instance_id,
                    ...,
                    started_at=utc_now_iso(),
                ),
            )
        atomic_write_text(
            paths.sessions_dir / f"{resolved_chat_id}.lease.json",
            json.dumps({
                "chat_id": resolved_chat_id,
                "session_instance_id": session_instance_id,
                "owner_pid": os.getpid(),
            }, sort_keys=True) + "\n",
        )
    except Exception:
        _unlock_handle(handle)
        raise

    _SESSION_LOCK_HANDLES[_session_lock_key(state_root, resolved_chat_id)] = handle
    return resolved_chat_id
```

```python
def cleanup_stale_sessions(state_root: Path) -> StaleSessionCleanup:
    paths = StateRootPaths.from_root_dir(state_root)
    candidates = _collect_unlocked_session_candidates(paths.sessions_dir)
    if not candidates:
        return StaleSessionCleanup(cleaned_ids=(), materialized_scopes=())

    cleaned: list[str] = []
    scopes: list[str] = []
    with lock_file(paths.sessions_lock):
        records = _records_by_session(state_root)
        stopped_at = utc_now_iso()
        for candidate in candidates:
            record = records.get(candidate.chat_id)
            if record is None or record.stopped_at is not None:
                continue
            if record.session_instance_id != candidate.session_instance_id:
                continue  # Different generation — do not stop
            _append_session_event(
                state_root,
                SessionStopEvent(
                    chat_id=candidate.chat_id,
                    session_instance_id=candidate.session_instance_id,
                    stopped_at=stopped_at,
                ),
                exclude_none=True,
            )
            cleaned.append(candidate.chat_id)
            if record.harness.strip():
                scopes.append(record.harness.strip())

    _finalize_stale_session_files(paths, candidates, cleaned)
    return StaleSessionCleanup(
        cleaned_ids=tuple(sorted(cleaned, key=_session_sort_key)),
        materialized_scopes=tuple(sorted(set(scopes))),
    )
```

---

## Phase 6a: Resolved Primary Launch Plan

**Goal:** Legibility (Goal 3) + Frontend-ready (Goal 2)

**Addresses:** `review-solid.md` MEDIUM finding 3, `review-correctness.md` gap 2, `review-fresh-eyes.md` §4c.

### Problem

Primary launch resolves policies twice: `prepare_launch_context()` loads profile/model/harness/skills for session tracking, then `build_harness_context()` repeats the same resolution for command construction. Both call `load_agent_profile_with_fallback()`, `resolve_run_defaults()`, `resolve_harness()`, `resolve_skills_from_profile()` independently.

An agent tracing "what model did this launch use?" must follow two resolution paths and verify they agree. A frontend displaying launch configuration would need to pick one of the two representations.

### Solution

One immutable, serializable plan that resolves all policies once:

```python
# src/meridian/lib/launch/plan.py
class ResolvedPrimaryLaunchPlan(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    repo_root: Path
    state_root: Path
    prompt: str
    request: LaunchRequest
    adapter: SubprocessLaunchHarness
    metadata: PrimarySessionMetadata
    run_params: SpawnParams
    permission_config: PermissionConfig
    command: tuple[str, ...]
    launch_env: dict[str, str]
    seed_harness_session_id: str


def resolve_primary_launch_plan(...) -> ResolvedPrimaryLaunchPlan:
    profile = load_agent_profile_with_fallback(...)
    defaults = resolve_run_defaults(...)
    adapter = harness_registry.get_subprocess_harness(...)
    resolved_skills = resolve_skills_from_profile(...)
    materialized = materialize_for_harness(...)
    policy = adapter.filter_launch_content(...)
    run_params = SpawnParams(...)
    command = tuple(adapter.build_command(run_params, resolver))
    launch_env = build_launch_env_from_plan(...)
    return ResolvedPrimaryLaunchPlan(...)
```

`run_harness_process()` receives the resolved plan and consumes it. No second resolution pass.

---

## Phase 6b: Prepared Spawn Plan DTO

**Goal:** Legibility (Goal 3) + Frontend-ready (Goal 2)

**Addresses:** `review-solid.md` MEDIUM finding 4, `review-correctness.md` gap 3, `review-risk.md` §1.

### Problem

`execute_with_finalization()` takes 15+ parameters. `_PreparedCreateLike` is a Protocol with 17+ properties spread across multiple files. An agent reading spawn execution must mentally assemble the full parameter surface. A frontend showing "what is this spawn doing?" has no single inspectable object.

### Solution

One concrete, frozen, serializable plan:

```python
# src/meridian/lib/ops/spawn/plan.py
class ExecutionPolicy(BaseModel):
    timeout_secs: float | None = None
    permission_config: PermissionConfig
    allowed_tools: tuple[str, ...] = ()


class SessionContinuation(BaseModel):
    chat_id: str
    harness_session_id: str | None = None
    continue_fork: bool = False


class PreparedSpawnPlan(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: str
    harness_id: str
    prompt: str
    agent_name: str | None
    skills: tuple[str, ...]
    reference_files: tuple[str, ...]
    template_vars: dict[str, str]
    session: SessionContinuation
    execution: ExecutionPolicy
    cli_command: tuple[str, ...]
```

```python
async def execute_with_finalization(
    plan: PreparedSpawnPlan,
    *,
    runtime: OperationRuntime,
    sink: OutputSink | None = None,
) -> int:
    ...
```

---

## Phase 7: Harness Adapter Protocol Split

**Goal:** Legibility (Goal 3)

**Addresses:** `review-solid.md` HIGH finding 1, `review-design-quality.md` finding 1, `review-risk.md` §1, `review-correctness.md` Phase 7.

### Problem

`HarnessAdapter` is one protocol with 17 methods. `DirectAdapter` stubs 12 of them via base class defaults because the interface conflates subprocess launching with in-process execution — two fundamentally different execution modes behind one type.

### Solution

Split at the execution-mode boundary. `SubprocessHarness` is one cohesive lifecycle protocol — callers that launch subprocesses need all of these behaviors bundled together, and splitting them further would fragment the main execution paths without improving legibility. `InProcessHarness` is the separate execution mode for direct/in-process adapters. `ConversationExtractingHarness` is opt-in for the conversation model feature.

```python
# src/meridian/lib/harness/adapter.py
class SubprocessHarness(Protocol):
    @property
    def id(self) -> HarnessId: ...
    @property
    def capabilities(self) -> HarnessCapabilities: ...
    def native_layout(self) -> HarnessNativeLayout | None: ...
    def run_prompt_policy(self) -> RunPromptPolicy: ...
    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]: ...
    def mcp_config(self, run: SpawnParams) -> McpConfig | None: ...
    def env_overrides(self, config: PermissionConfig) -> dict[str, str]: ...
    def blocked_child_env_vars(self) -> frozenset[str]: ...
    def parse_stream_event(self, line: str) -> StreamEvent | None: ...
    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...
    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
    def seed_session(...) -> SessionSeed: ...
    def detect_primary_session_id(...) -> str | None: ...
    def owns_untracked_session(...) -> bool: ...
    def filter_launch_content(...) -> PromptPolicy: ...


class InProcessHarness(Protocol):
    async def execute(self, request: DirectRunRequest) -> SpawnResult: ...


class ConversationExtractingHarness(Protocol):
    def extract_conversation(
        self, artifacts: ArtifactStore, spawn_id: SpawnId,
    ) -> Conversation | None: ...
```

Registry lookups become typed:

```python
class HarnessRegistry:
    def get_subprocess_harness(self, id: HarnessId) -> SubprocessHarness: ...
    def get_in_process_harness(self, id: HarnessId) -> InProcessHarness: ...
    def get_conversation_harness(self, id: HarnessId) -> ConversationExtractingHarness | None: ...
```

An agent reading the code can now answer "what does a subprocess harness need to do?" by reading one cohesive lifecycle protocol, not a 17-method kitchen sink.

---

## Phase 8: CLI Registration Consolidation

**Goal:** Legibility (Goal 3)

**Addresses:** `review-consistency.md` LOW finding 6, `review-solid.md` MEDIUM finding 5, `review-design-quality.md` finding 4, `review-correctness.md` Phase 8.

### Problem

Each CLI module (`spawn.py`, `work_cmd.py`, `report_cmd.py`, `models_cmd.py`, etc.) has a similar `register_X_commands()` function with the same manifest iteration loop. An agent reading CLI registration sees the same pattern in 6 files and has to verify they're all equivalent.

### Solution

One shared helper:

```python
# src/meridian/cli/common.py
def register_manifest_cli_group(
    app: App,
    *,
    group: str,
    handlers: Mapping[str, Callable[..., Any]],
    default_handler: Callable[..., Any] | None = None,
) -> None:
    for op in get_operations_for_surface("cli"):
        if op.cli_group != group:
            continue
        handler = handlers.get(op.name)
        if handler is None:
            raise RuntimeError(f"Missing CLI handler for {group}.{op.name}")
        app.command(name=op.name)(handler)
    if default_handler is not None:
        app.default(default_handler)
```

`main.py` remains the explicit composition root. Adding a new CLI group still requires a `main.py` edit — this design is honest about that.

---

## Phase 11a: Spawn Transition Model

**Goal:** Legibility (Goal 3) + Supports projection correctness (Goal 2)

**Addresses:** `review-solid.md` MEDIUM finding 4, `review-design-quality.md` finding 2, `review-correctness.md` Phase 11, `review-fresh-eyes.md` §4d.

### Problem

Spawn lifecycle rules are fragmented across `finalize_spawn()`, `finalize_spawn_if_running()`, `finalize_spawn_if_active()`, the reaper, and the CLI. An agent reading the code must check multiple functions to understand what transitions are legal. State projections (tier 5) need an authoritative transition table to validate changes.

### Solution

One transition table, one active/terminal classification, validation inside locked mutations:

```python
# src/meridian/lib/core/spawn_lifecycle.py
ACTIVE_SPAWN_STATUSES = frozenset({"queued", "running"})
TERMINAL_SPAWN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

_ALLOWED_TRANSITIONS = {
    "queued": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancelled"}),
}


def validate_transition(from_status: SpawnStatus, to_status: SpawnStatus) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise ValueError(f"Illegal spawn transition: {from_status} -> {to_status}")
```

```python
# src/meridian/lib/state/spawn_store.py
def finalize_spawn(..., status: SpawnStatus, ...) -> None:
    with lock_file(paths.spawns_lock):
        record = _current_spawn_record_unlocked(state_root, spawn_id)
        if record is None or record.status not in ACTIVE_SPAWN_STATUSES:
            return
        validate_transition(cast("SpawnStatus", record.status), status)
        _append_spawn_event(...)
```

Note: `queued -> failed` is explicitly allowed (startup failures). This corrects the prior design's bug where `finalize_spawn` hardcoded `running` as the only valid source status.

---

## State Projections

**Goal:** Frontend-ready (Goal 2)

### Problem

Every read operation re-scans the full JSONL file. `list_spawns()` reads all of `spawns.jsonl` every time. `collect_active_chat_ids()` reads all of `sessions.jsonl` every time. For a CLI (short-lived process), this is fine at current scale. For a future persistent server (MCP, web), this becomes a bottleneck — every API call, every poll, every dashboard refresh re-reads everything.

### Solution

In-memory projections that subscribe to the observable event store (Phase 2b):

SpawnIndex.stats() absorbs the Phase 11b concern. Stats are a derived view of the index — computing them from the projection avoids building a separate aggregation layer that would be replaced when projections land.

```python
# src/meridian/lib/state/projections.py
class SpawnStats(BaseModel):
    total_runs: int
    by_status: dict[str, int]
    by_model: dict[str, int]
    total_duration_secs: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


class SpawnIndex:
    """O(1) spawn lookup, maintained by event observation."""

    def __init__(self) -> None:
        self._by_id: dict[SpawnId, SpawnRecord] = {}
        self._by_status: dict[str, set[SpawnId]] = defaultdict(set)
        self._by_work_id: dict[str, set[SpawnId]] = defaultdict(set)
        self._stats: SpawnStats | None = None  # invalidated on change

    def rebuild(self, state_root: Path) -> None:
        """Full rebuild from JSONL. Called once on startup."""
        events = read_events(paths.spawns_jsonl, _parse_event)
        self._by_id = _record_from_events(events)
        self._rebuild_indexes()

    def on_event(self, store_name: str, payload: dict[str, Any]) -> None:
        """Incremental update from event observer."""
        if store_name != "spawns":
            return
        # Apply single event to existing projection
        ...

    def get(self, spawn_id: SpawnId) -> SpawnRecord | None:
        return self._by_id.get(spawn_id)

    def list(self, *, status: str | None = None, work_id: str | None = None) -> list[SpawnRecord]:
        ...

    def stats(self) -> SpawnStats:
        ...


def spawn_stats(state_root: Path) -> SpawnStats:
    index = SpawnIndex()
    index.rebuild(state_root)
    return index.stats()


class SessionIndex:
    """Active session tracking via event ordering."""

    def active_chat_ids(self) -> frozenset[str]:
        """Correctly handles reused chat IDs by processing events in order."""
        ...

    def on_event(self, store_name: str, payload: dict[str, Any]) -> None:
        if store_name != "sessions":
            return
        ...


class WorkIndex:
    """Work items with spawn associations."""
    ...
```

Usage:

```python
# For CLI (short-lived): rebuild on first access, equivalent to current full-scan
index = SpawnIndex()
index.rebuild(state_root)

# For persistent server: rebuild once, stay in sync via observer
index = SpawnIndex()
index.rebuild(state_root)
register_observer(index.on_event)
```

### Impact

- `SessionIndex.active_chat_ids()` replaces `collect_active_chat_ids()`, fixing the reused-chat-ID bug (absorbs Phase 12b) by using event ordering instead of set subtraction.
- `SpawnIndex.stats()` is a derived view of the index (absorbs Phase 11b's concern about re-aggregation).
- CLI performance is unchanged (same full scan, just through the projection).
- Future persistent server gets O(1) lookups for free.

---

## Conversation Model

**Goal:** Frontend-ready (Goal 2)

### Problem

Each harness stores conversation history in its own format and location:

- Claude: `.claude/projects/<repo-slug>/<session>.jsonl` (JSONL conversation turns)
- Codex: `~/.codex/sessions/rollout-*.jsonl` (session meta + conversation events)
- OpenCode: `~/.local/share/opencode/log/*.log` (structured log entries)

Meridian captures raw stream events in `.meridian/artifacts/<spawn_id>/output.jsonl`, but this is stdout parsing, not a clean conversation. There is no unified representation. A `meridian history` command, a web conversation viewer, or cross-harness comparison are all impossible without per-adapter extraction and a shared model.

### Solution

A unified conversation model with a per-adapter extraction protocol:

```python
# src/meridian/lib/core/conversation.py
class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_name: str
    input: dict[str, Any]
    output: str | None = None


class ConversationTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: Literal["user", "assistant", "system"]
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    timestamp: str | None = None


class Conversation(BaseModel):
    model_config = ConfigDict(frozen=True)
    spawn_id: str
    harness: str
    turns: tuple[ConversationTurn, ...]
```

Extraction protocol on harness adapters:

```python
# src/meridian/lib/harness/adapter.py
class ConversationExtractingHarness(Protocol):
    def extract_conversation(
        self, artifacts: ArtifactStore, spawn_id: SpawnId,
    ) -> Conversation | None: ...
```

Each adapter provides its own extraction from its native format. Claude's is the most straightforward (parse the JSONL conversation file). Codex and OpenCode need format-specific parsing.

This also enables a future `meridian history <spawn_id>` CLI command and a web UI conversation viewer, both consuming the same model.

---

## Sink Fan-Out

**Goal:** Frontend-ready (Goal 2)

### Problem

Only one `OutputSink` is active at a time. A future web UI needs to push events to a WebSocket AND log to a file AND display in a terminal. Plugin sinks (metrics, audit) need to run alongside the primary sink.

### Solution

```python
# src/meridian/lib/core/sink.py
class CompositeSink:
    """Fan-out to multiple sinks."""

    def __init__(self, *sinks: OutputSink) -> None:
        self._sinks = sinks

    def result(self, payload: Any) -> None:
        for sink in self._sinks:
            sink.result(payload)

    def status(self, message: str) -> None:
        for sink in self._sinks:
            sink.status(message)

    def warning(self, message: str) -> None:
        for sink in self._sinks:
            sink.warning(message)

    def error(self, message: str, exit_code: int = 1) -> None:
        for sink in self._sinks:
            sink.error(message, exit_code)

    def heartbeat(self, message: str) -> None:
        for sink in self._sinks:
            sink.heartbeat(message)

    def event(self, payload: dict[str, Any]) -> None:
        for sink in self._sinks:
            sink.event(payload)

    def flush(self) -> None:
        for sink in self._sinks:
            if hasattr(sink, "flush"):
                sink.flush()
```

Small implementation. Architecturally important as the extension point for any future output destination.

---

## Result

This plan addresses three goals with 19 work items:

**Goal 1 — Bug fixes and consistency** (Phases 10b, 1, 12a.1, 12a.2, 2a, 3b, 3, 6, 9a+9b): Fix malformed-event crashes, the primary-launch non-mutex, heartbeat lifecycle gaps, stale detection false failures, shared JSONL consistency drift, work-store races, work-store error inconsistency, session lifecycle duplication, and generation-safe session cleanup. Phase `9a+9b` ships atomically.

**Goal 2 — Frontend-ready** (Phase 2b observer hooks, state projections, conversation model, sink fan-out, Phase 5 async correctness): Build observable state, queryable state via projections, a unified conversation model, and sink fan-out — so a future `meridian view` web UI has efficient foundations to build on.

**Goal 3 — Legibility for AI agents** (Phases 2a, 4, 6, 6a, 6b, 7, 8, 11a, State projections): Consolidate duplicated helpers, extract session lifecycle to one place, replace duplicated policy resolution with single plans, narrow the harness protocol split to execution-mode boundaries, consolidate CLI registration, and establish an authoritative spawn transition model with projection-derived stats — so that agents exploring and modifying the codebase find single sources of truth and predictable patterns.

### What's Deferred

- JSONL compaction — projections solve the read problem; compaction is future work.
- `flock` on NFS — local-filesystem assumption remains.
- Cross-process state observation/invalidation — file-tailing or inotify needed for a persistent frontend server to receive real-time updates from other meridian processes.
- Read-path reconciliation isolation — separating reaper/repair behavior from query/read behavior so that reads are side-effect-free.
- Web UI (`meridian view`) — separate project consuming this infrastructure.
- HTTP/WebSocket transport — separate project reusing manifest + projections + sinks.
- Plugin loading mechanism — harness adapters are already registrable via code; config-driven external registration is future work when there's community demand.
- Interactive chat (injecting messages into running sessions) — requires a new execution mode.
- Primary launch post-fork ambiguity — reaper is conservative, not solved.
