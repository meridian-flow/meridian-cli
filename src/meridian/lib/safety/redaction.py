"""Secret parsing and redaction helpers."""

import re

from pydantic import BaseModel, ConfigDict

_SECRET_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class SecretSpec(BaseModel):
    """In-memory secret assignment for one run."""

    model_config = ConfigDict(frozen=True)

    key: str
    value: str


def parse_secret_specs(raw_assignments: tuple[str, ...]) -> tuple[SecretSpec, ...]:
    """Parse repeated --secret KEY=VALUE assignments."""

    parsed: dict[str, SecretSpec] = {}
    for raw in raw_assignments:
        assignment = raw.strip()
        if not assignment:
            continue
        key, sep, value = assignment.partition("=")
        if not sep:
            raise ValueError(f"Invalid --secret value '{raw}'. Expected KEY=VALUE.")
        normalized_key = key.strip().upper()
        if not _SECRET_KEY_RE.match(normalized_key):
            raise ValueError(
                f"Invalid secret key '{key}'. Use letters, numbers, and underscores only."
            )
        parsed[normalized_key] = SecretSpec(key=normalized_key, value=value)
    return tuple(parsed[key] for key in sorted(parsed))


def secrets_env_overrides(secrets: tuple[SecretSpec, ...]) -> dict[str, str]:
    """Convert secrets into harness environment variables."""

    return {f"MERIDIAN_SECRET_{secret.key}": secret.value for secret in secrets}


def redact_secrets(text: str, secrets: tuple[SecretSpec, ...]) -> str:
    """Replace secret values with key-specific placeholders."""

    redacted = text
    by_length = sorted(
        (secret for secret in secrets if secret.value),
        key=lambda item: len(item.value),
        reverse=True,
    )
    for secret in by_length:
        redacted = redacted.replace(secret.value, f"[REDACTED:{secret.key}]")
    return redacted


def redact_secret_bytes(data: bytes, secrets: tuple[SecretSpec, ...]) -> bytes:
    """Byte wrapper around redaction for streamed logs."""

    if not secrets:
        return data
    decoded = data.decode("utf-8", errors="replace")
    return redact_secrets(decoded, secrets).encode("utf-8")
