"""Unit tests for immutable resolved runtime context construction."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from meridian.lib.core.resolved_context import ContextBackend, ResolvedContext

_MERIDIAN_ENV_KEYS = (
    "MERIDIAN_SPAWN_ID",
    "MERIDIAN_DEPTH",
    "MERIDIAN_REPO_ROOT",
    "MERIDIAN_STATE_ROOT",
    "MERIDIAN_CHAT_ID",
    "MERIDIAN_WORK_ID",
    "MERIDIAN_WORK_DIR",
    "MERIDIAN_FS_DIR",
)


class FakeBackend(ContextBackend):
    def __init__(
        self,
        *,
        session_active_work_id: str | None = None,
        work_dir_suffix: str = "resolved",
    ) -> None:
        self.session_active_work_id = session_active_work_id
        self.work_dir_suffix = work_dir_suffix
        self.session_lookup_calls: list[tuple[Path, str]] = []
        self.work_dir_calls: list[tuple[Path, str]] = []

    def get_session_active_work_id(self, state_root: Path, chat_id: str) -> str | None:
        self.session_lookup_calls.append((state_root, chat_id))
        return self.session_active_work_id

    def resolve_work_scratch_dir(self, state_root: Path, work_id: str) -> Path:
        self.work_dir_calls.append((state_root, work_id))
        return state_root / "work" / self.work_dir_suffix / work_id


def _clear_meridian_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _MERIDIAN_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_environment_without_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_meridian_env(monkeypatch)
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.spawn_id is None
    assert resolved.depth == 0
    assert resolved.repo_root is None
    assert resolved.state_root is None
    assert resolved.chat_id == ""
    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert resolved.fs_dir is None
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == []


def test_from_environment_prefers_explicit_work_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_meridian_env(monkeypatch)
    repo_root = Path("/repo")
    state_root = Path("/runtime/state")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_REPO_ROOT", repo_root.as_posix())
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-from-env")

    resolved = ResolvedContext.from_environment(
        explicit_work_id="  explicit-work  ",
        backend=backend,
    )

    assert resolved.work_id == "explicit-work"
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == [(Path("/repo/.meridian"), "explicit-work")]


def test_from_environment_uses_meridian_work_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_meridian_env(monkeypatch)
    repo_root = Path("/repo")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_REPO_ROOT", repo_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-from-env")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id == "work-from-env"
    assert resolved.work_dir == Path("/repo/.meridian/work/resolved/work-from-env")
    assert resolved.fs_dir == Path("/repo/.meridian/fs")
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == [(Path("/repo/.meridian"), "work-from-env")]


def test_from_environment_falls_back_to_session_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_meridian_env(monkeypatch)
    state_root = Path("/runtime/state")
    backend = FakeBackend(session_active_work_id="active-work", work_dir_suffix="fallback")

    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id == "active-work"
    assert resolved.work_dir == Path("/runtime/state/work/fallback/active-work")
    assert backend.session_lookup_calls == [(state_root, "c42")]
    assert backend.work_dir_calls == [(state_root, "active-work")]


def test_child_env_overrides_output_format() -> None:
    resolved = ResolvedContext(
        depth=2,
        repo_root=Path("/repo"),
        state_root=Path("/runtime/state"),
        chat_id="c9",
        work_id="work-123",
        work_dir=Path("/repo/.meridian/work/work-123"),
        fs_dir=Path("/repo/.meridian/fs"),
    )

    overrides = resolved.child_env_overrides()

    assert overrides == {
        "MERIDIAN_DEPTH": "3",
        "MERIDIAN_REPO_ROOT": "/repo",
        "MERIDIAN_STATE_ROOT": "/runtime/state",
        "MERIDIAN_CHAT_ID": "c9",
        "MERIDIAN_WORK_ID": "work-123",
        "MERIDIAN_WORK_DIR": "/repo/.meridian/work/work-123",
        "MERIDIAN_FS_DIR": "/repo/.meridian/fs",
    }
    assert resolved.child_env_overrides(increment_depth=False)["MERIDIAN_DEPTH"] == "2"


def test_resolved_context_is_frozen() -> None:
    resolved = ResolvedContext(depth=1)

    with pytest.raises(FrozenInstanceError):
        resolved.depth = 2  # type: ignore[misc]


def test_work_dir_prefers_repo_state_root_over_runtime_state_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_meridian_env(monkeypatch)
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_REPO_ROOT", "/repo")
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", "/runtime/state")
    monkeypatch.setenv("MERIDIAN_WORK_ID", "selected-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_dir == Path("/repo/.meridian/work/resolved/selected-work")
    assert backend.work_dir_calls == [(Path("/repo/.meridian"), "selected-work")]


# ---------------------------------------------------------------------------
# Edge case 1: Invalid depth values
# ---------------------------------------------------------------------------


def test_from_environment_negative_depth_clamps_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative MERIDIAN_DEPTH must clamp to 0, not go negative."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "-5")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.depth == 0


def test_from_environment_non_integer_depth_defaults_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-parseable MERIDIAN_DEPTH string must silently default to 0."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "not-a-number")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.depth == 0


def test_from_environment_float_string_depth_defaults_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A float string like '3.5' is not a valid int and must default to 0."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "3.5")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.depth == 0


# ---------------------------------------------------------------------------
# Edge case 2: Empty env vars treated same as missing
# ---------------------------------------------------------------------------


def test_from_environment_empty_repo_root_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty MERIDIAN_REPO_ROOT must be treated as if the variable were absent."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", "")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.repo_root is None
    assert resolved.fs_dir is None


def test_from_environment_whitespace_only_repo_root_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitespace-only MERIDIAN_REPO_ROOT must be stripped and treated as absent."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", "   ")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.repo_root is None


def test_from_environment_empty_work_id_env_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty MERIDIAN_WORK_ID must not set work_id or trigger backend calls."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_WORK_ID", "")
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id is None
    assert resolved.work_dir is None
    # No session lookup because chat_id is also absent
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == []


def test_from_environment_empty_state_root_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty MERIDIAN_STATE_ROOT must be treated as absent (no session lookup)."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", "")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")
    backend = FakeBackend(session_active_work_id="active-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    # state_root is absent so the session lookup branch is never entered
    assert resolved.state_root is None
    assert resolved.work_id is None
    assert backend.session_lookup_calls == []


# ---------------------------------------------------------------------------
# Edge case 3: Explicit override precedence — empty/whitespace explicit_work_id
# ---------------------------------------------------------------------------


def test_from_environment_empty_explicit_work_id_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty explicit_work_id must not override the env-var work ID."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_WORK_ID", "env-work")
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(explicit_work_id="", backend=backend)

    assert resolved.work_id == "env-work"


def test_from_environment_whitespace_explicit_work_id_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitespace-only explicit_work_id must be stripped and treated as absent,
    falling through to MERIDIAN_WORK_ID."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_WORK_ID", "env-work")
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(explicit_work_id="   ", backend=backend)

    assert resolved.work_id == "env-work"


def test_from_environment_explicit_work_id_beats_session_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """explicit_work_id must be used even when a session lookup would return something."""
    _clear_meridian_env(monkeypatch)
    state_root = Path("/runtime/state")
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")
    backend = FakeBackend(session_active_work_id="session-work")

    resolved = ResolvedContext.from_environment(
        explicit_work_id="override-work", backend=backend
    )

    assert resolved.work_id == "override-work"
    # Session lookup must be skipped entirely
    assert backend.session_lookup_calls == []


# ---------------------------------------------------------------------------
# Edge case 4: Immutability — other fields besides depth
# ---------------------------------------------------------------------------


def test_resolved_context_frozen_repo_root() -> None:
    """ResolvedContext must reject mutations to repo_root."""
    resolved = ResolvedContext(repo_root=Path("/repo"))

    with pytest.raises(FrozenInstanceError):
        resolved.repo_root = Path("/other")  # type: ignore[misc]


def test_resolved_context_frozen_chat_id() -> None:
    """ResolvedContext must reject mutations to chat_id."""
    resolved = ResolvedContext(chat_id="original")

    with pytest.raises(FrozenInstanceError):
        resolved.chat_id = "changed"  # type: ignore[misc]


def test_resolved_context_frozen_work_id() -> None:
    """ResolvedContext must reject mutations to work_id."""
    resolved = ResolvedContext(work_id="w1")

    with pytest.raises(FrozenInstanceError):
        resolved.work_id = "w2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Edge case 5: Work dir derivation when only state_root is available (no repo_root)
# ---------------------------------------------------------------------------


def test_work_dir_uses_state_root_directly_when_no_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only MERIDIAN_STATE_ROOT is set (no MERIDIAN_REPO_ROOT),
    work_dir must be resolved against state_root, not a derived repo state root."""
    _clear_meridian_env(monkeypatch)
    state_root = Path("/runtime/state")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "my-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.repo_root is None
    assert resolved.state_root == state_root
    assert resolved.work_dir == Path("/runtime/state/work/resolved/my-work")
    assert backend.work_dir_calls == [(state_root, "my-work")]
    # fs_dir requires repo_root — must be None
    assert resolved.fs_dir is None


