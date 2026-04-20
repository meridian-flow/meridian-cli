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


def test_validate_rejects_unexpected_meridian_key() -> None:
    """An unknown MERIDIAN_* key must raise RuntimeError."""
    overrides = {"MERIDIAN_UNKNOWN_CUSTOM": "value"}
    with pytest.raises(RuntimeError, match="Unexpected MERIDIAN_\\* key in child env"):
        validate_child_env_keys(overrides)


def test_validate_rejects_unexpected_key_mixed_with_allowed() -> None:
    """RuntimeError must be raised even when some allowed keys are present."""
    overrides = {
        "MERIDIAN_DEPTH": "1",
        "MERIDIAN_REPO_ROOT": "/repo",
        "MERIDIAN_NOVEL_KEY": "bad",
    }
    with pytest.raises(RuntimeError, match="MERIDIAN_NOVEL_KEY"):
        validate_child_env_keys(overrides)


# ---------------------------------------------------------------------------
# build_child_env_overrides
# ---------------------------------------------------------------------------


def test_build_produces_depth_always() -> None:
    """MERIDIAN_DEPTH must always appear in the result."""
    result = build_child_env_overrides(
        repo_root=None,
        state_root=None,
        parent_chat_id=None,
        parent_depth=0,
    )
    assert "MERIDIAN_DEPTH" in result


def test_build_increments_depth_by_default() -> None:
    """Default increment_depth=True must produce parent_depth + 1."""
    result = build_child_env_overrides(
        repo_root=None,
        state_root=None,
        parent_chat_id=None,
        parent_depth=3,
    )
    assert result["MERIDIAN_DEPTH"] == "4"


def test_build_no_increment_keeps_depth() -> None:
    """increment_depth=False must keep the depth value unchanged."""
    result = build_child_env_overrides(
        repo_root=None,
        state_root=None,
        parent_chat_id=None,
        parent_depth=2,
        increment_depth=False,
    )
    assert result["MERIDIAN_DEPTH"] == "2"


def test_build_omits_none_fields() -> None:
    """Fields that are None/empty must not appear in the result dict."""
    result = build_child_env_overrides(
        repo_root=None,
        state_root=None,
        parent_chat_id=None,
        parent_depth=0,
        work_id=None,
        work_dir=None,
        fs_dir=None,
    )
    assert "MERIDIAN_REPO_ROOT" not in result
    assert "MERIDIAN_STATE_ROOT" not in result
    assert "MERIDIAN_CHAT_ID" not in result
    assert "MERIDIAN_WORK_ID" not in result
    assert "MERIDIAN_WORK_DIR" not in result
    assert "MERIDIAN_FS_DIR" not in result


def test_build_full_overrides() -> None:
    """All populated fields must appear with correct string values."""
    repo = Path("/repo")
    state = Path("/runtime/state")
    work_dir = Path("/repo/.meridian/work/w1")
    fs_dir = Path("/repo/.meridian/fs")

    result = build_child_env_overrides(
        repo_root=repo,
        state_root=state,
        parent_chat_id="c99",
        parent_depth=1,
        work_id="w1",
        work_dir=work_dir,
        fs_dir=fs_dir,
    )

    assert result == {
        "MERIDIAN_DEPTH": "2",
        "MERIDIAN_REPO_ROOT": "/repo",
        "MERIDIAN_STATE_ROOT": "/runtime/state",
        "MERIDIAN_CHAT_ID": "c99",
        "MERIDIAN_WORK_ID": "w1",
        "MERIDIAN_WORK_DIR": "/repo/.meridian/work/w1",
        "MERIDIAN_FS_DIR": "/repo/.meridian/fs",
    }


def test_build_result_keys_are_subset_of_allowed() -> None:
    """All keys produced by build_child_env_overrides must be in ALLOWED_CHILD_ENV_KEYS."""
    result = build_child_env_overrides(
        repo_root=Path("/r"),
        state_root=Path("/s"),
        parent_chat_id="c1",
        parent_depth=0,
        work_id="wid",
        work_dir=Path("/s/work/wid"),
        fs_dir=Path("/r/.meridian/fs"),
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
    fs_dir = Path("/my/repo/.meridian/fs")

    ctx = ResolvedContext(
        depth=2,
        repo_root=repo,
        state_root=state,
        chat_id="c7",
        work_id="w42",
        work_dir=work_dir,
        fs_dir=fs_dir,
    )
    expected = ctx.child_env_overrides()

    result = build_child_env_overrides(
        repo_root=repo,
        state_root=state,
        parent_chat_id="c7",
        parent_depth=2,
        work_id="w42",
        work_dir=work_dir,
        fs_dir=fs_dir,
    )

    assert result == expected


def test_integration_increment_depth_false_matches_resolved_context() -> None:
    """increment_depth=False must match child_env_overrides(increment_depth=False)."""
    ctx = ResolvedContext(
        depth=5,
        repo_root=Path("/r"),
        state_root=Path("/s"),
        chat_id="c5",
    )
    expected = ctx.child_env_overrides(increment_depth=False)

    result = build_child_env_overrides(
        repo_root=Path("/r"),
        state_root=Path("/s"),
        parent_chat_id="c5",
        parent_depth=5,
        increment_depth=False,
    )

    assert result == expected
