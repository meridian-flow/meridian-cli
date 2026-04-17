import json
from pathlib import Path

import pytest

from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.workspace_projection import (
    OPENCODE_CONFIG_CONTENT_ENV,
    project_workspace_roots,
)


@pytest.mark.parametrize(
    "harness_id",
    (
        HarnessId.CLAUDE,
        HarnessId.CODEX,
        HarnessId.OPENCODE,
    ),
)
def test_workspace_projection_ignores_empty_roots(harness_id: HarnessId) -> None:
    result = project_workspace_roots(harness_id=harness_id, roots=())

    assert result.applicability == "ignored:no_roots"
    assert result.args == ()
    assert result.env_overrides == {}
    assert result.diagnostics == ()


def test_workspace_projection_projects_claude_add_dir_args_in_order() -> None:
    roots = (
        Path("/tmp/workspace/root-a"),
        Path("/tmp/workspace/root-b"),
    )

    result = project_workspace_roots(harness_id=HarnessId.CLAUDE, roots=roots)

    assert result.applicability == "active"
    assert result.args == (
        "--add-dir",
        "/tmp/workspace/root-a",
        "--add-dir",
        "/tmp/workspace/root-b",
    )
    assert result.env_overrides == {}
    assert result.diagnostics == ()


def test_workspace_projection_projects_opencode_external_directories() -> None:
    roots = (
        Path("/tmp/workspace/root-a"),
        Path("/tmp/workspace/root-b"),
    )

    result = project_workspace_roots(harness_id=HarnessId.OPENCODE, roots=roots)

    assert result.applicability == "active"
    assert result.args == ()
    assert result.diagnostics == ()
    payload = json.loads(result.env_overrides[OPENCODE_CONFIG_CONTENT_ENV])
    assert payload == {
        "permission": {
            "external_directory": [
                "/tmp/workspace/root-a",
                "/tmp/workspace/root-b",
            ]
        }
    }


def test_workspace_projection_opencode_parent_env_suppresses_workspace_projection() -> None:
    result = project_workspace_roots(
        harness_id=HarnessId.OPENCODE,
        roots=(Path("/tmp/workspace/root-a"),),
        parent_opencode_config_content='{"permission":{"external_directory":["/preexisting"]}}',
    )

    assert result.applicability == "active"
    assert result.args == ()
    assert result.env_overrides == {}
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "workspace_opencode_parent_env_suppressed"
    assert diagnostic.payload == {"env_var": OPENCODE_CONFIG_CONTENT_ENV}


def test_workspace_projection_marks_codex_as_unsupported_with_roots() -> None:
    result = project_workspace_roots(
        harness_id=HarnessId.CODEX,
        roots=(Path("/tmp/workspace/root-a"),),
    )

    assert result.applicability == "unsupported:requires_config_generation"
    assert result.args == ()
    assert result.env_overrides == {}
