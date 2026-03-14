import json

from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter, build_claude_adhoc_agent_json


class _NoopResolver:
    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        _ = harness_id
        return []


def test_build_claude_adhoc_agent_json_uses_profile_fields() -> None:
    payload = build_claude_adhoc_agent_json(
        name="reviewer",
        description="Reviews code",
        prompt="You review code carefully.",
    )

    parsed = json.loads(payload)
    assert parsed == {
        "reviewer": {
            "description": "Reviews code",
            "prompt": "You review code carefully.",
        }
    }


def test_claude_command_includes_adhoc_agents_payload() -> None:
    adapter = ClaudeAdapter()
    adhoc_payload = build_claude_adhoc_agent_json(
        name="reviewer",
        description="Reviews code",
        prompt="You review code carefully.",
    )

    command = adapter.build_command(
        SpawnParams(
            prompt="hello",
            model=ModelId("claude-sonnet-4-6"),
            agent="reviewer",
            adhoc_agent_json=adhoc_payload,
        ),
        _NoopResolver(),
    )

    assert "--agent" in command
    assert "reviewer" in command
    assert "--agents" in command
    agents_index = command.index("--agents")
    assert json.loads(command[agents_index + 1])["reviewer"]["prompt"] == "You review code carefully."
