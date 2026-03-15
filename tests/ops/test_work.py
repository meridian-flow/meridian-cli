from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.work_dashboard import (
    WorkDashboardInput,
    WorkShowInput,
    work_dashboard_sync,
    work_show_sync,
)
from meridian.lib.ops.work_lifecycle import (
    WorkClearInput,
    WorkDoneInput,
    WorkRenameInput,
    WorkReopenInput,
    WorkStartInput,
    WorkUpdateInput,
    work_clear_sync,
    work_done_sync,
    work_rename_sync,
    work_reopen_sync,
    work_start_sync,
    work_update_sync,
)
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.paths import resolve_state_paths


def test_work_start_creates_item_and_sets_active_work(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    started = work_start_sync(
        WorkStartInput(label="Auth refactor", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )

    assert started.name == "auth-refactor"
    assert (state_root / "work-items" / "auth-refactor.json").exists()
    assert not (state_root / "work" / "auth-refactor").exists()

    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == "auth-refactor"

    session_store.stop_session(state_root, chat_id)


def test_work_start_switches_to_existing_open_work_item(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    first = work_start_sync(
        WorkStartInput(label="Auth refactor", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    second = work_start_sync(
        WorkStartInput(label="Auth refactor", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )

    assert first.created is True
    assert second.created is False
    assert second.name == "auth-refactor"
    assert second.description == first.description

    session_store.stop_session(state_root, chat_id)


def test_work_start_rejects_done_work_item_with_reopen_hint(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    started = work_start_sync(
        WorkStartInput(label="Auth refactor", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    work_done_sync(WorkDoneInput(work_id=started.name, repo_root=tmp_path.as_posix()))

    try:
        work_start_sync(
            WorkStartInput(label="Auth refactor", chat_id=chat_id, repo_root=tmp_path.as_posix())
        )
    except ValueError as exc:
        assert f"work reopen {started.name}" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected done work start to fail.")

    session_store.stop_session(state_root, chat_id)


def test_work_rename_updates_spawns_and_session(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    started = work_start_sync(
        WorkStartInput(label="Old name", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    spawn_store.start_spawn(
        state_root,
        chat_id=chat_id,
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="task",
        desc="step 1",
        work_id=started.name,
    )

    renamed = work_rename_sync(
        WorkRenameInput(
            work_id=started.name,
            new_name="new-name",
            chat_id=chat_id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert renamed.old_name == "old-name"
    assert renamed.new_name == "new-name"
    spawns = spawn_store.list_spawns(state_root, filters={"work_id": "new-name"})
    assert len(spawns) == 1
    assert spawn_store.list_spawns(state_root, filters={"work_id": "old-name"}) == []

    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == "new-name"

    session_store.stop_session(state_root, chat_id)


def test_work_rename_preserves_unrelated_session_work_id(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    first = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    second = work_start_sync(
        WorkStartInput(label="Feature B", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )

    work_rename_sync(
        WorkRenameInput(
            work_id=first.name,
            new_name="feature-a-renamed",
            chat_id=chat_id,
            repo_root=tmp_path.as_posix(),
        )
    )

    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == second.name

    session_store.stop_session(state_root, chat_id)


def test_work_dashboard_projects_primary_session_attachment(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )
    started = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    primary_spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id=chat_id,
        model="gpt-5.4",
        agent="",
        harness="codex",
        prompt="task",
        kind="primary",
        status="running",
    )

    dashboard = work_dashboard_sync(WorkDashboardInput(repo_root=tmp_path.as_posix()))
    cleared = work_clear_sync(WorkClearInput(chat_id=chat_id, repo_root=tmp_path.as_posix()))
    cleared_dashboard = work_dashboard_sync(WorkDashboardInput(repo_root=tmp_path.as_posix()))

    assert dashboard.items[0].name == started.name
    assert [spawn.id for spawn in dashboard.items[0].spawns] == [primary_spawn_id]
    assert cleared.message == "Cleared active work item."
    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id is None
    spawn = spawn_store.get_spawn(state_root, primary_spawn_id)
    assert spawn is not None
    assert spawn.work_id is None
    assert [item.name for item in cleared_dashboard.items] == []
    assert [spawn.id for spawn in cleared_dashboard.ungrouped_spawns] == [primary_spawn_id]

    session_store.stop_session(state_root, chat_id)


def test_work_show_includes_active_primary_via_session_attachment(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )
    started = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    primary_spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id=chat_id,
        model="gpt-5.4",
        agent="",
        harness="codex",
        prompt="task",
        kind="primary",
        status="running",
    )

    shown = work_show_sync(WorkShowInput(work_id=started.name, repo_root=tmp_path.as_posix()))

    assert [spawn.id for spawn in shown.spawns] == [primary_spawn_id]

    session_store.stop_session(state_root, chat_id)


def test_nested_work_start_and_update_warn(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )
    ctx = RuntimeContext(depth=1, chat_id=chat_id)

    started = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix()),
        ctx=ctx,
    )
    updated = work_update_sync(
        WorkUpdateInput(work_id=started.name, status="in-progress", repo_root=tmp_path.as_posix()),
        ctx=ctx,
    )
    done = work_done_sync(
        WorkDoneInput(work_id=started.name, repo_root=tmp_path.as_posix()),
        ctx=ctx,
    )
    cleared = work_clear_sync(
        WorkClearInput(chat_id=chat_id, repo_root=tmp_path.as_posix()),
        ctx=ctx,
    )

    assert started.warning is not None
    assert updated.warning == started.warning
    assert done.warning is not None
    assert started.warning in done.warning
    assert "session(s):" in done.warning
    assert cleared.warning == started.warning

    session_store.stop_session(state_root, chat_id)


def test_work_done_archives_scratch_dir_and_work_reopen_restores_it(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    started = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    active_dir = state_root / "work" / started.name
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "notes.md").write_text("hello", encoding="utf-8")

    done = work_done_sync(WorkDoneInput(work_id=started.name, repo_root=tmp_path.as_posix()))
    show_done = work_show_sync(WorkShowInput(work_id=started.name, repo_root=tmp_path.as_posix()))

    archived_dir = state_root / "work-archive" / started.name
    assert done.status == "done"
    assert not active_dir.exists()
    assert (archived_dir / "notes.md").read_text(encoding="utf-8") == "hello"
    assert show_done.work_dir == ".meridian/work-archive/feature-a"

    reopened = work_reopen_sync(
        WorkReopenInput(work_id=started.name, repo_root=tmp_path.as_posix())
    )
    show_reopened = work_show_sync(
        WorkShowInput(work_id=started.name, repo_root=tmp_path.as_posix())
    )

    assert reopened.status == "open"
    assert not archived_dir.exists()
    assert (active_dir / "notes.md").read_text(encoding="utf-8") == "hello"
    assert show_reopened.work_dir == ".meridian/work/feature-a"

    session_store.stop_session(state_root, chat_id)


def test_work_update_status_done_archives_and_done_warning_mentions_active_references(
    tmp_path: Path,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )
    started = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    spawn_store.start_spawn(
        state_root,
        chat_id=chat_id,
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="task",
        desc="step 1",
        work_id=started.name,
        status="running",
    )
    active_dir = state_root / "work" / started.name
    active_dir.mkdir(parents=True, exist_ok=True)

    updated = work_update_sync(
        WorkUpdateInput(work_id=started.name, status="done", repo_root=tmp_path.as_posix())
    )

    assert updated.status == "done"
    assert updated.warning is not None
    assert "session(s):" in updated.warning
    assert "active spawn(s):" in updated.warning
    assert not active_dir.exists()
    assert (state_root / "work-archive" / started.name).exists()

    session_store.stop_session(state_root, chat_id)
