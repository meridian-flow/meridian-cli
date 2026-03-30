import importlib
from pathlib import Path

import pytest

from meridian.lib.launch.types import LaunchRequest, LaunchResult, SessionMode
from meridian.lib.ops.reference import ResolvedSessionReference

main_cli = importlib.import_module("meridian.cli.main")


def _stub_launch_primary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    continue_ref: str = "c402",
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def _fake_launch_primary(
        *,
        repo_root: Path,
        request: LaunchRequest,
        harness_registry: object,
    ) -> LaunchResult:
        captured["repo_root"] = repo_root
        captured["request"] = request
        captured["harness_registry"] = harness_registry
        return LaunchResult(
            command=("meridian", "dry-run"),
            exit_code=0,
            continue_ref=continue_ref,
            warning=None,
        )

    monkeypatch.setattr(main_cli, "launch_primary", _fake_launch_primary)
    return captured


def test_run_primary_launch_fork_sets_launch_request_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(main_cli, "get_default_harness_registry", lambda: object())
    monkeypatch.setattr(
        main_cli,
        "resolve_session_reference",
        lambda _repo_root, _ref: ResolvedSessionReference(
            harness_session_id="session-42",
            harness="claude",
            source_chat_id="c42",
            source_model="gpt-source",
            source_agent="reviewer",
            source_skills=(),
            source_work_id="w-source",
            tracked=True,
        ),
    )
    captured = _stub_launch_primary(monkeypatch)
    emitted: list[main_cli.PrimaryLaunchOutput] = []
    monkeypatch.setattr(main_cli, "emit", emitted.append)

    main_cli._run_primary_launch(
        continue_ref=None,
        fork_ref="p42",
        model="",
        harness=None,
        agent=None,
        work="",
        yolo=False,
        approval=None,
        autocompact=None,
        thinking=None,
        sandbox=None,
        timeout=None,
        dry_run=True,
        passthrough=(),
    )

    request = captured["request"]
    assert isinstance(request, LaunchRequest)
    assert request.session_mode == SessionMode.FORK
    assert request.continue_harness_session_id == "session-42"
    assert request.continue_chat_id is None
    assert request.continue_fork is True
    assert request.forked_from_chat_id == "c42"
    assert request.model == "gpt-source"
    assert request.agent == "reviewer"
    assert request.work_id == "w-source"

    output = emitted[0]
    assert output.message == "Fork dry-run."
    assert output.forked_from == "c42"


def test_run_primary_launch_fork_allows_model_and_agent_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(main_cli, "get_default_harness_registry", lambda: object())
    monkeypatch.setattr(
        main_cli,
        "resolve_session_reference",
        lambda _repo_root, _ref: ResolvedSessionReference(
            harness_session_id="session-42",
            harness="claude",
            source_chat_id="c42",
            source_model="gpt-source",
            source_agent="source-agent",
            source_skills=(),
            source_work_id="w-source",
            tracked=True,
        ),
    )
    captured = _stub_launch_primary(monkeypatch)
    monkeypatch.setattr(main_cli, "emit", lambda _payload: None)

    main_cli._run_primary_launch(
        continue_ref=None,
        fork_ref="c42",
        model="gpt-override",
        harness="claude",
        agent="override-agent",
        work="w-override",
        yolo=False,
        approval=None,
        autocompact=None,
        thinking=None,
        sandbox=None,
        timeout=None,
        dry_run=True,
        passthrough=(),
    )

    request = captured["request"]
    assert isinstance(request, LaunchRequest)
    assert request.model == "gpt-override"
    assert request.agent == "override-agent"
    assert request.work_id == "w-override"


def test_run_primary_launch_fork_rejects_conflicting_flags() -> None:
    with pytest.raises(ValueError, match="Cannot combine --fork with --continue\\."):
        main_cli._run_primary_launch(
            continue_ref="c1",
            fork_ref="c2",
            model="",
            harness=None,
            agent=None,
            work="",
            yolo=False,
            approval=None,
            autocompact=None,
            thinking=None,
            sandbox=None,
            timeout=None,
            dry_run=True,
            passthrough=(),
        )


def test_run_primary_launch_continue_still_rejects_model_override() -> None:
    with pytest.raises(ValueError, match="Cannot combine --continue with --model\\."):
        main_cli._run_primary_launch(
            continue_ref="c1",
            fork_ref=None,
            model="gpt-5.4",
            harness=None,
            agent=None,
            work="",
            yolo=False,
            approval=None,
            autocompact=None,
            thinking=None,
            sandbox=None,
            timeout=None,
            dry_run=True,
            passthrough=(),
        )


def test_run_primary_launch_fork_rejects_cross_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(main_cli, "get_default_harness_registry", lambda: object())
    monkeypatch.setattr(
        main_cli,
        "resolve_session_reference",
        lambda _repo_root, _ref: ResolvedSessionReference(
            harness_session_id="session-42",
            harness="claude",
            source_chat_id="c42",
            source_model=None,
            source_agent=None,
            source_skills=(),
            source_work_id=None,
            tracked=True,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Cannot fork across harnesses: source is 'claude', target is 'codex'\\.",
    ):
        main_cli._run_primary_launch(
            continue_ref=None,
            fork_ref="c42",
            model="",
            harness="codex",
            agent=None,
            work="",
            yolo=False,
            approval=None,
            autocompact=None,
            thinking=None,
            sandbox=None,
            timeout=None,
            dry_run=True,
            passthrough=(),
        )


def test_run_primary_launch_fork_requires_recorded_harness_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(main_cli, "get_default_harness_registry", lambda: object())
    monkeypatch.setattr(
        main_cli,
        "resolve_session_reference",
        lambda _repo_root, _ref: ResolvedSessionReference(
            harness_session_id=None,
            harness="claude",
            source_chat_id="c42",
            source_model=None,
            source_agent=None,
            source_skills=(),
            source_work_id=None,
            tracked=True,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Spawn 'p42' has no recorded session — cannot fork\\.",
    ):
        main_cli._run_primary_launch(
            continue_ref=None,
            fork_ref="p42",
            model="",
            harness=None,
            agent=None,
            work="",
            yolo=False,
            approval=None,
            autocompact=None,
            thinking=None,
            sandbox=None,
            timeout=None,
            dry_run=True,
            passthrough=(),
        )


def test_first_positional_token_treats_fork_as_value_flag() -> None:
    assert main_cli._first_positional_token(("--fork", "c1")) is None
