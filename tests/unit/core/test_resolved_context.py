"""Unit tests for immutable resolved runtime context construction."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from meridian.lib.config.context_config import ContextConfig
from meridian.lib.core.resolved_context import ContextBackend, ResolvedContext

_MERIDIAN_ENV_KEYS = (
    "MERIDIAN_SPAWN_ID",
    "MERIDIAN_PARENT_SPAWN_ID",
    "MERIDIAN_DEPTH",
    "MERIDIAN_PROJECT_DIR",
    "MERIDIAN_RUNTIME_DIR",
    "MERIDIAN_CHAT_ID",
    "MERIDIAN_WORK_ID",
    "MERIDIAN_WORK_DIR",
    "MERIDIAN_KB_DIR",
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

    def get_session_active_work_id(self, runtime_root: Path, chat_id: str) -> str | None:
        self.session_lookup_calls.append((runtime_root, chat_id))
        return self.session_active_work_id

    def resolve_work_scratch_dir(self, runtime_root: Path, work_id: str) -> Path:
        self.work_dir_calls.append((runtime_root, work_id))
        return runtime_root / "work" / self.work_dir_suffix / work_id


def _clear_meridian_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _MERIDIAN_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_environment_without_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical resolver output should remain empty/default when env is unset."""
    _clear_meridian_env(monkeypatch)
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.spawn_id is None
    assert resolved.parent_spawn_id is None
    assert resolved.depth == 0
    assert resolved.project_root is None
    assert resolved.runtime_root is None
    assert resolved.chat_id == ""
    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert resolved.kb_dir is None
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == []


def test_from_environment_prefers_explicit_work_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit work override must win over MERIDIAN_WORK_ID in resolver precedence."""
    _clear_meridian_env(monkeypatch)
    project_root = Path("/repo")
    runtime_root = Path("/runtime/state")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", project_root.as_posix())
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", runtime_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-from-env")

    resolved = ResolvedContext.from_environment(
        explicit_work_id="  explicit-work  ",
        backend=backend,
    )

    assert resolved.work_id == "explicit-work"
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == []


def test_from_environment_uses_meridian_work_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolver must honor MERIDIAN_WORK_ID when no explicit override is provided."""
    _clear_meridian_env(monkeypatch)
    project_root = Path("/repo")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", project_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "work-from-env")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id == "work-from-env"
    assert resolved.work_dir == Path("/repo/.meridian/work/work-from-env")
    assert resolved.kb_dir == Path("/repo/.meridian/kb")
    assert backend.session_lookup_calls == []
    assert backend.work_dir_calls == []


