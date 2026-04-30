from __future__ import annotations

from io import StringIO

import pytest

from meridian.cli import chat_cmd
from meridian.cli.chat_cmd import run_chat_server
from meridian.lib.harness.ids import HarnessId


def test_chat_cli_auto_port_prints_local_backend_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("meridian.cli.chat_cmd.get_user_home", lambda: tmp_path / "runtime")
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run(app, *, host: str, port: int) -> None:
        calls.append({"app": app, "host": host, "port": port})

    stdout = StringIO()
    actual_port = run_chat_server(
        host="127.0.0.1",
        port=0,
        model="test-model",
        harness="claude",
        uvicorn_run=fake_run,
        stdout=stdout,
    )

    assert actual_port > 0
    assert stdout.getvalue() == f"Chat backend: http://127.0.0.1:{actual_port}\n"
    assert len(calls) == 1
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == actual_port


def test_chat_cli_uses_requested_host_and_port(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("meridian.cli.chat_cmd.get_user_home", lambda: tmp_path / "runtime")
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, int]] = []

    def fake_run(_app, *, host: str, port: int) -> None:
        calls.append((host, port))

    stdout = StringIO()
    actual_port = run_chat_server(
        host="0.0.0.0",
        port=8765,
        harness="codex",
        uvicorn_run=fake_run,
        stdout=stdout,
    )

    assert actual_port == 8765
    assert calls == [("0.0.0.0", 8765)]
    assert stdout.getvalue() == "Chat backend: http://0.0.0.0:8765\n"


@pytest.mark.parametrize("harness", ["claude", "codex", "opencode"])
def test_chat_cli_accepts_supported_harness_matrix(monkeypatch, tmp_path, harness: str) -> None:
    monkeypatch.setattr("meridian.cli.chat_cmd.get_user_home", lambda: tmp_path / harness)
    monkeypatch.chdir(tmp_path)

    run_chat_server(
        harness=harness,
        port=8900,
        uvicorn_run=lambda *_args, **_kwargs: None,
        stdout=StringIO(),
    )


def test_chat_cli_rejects_unknown_harness(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("meridian.cli.chat_cmd.get_user_home", lambda: tmp_path / "runtime")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="unsupported chat harness"):
        run_chat_server(
            harness="bogus",
            port=8900,
            uvicorn_run=lambda *_args, **_kwargs: None,
            stdout=StringIO(),
        )


@pytest.mark.parametrize("harness", [HarnessId.CLAUDE, HarnessId.CODEX, HarnessId.OPENCODE])
def test_backend_acquisition_preserves_requested_harness(tmp_path, harness: HarnessId) -> None:
    acquisition = chat_cmd._build_backend_acquisition(
        runtime_root=tmp_path / "runtime",
        project_root=tmp_path,
        harness_id=harness,
        model="model-x",
    )

    config = acquisition._build_connection_config("c1", "hello")
    spec = acquisition._build_launch_spec("hello")

    assert config.harness_id == harness
    assert spec.model == "model-x"
