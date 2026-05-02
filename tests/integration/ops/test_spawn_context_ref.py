from pathlib import Path

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.ops.spawn.api import SpawnCreateInput, spawn_create_sync
from meridian.lib.ops.spawn.context_ref import render_context_refs, resolve_context_ref
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_project_runtime_root


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


def _write_minimal_mars_config(project_root: Path) -> None:
    (project_root / "mars.toml").write_text(
        "[settings]\n"
        'targets = [".claude"]\n',
        encoding="utf-8",
    )


def _seed_session(project_root: Path, chat_id: str) -> None:
    runtime_root = resolve_project_runtime_root(project_root)
    session_store.start_session(
        runtime_root,
        chat_id=chat_id,
        harness="codex",
        harness_session_id="thread-1",
        model="gpt-5.3-codex",
        agent="coder",
        kind="primary",
    )
    session_store.stop_session(runtime_root, chat_id)


def _seed_spawn(
    project_root: Path,
    *,
    chat_id: str,
    status: SpawnStatus,
    desc: str,
    kind: str = "child",
    report_text: str | None = None,
    written_files: tuple[str, ...] = (),
) -> str:
    runtime_root = resolve_project_runtime_root(project_root)
    spawn_id = str(
        spawn_store.start_spawn(
            runtime_root,
            chat_id=chat_id,
            model="gpt-5.3-codex",
            agent="coder",
            harness="codex",
            kind=kind,
            prompt="seed prompt",
            desc=desc,
            harness_session_id="thread-1",
        )
    )
    if status not in {"queued", "running", "finalizing"}:
        exit_code = 0 if status == "succeeded" else 1
        spawn_store.finalize_spawn(
            runtime_root,
            spawn_id,
            status=status,
            exit_code=exit_code,
            origin="runner",
            error=None if status == "succeeded" else "failed",
        )
    if report_text is not None:
        report_path = runtime_root / "spawns" / spawn_id / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
    if written_files:
        artifact_store = LocalStore(root_dir=runtime_root / "artifacts")
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


def test_resolve_context_ref_session_uses_primary_spawn(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    primary_id = _seed_spawn(
        project_root,
        chat_id="c5",
        status="running",
        desc="Primary",
        kind="primary",
    )
    _seed_spawn(project_root, chat_id="c5", status="failed", desc="Phase 0")
    _seed_spawn(
        project_root,
        chat_id="c5",
        status="succeeded",
        desc="Phase 1: Data Model",
        report_text="# Report\n\nImplemented phase 1.",
        written_files=("src/auth/models.py", "src/auth/token_store.py"),
    )
    _seed_spawn(project_root, chat_id="c5", status="failed", desc="Phase 2")

    resolved = resolve_context_ref(project_root, "c5")

    assert resolved.ref_kind == "session"
    assert resolved.primary_spawn_id == primary_id
    assert resolved.status == "running"
    assert resolved.chat_id == "c5"

    rendered = render_context_refs((resolved,))
    assert f'<prior-session-context chat="c5" primary_spawn="{primary_id}">' in rendered
    assert "## Report" not in rendered
    assert "## Files Modified" not in rendered
    assert f"`meridian spawn show {primary_id}`" in rendered
    assert "`meridian session log c5`" in rendered


def test_resolve_context_ref_session_requires_primary_spawn(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    _seed_spawn(project_root, chat_id="c8", status="failed", desc="Earlier")

    try:
        resolve_context_ref(project_root, "c8")
    except ValueError as exc:
        assert "No primary spawn found for session 'c8'" in str(exc)
    else:
        raise AssertionError("expected missing primary spawn to fail")


def test_resolve_context_ref_accepts_tracked_arbitrary_chat_id(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    _seed_session(project_root, "chat-parent")
    primary_id = _seed_spawn(
        project_root,
        chat_id="chat-parent",
        status="running",
        desc="Primary",
        kind="primary",
    )
    child_id = _seed_spawn(
        project_root,
        chat_id="chat-parent",
        status="succeeded",
        desc="Child",
    )

    resolved = resolve_context_ref(project_root, "chat-parent")

    assert resolved.ref_kind == "session"
    assert resolved.primary_spawn_id == primary_id
    assert resolved.primary_spawn_id != child_id
    rendered = render_context_refs((resolved,))
    assert f"`meridian session log {primary_id}`" in rendered
    assert "`meridian session log chat-parent`" not in rendered


def test_spawn_create_dry_run_injects_prior_context_from_session(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    _write_minimal_mars_config(project_root)
    _write_agent(project_root / ".mars" / "agents" / "coder.md", sandbox="workspace-write")
    primary_id = _seed_spawn(
        project_root,
        chat_id="c11",
        status="running",
        desc="Primary",
        kind="primary",
    )
    _seed_spawn(
        project_root,
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
            project_root=project_root.as_posix(),
            dry_run=True,
            context_from=("c11",),
        )
    )

    assert result.status == "dry-run"
    assert result.context_from_resolved == ("c11",)
    assert result.composed_prompt is not None
    assert "<prior-run-output>" in result.composed_prompt
    assert (
        f'<prior-session-context chat="c11" primary_spawn="{primary_id}">'
        in result.composed_prompt
    )
    assert "# Report\n\nDone." not in result.composed_prompt
    assert "- src/auth/models.py" not in result.composed_prompt
    assert f"`meridian spawn show {primary_id}`" in result.composed_prompt
    assert "`meridian session log c11`" in result.composed_prompt