def test_from_environment_falls_back_to_session_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver must consult session active-work lookup only after env sources miss."""
    _clear_meridian_env(monkeypatch)
    runtime_root = Path("/runtime/state")
    backend = FakeBackend(session_active_work_id="active-work", work_dir_suffix="fallback")

    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", runtime_root.as_posix())
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id == "active-work"
    assert resolved.work_dir == Path("/runtime/state/work/fallback/active-work")
    assert backend.session_lookup_calls == [(runtime_root, "c42")]
    assert backend.work_dir_calls == [(runtime_root, "active-work")]


def test_child_env_overrides_output_format() -> None:
    """Child-env projection must serialize the canonical ResolvedContext fields."""
    resolved = ResolvedContext(
        depth=2,
        project_root=Path("/repo"),
        runtime_root=Path("/runtime/state"),
        chat_id="c9",
        work_id="work-123",
        work_dir=Path("/repo/.meridian/work/work-123"),
        kb_dir=Path("/repo/.meridian/kb"),
    )

    overrides = resolved.child_env_overrides()

    assert overrides == {
        "MERIDIAN_DEPTH": "3",
        "MERIDIAN_PROJECT_DIR": "/repo",
        "MERIDIAN_RUNTIME_DIR": "/runtime/state",
        "MERIDIAN_CHAT_ID": "c9",
        "MERIDIAN_WORK_ID": "work-123",
        "MERIDIAN_WORK_DIR": "/repo/.meridian/work/work-123",
        "MERIDIAN_KB_DIR": "/repo/.meridian/kb",
        "MERIDIAN_FS_DIR": "/repo/.meridian/kb",
    }
    assert resolved.child_env_overrides(increment_depth=False)["MERIDIAN_DEPTH"] == "2"


def test_from_environment_reads_parent_spawn_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PARENT_SPAWN_ID", "p-parent")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.parent_spawn_id == "p-parent"


def test_child_env_overrides_emits_child_spawn_id() -> None:
    from meridian.lib.core.types import SpawnId

    resolved = ResolvedContext(spawn_id=SpawnId("p-parent"), depth=2)

    overrides = resolved.child_env_overrides(child_spawn_id="p-child")

    assert overrides["MERIDIAN_SPAWN_ID"] == "p-child"


def test_child_env_overrides_emits_parent_spawn_id() -> None:
    from meridian.lib.core.types import SpawnId

    resolved = ResolvedContext(spawn_id=SpawnId("p-parent"), depth=2)

    overrides = resolved.child_env_overrides()

    assert overrides["MERIDIAN_PARENT_SPAWN_ID"] == "p-parent"


def test_child_env_overrides_omits_parent_spawn_id_at_depth_0() -> None:
    resolved = ResolvedContext(depth=0)

    overrides = resolved.child_env_overrides()

    assert "MERIDIAN_PARENT_SPAWN_ID" not in overrides


def test_resolved_context_is_frozen() -> None:
    """ResolvedContext contract requires immutability after resolution."""
    resolved = ResolvedContext(depth=1)

    with pytest.raises(FrozenInstanceError):
        resolved.depth = 2  # type: ignore[misc]


def test_work_dir_prefers_repo_state_root_over_runtime_state_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver must derive work_dir from repo-scoped state when project_root exists."""
    _clear_meridian_env(monkeypatch)
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "/repo")
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", "/runtime/state")
    monkeypatch.setenv("MERIDIAN_WORK_ID", "selected-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_dir == Path("/repo/.meridian/work/selected-work")
    assert backend.work_dir_calls == []


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


def test_from_environment_empty_project_root_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty MERIDIAN_PROJECT_DIR must be treated as if the variable were absent."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.project_root is None
    assert resolved.kb_dir is None


def test_from_environment_whitespace_only_project_root_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whitespace-only MERIDIAN_PROJECT_DIR must be stripped and treated as absent."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "   ")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    assert resolved.project_root is None


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
    """An empty MERIDIAN_RUNTIME_DIR must be treated as absent (no session lookup)."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", "")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")
    backend = FakeBackend(session_active_work_id="active-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    # runtime_root is absent so the session lookup branch is never entered
    assert resolved.runtime_root is None
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
    runtime_root = Path("/runtime/state")
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", runtime_root.as_posix())
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")
    backend = FakeBackend(session_active_work_id="session-work")

    resolved = ResolvedContext.from_environment(
        explicit_work_id="override-work", backend=backend
    )

    assert resolved.work_id == "override-work"
    # Session lookup must be skipped entirely
    assert backend.session_lookup_calls == []


def test_from_environment_work_id_resolution_precedence_d8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D8 precedence: explicit_work_id > MERIDIAN_WORK_ID > session lookup."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "/repo")
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", "/runtime/state")
    monkeypatch.setenv("MERIDIAN_CHAT_ID", "c42")
    monkeypatch.setenv("MERIDIAN_WORK_ID", "env-work")

    explicit_backend = FakeBackend(session_active_work_id="session-work")
    resolved_explicit = ResolvedContext.from_environment(
        explicit_work_id="explicit-work",
        backend=explicit_backend,
    )
    assert resolved_explicit.work_id == "explicit-work"
    assert explicit_backend.session_lookup_calls == []
    assert explicit_backend.work_dir_calls == []

    env_backend = FakeBackend(session_active_work_id="session-work")
    resolved_env = ResolvedContext.from_environment(backend=env_backend)
    assert resolved_env.work_id == "env-work"
    assert env_backend.session_lookup_calls == []
    assert env_backend.work_dir_calls == []

    monkeypatch.delenv("MERIDIAN_WORK_ID", raising=False)
    session_backend = FakeBackend(session_active_work_id="session-work")
    resolved_session = ResolvedContext.from_environment(backend=session_backend)
    assert resolved_session.work_id == "session-work"
    assert session_backend.session_lookup_calls == [(Path("/runtime/state"), "c42")]
    assert session_backend.work_dir_calls == []


# ---------------------------------------------------------------------------
# Edge case 4: Immutability — other fields besides depth
# ---------------------------------------------------------------------------


def test_resolved_context_frozen_project_root() -> None:
    """ResolvedContext must reject mutations to project_root."""
    resolved = ResolvedContext(project_root=Path("/repo"))

    with pytest.raises(FrozenInstanceError):
        resolved.project_root = Path("/other")  # type: ignore[misc]


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
# Edge case 5: Work dir derivation when only runtime_root is available (no project_root)
# ---------------------------------------------------------------------------


def test_work_dir_uses_state_root_directly_when_no_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only MERIDIAN_RUNTIME_DIR is set (no MERIDIAN_PROJECT_DIR),
    work_dir must be resolved against runtime_root, not a derived repo state root."""
    _clear_meridian_env(monkeypatch)
    runtime_root = Path("/runtime/state")
    backend = FakeBackend()

    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", runtime_root.as_posix())
    monkeypatch.setenv("MERIDIAN_WORK_ID", "my-work")

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.project_root is None
    assert resolved.runtime_root == runtime_root
    assert resolved.work_dir == Path("/runtime/state/work/resolved/my-work")
    assert backend.work_dir_calls == [(runtime_root, "my-work")]
    # kb_dir requires project_root — must be None
    assert resolved.kb_dir is None


def test_work_dir_is_none_when_no_work_id_even_with_state_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """work_dir must stay None when work_id cannot be resolved,
    even when runtime_root is populated."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", "/runtime/state")
    # No MERIDIAN_WORK_ID and no MERIDIAN_CHAT_ID (so session lookup skipped)
    backend = FakeBackend()

    resolved = ResolvedContext.from_environment(backend=backend)

    assert resolved.work_id is None
    assert resolved.work_dir is None
    assert backend.work_dir_calls == []


# ---------------------------------------------------------------------------
# Edge case: spawn_id is NOT propagated to child env overrides
# ---------------------------------------------------------------------------


def test_child_env_overrides_propagates_spawn_id() -> None:
    """MERIDIAN_SPAWN_ID must appear in child_env_overrides output so
    children know their parent spawn for parent_id tracking."""
    from meridian.lib.core.types import SpawnId

    resolved = ResolvedContext(
        spawn_id=SpawnId("parent-spawn"),
        depth=1,
        chat_id="c1",
    )

    overrides = resolved.child_env_overrides()

    assert overrides.get("MERIDIAN_SPAWN_ID") == "parent-spawn"


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
# Edge case: runtime_root present + empty chat_id → session lookup skipped
# ---------------------------------------------------------------------------


def test_from_environment_session_lookup_skipped_when_chat_id_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session lookup must be skipped when chat_id resolves to '' even if
    runtime_root is populated.  The lookup branch guards on both runtime_root and
    a non-empty chat_id — an empty MERIDIAN_CHAT_ID must prevent the call."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", "/runtime/state")
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
# Edge case: relative path in MERIDIAN_PROJECT_DIR is handled without error
# ---------------------------------------------------------------------------


def test_from_environment_relative_project_root_handled_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative path string in MERIDIAN_PROJECT_DIR must not raise an exception.
    The module performs no filesystem existence check — it merely constructs
    the Path object and derives downstream paths from it."""
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "../relative/repo")

    resolved = ResolvedContext.from_environment(backend=FakeBackend())

    # Relative path accepted without error — downstream callers must resolve
    assert resolved.project_root == Path("../relative/repo")
    # kb_dir is also derived relative — still no error
    assert resolved.kb_dir == Path("../relative/repo/.meridian/kb")


def test_from_environment_uses_context_config_for_repo_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_meridian_env(monkeypatch)
    monkeypatch.setenv("MERIDIAN_PROJECT_DIR", "/repo")
    monkeypatch.setenv("MERIDIAN_WORK_ID", "my-work")
    config = ContextConfig.model_validate(
        {
            "work": {"path": "contexts/work", "archive": "contexts/archive/work"},
            "kb": {"path": "contexts/kb"},
        }
    )

    resolved = ResolvedContext.from_environment(context_config=config, backend=FakeBackend())

    assert resolved.work_dir == Path("/repo/contexts/work/my-work")
    assert resolved.kb_dir == Path("/repo/contexts/kb")


def test_child_env_overrides_exports_arbitrary_context_dirs() -> None:
    resolved = ResolvedContext(
        depth=0,
        context_dirs=(
            ("docs", Path("/contexts/docs")),
            ("team-notes", Path("/contexts/team-notes")),
        ),
    )

    overrides = resolved.child_env_overrides()

    assert overrides["MERIDIAN_CONTEXT_DOCS_DIR"] == "/contexts/docs"
    assert overrides["MERIDIAN_CONTEXT_TEAM_NOTES_DIR"] == "/contexts/team-notes"
