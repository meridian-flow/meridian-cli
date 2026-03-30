from pathlib import Path

from meridian.lib.config.settings import load_config
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.resolve import ResolvedPolicies, ResolvedSkills
from meridian.lib.ops.runtime import build_runtime_from_root_and_config
from meridian.lib.ops.spawn.models import SpawnCreateInput
from meridian.lib.ops.spawn.prepare import build_create_payload


def _patch_codex_policies(monkeypatch, repo_root: Path):
    harness_registry = get_default_harness_registry()
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)

    monkeypatch.setattr(
        "meridian.lib.ops.spawn.prepare.ensure_bootstrap_ready",
        lambda **kwargs: type(
            "_BootstrapPlan",
            (),
            {"required_items": (), "missing_items": ()},
        )(),
    )
    monkeypatch.setattr(
        "meridian.lib.ops.spawn.prepare.resolve_policies",
        lambda **kwargs: ResolvedPolicies(
            profile=None,
            model="gpt-5.3-codex",
            harness=HarnessId.CODEX,
            adapter=codex_adapter,
            resolved_skills=ResolvedSkills(
                skill_names=(),
                loaded_skills=(),
                skill_sources={},
                missing_skills=(),
            ),
            warning=None,
        ),
    )
    return codex_adapter, build_runtime_from_root_and_config(
        repo_root, load_config(repo_root)
    )


def test_build_create_payload_materializes_codex_fork_session(monkeypatch, tmp_path: Path) -> None:
    codex_adapter, runtime = _patch_codex_policies(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        codex_adapter,
        "fork_session",
        lambda source_session_id: calls.append(source_session_id) or "forked-session",
    )

    prepared = build_create_payload(
        SpawnCreateInput(
            prompt="fork prompt",
            repo_root=tmp_path.as_posix(),
            continue_harness_session_id="source-session",
            continue_harness="codex",
            continue_fork=True,
            dry_run=False,
        ),
        runtime=runtime,
    )

    assert calls == ["source-session"]
    assert prepared.session.harness_session_id == "forked-session"
    assert prepared.session.continue_fork is False


def test_build_create_payload_skips_codex_fork_on_dry_run(monkeypatch, tmp_path: Path) -> None:
    codex_adapter, runtime = _patch_codex_policies(monkeypatch, tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        codex_adapter,
        "fork_session",
        lambda source_session_id: calls.append(source_session_id) or "forked-session",
    )

    prepared = build_create_payload(
        SpawnCreateInput(
            prompt="fork prompt",
            repo_root=tmp_path.as_posix(),
            continue_harness_session_id="source-session",
            continue_harness="codex",
            continue_fork=True,
            dry_run=True,
        ),
        runtime=runtime,
    )

    assert calls == []
    assert prepared.session.harness_session_id == "source-session"
    assert prepared.session.continue_fork is True
