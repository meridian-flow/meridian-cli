import pytest

from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.codex import CodexAdapter


class _StaticResolver:
    def __init__(self, flags: list[str]) -> None:
        self._flags = flags

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        assert harness_id is HarnessId.CODEX
        return list(self._flags)


def test_noninteractive_codex_resume_places_permission_flags_before_subcommand() -> None:
    permission_flags = ["--sandbox", "workspace-write"]
    session_id = "session-123456"
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="ignored",
            continue_harness_session_id=session_id,
            interactive=False,
        ),
        _StaticResolver(permission_flags),
    )

    resume_index = command.index("resume")
    assert command[resume_index + 1] == session_id
    for flag in permission_flags:
        assert command.index(flag) < resume_index


def test_interactive_codex_resume_places_permission_flags_before_subcommand() -> None:
    permission_flags = ["--sandbox", "workspace-write"]
    session_id = "session-123456"
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="hello",
            continue_harness_session_id=session_id,
            interactive=True,
        ),
        _StaticResolver(permission_flags),
    )

    resume_index = command.index("resume")
    assert command[resume_index + 1] == session_id
    for flag in permission_flags:
        assert command.index(flag) < resume_index


@pytest.mark.parametrize(
    ("interactive", "expected_prefix"),
    (
        (False, ("codex", "exec", "--json")),
        (True, ("codex",)),
    ),
)
def test_fresh_codex_command_has_no_resume_subcommand(
    interactive: bool,
    expected_prefix: tuple[str, ...],
) -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="hello",
            interactive=interactive,
        ),
        _StaticResolver([]),
    )

    assert tuple(command[: len(expected_prefix)]) == expected_prefix
    assert "resume" not in command
