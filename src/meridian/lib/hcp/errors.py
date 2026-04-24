"""HCP error taxonomy."""

from enum import StrEnum


class HcpErrorCategory(StrEnum):
    HARNESS_NOT_FOUND = "harness_not_found"
    HARNESS_CRASHED = "harness_crashed"
    HARNESS_AUTH_FAILED = "harness_auth_failed"
    RESUME_FAILED = "resume_failed"
    SESSION_EXPIRED = "session_expired"
    CONCURRENT_PROMPT = "concurrent_prompt"
    PERMISSION_DENIED = "permission_denied"
    PROMPT_TOO_LARGE = "prompt_too_large"
    FAILED_PERSISTENCE = "failed_persistence"


class HcpError(Exception):
    def __init__(self, category: HcpErrorCategory, message: str) -> None:
        self.category = category
        self.message = message
        super().__init__(f"{category.value}: {message}")


__all__ = ["HcpError", "HcpErrorCategory"]
