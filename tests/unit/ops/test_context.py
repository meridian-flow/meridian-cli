"""Unit tests for ops context query centralization."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config.context_config import ContextConfig, ContextSourceType
from meridian.lib.context.resolver import ResolvedContextPaths
from meridian.lib.core.resolved_context import ResolvedContext
from meridian.lib.ops.context import (
    ContextInput,
    ContextOutput,
    WorkCurrentInput,
    _resolve_runtime_context,
    context_sync,
    work_current_sync,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_resolve_runtime_context_delegates_to_resolved_context(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERIDIAN_PROJECT_DIR", raising=False)
    monkeypatch.delenv("MERIDIAN_RUNTIME_DIR", raising=False)

    seen_env: list[tuple[str | None, str | None]] = []
    expected = ResolvedContext(depth=7, work_id="w7", work_dir=Path("/repo/.meridian/work/w7"))

    def fake_from_environment(cls: type[ResolvedContext]) -> ResolvedContext:
        _ = cls
        seen_env.append(
            (
                os.environ.get("MERIDIAN_PROJECT_DIR"),
                os.environ.get("MERIDIAN_RUNTIME_DIR"),
            )
        )
        return expected

    monkeypatch.setattr(ResolvedContext, "from_environment", classmethod(fake_from_environment))

    resolved = _resolve_runtime_context(Path("/repo"), Path("/runtime/state"))

    assert resolved is expected
    assert seen_env == [("/repo", "/runtime/state")]
    assert os.environ.get("MERIDIAN_PROJECT_DIR") is None
    assert os.environ.get("MERIDIAN_RUNTIME_DIR") is None


def test_context_sync_returns_catalog_fields_from_context_resolution(
    monkeypatch: MonkeyPatch,
) -> None:
    project_root = Path("/repo")

    def fake_resolve_project_root() -> Path:
        return project_root

    def fake_load_context_config(_repo: Path) -> None:
        return None

    def fake_resolve_context_paths(
        _repo: Path,
        config: ContextConfig,
    ) -> ResolvedContextPaths:
        return ResolvedContextPaths(
            work_root=Path("/abs/work"),
            work_archive=Path("/abs/archive/work"),
            work_source=config.work.source,
            kb_root=Path("/abs/kb"),
            kb_source=config.kb.source,
            extra={},
        )

    monkeypatch.setattr("meridian.lib.ops.context.resolve_project_root", fake_resolve_project_root)
    monkeypatch.setattr("meridian.lib.ops.context.load_context_config", fake_load_context_config)
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_context_paths",
        fake_resolve_context_paths,
    )

    output = context_sync(ContextInput())

    assert output.work_path == ".meridian/work"
    assert output.work_resolved == "/abs/work"
    assert output.work_source == "local"
    assert output.work_archive == ".meridian/archive/work"
    assert output.work_archive_resolved == "/abs/archive/work"
    assert output.kb_path == ".meridian/kb"
    assert output.kb_resolved == "/abs/kb"
    assert output.kb_source == "local"


def test_context_sync_uses_loaded_config_paths_and_sources(monkeypatch: MonkeyPatch) -> None:
    project_root = Path("/repo")
    config = ContextConfig.model_validate(
        {
            "work": {
                "source": ContextSourceType.GIT.value,
                "path": "custom/work",
                "archive": "custom/archive",
            },
            "kb": {
                "source": ContextSourceType.LOCAL.value,
                "path": "custom/kb",
            },
        }
    )

    def fake_resolve_project_root() -> Path:
        return project_root

    def fake_load_context_config(_repo: Path) -> ContextConfig:
        return config

    def fake_resolve_context_paths(
        _repo: Path,
        _config: ContextConfig,
    ) -> ResolvedContextPaths:
        return ResolvedContextPaths(
            work_root=Path("/resolved/work"),
            work_archive=Path("/resolved/archive"),
            work_source=ContextSourceType.GIT,
            kb_root=Path("/resolved/kb"),
            kb_source=ContextSourceType.LOCAL,
            extra={},
        )

    monkeypatch.setattr("meridian.lib.ops.context.resolve_project_root", fake_resolve_project_root)
    monkeypatch.setattr("meridian.lib.ops.context.load_context_config", fake_load_context_config)
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_context_paths",
        fake_resolve_context_paths,
    )

    output = context_sync(ContextInput())

    assert output.work_path == "custom/work"
    assert output.work_resolved == "/resolved/work"
    assert output.work_source == "git"
    assert output.work_archive == "custom/archive"
    assert output.work_archive_resolved == "/resolved/archive"
    assert output.kb_path == "custom/kb"
    assert output.kb_resolved == "/resolved/kb"
    assert output.kb_source == "local"


def test_context_output_text_formats_default_and_verbose() -> None:
    output = ContextOutput(
        work_path=".meridian/work",
        work_resolved="/repo/.meridian/work",
        work_source="local",
        work_archive=".meridian/archive/work",
        work_archive_resolved="/repo/.meridian/archive/work",
        kb_path=".meridian/kb",
        kb_resolved="/repo/.meridian/kb",
        kb_source="local",
    )

    assert (
        output.format_text()
        == "work: .meridian/work (local)\n"
        "  archive: .meridian/archive/work\n"
        "kb: .meridian/kb (local)"
    )

    verbose_output = output.model_copy(update={"render_verbose": True})
    assert (
        verbose_output.format_text()
        == "work:\n"
        "  source: local\n"
        "  path: .meridian/work\n"
        "  resolved: /repo/.meridian/work\n"
        "  archive: .meridian/archive/work\n"
        "  archive_resolved: /repo/.meridian/archive/work\n"
        "kb:\n"
        "  source: local\n"
        "  path: .meridian/kb\n"
        "  resolved: /repo/.meridian/kb"
    )


def test_context_output_resolve_name_supports_catalog_paths() -> None:
    output = ContextOutput(
        work_path=".meridian/work",
        work_resolved="/repo/.meridian/work",
        work_source="local",
        work_archive=".meridian/archive/work",
        work_archive_resolved="/repo/.meridian/archive/work",
        kb_path=".meridian/kb",
        kb_resolved="/repo/.meridian/kb",
        kb_source="local",
    )

    assert output.resolve_name("work") == "/repo/.meridian/work"
    assert output.resolve_name("kb") == "/repo/.meridian/kb"
    assert output.resolve_name("work.archive") == "/repo/.meridian/archive/work"

    try:
        output.resolve_name("unknown")
    except KeyError as exc:
        assert (
            str(exc.args[0])
            == "Unknown context 'unknown'. Expected one of: work, kb, work.archive."
        )
    else:
        raise AssertionError("Expected KeyError for unknown context lookup")


def test_work_current_sync_uses_resolved_context(monkeypatch: MonkeyPatch) -> None:
    project_root = Path("/repo")
    runtime_root = Path("/runtime/state")

    def fake_resolve_project_root() -> Path:
        return project_root

    def fake_resolve_runtime_root_for_read(_project_root: Path) -> Path:
        return runtime_root

    def fake_resolve_runtime_context(_repo: Path, _state: Path) -> ResolvedContext:
        return ResolvedContext(work_dir=Path("/repo/.meridian/work/current"))

    monkeypatch.setattr("meridian.lib.ops.context.resolve_project_root", fake_resolve_project_root)
    monkeypatch.setattr(
        "meridian.lib.ops.context.resolve_runtime_root_for_read",
        fake_resolve_runtime_root_for_read,
    )
    monkeypatch.setattr(
        "meridian.lib.ops.context._resolve_runtime_context",
        fake_resolve_runtime_context,
    )

    output = work_current_sync(WorkCurrentInput())

    assert output.work_dir == "/repo/.meridian/work/current"


def test_ops_context_env_parsing_is_limited_to_repo_and_state_defaults() -> None:
    source_path = Path(__file__).resolve().parents[3] / "src/meridian/lib/ops/context.py"
    source = source_path.read_text(encoding="utf-8")
    meridian_keys = set(re.findall(r"MERIDIAN_[A-Z_]+", source))

    assert meridian_keys == {"MERIDIAN_PROJECT_DIR", "MERIDIAN_RUNTIME_DIR"}
