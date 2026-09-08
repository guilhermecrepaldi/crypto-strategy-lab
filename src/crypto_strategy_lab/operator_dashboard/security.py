"""Security primitives shared by the local operator HTTP and persistence layers."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_NAME = re.compile(
    r"(?i)^(?:binance[_-]?api[_-]?(?:key|secret)|api[_-]?(?:key|secret)|"
    r"authorization|x-mbx-apikey|signature)$"
)
_SENSITIVE_PAIR = re.compile(
    r"(?i)(binance[_-]?api[_-]?(?:key|secret)|api[_-]?(?:key|secret)|"
    r"authorization|x-mbx-apikey|signature)"
    r"(\s*[=:]\s*)([^\s&,;\"']+)"
)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def redact_text(value: str, known_secrets: Sequence[str] = ()) -> str:
    """Remove credentials and signed-query material without trying to log it safely."""
    sanitized = value
    for secret in known_secrets:
        if secret:
            sanitized = sanitized.replace(secret, REDACTED)
    return _SENSITIVE_PAIR.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", sanitized
    )


def redact(value: Any, known_secrets: Sequence[str] = ()) -> Any:
    """Recursively sanitize structures before any response or journal write."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED
            if _SENSITIVE_NAME.fullmatch(str(key))
            else redact(item, known_secrets)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return redact_text(value, known_secrets)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item, known_secrets) for item in value]
    return value


def mask_api_key(value: str) -> str:
    if len(value) <= 8:
        return f"***{value[-4:]}" if value else ""
    return f"{value[:4]}...{value[-4:]}"


def contains_sensitive_name(value: str) -> bool:
    return _SENSITIVE_NAME.fullmatch(value) is not None
