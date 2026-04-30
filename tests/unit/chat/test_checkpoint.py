from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.chat.checkpoint import CheckpointService


class Pipeline:
    chat_id = "c1"

    async def ingest(self, event):
        _ = event


@pytest.mark.asyncio
async def test_checkpoint_create_skips_when_multiple_chats_active(tmp_path: Path) -> None:
    service = CheckpointService(tmp_path, Pipeline(), chat_registry=lambda: 2)

    assert await service.create_checkpoint("turn-1") is None


@pytest.mark.asyncio
async def test_checkpoint_revert_blocks_when_multiple_chats_active(tmp_path: Path) -> None:
    service = CheckpointService(tmp_path, Pipeline(), chat_registry=lambda: 2)

    with pytest.raises(RuntimeError, match="checkpoint_revert_unsafe_multi_chat"):
        await service.revert_to_checkpoint("abc123")
