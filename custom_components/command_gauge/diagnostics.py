"""Redacted diagnostics for Command Gauge."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_BASE_URL,
    DOMAIN,
    token_fingerprint,
)

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "authorization",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)

_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+\S+"),
    re.compile(
        r"(?i)(?P<prefix>\b(?:api[-_ ]?key|apikey|access[-_ ]?token|"
        r"refresh[-_ ]?token|token|secret|password|authorization)\s*"
        r"(?:=|:)\s*)(?P<value>[^\s&\"'}]+)"
    ),
    re.compile(r"(?i)\b(?:user|cc)[_-][A-Za-z0-9_-]{8,}\b"),
)


def _redact(value: Any, key: str | None = None) -> Any:
    """Recursively remove secret-shaped values from diagnostic data."""
    if key and key.lower() in _SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        redacted = _SECRET_TEXT_PATTERNS[0].sub("Bearer [REDACTED]", value)
        redacted = _SECRET_TEXT_PATTERNS[1].sub(r"\g<prefix>[REDACTED]", redacted)
        return _SECRET_TEXT_PATTERNS[2].sub("[REDACTED]", redacted)
    return value


def _safe_base_url(value: Any) -> str | None:
    """Export only URL origin/path, never query strings or userinfo."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parts = urlsplit(value)
        hostname = parts.hostname or ""
        port = parts.port
    except ValueError:
        return None
    if port:
        hostname = f"{hostname}:{port}"
    return urlunsplit((parts.scheme, hostname, parts.path, "", ""))


def _account_snapshot(account: Any) -> dict[str, Any]:
    """Keep identity non-reversible; do not export login or provider IDs."""
    if not isinstance(account, dict):
        return {}
    scope = account.get("scope_key")
    return {
        "present": True,
        "subject_type": account.get("subject_type"),
        "scope_fingerprint": (
            hashlib.sha256(str(scope).encode()).hexdigest()[:8] if scope else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return sanitized config-entry and coordinator diagnostics."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    coordinator_data = _redact(dict(coordinator.data or {})) if coordinator else {}
    coordinator_data["account"] = _account_snapshot(
        (coordinator.data or {}).get("account") if coordinator else None
    )
    return {
        "entry": {
            "data": {
                CONF_ACCOUNT_NAME: _redact(entry.data.get(CONF_ACCOUNT_NAME)),
                CONF_BASE_URL: _safe_base_url(entry.data.get(CONF_BASE_URL)),
                "api_key_fingerprint": token_fingerprint(str(entry.data.get(CONF_API_KEY) or "")),
            },
            "options": _redact(dict(entry.options)),
        },
        "coordinator": coordinator_data,
    }
