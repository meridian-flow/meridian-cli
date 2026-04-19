import importlib
from io import StringIO

import pytest

cli_main = importlib.import_module("meridian.cli.main")
mars_passthrough = importlib.import_module("meridian.cli.mars_passthrough")


def test_run_mars_passthrough_non_sync_json_streams_stdout_stderr() -> None:
    request = mars_passthrough.MarsPassthroughRequest(
        command=("/usr/bin/mars", "--json", "list"),
        mars_args=("--json", "list"),
        is_sync=False,
        wants_json=True,
        root_override=None,
    )
    stdout = StringIO()
    stderr = StringIO()

    with pytest.raises(SystemExit) as exc_info:
        mars_passthrough.run_mars_passthrough(
            ["list"],
            output_format="json",
            resolve_executable=lambda: "/usr/bin/mars",
            parse_request=lambda *_args, **_kwargs: request,
            execute_request=lambda _request: mars_passthrough.MarsPassthroughResult(
                request=request,
                returncode=7,
                stdout_text='{"packages": []}\n',
                stderr_text="warning\n",
            ),
            stdout=stdout,
            stderr=stderr,
        )

    assert exc_info.value.code == 7
    assert stdout.getvalue() == '{"packages": []}\n'
    assert stderr.getvalue() == "warning\n"


def test_run_mars_passthrough_sync_calls_augment_result() -> None:
    request = mars_passthrough.MarsPassthroughRequest(
        command=("/usr/bin/mars", "sync"),
        mars_args=("sync",),
        is_sync=True,
        wants_json=False,
        root_override=None,
    )
    observed: list[mars_passthrough.MarsPassthroughResult] = []

    with pytest.raises(SystemExit) as exc_info:
        mars_passthrough.run_mars_passthrough(
            ["sync"],
            resolve_executable=lambda: "/usr/bin/mars",
            parse_request=lambda *_args, **_kwargs: request,
            execute_request=lambda _request: mars_passthrough.MarsPassthroughResult(
                request=request,
                returncode=1,
            ),
            augment_result=lambda result: observed.append(result),
        )

    assert exc_info.value.code == 1
    assert len(observed) == 1
    assert observed[0].request.is_sync is True


def test_main_mars_defaults_to_json_in_agent_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_run_mars_passthrough(
        args: tuple[str, ...] | list[str],
        *,
        output_format: str | None = None,
        **_kwargs: object,
    ) -> None:
        captured["args"] = tuple(args)
        captured["output_format"] = output_format
        raise SystemExit(0)

    monkeypatch.setattr(mars_passthrough, "run_mars_passthrough", _fake_run_mars_passthrough)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["mars", "list"])

    assert exc_info.value.code == 0
    assert captured["args"] == ("list",)
    assert captured["output_format"] == "json"


def test_main_mars_honors_explicit_text_in_agent_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_run_mars_passthrough(
        args: tuple[str, ...] | list[str],
        *,
        output_format: str | None = None,
        **_kwargs: object,
    ) -> None:
        captured["args"] = tuple(args)
        captured["output_format"] = output_format
        raise SystemExit(0)

    monkeypatch.setattr(mars_passthrough, "run_mars_passthrough", _fake_run_mars_passthrough)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--format", "text", "mars", "list"])

    assert exc_info.value.code == 0
    assert captured["args"] == ("list",)
    assert captured["output_format"] == "text"