def test_work_dir_is_none_when_no_work_id_even_with_state_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """work_dir must stay None when work_id cannot be resolved,
    even when state_root is populated."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", "/runtime/state")
    # No MERIDIAN_WORK_ID and no MERIDIAN_CHAT_ID (so session lookup skipped)
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert backend.work_dir_calls == []


# ---------------------------------------------------------------------------
# Edge case: spawn_id is NOT propagated to child env overrides
# ---------------------------------------------------------------------------


def test_child_env_overrides_does_not_propagate_spawn_id() -> None:
    """MERIDIAN_SPAWN_ID must never appear in child_env_overrides output —
    each child gets its own spawn identity."""
    from meridian.lib.core.types import SpawnId

    resolved = ResolvedContext(
        spawn_id=SpawnId("parent-spawn"),
        depth=1,
        chat_id="c1",
    )

    overrides = resolved.child_env_overrides()

    assert "MERIDIAN_SPAWN_ID" not in overrides


# ---------------------------------------------------------------------------
# Edge case: whitespace-only MERIDIAN_SPAWN_ID → spawn_id is None
# ---------------------------------------------------------------------------


def test_from_environment_whitespace_only_spawn_id_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitespace-only MERIDIAN_SPAWN_ID must be stripped to '' and treated as absent,
    producing spawn_id=None rather than a SpawnId wrapping a blank string."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", "   ")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.spawn_id is None


# ---------------------------------------------------------------------------
# Edge case: large valid MERIDIAN_DEPTH is preserved exactly
# ---------------------------------------------------------------------------


def test_from_environment_large_valid_depth_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A large but valid positive integer MERIDIAN_DEPTH must be preserved exactly.
    Only negative values are clamped — large valid integers pass through unchanged."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_DEPTH", "9999")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.depth == 9999


# ---------------------------------------------------------------------------
# Edge case: state_root present + empty chat_id → session lookup skipped
# ---------------------------------------------------------------------------


def test_from_environment_session_lookup_skipped_when_chat_id_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session lookup must be skipped when chat_id resolves to '' even if
    state_root is populated.  The lookup branch guards on both state_root and
    a non-empty chat_id — an empty MERIDIAN_CHAT_ID must prevent the call."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", "/runtime/state")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "")
    backend = FakeBackend(session_active_work_id="should-not-be-returned")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert backend.session_lookup_calls == []


# ---------------------------------------------------------------------------
# Edge case: child_env_overrides with all optional fields absent
# ---------------------------------------------------------------------------


def test_child_env_overrides_minimal_context_only_emits_depth() -> None:
    """When all optional fields are None/empty, child_env_overrides must emit only
    MERIDIAN_DEPTH — no spurious keys for absent paths or IDs."""
    resolved = ResolvedContext()  # all defaults: depth=0, everything else None/""

    overrides = resolved.child_env_overrides()

    assert list(overrides.keys()) == ["MERIDIAN_DEPTH"]
    assert overrides["MERIDIAN_DEPTH"] == "1"


# ---------------------------------------------------------------------------
# Edge case: relative path in MERIDIAN_REPO_ROOT is handled without error
# ---------------------------------------------------------------------------


def test_from_environment_relative_repo_root_handled_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative path string in MERIDIAN_REPO_ROOT must not raise an exception.
    The module performs no filesystem existence check — it merely constructs
    the Path object and derives downstream paths from it."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_REPO_ROOT", "../relative/repo")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    # Relative path accepted without error — downstream callers must resolve
    assert resolved.repo_root == Path("../relative/repo")
    # fs_dir is also derived relative — still no error
    assert resolved.fs_dir == Path("../relative/repo/.meridian/fs")
