"""CLI integration checks for Slice 3 dry-run prompt composition."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.helpers.fixtures import write_agent, write_config, write_skill

def test_run_create_dry_run_outputs_composed_prompt_and_command(
    package_root: Path, tmp_path: Path
) -> None:
    repo_root = tmp_path / "slice3-test-repo"
    (repo_root / ".agents" / "agents").mkdir(parents=True, exist_ok=True)

    write_skill(repo_root, "run-agent", "Base run-agent skill.")
    write_skill(repo_root, "agent", "Base agent skill.")
    write_skill(repo_root, "reviewing", "Reviewing skill body.")
    guidance_file = (
        repo_root
        / ".agents"
        / "skills"
        / "run-agent"
        / "references"
        / "default-model-guidance.md"
    )
    guidance_file.parent.mkdir(parents=True, exist_ok=True)
    guidance_file.write_text("Prefer deterministic tests.", encoding="utf-8")

    agent_file = repo_root / ".agents" / "agents" / "reviewer.md"
    agent_file.write_text(
        (
            "---\n"
            "name: reviewer\n"
            "model: gpt-5.3-codex\n"
            "skills: [reviewing]\n"
            "---\n\n"
            "Agent profile body.\n"
        ),
        encoding="utf-8",
    )

    reference_file = repo_root / "context.md"
    reference_file.write_text("Context value: {{VALUE}}", encoding="utf-8")

    env = os.environ.copy()
    env["MERIDIAN_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(package_root / "src")
    env["MERIDIAN_SPACE_ID"] = "s1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian",
            "--json",
            "spawn",
            "--dry-run",
            "--agent",
            "reviewer",
            "-f",
            str(reference_file),
            "--prompt-var",
            "VALUE=ok",
            "-p",
            "Implement the task.",
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["command"] == "spawn.create"
    assert payload["status"] == "dry-run"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["harness_id"] == "codex"
    assert payload["cli_command"][0] == "codex"
    assert payload["cli_command"][-1] == "-"
    # Model guidance only injected when run-agent skill is loaded; reviewer
    # profile uses skills: [reviewing], so guidance is absent.
    assert "Prefer deterministic tests." not in payload["composed_prompt"]
    assert "# Reference Files" in payload["composed_prompt"]
    assert str(reference_file) in payload["composed_prompt"]
    assert "Context value: ok" not in payload["composed_prompt"]
    assert "Implement the task." in payload["composed_prompt"]


def test_start_dry_run_agent_flag_overrides_default_primary_agent(
    package_root: Path, tmp_path: Path
) -> None:
    repo_root = tmp_path / "start-agent-override"
    write_config(
        repo_root,
        "[defaults]\ndefault_primary_agent = 'lead-primary'\n",
    )
    write_agent(repo_root, name="lead-primary", model="claude-opus-4-6")
    write_agent(repo_root, name="review-primary", model="claude-sonnet-4-6")

    env = os.environ.copy()
    env["MERIDIAN_REPO_ROOT"] = str(repo_root)
    env["PYTHONPATH"] = str(package_root / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian",
            "--json",
            "--dry-run",
            "--agent",
            "review-primary",
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    command = payload["command"]
    assert payload["message"] == "Space launch dry-run."
    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "_meridian-dry-run-review-primary"
    assert "--model" in command
    assert command[command.index("--model") + 1] == "claude-sonnet-4-6"
    assert "--append-system-prompt" in command
    appended_prompt = command[command.index("--append-system-prompt") + 1]
    assert "# Meridian Space Session" in appended_prompt
