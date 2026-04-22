"""Auto-mark integration tests collected under tests/integration/."""

from __future__ import annotations

import pytest
import structlog


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/tests/integration/" in path and item.get_closest_marker("integration") is None:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    """Reset structlog so cached loggers don't write to stale capsys buffers.

    CLI tests configure structlog with cache_logger_on_first_use=True. When
    integration tests run after CLI tests, cached loggers hold references to
    closed CaptureIO objects, causing ValueError on log writes.
    """
    structlog.reset_defaults()
