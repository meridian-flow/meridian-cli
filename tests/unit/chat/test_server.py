import pytest

from meridian.lib.chat.server import _UnconfiguredRuntime


def test_unconfigured_runtime_raises_for_any_access() -> None:
    runtime = _UnconfiguredRuntime()

    with pytest.raises(RuntimeError, match="not configured"):
        runtime.start()

    with pytest.raises(RuntimeError, match="not configured"):
        runtime.list_chats()
