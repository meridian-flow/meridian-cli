"""Slice 2 config-layer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import meridian.lib.config.agent as agent_config
from meridian.lib.config.agent import load_agent_profile
from meridian.lib.config.catalog import load_model_catalog, resolve_model
from meridian.lib.config.model_guidance import load_model_guidance, selected_guidance_paths
from meridian.lib.config.routing import route_model
from meridian.lib.config.skill import parse_skill_file
from meridian.lib.config.skill_registry import SkillRegistry


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_skill(
    repo_root: Path,
    name: str,
    description: str,
    tags: list[str] | None = None,
) -> None:
    tags = tags or []
    tag_line = f"tags: [{', '.join(tags)}]\n" if tags else ""
    _write(
        repo_root / ".agents" / "skills" / name / "SKILL.md",
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"{tag_line}"
            "---\n\n"
            f"# {name}\n\n"
            f"{description}\n"
        ),
    )


def test_parse_skill_frontmatter_from_fixture(package_root: Path) -> None:
    fixture = package_root / "tests" / "fixtures" / "skills" / "sample" / "SKILL.md"
    parsed = parse_skill_file(fixture)
    assert parsed.name == "sample-skill"
    assert "Sample fixture skill" in parsed.description
    assert parsed.frontmatter.get("user-invocable") is False
    assert "# Sample Skill" in parsed.body


def test_skill_registry_reindex_search_and_load(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _create_skill(repo_root, "run-agent", "Spawn delegation skill", tags=["base"])
    _create_skill(repo_root, "agent", "Worker guidance", tags=["base"])
    _create_skill(repo_root, "orchestrate", "Primary guidance", tags=["base"])
    _create_skill(repo_root, "reviewing", "Review code", tags=["review", "quality"])

    registry = SkillRegistry(
        repo_root=repo_root,
        db_path=repo_root / ".meridian" / "index" / "spawns.db",
    )
    assert registry.db_path == repo_root / ".meridian" / "index" / "skills.json"
    report = registry.reindex()
    assert report.indexed_count >= 4  # may include bundled skills

    search_hits = registry.search("quality")
    assert [item.name for item in search_hits] == ["reviewing"]
    loaded = registry.show("reviewing")
    assert loaded.name == "reviewing"
    assert "Review code" in loaded.content

    other_dir = repo_root / "not-skills"
    other_dir.mkdir(parents=True)
    with pytest.raises(ValueError, match=r"\.agents/skills"):
        registry.reindex(other_dir)


def test_model_guidance_override_precedence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    refs = repo_root / ".agents" / "skills" / "run-agent" / "references"
    _write(refs / "default-model-guidance.md", "# default\n")

    default_paths = selected_guidance_paths(repo_root)
    assert default_paths == (refs / "default-model-guidance.md",)

    custom = refs / "model-guidance"
    _write(custom / "20-a.md", "A")
    _write(custom / "10-b.md", "B")
    _write(custom / "README.md", "ignored")

    bundle = load_model_guidance(repo_root)
    assert [path.name for path in bundle.paths] == ["10-b.md", "20-a.md"]
    assert "B" in bundle.content and "A" in bundle.content
    assert "default" not in bundle.content


def test_agent_profile_parsing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write(
        repo_root / ".agents" / "agents" / "reviewer.md",
        (
            "---\n"
            "name: reviewer\n"
            "description: Reviews code\n"
            "model: claude-sonnet-4-6\n"
            "variant: high\n"
            "skills: [reviewing]\n"
            "allowed-tools: [Read, Grep]\n"
            "mcp-tools: [spawn_list, spawn_show]\n"
            "sandbox: danger-full-access\n"
            "variant-models:\n"
            "  - claude-opus-4-6\n"
            "---\n\n"
            "# reviewer\n\n"
            "Review code.\n"
        ),
    )

    profile = load_agent_profile("reviewer", repo_root=repo_root)
    assert profile.name == "reviewer"
    assert profile.model == "claude-sonnet-4-6"
    assert profile.skills == ("reviewing",)
    assert profile.allowed_tools == ("Read", "Grep")
    assert profile.mcp_tools == ("spawn_list", "spawn_show")
    assert profile.variant_models == ("claude-opus-4-6",)
    assert "Review code." in profile.body


def test_agent_profile_unknown_sandbox_warns_at_parse_time(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write(
        repo_root / ".agents" / "agents" / "reviewer.md",
        (
            "---\n"
            "name: reviewer\n"
            "model: claude-sonnet-4-6\n"
            "sandbox: full_access\n"
            "---\n\n"
            "body\n"
        ),
    )

    class _Logger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def warning(self, message: str, *args: object) -> None:
            self.messages.append(message % args if args else message)

    stub_logger = _Logger()
    monkeypatch.setattr(agent_config, "logger", stub_logger)

    profile = load_agent_profile("reviewer", repo_root=repo_root)

    assert profile.sandbox == "full_access"
    assert any(
        message == "Agent profile 'reviewer' has unknown sandbox 'full_access'."
        for message in stub_logger.messages
    )


def test_agent_profile_mcp_tools_normalizes_and_warns_unknown(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write(
        repo_root / ".agents" / "agents" / "reviewer.md",
        (
            "---\n"
            "name: reviewer\n"
            "model: claude-sonnet-4-6\n"
            "mcp-tools: [spawn_list, SPAWN_SHOW, spawn_list, unknown_tool]\n"
            "---\n\n"
            "body\n"
        ),
    )

    class _Logger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def warning(self, message: str, *args: object) -> None:
            self.messages.append(message % args if args else message)

    stub_logger = _Logger()
    monkeypatch.setattr(agent_config, "logger", stub_logger)

    profile = load_agent_profile("reviewer", repo_root=repo_root)

    assert profile.mcp_tools == ("spawn_list", "spawn_show", "unknown_tool")
    assert any(
        message == "Agent profile 'reviewer' includes unknown MCP tool 'unknown_tool'."
        for message in stub_logger.messages
    )


def test_route_model_matches_bash_rules() -> None:
    assert route_model("claude-opus-4-6").harness_id == "claude"
    assert route_model("sonnet-foo").harness_id == "claude"
    assert route_model("gpt-5.3-codex").harness_id == "codex"
    assert route_model("codex-mini").harness_id == "codex"
    assert route_model("opencode-kimi").harness_id == "opencode"
    assert route_model("google/gemini-2.5-pro").harness_id == "opencode"
    assert route_model("any-model", mode="direct").harness_id == "direct"

    fallback = route_model("totally-unknown-family")
    assert fallback.harness_id == "codex"
    assert fallback.warning is not None


def test_model_catalog_override_and_resolution(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write(
        repo_root / ".meridian" / "models.toml",
        (
            "[[models]]\n"
            "model_id = 'my-custom-model'\n"
            "aliases = ['custom']\n"
            "role = 'custom role'\n"
            "strengths = 'custom strengths'\n"
            "cost_tier = '$'\n"
            "harness = 'opencode'\n"
        ),
    )

    loaded = load_model_catalog(repo_root=repo_root)
    assert any(str(entry.model_id) == "my-custom-model" for entry in loaded)

    resolved = resolve_model("custom", repo_root=repo_root)
    assert str(resolved.model_id) == "my-custom-model"
    assert resolved.harness == "opencode"
