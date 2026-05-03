import io
import logging
from pathlib import Path

from meridian.lib.diagnostics import capture_library_diagnostics
from meridian.lib.launch.prompt import build_agent_inventory_prompt


def _root_stream_handler() -> tuple[logging.StreamHandler[io.StringIO], io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)
    return handler, stream


class _CapturingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _write_legacy_profile(project_root: Path) -> None:
    agents_dir = project_root / ".mars" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "legacy.md").write_text(
        "\n".join(
            [
                "---",
                "name: Legacy",
                "models:",
                "  gpt55:",
                "    effort: low",
                "---",
                "",
                "Profile body.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_capture_library_diagnostics_captures_warnings_not_stderr() -> None:
    handler, stream = _root_stream_handler()
    logger = logging.getLogger("meridian.lib.catalog.agent")
    try:
        with capture_library_diagnostics() as diag:
            logger.warning("catalog warning")

        assert [record.getMessage() for record in diag.records] == ["catalog warning"]
        assert stream.getvalue() == ""
    finally:
        logging.getLogger().removeHandler(handler)


def test_capture_library_diagnostics_allows_errors_to_stderr() -> None:
    handler, stream = _root_stream_handler()
    logger = logging.getLogger("meridian.lib.catalog.agent")
    try:
        with capture_library_diagnostics() as diag:
            logger.error("catalog error")

        assert diag.records == []
        assert "catalog error" in stream.getvalue()
    finally:
        logging.getLogger().removeHandler(handler)


def test_capture_library_diagnostics_leaves_non_meridian_warnings_unaffected() -> None:
    handler, stream = _root_stream_handler()
    logger = logging.getLogger("external.library")
    try:
        with capture_library_diagnostics() as diag:
            logger.warning("external warning")

        assert diag.records == []
        assert "external warning" in stream.getvalue()
    finally:
        logging.getLogger().removeHandler(handler)


def test_capture_library_diagnostics_restores_warning_logging_after_exit() -> None:
    handler, stream = _root_stream_handler()
    logger = logging.getLogger("meridian.lib.catalog.agent")
    try:
        with capture_library_diagnostics():
            logger.warning("captured warning")

        logger.warning("normal warning")

        output = stream.getvalue()
        assert "captured warning" not in output
        assert "normal warning" in output
    finally:
        logging.getLogger().removeHandler(handler)


def test_build_launch_context_does_not_leak_library_warnings_to_stderr(
    tmp_path: Path,
) -> None:
    """Structural guard: library warnings during launch must not reach stderr."""

    _write_legacy_profile(tmp_path)
    handler = _CapturingHandler()
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)
    try:
        build_agent_inventory_prompt(project_root=tmp_path)

        assert any(
            record.name.startswith("meridian.lib")
            and record.levelno == logging.WARNING
            and "uses legacy models" in record.getMessage()
            for record in handler.records
        )

        handler.records.clear()
        with capture_library_diagnostics() as diag:
            build_agent_inventory_prompt(project_root=tmp_path)

        assert any(
            record.name.startswith("meridian.lib")
            and record.levelno == logging.WARNING
            and "uses legacy models" in record.getMessage()
            for record in diag.records
        )
        assert not [
            record
            for record in handler.records
            if record.name.startswith("meridian.lib")
            and record.levelno == logging.WARNING
        ]
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)
