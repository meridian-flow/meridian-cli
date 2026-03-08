"""Runtime context derived from MERIDIAN_* environment variables."""


from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId


class RuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: SpawnId | None = None
    parent_spawn_id: SpawnId | None = None
    depth: int = 0
    repo_root: Path | None = None
    state_root: Path | None = None
    chat_id: str = ""

    @classmethod
    def from_environment(cls) -> Self:
        """Build context from MERIDIAN_* environment variables."""

        import os

        spawn_id_raw = os.getenv("MERIDIAN_SPAWN_ID", "").strip()
        parent_spawn_id_raw = os.getenv("MERIDIAN_PARENT_SPAWN_ID", "").strip()
        depth_raw = os.getenv("MERIDIAN_DEPTH", "0").strip()
        repo_root_raw = os.getenv("MERIDIAN_REPO_ROOT", "").strip()
        state_root_raw = os.getenv("MERIDIAN_STATE_ROOT", "").strip()
        chat_id_raw = os.getenv("MERIDIAN_CHAT_ID", "").strip()

        depth = 0
        try:
            depth = max(0, int(depth_raw))
        except (ValueError, TypeError):
            pass

        return cls(
            spawn_id=SpawnId(spawn_id_raw) if spawn_id_raw else None,
            parent_spawn_id=SpawnId(parent_spawn_id_raw) if parent_spawn_id_raw else None,
            depth=depth,
            repo_root=Path(repo_root_raw) if repo_root_raw else None,
            state_root=Path(state_root_raw) if state_root_raw else None,
            chat_id=chat_id_raw,
        )

    def child_context(self, *, spawn_id: SpawnId) -> "RuntimeContext":
        """Create child context for a nested spawn."""

        return RuntimeContext(
            spawn_id=spawn_id,
            parent_spawn_id=self.spawn_id,
            depth=self.depth + 1,
            repo_root=self.repo_root,
            state_root=self.state_root,
            chat_id=self.chat_id,
        )

    def to_env_overrides(self) -> dict[str, str]:
        """Produce MERIDIAN_* env overrides for child processes."""

        overrides: dict[str, str] = {"MERIDIAN_DEPTH": str(self.depth)}
        if self.spawn_id is not None:
            overrides["MERIDIAN_SPAWN_ID"] = str(self.spawn_id)
        if self.parent_spawn_id is not None:
            overrides["MERIDIAN_PARENT_SPAWN_ID"] = str(self.parent_spawn_id)
        if self.repo_root is not None:
            overrides["MERIDIAN_REPO_ROOT"] = self.repo_root.as_posix()
        if self.state_root is not None:
            overrides["MERIDIAN_STATE_ROOT"] = self.state_root.as_posix()
        if self.chat_id:
            overrides["MERIDIAN_CHAT_ID"] = self.chat_id
        return overrides
