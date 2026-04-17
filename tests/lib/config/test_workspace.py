from pathlib import Path

import pytest

from meridian.lib.config.workspace import (
    get_projectable_roots,
    resolve_workspace_snapshot,
)
from meridian.lib.launch.workspace import ensure_workspace_valid_for_launch


@pytest.fixture(autouse=True)
def _clear_state_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)


def _repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def test_resolve_workspace_snapshot_is_none_when_workspace_file_absent(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    snapshot = resolve_workspace_snapshot(repo_root)

    assert snapshot.status == "none"
    assert snapshot.path is None
    assert snapshot.roots == ()
    assert snapshot.findings == ()


def test_workspace_snapshot_resolves_paths_relative_to_workspace_file(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    sibling_root = tmp_path / "sibling"
    sibling_root.mkdir()
    workspace_path = repo_root / "workspace.local.toml"
    workspace_path.write_text(
        "[[context-roots]]\n"
        'path = "../sibling"\n'
        "\n"
        "[[context-roots]]\n"
        'path = "./disabled-missing"\n'
        "enabled = false\n",
        encoding="utf-8",
    )

    snapshot = resolve_workspace_snapshot(repo_root)

    assert snapshot.status == "present"
    assert snapshot.path == workspace_path.resolve()
    assert [root.declared_path for root in snapshot.roots] == [
        "../sibling",
        "./disabled-missing",
    ]
    assert snapshot.roots[0].resolved_path == sibling_root.resolve()
    assert snapshot.roots[0].enabled is True
    assert snapshot.roots[0].exists is True
    assert snapshot.roots[1].resolved_path == (repo_root / "disabled-missing").resolve()
    assert snapshot.roots[1].enabled is False
    assert snapshot.roots[1].exists is False
    assert snapshot.missing_roots_count == 0


def test_get_projectable_roots_returns_only_enabled_existing_entries(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    existing = repo_root / "existing"
    existing.mkdir()
    (repo_root / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./existing"\n'
        "\n"
        "[[context-roots]]\n"
        'path = "./missing"\n'
        "\n"
        "[[context-roots]]\n"
        'path = "./disabled"\n'
        "enabled = false\n",
        encoding="utf-8",
    )

    snapshot = resolve_workspace_snapshot(repo_root)

    assert get_projectable_roots(snapshot) == (existing.resolve(),)


def test_workspace_snapshot_surfaces_unknown_keys_and_missing_enabled_roots(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    workspace_path = repo_root / "workspace.local.toml"
    workspace_path.write_text(
        'future = "value"\n'
        "[[context-roots]]\n"
        'path = "./missing-root"\n'
        'comment = "kept"\n',
        encoding="utf-8",
    )

    snapshot = resolve_workspace_snapshot(repo_root)

    assert snapshot.status == "present"
    finding_codes = {finding.code for finding in snapshot.findings}
    assert finding_codes == {"workspace_unknown_key", "workspace_missing_root"}
    unknown = next(f for f in snapshot.findings if f.code == "workspace_unknown_key")
    assert unknown.payload == {"keys": ["future", "context-roots[1].comment"]}
    missing = next(f for f in snapshot.findings if f.code == "workspace_missing_root")
    assert missing.payload == {"roots": [(repo_root / "missing-root").resolve().as_posix()]}


def test_workspace_snapshot_uses_state_root_parent_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    override_root = tmp_path / "state-root" / ".meridian"
    override_root.parent.mkdir(parents=True)
    workspace_path = override_root.parent / "workspace.local.toml"
    (override_root.parent / "shared-root").mkdir()
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", override_root.as_posix())
    workspace_path.write_text(
        "[[context-roots]]\n"
        'path = "./shared-root"\n',
        encoding="utf-8",
    )

    snapshot = resolve_workspace_snapshot(repo_root)

    assert snapshot.status == "present"
    assert snapshot.path == workspace_path.resolve()
    assert snapshot.roots[0].resolved_path == (override_root.parent / "shared-root").resolve()


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        (
            "[[context-roots]\npath = './bad'\n",
            "Invalid workspace TOML",
        ),
        (
            "[[context-roots]]\nenabled = true\n",
            "'context-roots[1].path' is required",
        ),
        (
            "[[context-roots]]\npath = '   '\n",
            "'context-roots[1].path' must be non-empty",
        ),
        (
            "[[context-roots]]\npath = 123\n",
            "'context-roots[1].path' must be a string",
        ),
        (
            "[[context-roots]]\npath = './root'\nenabled = 'yes'\n",
            "'context-roots[1].enabled' must be a boolean",
        ),
    ],
)
def test_workspace_snapshot_marks_invalid_schema_cases(
    tmp_path: Path,
    content: str,
    expected_message: str,
) -> None:
    repo_root = _repo(tmp_path)
    workspace_path = repo_root / "workspace.local.toml"
    workspace_path.write_text(content, encoding="utf-8")

    snapshot = resolve_workspace_snapshot(repo_root)

    assert snapshot.status == "invalid"
    assert snapshot.path == workspace_path.resolve()
    assert snapshot.findings
    assert snapshot.findings[0].code == "workspace_invalid"
    assert expected_message in snapshot.findings[0].message


def test_workspace_launch_validation_raises_for_invalid_workspace(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    (repo_root / "workspace.local.toml").write_text("[[context-roots]]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid workspace file"):
        ensure_workspace_valid_for_launch(repo_root)


def test_workspace_launch_validation_allows_absent_or_valid_workspace(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    ensure_workspace_valid_for_launch(repo_root)

    (repo_root / "existing").mkdir()
    (repo_root / "workspace.local.toml").write_text(
        "[[context-roots]]\n"
        'path = "./existing"\n',
        encoding="utf-8",
    )
    ensure_workspace_valid_for_launch(repo_root)
