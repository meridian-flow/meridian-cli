from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.types import SpawnId
from meridian.lib.ops.spawn.execute import _spawn_child_env


def test_spawn_child_env_propagates_work_id_and_dir(tmp_path: Path) -> None:
    ctx = RuntimeContext(
        spawn_id=SpawnId("p1"),
        depth=1,
        repo_root=tmp_path,
        state_root=tmp_path / ".meridian",
        chat_id="c1",
        work_id="work-5",
    )

    env = _spawn_child_env("p2", state_root=ctx.state_root, ctx=ctx)

    assert env["MERIDIAN_SPAWN_ID"] == "p2"
    assert env["MERIDIAN_PARENT_SPAWN_ID"] == "p1"
    assert env["MERIDIAN_WORK_ID"] == "work-5"
    assert env["MERIDIAN_WORK_DIR"] == (ctx.state_root / "work" / "work-5").as_posix()


def test_spawn_child_env_can_override_work_id(tmp_path: Path) -> None:
    ctx = RuntimeContext(
        depth=0,
        repo_root=tmp_path,
        state_root=tmp_path / ".meridian",
        chat_id="c1",
        work_id="work-1",
    )

    env = _spawn_child_env("p9", work_id="work-2", state_root=ctx.state_root, ctx=ctx)

    assert env["MERIDIAN_WORK_ID"] == "work-2"
    assert env["MERIDIAN_WORK_DIR"] == (ctx.state_root / "work" / "work-2").as_posix()
