from pathlib import Path

from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
from meridian.lib.ops.spawn.context_ref import render_context_refs, resolve_context_ref
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_runtime_state_root


def _write_agent(path: Path, *, sandbox: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "name: coder",
                "description: test coder",
                "model: gpt-5.3-codex",
                f"sandbox: {sandbox}",
                "---",
                "",
                "# Coder",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_minimal_mars_config(repo_root: Path) -> None:
    (repo_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".agents"]\n',
        encoding="utf-8",
    )


def _seed_spawn(
    repo_root: Path,
    *,
    chat_id: str,
    status: str,
    desc: str,
    report_text: str | None = None,
    written_files: tuple[str, ...] = (),
) -> str:
    state_root = resolve_runtime_state_root(repo_root)
    spawn_id = str(
        spawn_store.start_spawn(
            state_root,
            chat_id=chat_id,
            model="gpt-5.3-codex",
            agent="coder",
            harness="codex",
            kind="child",
            prompt="seed prompt",
            desc=desc,
            harness_session_id="thread-1",
        )
    )
    exit_code = 0 if status == "succeeded" else 1
    spawn_store.finalize_spawn(
        state_root,
        spawn_id,
        status=status,
        exit_code=exit_code,
        origin="runner",
        error=None if status == "succeeded" else "failed",
    )
    if report_text is not None:
        report_path = state_root / "spawns" / spawn_id / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
    if written_files:
        artifact_store = LocalStore(root_dir=state_root / "artifacts")
        payload = (
            "{"
            + '"written_files":['
            + ",".join(f'"{path}"' for path in written_files)
            + "]}"
        )
        artifact_store.put(
            make_artifact_key(spawn_id, "written_files.json"),
            payload.encode("utf-8"),
        )
    return spawn_id


def test_resolve_context_ref_session_prefers_latest_succeeded(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    _seed_spawn(repo_root, chat_id="c5", status="failed", desc="Phase 0")
    succeeded_id = _seed_spawn(
        repo_root,
        chat_id="c5",
        status="succeeded",
        desc="Phase 1: Data Model",
        report_text="# Report\n\nImplemented phase 1.",
        written_files=("src/auth/models.py", "src/auth/token_store.py"),
    )
    _seed_spawn(repo_root, chat_id="c5", status="failed", desc="Phase 2")

    resolved = resolve_context_ref(repo_root, "c5")

    assert resolved.spawn_id == succeeded_id
    assert resolved.status == "succeeded"
    assert resolved.chat_id == "c5"
    assert resolved.report_text == "# Report\n\nImplemented phase 1."
    assert resolved.written_files == ("src/auth/models.py", "src/auth/token_store.py")

    rendered = render_context_refs((resolved,))
    assert f'<prior-spawn-context spawn="{succeeded_id}">' in rendered
    assert "## Report" in rendered
    assert "## Files Modified" in rendered
    assert f"`meridian spawn show {succeeded_id}`" in rendered
    assert "`meridian session log c5`" in rendered


def test_resolve_context_ref_session_falls_back_to_latest_when_no_success(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    _seed_spawn(repo_root, chat_id="c8", status="failed", desc="Earlier")
    latest_id = _seed_spawn(repo_root, chat_id="c8", status="failed", desc="Latest failure")

    resolved = resolve_context_ref(repo_root, "c8")

    assert resolved.spawn_id == latest_id
    assert resolved.status == "failed"

    rendered = render_context_refs((resolved,))
    assert "No report available." in rendered
    assert "## Files Modified" not in rendered


def test_spawn_create_dry_run_injects_prior_context_from_session(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_minimal_mars_config(repo_root)
    _write_agent(repo_root / ".agents" / "agents" / "coder.md", sandbox="workspace-write")
    seed_id = _seed_spawn(
        repo_root,
        chat_id="c11",
        status="succeeded",
        desc="Phase 1: Data Model",
        report_text="# Report\n\nDone.",
        written_files=("src/auth/models.py",),
    )

    result = spawn_create_sync(
        SpawnCreateInput(
            prompt="Implement phase 2.",
            agent="coder",
            repo_root=repo_root.as_posix(),
            dry_run=True,
            context_from=("c11",),
        )
    )

    assert result.status == "dry-run"
    assert result.context_from_resolved == (seed_id,)
    assert result.composed_prompt is not None
    assert "<prior-run-output>" in result.composed_prompt
    assert f'<prior-spawn-context spawn="{seed_id}">' in result.composed_prompt
    assert "# Report\n\nDone." in result.composed_prompt
    assert "- src/auth/models.py" in result.composed_prompt
    assert f"`meridian spawn files {seed_id}`" in result.composed_prompt
