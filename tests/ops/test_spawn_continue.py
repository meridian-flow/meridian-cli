from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.spawn.api import spawn_continue_sync
from meridian.lib.ops.spawn.models import SpawnContinueInput
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths


def _write_agent(path: Path, *, sandbox: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "name: coder",
                "description: test coder",
                "model: gpt-5.3-codex",
                f"sandbox: {sandbox}",
                "---",
                "",
                "# Coder",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_spawn_continue_uses_source_spawn_harness_session(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")

    state_root = resolve_state_paths(repo_root).root_dir
    source_spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="agent",
        harness="codex",
        kind="child",
        prompt="source prompt",
        harness_session_id="session-1",
    )

    result = spawn_continue_sync(
        SpawnContinueInput(
            spawn_id=str(source_spawn_id),
            prompt="follow up",
            agent="coder",
            dry_run=True,
            repo_root=repo_root.as_posix(),
        ),
        ctx=RuntimeContext(
            chat_id="c-parent",
            work_id="work-9",
        ),
    )

    assert result.status == "dry-run"
