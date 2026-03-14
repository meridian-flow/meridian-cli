from pathlib import Path

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.source_adapter import PathSourceAdapter, default_source_adapters


def test_default_source_adapters_expose_git_and_path() -> None:
    adapters = default_source_adapters()

    assert set(adapters) == {"git", "path"}


def test_path_source_adapter_resolves_repo_relative_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    tree = repo_root / "tools" / "agents"
    tree.mkdir(parents=True)

    resolved = PathSourceAdapter().resolve(
        ManagedSourceConfig(name="local", kind="path", path="./tools/agents"),
        cache_dir=repo_root / ".meridian" / "cache" / "agents",
        repo_root=repo_root,
    )

    assert resolved.kind == "path"
    assert resolved.locator == "./tools/agents"
    assert resolved.tree_path == tree.resolve()
    assert resolved.resolved_identity == {"path": "./tools/agents"}
