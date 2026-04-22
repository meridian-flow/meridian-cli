"""Integration tests for /api/models and /api/agents endpoints (APP-CAT-01, APP-CAT-02)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.app.server import create_app
from meridian.lib.core.types import SpawnId
from meridian.lib.state.paths import resolve_runtime_paths


class FakeManager:
    def __init__(self, *, project_root: Path) -> None:
        self.project_root = project_root
        self.state_root = resolve_runtime_paths(project_root).root_dir

    async def shutdown(self) -> None:
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    project_root = tmp_path
    manager = FakeManager(project_root=project_root)
    app = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)
    with TestClient(app) as client:
        yield client, project_root


# ---------------------------------------------------------------------------
# APP-CAT-01: GET /api/models
# ---------------------------------------------------------------------------


def test_models_returns_valid_structure(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-01: /api/models returns a JSON object with a 'models' list."""
    client, _project_root = app_client

    response = client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert isinstance(payload["models"], list)


def test_models_items_have_required_fields(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-01: Each model entry has at least model_id and harness fields."""
    client, _project_root = app_client

    response = client.get("/api/models")

    assert response.status_code == 200
    for model in response.json()["models"]:
        assert "model_id" in model, f"Missing model_id in {model}"
        assert "harness" in model, f"Missing harness in {model}"


def test_models_field_names_stable_across_calls(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-01: Repeated calls return the same top-level JSON field names."""
    client, _project_root = app_client

    first = client.get("/api/models").json()
    second = client.get("/api/models").json()

    assert set(first.keys()) == set(second.keys())
    if first["models"] and second["models"]:
        assert set(first["models"][0].keys()) == set(second["models"][0].keys())


# ---------------------------------------------------------------------------
# APP-CAT-02: GET /api/agents
# ---------------------------------------------------------------------------


def test_agents_empty_when_no_agents_dir(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-02: /api/agents returns empty list when .agents/agents/ doesn't exist."""
    client, project_root = app_client
    # Ensure agents directory does not exist.
    agents_dir = project_root / ".agents" / "agents"
    assert not agents_dir.exists()

    response = client.get("/api/agents")

    assert response.status_code == 200
    payload = response.json()
    assert "agents" in payload
    assert payload["agents"] == []


def test_agents_returns_discovered_profiles(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-02: /api/agents returns summaries for agents found in .agents/agents/."""
    client, project_root = app_client
    agents_dir = project_root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "coder.md").write_text(
        "---\nname: coder\ndescription: Writes code\nmodel: claude-opus-4-5\n---\n\nAgent body.\n",
        encoding="utf-8",
    )

    response = client.get("/api/agents")

    assert response.status_code == 200
    payload = response.json()
    assert "agents" in payload
    assert len(payload["agents"]) == 1
    agent = payload["agents"][0]
    assert agent["name"] == "coder"
    assert agent["description"] == "Writes code"
    assert agent["model"] == "claude-opus-4-5"


def test_agents_summary_has_stable_fields(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-02: Agent summaries always include the expected top-level fields."""
    client, project_root = app_client
    agents_dir = project_root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code\n---\n\nBody.\n",
        encoding="utf-8",
    )

    response = client.get("/api/agents")

    assert response.status_code == 200
    agents = response.json()["agents"]
    assert len(agents) == 1
    expected_keys = {"name", "description", "model", "harness", "skills", "path"}
    assert expected_keys.issubset(set(agents[0].keys())), (
        f"Missing expected fields. Got: {set(agents[0].keys())}"
    )


def test_agents_multiple_profiles(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-CAT-02: Multiple agent profiles are all returned."""
    client, project_root = app_client
    agents_dir = project_root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "alpha.md").write_text(
        "---\nname: alpha\ndescription: Alpha agent\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (agents_dir / "beta.md").write_text(
        "---\nname: beta\ndescription: Beta agent\n---\n\nBody.\n",
        encoding="utf-8",
    )

    response = client.get("/api/agents")

    assert response.status_code == 200
    agents = response.json()["agents"]
    names = {a["name"] for a in agents}
    assert "alpha" in names
    assert "beta" in names
