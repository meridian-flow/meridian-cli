from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.runtime import ResolvedRoots, resolve_chat_id, resolve_roots, runtime_context


def test_resolved_roots_is_frozen() -> None:
    roots = ResolvedRoots(repo_root=Path("/tmp/repo"), state_root=Path("/tmp/repo/.meridian"))

    with pytest.raises(FrozenInstanceError):
        setattr(roots, "repo_root", Path("/tmp/other"))


def test_resolved_roots_has_expected_fields() -> None:
    field_names = {field.name for field in fields(ResolvedRoots)}
    assert "repo_root" in field_names
    assert "state_root" in field_names


def test_runtime_context_returns_explicit_ctx() -> None:
    ctx = RuntimeContext(chat_id="c1")

    assert runtime_context(ctx) is ctx


def test_runtime_context_uses_environment_when_ctx_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "env-chat")

    resolved = runtime_context(None)

    assert resolved.chat_id == "env-chat"


def test_resolve_roots_returns_repo_and_state_root(tmp_path: Path) -> None:
    roots = resolve_roots(tmp_path.as_posix())

    assert isinstance(roots, ResolvedRoots)
    assert roots.repo_root == tmp_path.resolve()
    assert roots.state_root == roots.repo_root / ".meridian"


def test_resolve_chat_id_prefers_non_empty_payload_chat_id() -> None:
    ctx = RuntimeContext(chat_id="ctx-chat")

    resolved = resolve_chat_id(payload_chat_id="  payload-chat  ", ctx=ctx, fallback="c0")

    assert resolved == "payload-chat"


def test_resolve_chat_id_uses_ctx_chat_id_when_payload_is_empty() -> None:
    ctx = RuntimeContext(chat_id="  ctx-chat  ")

    resolved = resolve_chat_id(payload_chat_id="", ctx=ctx, fallback="c0")

    assert resolved == "ctx-chat"


def test_resolve_chat_id_uses_ctx_chat_id_when_payload_is_whitespace() -> None:
    ctx = RuntimeContext(chat_id="ctx-chat")

    resolved = resolve_chat_id(payload_chat_id="   ", ctx=ctx, fallback="c0")

    assert resolved == "ctx-chat"


def test_resolve_chat_id_uses_fallback_when_payload_and_ctx_are_empty() -> None:
    resolved = resolve_chat_id(payload_chat_id="", ctx=None, fallback="fallback-chat")

    assert resolved == "fallback-chat"


def test_resolve_chat_id_uses_c0_fallback_when_requested() -> None:
    resolved = resolve_chat_id(payload_chat_id="", ctx=None, fallback="c0")

    assert resolved == "c0"


def test_resolve_chat_id_defaults_to_empty_string_when_all_sources_empty() -> None:
    resolved = resolve_chat_id(payload_chat_id="", ctx=None)

    assert resolved == ""


@pytest.mark.parametrize(
    ("relative_path", "forbidden_defs"),
    [
        (
            "src/meridian/lib/ops/spawn/execute.py",
            ("_runtime_context", "_resolve_chat_id"),
        ),
        ("src/meridian/lib/ops/spawn/api.py", ("_runtime_context", "_state_root")),
        (
            "src/meridian/lib/ops/work.py",
            ("_runtime_context", "_resolve_roots", "_resolve_chat_id"),
        ),
    ],
)
def test_removed_runtime_helpers_not_defined(
    relative_path: str,
    forbidden_defs: tuple[str, ...],
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / relative_path).read_text(encoding="utf-8")

    for helper_name in forbidden_defs:
        assert f"def {helper_name}(" not in source
