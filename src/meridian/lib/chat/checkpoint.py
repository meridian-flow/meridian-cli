"""Git-backed checkpoints for chat turns."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from meridian.lib.chat.event_pipeline import ChatEventPipeline
from meridian.lib.chat.protocol import ChatEvent, utc_now_iso

logger = logging.getLogger(__name__)


class CheckpointService:
    """Create and revert durable git commits around chat turn boundaries."""

    def __init__(
        self,
        project_root: Path,
        event_pipeline: ChatEventPipeline,
        *,
        chat_registry: Callable[[], int] | None = None,
    ) -> None:
        self._project_root = project_root
        self._pipeline = event_pipeline
        self._chat_registry = chat_registry

    async def create_checkpoint(self, turn_id: str) -> str | None:
        if self._unsafe_multi_chat():
            logger.warning("Skipping checkpoint create for multi-chat project root")
            return None
        if not await _is_git_repo(self._project_root):
            return None
        await _git(self._project_root, "add", "-A")
        diff = await _git(self._project_root, "diff", "--cached", "--quiet", check=False)
        if diff.returncode == 0:
            commit_sha = (await _git_stdout(self._project_root, "rev-parse", "HEAD")).strip()
            if commit_sha:
                await self._emit("checkpoint.created", turn_id, commit_sha, clean=True)
                return commit_sha
            return None
        message = f"meridian checkpoint {turn_id}"
        await _git(self._project_root, "commit", "-m", message)
        commit_sha = (await _git_stdout(self._project_root, "rev-parse", "HEAD")).strip()
        await self._emit("checkpoint.created", turn_id, commit_sha, clean=False)
        return commit_sha

    async def revert_to_checkpoint(self, commit_sha: str) -> None:
        if not commit_sha:
            raise ValueError("invalid_command:missing_commit_sha")
        if self._unsafe_multi_chat():
            logger.warning("Blocking checkpoint revert for multi-chat project root")
            raise RuntimeError("checkpoint_revert_unsafe_multi_chat")
        if not await _is_git_repo(self._project_root):
            raise RuntimeError("checkpoint_requires_git_repo")
        await _git(self._project_root, "reset", "--hard", commit_sha)
        await self._emit("checkpoint.reverted", "", commit_sha)

    def _unsafe_multi_chat(self) -> bool:
        return self._chat_registry is not None and self._chat_registry() > 1

    async def _emit(
        self, event_type: str, turn_id: str, commit_sha: str, **payload: object
    ) -> None:
        await self._pipeline.ingest(
            ChatEvent(
                type=event_type,
                seq=0,
                chat_id=self._pipeline.chat_id,
                execution_id="",
                timestamp=utc_now_iso(),
                turn_id=turn_id or None,
                payload={"turn_id": turn_id, "commit_sha": commit_sha, **payload},
            )
        )


async def _is_git_repo(cwd: Path) -> bool:
    result = await _git(cwd, "rev-parse", "--is-inside-work-tree", check=False)
    return result.returncode == 0 and result.stdout.strip() == b"true"


async def _git_stdout(cwd: Path, *args: str) -> str:
    result = await _git(cwd, *args)
    return result.stdout.decode("utf-8")


async def _git(cwd: Path, *args: str, check: bool = True) -> _CompletedProcess:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    returncode = proc.returncode
    if returncode is None:
        raise RuntimeError("git command did not report an exit code")
    result = _CompletedProcess(returncode, stdout, stderr)
    if check and result.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace").strip() or "git command failed")
    return result


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


__all__ = ["CheckpointService"]
