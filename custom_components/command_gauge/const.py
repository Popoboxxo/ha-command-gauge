"""Constants and small pure helpers for Command Gauge."""

from __future__ import annotations

import hashlib
import ipaddress
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

DOMAIN = "command_gauge"
MANUFACTURER = "Popoboxxo"
MODEL = "CommandCode Cloud"

CONF_ACCOUNT_NAME = "account_name"
CONF_ACCOUNT_SCOPE_KEY = "account_scope_key"
CONF_ALLOW_CUSTOM_BASE_URL = "allow_custom_base_url"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_OFFLINE_PENDING = "offline_pending"
CONF_WARN_PERCENT = "warn_percent"
CONF_PACE_RED_PERCENT = "pace_red_percent"
CONF_AUTO_UPDATE_USAGE = "auto_update_usage"
CONF_USAGE_REFRESH_MINUTES = "usage_refresh_minutes"
CONF_AUTO_UPDATE_MODELS = "auto_update_models"
CONF_MODELS_REFRESH_MINUTES = "models_refresh_minutes"

DEFAULT_BASE_URL = "https://api.commandcode.ai"
APPROVED_BASE_HOSTS = frozenset({"api.commandcode.ai"})
DEFAULT_WARN_PERCENT = 80
DEFAULT_PACE_RED_PERCENT = 100
DEFAULT_USAGE_REFRESH_MINUTES = 10
DEFAULT_MODELS_REFRESH_MINUTES = 60

WINDOW_LABELS = {"5h": "5h rolling", "week": "Weekly"}
WINDOW_SECONDS = {"5h": 5 * 3600, "week": 7 * 24 * 3600}
WINDOW_API_KEYS = {"5h": "fiveHour", "week": "weekly"}

_PASTE_MARKERS = ("\x1b[200~", "\x1b[201~", "[200~", "[201~")


def _short_hash(value: str) -> str:
    """Return a non-secret, stable short hash."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def text(value: Any) -> str | None:
    """Return a non-empty string identifier, rejecting numbers and booleans."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def normalize_api_key(value: Any) -> str | None:
    """Remove terminal paste markers and reject control characters or spaces."""
    if not isinstance(value, str):
        return None
    candidate = value
    for marker in _PASTE_MARKERS:
        candidate = candidate.replace(marker, "")
    candidate = candidate.strip()
    if not candidate or any(ord(char) < 32 or ord(char) == 127 for char in candidate):
        return None
    if any(char.isspace() for char in candidate):
        return None
    return candidate


def account_unique_id(account: dict[str, Any]) -> str:
    """Return a stable config-entry ID for an organization/user billing scope."""
    scope = text(account.get("scope_key"))
    if not scope:
        raise ValueError("CommandCode account has no stable billing scope")
    return f"{DOMAIN}_{_short_hash(scope)}"


def account_scope_key(account: dict[str, Any]) -> str | None:
    """Return a stable, non-reversible identity key for reconciliation."""
    try:
        return account_unique_id(account)
    except ValueError:
        return None


def api_key_unique_id(api_key: str) -> str:
    """Return a stable non-secret fallback ID for legacy/offline entries."""
    return f"{DOMAIN}_{_short_hash(api_key)}"


def token_fingerprint(api_key: str) -> str | None:
    """Return a short fingerprint safe for diagnostics."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:8] if api_key else None


def _unsafe_custom_host(host: str) -> bool:
    """Reject local/private literal hosts when custom HTTPS is explicitly enabled."""
    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return not address.is_global


def validate_base_url(value: Any, allow_custom: bool = False) -> str:
    """Validate an API origin before it can receive credentials."""
    candidate = str(value or "").strip().rstrip("/")
    if not candidate:
        raise ValueError("invalid_base_url")
    try:
        parts = urlsplit(candidate)
        port = parts.port
        hostname = parts.hostname
    except ValueError as err:
        raise ValueError("invalid_base_url") from err
    if (
        parts.scheme.lower() != "https"
        or not hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
        or (port is not None and port != 443)
    ):
        raise ValueError("invalid_base_url")
    hostname = hostname.lower().rstrip(".")
    if not allow_custom and hostname not in APPROVED_BASE_HOSTS:
        raise ValueError("invalid_base_url")
    if allow_custom and _unsafe_custom_host(hostname):
        raise ValueError("invalid_base_url")
    rendered = hostname if port is None else f"{hostname}:{port}"
    return f"https://{rendered}"


def build_url(base_url: str, path: str, **params: str | None) -> str:
    """Build a CommandCode URL while omitting empty query parameters."""
    query = {key: value for key, value in params.items() if value}
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}{suffix}"


def parse_timestamp(value: Any) -> datetime | None:
    """Parse CommandCode epoch/ISO values into an aware UTC datetime."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            timestamp = float(value)
            if timestamp < 0:
                return None
            if timestamp >= 1_000_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)
        elif isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return None
            if text_value.isdigit():
                return parse_timestamp(int(text_value))
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        else:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
