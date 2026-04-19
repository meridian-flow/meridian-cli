"""Auto-mark unit tests collected under tests/unit/."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/tests/unit/" in path and item.get_closest_marker("unit") is None:
            item.add_marker(pytest.mark.unit)
