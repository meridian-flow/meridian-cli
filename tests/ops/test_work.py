from pathlib import Path

from meridian.lib.ops.work import (
    WorkClearInput,
    WorkDashboardInput,
    WorkDoneInput,
    WorkListInput,
    WorkRenameInput,
    WorkShowInput,
    WorkStartInput,
    WorkSwitchInput,
    WorkUpdateInput,
    work_clear_sync,
    work_dashboard_sync,
    work_done_sync,
    work_list_sync,
    work_rename_sync,
    work_show_sync,
    work_start_sync,
    work_switch_sync,
    work_update_sync,
)
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.paths import resolve_state_paths


def test_work_dashboard_groups_active_spawns(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    item = work_start_sync(
        WorkStartInput(label="Auth refactor", description="step 1", repo_root=tmp_path.as_posix())
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="Implement step 1",
        desc="Implement step 1",
        work_id=item.name,
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="Loose task",
        desc="Loose task",
    )
    finished_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="Done",
        desc="Done",
        work_id=item.name,
    )
    spawn_store.finalize_spawn(state_root, finished_id, status="succeeded", exit_code=0)

    result = work_dashboard_sync(WorkDashboardInput(repo_root=tmp_path.as_posix()))

    assert len(result.items) == 1
    assert result.items[0].name == item.name
    assert result.items[0].status == "open"
    assert tuple(spawn.id for spawn in result.items[0].spawns) == ("p1",)
    assert tuple(spawn.id for spawn in result.ungrouped_spawns) == ("p2",)
    assert result.format_text().endswith("Run `meridian spawn show <id>` for details.")


def test_work_dashboard_omits_hint_when_empty(tmp_path: Path) -> None:
    result = work_dashboard_sync(WorkDashboardInput(repo_root=tmp_path.as_posix()))

    assert result.format_text() == "ACTIVE\n  (no work items)"


