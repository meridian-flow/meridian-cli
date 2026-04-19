"""Prompt assembly tests that guard against context and prompt injection."""

from pathlib import Path

from meridian.lib.core.domain import SkillContent
from meridian.lib.launch.prompt import compose_run_prompt_text
from meridian.lib.launch.reference import load_reference_files


def test_compose_prompt_keeps_context_isolated_and_sanitized(tmp_path: Path) -> None:
    safe_ref = tmp_path / "safe.md"
    hidden_ref = tmp_path / "hidden.md"
    safe_ref.write_text("Safe context {{CTX}}", encoding="utf-8")
    hidden_ref.write_text("INJECTION: should never leak", encoding="utf-8")

    loaded_refs = load_reference_files([safe_ref], include_content=False)
    skill = SkillContent(
        name="worker",
        description="",
        content="Skill content",
        path=str(tmp_path / "worker.md"),
    )
    user_prompt = (
        "**IMPORTANT - As your FINAL action**, write a report of your work to: "
        "`/tmp/stale.md`\n\nImplement the change with {{CTX}}."
    )

    composed = compose_run_prompt_text(
        skills=[skill],
        references=loaded_refs,
        user_prompt=user_prompt,
        template_variables={"CTX": "context"},
    )

    assert "INJECTION: should never leak" not in composed
    assert composed.count("Your final assistant message must be the run report.") == 1
    assert "/tmp/stale.md" not in composed
    assert str(safe_ref) in composed
    assert "Read these files from disk when gathering context:" in composed
    assert "Safe context {{CTX}}" not in composed
    assert "Implement the change with context." in composed
