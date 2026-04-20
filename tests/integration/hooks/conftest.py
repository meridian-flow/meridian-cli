"""Hook test fixtures."""

import pytest
import structlog


@pytest.fixture(autouse=True)
def _reset_structlog_before_capture() -> None:
    """Reset structlog defaults so capture_logs() works correctly.

    CLI tests configure structlog globally with cache_logger_on_first_use=True.
    When hook dispatch tests run after CLI tests, cached loggers don't pick up
    the test configuration from capture_logs(). This fixture ensures structlog
    is reset to defaults before each test.
    """
    structlog.reset_defaults()