def test_work_start_switch_clear_and_show_round_trip(tmp_path: Path) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    started = work_start_sync(
        WorkStartInput(
            label="Feature plan",
            description="initial design",
            chat_id=chat_id,
            repo_root=tmp_path.as_posix(),
        )
    )
    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == started.name

    spawn_store.start_spawn(
        state_root,
        chat_id=chat_id,
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        prompt="Implement step 2",
        desc="Implement step 2",
        work_id=started.name,
    )

    shown = work_show_sync(WorkShowInput(work_id=started.name, repo_root=tmp_path.as_posix()))
    assert shown.name == started.name
    assert shown.work_dir == f".meridian/work/{started.name}"
    assert tuple(spawn.id for spawn in shown.spawns) == ("p1",)

    updated = work_update_sync(
        WorkUpdateInput(
            work_id=started.name,
            status="implementing step 2",
            description="step 2 in progress",
            repo_root=tmp_path.as_posix(),
        )
    )
    assert updated.status == "implementing step 2"

    switched = work_switch_sync(
        WorkSwitchInput(work_id=started.name, chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    assert switched.message == f"Active work item: {started.name}"

    cleared = work_clear_sync(WorkClearInput(chat_id=chat_id, repo_root=tmp_path.as_posix()))
    assert cleared.message == "Cleared active work item."
    cleared_session = session_store.resolve_session_ref(state_root, "session-1")
    assert cleared_session is not None
    assert cleared_session.active_work_id is None

    done = work_done_sync(WorkDoneInput(work_id=started.name, repo_root=tmp_path.as_posix()))
    assert done.status == "done"

    listed = work_list_sync(WorkListInput(repo_root=tmp_path.as_posix()))
    assert tuple(item.name for item in listed.items) == (started.name,)
    assert work_list_sync(WorkListInput(active=True, repo_root=tmp_path.as_posix())).items == ()

    session_store.stop_session(state_root, chat_id)


def test_work_rename_updates_spawns_and_session(tmp_path: Path) -> None:
    """Rename propagates to spawns with the old work_id and updates session active_work_id."""
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

    # Create a spawn tagged with the old work_id
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

    # Spawn should now reference the new work_id
    spawns = spawn_store.list_spawns(state_root, filters={"work_id": "new-name"})
    assert len(spawns) == 1
    assert spawns[0].work_id == "new-name"

    # No spawns should still reference the old work_id
    assert spawn_store.list_spawns(state_root, filters={"work_id": "old-name"}) == []

    # Session active_work_id should be updated
    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == "new-name"

    session_store.stop_session(state_root, chat_id)


def test_work_start_renames_auto_generated_item(tmp_path: Path) -> None:
    """work start renames the active auto-generated item instead of creating a new one."""
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    # Create an auto-generated work item and set it as active
    from meridian.lib.state.work_store import create_auto_work_item, get_work_item
    auto_item = create_auto_work_item(state_root)
    session_store.update_session_work_id(state_root, chat_id, auto_item.name)

    # Write a file to the work dir to prove it persists after rename
    work_dir = state_root / "work" / auto_item.name
    (work_dir / "design.md").write_text("my design doc")

    # Now call work start — should rename, not create new
    started = work_start_sync(
        WorkStartInput(
            label="Auth refactor",
            description="step 1",
            chat_id=chat_id,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert started.name == "auth-refactor"

    # Old directory should be gone, new one should exist with the design doc preserved
    assert not (state_root / "work" / auto_item.name).exists()
    assert (state_root / "work" / "auth-refactor" / "design.md").read_text() == "my design doc"

    # The item should no longer be auto-generated
    item = get_work_item(state_root, "auth-refactor")
    assert item is not None
    assert item.auto_generated is False

    # Session should point to the new name
    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == "auth-refactor"

    session_store.stop_session(state_root, chat_id)


def test_work_start_creates_new_when_not_auto_generated(tmp_path: Path) -> None:
    """work start creates a new item when the active item is not auto-generated."""
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    # Create a normal (non-auto) work item
    first = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    assert first.name == "feature-a"

    # Start a second work item — should create new, not rename
    second = work_start_sync(
        WorkStartInput(label="Feature B", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    assert second.name == "feature-b"

    # Both should exist
    from meridian.lib.state.work_store import get_work_item
    assert get_work_item(state_root, "feature-a") is not None
    assert get_work_item(state_root, "feature-b") is not None

    session_store.stop_session(state_root, chat_id)


def test_work_rename_clears_auto_generated_flag(tmp_path: Path) -> None:
    """work rename on an auto-generated item clears the auto_generated flag."""
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    # Create an auto-generated work item
    from meridian.lib.state.work_store import create_auto_work_item, get_work_item
    auto_item = create_auto_work_item(state_root)
    session_store.update_session_work_id(state_root, chat_id, auto_item.name)

    # Rename it
    renamed = work_rename_sync(
        WorkRenameInput(
            work_id=auto_item.name,
            new_name="my-feature",
            chat_id=chat_id,
            repo_root=tmp_path.as_posix(),
        )
    )
    assert renamed.new_name == "my-feature"

    # Should no longer be auto-generated
    item = get_work_item(state_root, "my-feature")
    assert item is not None
    assert item.auto_generated is False

    session_store.stop_session(state_root, chat_id)


def test_work_rename_preserves_unrelated_session_work_id(tmp_path: Path) -> None:
    """Rename should not overwrite session active_work_id if it points to a different item."""
    state_root = resolve_state_paths(tmp_path).root_dir
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    # Create two work items
    first = work_start_sync(
        WorkStartInput(label="Feature A", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )
    second = work_start_sync(
        WorkStartInput(label="Feature B", chat_id=chat_id, repo_root=tmp_path.as_posix())
    )

    # Session now points to the second work item (last started)
    session = session_store.resolve_session_ref(state_root, "session-1")
    assert session is not None
    assert session.active_work_id == second.name

    # Rename the first work item — should NOT change the session's active_work_id
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
    assert session.active_work_id == second.name  # Should still point to feature-b

    session_store.stop_session(state_root, chat_id)
