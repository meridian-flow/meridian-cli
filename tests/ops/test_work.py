from pathlib import Path

from meridian.lib.ops.work import (
    WorkClearInput,
    WorkDashboardInput,
    WorkDoneInput,
    WorkListInput,
    WorkShowInput,
    WorkStartInput,
    WorkSwitchInput,
    WorkUpdateInput,
    work_clear_sync,
    work_dashboard_sync,
    work_done_sync,
    work_list_sync,
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
