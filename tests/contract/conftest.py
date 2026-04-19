"""Auto-mark contract tests collected under tests/contract/."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/tests/contract/" in path and item.get_closest_marker("contract") is None:
            item.add_marker(pytest.mark.contract)
