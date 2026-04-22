"""Unit tests for the shared child-env contract."""

from pathlib import Path

import pytest

from meridian.lib.core.child_env import (
    ALLOWED_CHILD_ENV_KEYS,
    build_child_env_overrides,
    validate_child_env_keys,
)
from meridian.lib.core.resolved_context import ResolvedContext

# ---------------------------------------------------------------------------
# validate_child_env_keys
# ---------------------------------------------------------------------------


def test_validate_accepts_all_allowed_keys() -> None:
    """All keys in ALLOWED_CHILD_ENV_KEYS must pass validation without error."""
    overrides = {key: "value" for key in ALLOWED_CHILD_ENV_KEYS}
    # Should not raise
    validate_child_env_keys(overrides)


def test_validate_accepts_non_meridian_keys() -> None:
    """Non-MERIDIAN_* keys must always pass validation."""
    overrides = {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80",
    }
    validate_child_env_keys(overrides)


def test_validate_accepts_empty_mapping() -> None:
    """Empty mapping must pass without error."""
    validate_child_env_keys({})


def test_validate_accepts_parent_spawn_id() -> None:
    validate_child_env_keys({"MERIDIAN_PARENT_SPAWN_ID": "p1"})


def test_validate_accepts_context_dir_keys() -> None:
    validate_child_env_keys({"MERIDIAN_CONTEXT_DOCS_DIR": "/contexts/docs"})


def test_validate_rejects_unexpected_meridian_key() -> None:
    """An unknown MERIDIAN_* key must raise RuntimeError."""
    overrides = {"MERIDIAN_UNKNOWN_CUSTOM": "value"}
    with pytest.raises(RuntimeError, match="Unexpected MERIDIAN_\\* key in child env"):
        validate_child_env_keys(overrides)


def test_validate_rejects_unexpected_key_mixed_with_allowed() -> None:
    """RuntimeError must be raised even when some allowed keys are present."""
    overrides = {
        "MERIDIAN_DEPTH": "1",
        "MERIDIAN_PROJECT_DIR": "/repo",
        "MERIDIAN_NOVEL_KEY": "bad",
    }
    with pytest.raises(RuntimeError, match="MERIDIAN_NOVEL_KEY"):
        validate_child_env_keys(overrides)


def test_validate_rejects_context_dir_near_misses() -> None:
    for key in (
        "MERIDIAN_CONTEXT_DOCS",
        "MERIDIAN_CONTEXT__DIR",
        "MERIDIAN_CONTEXT_DOCS_DIR_EXTRA",
    ):
        with pytest.raises(RuntimeError, match=key):
            validate_child_env_keys({key: "/bad"})


# ---------------------------------------------------------------------------
# build_child_env_overrides
# ---------------------------------------------------------------------------


def test_build_produces_depth_always() -> None:
    """MERIDIAN_DEPTH must always appear in the result."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=0,
    )
    assert "MERIDIAN_DEPTH" in result


def test_build_increments_depth_by_default() -> None:
    """Default increment_depth=True must produce parent_depth + 1."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=3,
    )
    assert result["MERIDIAN_DEPTH"] == "4"


def test_build_no_increment_keeps_depth() -> None:
    """increment_depth=False must keep the depth value unchanged."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=2,
        increment_depth=False,
    )
    assert result["MERIDIAN_DEPTH"] == "2"


def test_build_omits_none_fields() -> None:
    """Fields that are None/empty must not appear in the result dict."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=0,
        work_id=None,
        work_dir=None,
        kb_dir=None,
    )
    assert "MERIDIAN_PROJECT_DIR" not in result
    assert "MERIDIAN_RUNTIME_DIR" not in result
    assert "MERIDIAN_CHAT_ID" not in result
    assert "MERIDIAN_WORK_ID" not in result
    assert "MERIDIAN_WORK_DIR" not in result
    assert "MERIDIAN_KB_DIR" not in result
    assert "MERIDIAN_FS_DIR" not in result


def test_build_full_overrides() -> None:
    """All populated fields must appear with correct string values."""
    repo = Path("/repo")
    state = Path("/runtime/state")
    work_dir = Path("/repo/.meridian/work/w1")
    kb_dir = Path("/repo/.meridian/kb")

    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=repo,
        runtime_root=state,
        parent_chat_id="c99",
        parent_depth=1,
        work_id="w1",
        work_dir=work_dir,
        kb_dir=kb_dir,
    )

    assert result == {
        "MERIDIAN_DEPTH": "2",
        "MERIDIAN_PROJECT_DIR": "/repo",
        "MERIDIAN_RUNTIME_DIR": "/runtime/state",
        "MERIDIAN_CHAT_ID": "c99",
        "MERIDIAN_WORK_ID": "w1",
        "MERIDIAN_WORK_DIR": "/repo/.meridian/work/w1",
        "MERIDIAN_KB_DIR": "/repo/.meridian/kb",
        "MERIDIAN_FS_DIR": "/repo/.meridian/kb",
    }


def test_build_with_child_spawn_id() -> None:
    result = build_child_env_overrides(
        parent_spawn_id="p-parent",
        child_spawn_id="p-child",
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=1,
    )

    assert result["MERIDIAN_SPAWN_ID"] == "p-child"
    assert result["MERIDIAN_PARENT_SPAWN_ID"] == "p-parent"


def test_build_with_context_dirs() -> None:
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=0,
        context_dirs=(("docs", Path("/contexts/docs")),),
    )

    assert result["MERIDIAN_CONTEXT_DOCS_DIR"] == "/contexts/docs"


