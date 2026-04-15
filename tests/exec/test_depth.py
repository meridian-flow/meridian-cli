"""Depth limit helper behavior for recursive child spawns."""

import pytest

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.spawn.execute import depth_exceeded_output, depth_limits


def test_depth_limits_returns_current_and_max() -> None:
    ctx = RuntimeContext(depth=2)
    current_depth, max_depth = depth_limits(2, ctx=ctx)

    assert current_depth == 2
    assert max_depth == 2


def test_depth_limits_rejects_negative_max_depth() -> None:
    with pytest.raises(ValueError, match="max_depth must be >= 0"):
        depth_limits(-1)


def test_depth_exceeded_output_contract() -> None:
    output = depth_exceeded_output(current_depth=3, max_depth=2)

    assert output.command == "spawn.create"
    assert output.status == "failed"
    assert output.error == "max_depth_exceeded"
    assert output.current_depth == 3
    assert output.max_depth == 2
