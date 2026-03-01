"""Slice 5a error classification tests."""

from __future__ import annotations

import pytest

from meridian.lib.exec.errors import ErrorCategory, classify_error, should_retry


@pytest.mark.parametrize(
    "error_message,expected",
    [
        pytest.param(
            "Request failed: token limit exceeded for this model.",
            ErrorCategory.UNRECOVERABLE,
            id="token-limit",
        ),
        pytest.param(
            "Model not found: gpt-unknown",
            ErrorCategory.UNRECOVERABLE,
            id="model-not-found",
        ),
        pytest.param(
            "Network error: connection reset by peer",
            ErrorCategory.RETRYABLE,
            id="network-error",
        ),
        pytest.param(
            "Maximum context length exceeded; prompt too long.",
            ErrorCategory.STRATEGY_CHANGE,
            id="context-overflow",
        ),
    ],
)
def test_classify_error_categories(error_message: str, expected: ErrorCategory) -> None:
    assert classify_error(1, error_message) == expected


def test_should_retry_honors_retryable_and_max_limit() -> None:
    assert (
        should_retry(
            exit_code=1,
            stderr="network error: connection reset",
            retries_attempted=0,
            max_retries=3,
        )
        is True
    )
    assert (
        should_retry(
            exit_code=1,
            stderr="network error: connection reset",
            retries_attempted=3,
            max_retries=3,
        )
        is False
    )
    assert (
        should_retry(
            exit_code=1,
            stderr="model not found",
            retries_attempted=0,
            max_retries=3,
        )
        is False
    )


def test_should_retry_never_retries_timeouts() -> None:
    assert (
        should_retry(
            exit_code=3,
            stderr="",
            timed_out=True,
            retries_attempted=0,
            max_retries=3,
        )
        is False
    )


def test_classify_error_timeout_flag_returns_timeout_category() -> None:
    assert classify_error(3, "", timed_out=True) == ErrorCategory.TIMEOUT