def test_build_result_keys_are_subset_of_allowed() -> None:
    """All keys produced by build_child_env_overrides must be in ALLOWED_CHILD_ENV_KEYS."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=Path("/r"),
        runtime_root=Path("/s"),
        parent_chat_id="c1",
        parent_depth=0,
        work_id="wid",
        work_dir=Path("/s/work/wid"),
        kb_dir=Path("/r/.meridian/kb"),
    )
    unexpected = set(result) - ALLOWED_CHILD_ENV_KEYS
    assert unexpected == set(), f"Unexpected keys: {unexpected}"


# ---------------------------------------------------------------------------
# Integration: build_child_env_overrides ↔ ResolvedContext.child_env_overrides
# ---------------------------------------------------------------------------


def test_integration_matches_resolved_context_child_env_overrides() -> None:
    """build_child_env_overrides must produce identical output to the underlying
    ResolvedContext.child_env_overrides() call it delegates to."""
    repo = Path("/my/repo")
    state = Path("/my/state")
    work_dir = Path("/my/state/work/w42")
    kb_dir = Path("/my/repo/.meridian/kb")

    ctx = ResolvedContext(
        depth=2,
        project_root=repo,
        runtime_root=state,
        chat_id="c7",
        work_id="w42",
        work_dir=work_dir,
        kb_dir=kb_dir,
    )
    expected = ctx.child_env_overrides()

    result = build_child_env_overrides(
        parent_spawn_id=None,
        child_spawn_id=None,
        project_root=repo,
        runtime_root=state,
        parent_chat_id="c7",
        parent_depth=2,
        work_id="w42",
        work_dir=work_dir,
        kb_dir=kb_dir,
        context_dirs=(),
    )

    assert result == expected


def test_integration_increment_depth_false_matches_resolved_context() -> None:
    """increment_depth=False must match child_env_overrides(increment_depth=False)."""
    ctx = ResolvedContext(
        depth=5,
        project_root=Path("/r"),
        runtime_root=Path("/s"),
        chat_id="c5",
    )
    expected = ctx.child_env_overrides(increment_depth=False)

    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=Path("/r"),
        runtime_root=Path("/s"),
        parent_chat_id="c5",
        parent_depth=5,
        increment_depth=False,
    )

    assert result == expected


# ---------------------------------------------------------------------------
# Edge case 6: increment_depth=False at depth 0 stays at 0
# ---------------------------------------------------------------------------


def test_build_no_increment_at_depth_zero_stays_zero() -> None:
    """increment_depth=False at parent_depth=0 must produce MERIDIAN_DEPTH=0, not -1."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=0,
        increment_depth=False,
    )
    assert result["MERIDIAN_DEPTH"] == "0"


def test_build_no_increment_preserves_large_depth() -> None:
    """increment_depth=False must keep an arbitrary depth value unchanged."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=99,
        increment_depth=False,
    )
    assert result["MERIDIAN_DEPTH"] == "99"


# ---------------------------------------------------------------------------
# Edge case 7: validate_child_env_keys with mixed allowed/disallowed keys
# ---------------------------------------------------------------------------


def test_validate_rejects_bad_key_alongside_non_meridian_keys() -> None:
    """A disallowed MERIDIAN_* key must be caught even when mixed with
    unrelated non-MERIDIAN_ keys that are always allowed."""
    overrides = {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "MERIDIAN_DEPTH": "2",
        "MERIDIAN_BAD_KEY": "oops",
    }
    with pytest.raises(RuntimeError, match="MERIDIAN_BAD_KEY"):
        validate_child_env_keys(overrides)


def test_validate_multiple_bad_keys_raises_on_first_encountered() -> None:
    """Having more than one unknown MERIDIAN_* key must still raise RuntimeError."""
    overrides = {
        "MERIDIAN_ALPHA": "a",
        "MERIDIAN_BETA": "b",
    }
    with pytest.raises(RuntimeError, match="Unexpected MERIDIAN_\\* key"):
        validate_child_env_keys(overrides)


# ---------------------------------------------------------------------------
# Edge case: empty/None chat_id is omitted from child env overrides
# ---------------------------------------------------------------------------


def test_build_empty_string_chat_id_is_omitted() -> None:
    """An empty parent_chat_id string must not produce a MERIDIAN_CHAT_ID key."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id="",
        parent_depth=1,
    )
    assert "MERIDIAN_CHAT_ID" not in result


def test_build_none_chat_id_is_omitted() -> None:
    """A None parent_chat_id must not produce a MERIDIAN_CHAT_ID key."""
    result = build_child_env_overrides(
        parent_spawn_id=None,
        project_root=None,
        runtime_root=None,
        parent_chat_id=None,
        parent_depth=1,
    )
    assert "MERIDIAN_CHAT_ID" not in result


# ---------------------------------------------------------------------------
# Edge case: MERIDIAN_DEPTH is always present and is a numeric string
# ---------------------------------------------------------------------------


def test_build_depth_is_always_numeric_string() -> None:
    """MERIDIAN_DEPTH must always be a string representation of a non-negative integer."""
    for depth in (0, 1, 10, 100):
        result = build_child_env_overrides(
            parent_spawn_id=None,
            project_root=None,
            runtime_root=None,
            parent_chat_id=None,
            parent_depth=depth,
        )
        assert result["MERIDIAN_DEPTH"].isdigit(), (
            f"Expected numeric string, got {result['MERIDIAN_DEPTH']!r} for depth={depth}"
        )
