from pathlib import Path

from meridian.lib.config.settings import load_config
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.ops.runtime import build_runtime_from_root_and_config
from meridian.lib.ops.spawn.models import SpawnCreateInput
from meridian.lib.ops.spawn.plan import SessionContinuation
from meridian.lib.ops.spawn.prepare import build_create_payload


def _write_minimal_subagent(repo_root: Path) -> None:
    agents_dir = repo_root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "meridian-subagent.md").write_text(
        "---\n"
        "name: meridian-subagent\n"
        "description: Test subagent profile\n"
        "model: gpt-5.3-codex\n"
        "---\n"
        "\n"
        "Test profile body.\n",
        encoding="utf-8",
    )


def _prepare_codex_runtime(repo_root: Path):
    _write_minimal_subagent(repo_root)
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )
    harness_registry = get_default_harness_registry()
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)
    return codex_adapter, build_runtime_from_root_and_config(
        repo_root, load_config(repo_root)
    )


def test_fork_prepare_preserves_continue_fork_and_defers_materialization(
    monkeypatch, tmp_path: Path
) -> None:
    """I-10: build_create_payload must NOT call fork_session.

    Fork materialization is deferred to execute.py (after the spawn row exists).
    prepare.py's job is to preserve continue_fork=True so the executor can act on it.
    """
    codex_adapter, runtime = _prepare_codex_runtime(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        codex_adapter,
        "fork_session",
        lambda source_session_id: calls.append(source_session_id) or "forked-session",
    )

    prepared = build_create_payload(
        SpawnCreateInput(
            prompt="fork prompt",
            repo_root=tmp_path.as_posix(),
            session=SessionContinuation(
                harness_session_id="source-session",
                continue_harness="codex",
                continue_fork=True,
            ),
            dry_run=False,
        ),
        runtime=runtime,
    )
    dry_run_prepared = build_create_payload(
        SpawnCreateInput(
            prompt="fork prompt",
            repo_root=tmp_path.as_posix(),
            session=SessionContinuation(
                harness_session_id="source-session",
                continue_harness="codex",
                continue_fork=True,
            ),
            dry_run=True,
        ),
        runtime=runtime,
    )

    # I-10: fork_session must NOT be called in prepare — fork happens after the row exists.
    assert calls == []
    # The source session ID and continue_fork=True are preserved for the executor.
    assert prepared.session.harness_session_id == "source-session"
    assert prepared.session.continue_fork is True
    # dry_run also preserves the deferred state.
    assert dry_run_prepared.session.harness_session_id == "source-session"
    assert dry_run_prepared.session.continue_fork is True
