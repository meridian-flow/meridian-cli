from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.chat.checkpoint import CheckpointService


class Pipeline:
    chat_id = "c1"

    def __init__(self):
        self.events = []

    async def ingest(self, event):
        self.events.append(event)


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.mark.asyncio
async def test_checkpoint_create_skips_when_multiple_chats_active(tmp_path: Path) -> None:
    pipeline = Pipeline()
    service = CheckpointService(tmp_path, pipeline, chat_registry=lambda: 2)

    assert await service.create_checkpoint("turn-1") is None
    assert pipeline.events == []


@pytest.mark.asyncio
async def test_checkpoint_revert_blocks_when_multiple_chats_active(tmp_path: Path) -> None:
    service = CheckpointService(tmp_path, Pipeline(), chat_registry=lambda: 2)

    with pytest.raises(RuntimeError, match="checkpoint_revert_unsafe_multi_chat"):
        await service.revert_to_checkpoint("abc123")


@pytest.mark.asyncio
async def test_checkpoint_create_returns_head_for_clean_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = Pipeline()
    service = CheckpointService(tmp_path, pipeline)
    git_calls = []

    async def fake_is_git_repo(cwd: Path) -> bool:
        assert cwd == tmp_path
        return True

    async def fake_git(cwd: Path, *args: str, check: bool = True):
        assert cwd == tmp_path
        git_calls.append((args, check))
        if args == ("add", "-A"):
            return FakeCompletedProcess(returncode=0)
        if args == ("diff", "--cached", "--quiet"):
            assert check is False
            return FakeCompletedProcess(returncode=0)
        raise AssertionError(f"unexpected git call: {args}")

    async def fake_git_stdout(cwd: Path, *args: str) -> str:
        assert cwd == tmp_path
        assert args == ("rev-parse", "HEAD")
        return "deadbeef\n"

    monkeypatch.setattr("meridian.lib.chat.checkpoint._is_git_repo", fake_is_git_repo)
    monkeypatch.setattr("meridian.lib.chat.checkpoint._git", fake_git)
    monkeypatch.setattr("meridian.lib.chat.checkpoint._git_stdout", fake_git_stdout)

    commit_sha = await service.create_checkpoint("turn-1")

    assert commit_sha == "deadbeef"
    assert git_calls == [
        (("add", "-A"), True),
        (("diff", "--cached", "--quiet"), False),
    ]
    assert [event.type for event in pipeline.events] == ["checkpoint.created"]
    assert pipeline.events[0].payload["commit_sha"] == "deadbeef"
    assert pipeline.events[0].payload["clean"] is True


@pytest.mark.asyncio
async def test_checkpoint_create_skips_when_not_in_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = Pipeline()
    service = CheckpointService(tmp_path, pipeline)

    async def fake_is_git_repo(cwd: Path) -> bool:
        assert cwd == tmp_path
        return False

    monkeypatch.setattr("meridian.lib.chat.checkpoint._is_git_repo", fake_is_git_repo)

    commit_sha = await service.create_checkpoint("turn-1")

    assert commit_sha is None
    assert pipeline.events == []


@pytest.mark.asyncio
async def test_checkpoint_revert_requires_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = CheckpointService(tmp_path, Pipeline())

    async def fake_is_git_repo(cwd: Path) -> bool:
        assert cwd == tmp_path
        return False

    monkeypatch.setattr("meridian.lib.chat.checkpoint._is_git_repo", fake_is_git_repo)

    with pytest.raises(RuntimeError, match="checkpoint_requires_git_repo"):
        await service.revert_to_checkpoint("abc123")
