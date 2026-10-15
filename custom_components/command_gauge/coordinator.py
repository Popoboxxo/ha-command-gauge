"""CommandCode API client, defensive parsers, and polling coordinator."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    CONF_AUTO_UPDATE_MODELS,
    CONF_AUTO_UPDATE_USAGE,
    CONF_MODELS_REFRESH_MINUTES,
    CONF_PACE_RED_PERCENT,
    CONF_USAGE_REFRESH_MINUTES,
    CONF_WARN_PERCENT,
    DEFAULT_BASE_URL,
    DEFAULT_MODELS_REFRESH_MINUTES,
    DEFAULT_PACE_RED_PERCENT,
    DEFAULT_USAGE_REFRESH_MINUTES,
    DEFAULT_WARN_PERCENT,
    DOMAIN,
    WINDOW_API_KEYS,
    WINDOW_SECONDS,
    api_param,
    build_url,
    iso_z,
    parse_timestamp,
    plan_monthly_credits,
    text,
)

_LOGGER = logging.getLogger(__name__)
MODELS_URL = "/provider/v1/models"
# Read the version from the manifest - the same file Home Assistant reports in
# the integration page - instead of hardcoding it. A literal here silently went
# stale at 0.1.0 while the manifest already said 0.1.1, so the API was being
# told the wrong version in the User-Agent.
INTEGRATION_VERSION: str = json.loads(
    (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
).get("version", "0.0.0")
BURN_RATE_LOOKBACK_SECONDS = 2 * 3600
BURN_RATE_MIN_SPAN_SECONDS = 300
AUTH_STATUSES = frozenset({401})
SECTION_KEYS = {
    "account": "account",
    "credits": "credits",
    "subscription": "subscription",
    "usage": "summary",
    "models": "models",
}


class CommandCodeApiError(Exception):
    """A sanitized CommandCode HTTP failure without response-body data."""

    def __init__(self, status: int, path: str) -> None:
        self.status = status
        self.path = path
        super().__init__(f"CommandCode HTTP {status} ({path})")


def number(value: Any) -> float | None:
    """Return a finite non-negative number or None.

    Accepts JSON numbers and numeric strings: the CommandCode API is alpha and
    the official CLI coerces both, so a stringified number must not turn a
    whole section into an unrecognized response.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except (TypeError, ValueError):
            return None
    if not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _parse_window(limit: Any) -> dict[str, Any] | None:
    """Parse one five-hour/weekly limit object."""
    if not isinstance(limit, dict):
        return None
    used = number(limit.get("used"))
    cap = number(limit.get("cap"))
    if used is None or cap is None or cap <= 0:
        return None
    exceeded = limit.get("exceeded")
    return {
        "used": used,
        "cap": cap,
        "percent": round(used / cap * 100, 2),
        "resets_at": parse_timestamp(limit.get("resetAt")),
        "exceeded": bool(exceeded) if isinstance(exceeded, bool) else used >= cap,
    }


def _unwrap_payload(payload: Any) -> Any:
    """Unwrap the common CommandCode ``data`` envelope when present."""
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def parse_credits(payload: Any) -> dict[str, Any] | None:
    """Parse credits from the verified and common alpha response shapes."""
    root = _unwrap_payload(payload)
    if not isinstance(root, dict):
        return None
    credits = root.get("credits")
    if not isinstance(credits, dict):
        credits = root
    values = {
        key: number(credits.get(key))
        for key in ("monthlyCredits", "purchasedCredits", "freeCredits")
    }
    known_values = [value for value in values.values() if value is not None]
    if not known_values:
        return None

    credit_threshold = number(credits.get("creditThreshold", root.get("creditThreshold")))

    windows: dict[str, dict[str, Any]] = {}
    window_limits = root.get("windowLimits")
    if isinstance(window_limits, dict):
        for key, api_key in WINDOW_API_KEYS.items():
            parsed = _parse_window(window_limits.get(api_key))
            if parsed is not None:
                parsed["key"] = key
                windows[key] = parsed

    below_threshold = credits.get("belowThreshold")
    explicit_remaining = number(
        root.get(
            "remainingCredits",
            root.get(
                "remaining_credit",
                root.get("remaining", credits.get("remainingCredits")),
            ),
        )
    )
    return {
        "monthly_credits": values["monthlyCredits"],
        "purchased_credits": values["purchasedCredits"],
        "free_credits": values["freeCredits"],
        "remaining_credits": explicit_remaining
        if explicit_remaining is not None
        else (round(sum(known_values), 4) if len(known_values) == len(values) else None),
        "credit_threshold": credit_threshold,
        "below_threshold": below_threshold if isinstance(below_threshold, bool) else None,
        "windows": windows,
    }


def parse_subscription(payload: Any) -> dict[str, Any] | None:
    """Parse a subscription from the documented data envelope or one-item list."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        root = payload["data"]
    elif isinstance(payload, list):
        root = payload
    elif isinstance(payload, dict) and isinstance(payload.get("subscriptions"), list):
        root = payload["subscriptions"]
    else:
        return None
    if isinstance(root, list):
        root = next((item for item in root if isinstance(item, dict)), None)
    if not isinstance(root, dict):
        return None
    data = root.get("subscription") if isinstance(root.get("subscription"), dict) else root
    plan_id = text(data.get("planId") or data.get("plan_id") or data.get("plan"))
    status = text(data.get("status"))
    start_raw = data.get("currentPeriodStart") or data.get("current_period_start")
    start = parse_timestamp(start_raw)
    end = parse_timestamp(data.get("currentPeriodEnd") or data.get("current_period_end"))
    if not any((plan_id, status, start, end)):
        # A valid no-subscription response may contain only a typed data envelope.
        if payload == {"data": data}:
            return {
                "plan_id": None,
                "status": None,
                "period_start": None,
                "period_end": None,
                "period_start_raw": None,
            }
        return None
    return {
        "plan_id": plan_id,
        "status": status,
        "period_start": start,
        # Keep the provider's raw timestamp: the summary endpoint rejects the
        # ``+00:00`` form and only accepts the value it emitted itself.
        "period_start_raw": api_param(start_raw),
        "period_end": end,
    }


def parse_summary(payload: Any) -> dict[str, Any] | None:
    """Parse all recognized aggregate usage fields, allowing field-level gaps."""
    root = _unwrap_payload(payload)
    if isinstance(root, dict) and isinstance(root.get("summary"), dict):
        root = root["summary"]
    if not isinstance(root, dict):
        return None
    total_cost = number(root.get("totalCost", root.get("total_cost")))
    total_count = number(root.get("totalCount", root.get("total_count")))
    total_tokens = number(root.get("totalTokens", root.get("total_tokens", root.get("tokens"))))
    if all(value is None for value in (total_cost, total_count, total_tokens)):
        return None
    if total_cost is None or total_count is None:
        return None
    return {
        "total_cost": total_cost,
        "total_count": total_count,
        "total_tokens": total_tokens,
    }


def parse_whoami(payload: Any) -> dict[str, Any] | None:
    """Parse a stable organization-first billing identity from whoami."""
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is False:
        return None
    org = payload.get("org") if isinstance(payload.get("org"), dict) else {}
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    org_id = text(org.get("id"))
    user_id = text(user.get("id"))
    org_login = text(org.get("login"))
    user_login = text(user.get("userName")) or text(user.get("name"))
    login = org_login or user_login
    if not login:
        return None
    subject_type = "organization" if org_id else "user"
    subject_id = org_id or user_id or (login or "").lower()
    return {
        "login": login,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "org_id": org_id,
        "key_name": text(user.get("keyName")) or text(user.get("displayName")),
        "scope_key": f"{subject_type}:{subject_id}",
    }


def remaining_percent(window: dict[str, Any] | None) -> float | None:
    """Return the non-negative remaining percentage of a usage window."""
    if not window or window.get("percent") is None:
        return None
    return max(0.0, 100.0 - float(window["percent"]))


def window_elapsed_fraction(
    window: dict[str, Any] | None,
    now: datetime | None = None,
) -> float | None:
    """Return the elapsed fraction of a window, or None before its reset."""
    if not window or not window.get("resets_at"):
        return None
    total = WINDOW_SECONDS.get(str(window.get("key", "")))
    if not total:
        return None
    current = now or datetime.now(UTC)
    elapsed = total - (window["resets_at"] - current).total_seconds()
    if elapsed <= 0:
        return None
    return min(elapsed / total, 1.0)


def forecast_percent(
    window: dict[str, Any] | None,
    now: datetime | None = None,
) -> float | None:
    """Extrapolate current window usage linearly to the window end."""
    fraction = window_elapsed_fraction(window, now)
    if fraction is None or window is None or window.get("percent") is None:
        return None
    return round(float(window["percent"]) / fraction, 1)


def seconds_until_reset(
    window: dict[str, Any] | None,
    now: datetime | None = None,
) -> float | None:
    """Return seconds until reset, clamped at zero."""
    if not window or not window.get("resets_at"):
        return None
    current = now or datetime.now(UTC)
    return max((window["resets_at"] - current).total_seconds(), 0.0)


def burn_rate_per_hour(
    samples: list[tuple[datetime, float]] | None,
    now: datetime | None = None,
) -> float | None:
    """Return a stable %/h slope from the recent sample history."""
    if not samples or len(samples) < 2:
        return None
    current = now or datetime.now(UTC)
    recent = [
        item
        for item in sorted(samples, key=lambda item: item[0])
        if (current - item[0]).total_seconds() <= BURN_RATE_LOOKBACK_SECONDS
    ]
    if len(recent) < 2:
        return None
    first_ts, first_pct = recent[0]
    last_ts, last_pct = recent[-1]
    span = (last_ts - first_ts).total_seconds()
    if span < BURN_RATE_MIN_SPAN_SECONDS:
        return None
    rate = (last_pct - first_pct) / (span / 3600.0)
    return round(rate, 2) if rate >= 0 else None


def pace_status(
    forecast: float | None,
    green_below: float,
    red_above: float,
) -> str | None:
    """Classify a forecast without ever inverting the threshold band."""
    if forecast is None:
        return None
    red_above = max(red_above, green_below)
    if forecast < green_below:
        return "green"
    if forecast > red_above:
        return "red"
    return "yellow"


def usage_status(data: dict[str, Any] | None) -> str:
    """Resolve the canon usage status of the account scope from a snapshot.

    Canon parity (go_gauge ``UsagePercentSensor``): the usage state is ``None``
    on ``no_subscription``/``error`` instead of a string on a MEASUREMENT-%-
    sensor. CommandCode exposes the subscription only account-wide, so the
    account scope's status is derived from that section.
    """
    payload = data or {}
    subscription = payload.get("subscription")
    if not isinstance(subscription, dict):
        section = (payload.get("section_status") or {}).get("subscription") or {}
        return "error" if section.get("error_code") else "unknown"
    status = subscription.get("status")
    if not isinstance(status, str) or not status:
        return "unknown"
    return "ok" if status.lower() in ACTIVE_SUBSCRIPTION_STATUSES else "no_subscription"


API_STATUS_UNKNOWN = "unknown"
API_STATUS_VALUES = (
    "ok",
    "no_subscription",
    "rate_limited",
    "auth_error",
    "api_error",
    "unknown",
)


def api_status(data: dict[str, Any] | None) -> str:
    """Derive the canon ``api_status`` cause-of-failure from a snapshot.

    Canon §4: one per-scope enum that names *why* data may be missing, instead
    of a bare reachable yes/no. Precedence: a rejected key (401) is an
    ``auth_error``; a non-active subscription is ``no_subscription``; any other
    failed section is an ``api_error`` (transient/schema); a still-healthy API
    with an exceeded rolling window is ``rate_limited``; otherwise ``ok``.
    """
    payload = data or {}
    statuses = payload.get("section_status")
    if not isinstance(statuses, dict) or not statuses:
        return API_STATUS_UNKNOWN
    codes = {status.get("error_code") for status in statuses.values() if isinstance(status, dict)}
    codes.discard(None)
    if "http_401" in codes:
        return "auth_error"
    subscription = payload.get("subscription")
    if isinstance(subscription, dict):
        status = subscription.get("status")
        if (
            isinstance(status, str)
            and status
            and status.lower() not in ACTIVE_SUBSCRIPTION_STATUSES
        ):
            return "no_subscription"
    if codes:
        return "api_error"
    windows = (payload.get("credits") or {}).get("windows") or {}
    if any(isinstance(window, dict) and window.get("exceeded") for window in windows.values()):
        return "rate_limited"
    return "ok"


def synthesize_month_window(
    credits: dict[str, Any] | None,
    subscription: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Derive the canon ``month`` window from the plan's monthly credit grant.

    CommandCode has no rolling monthly window - ``windowLimits`` only ever
    carry ``fiveHour``/``weekly``. The monthly limit is the plan's credit
    grant per billing cycle, and ``/alpha/billing/credits`` exposes only the
    *remaining* ``monthlyCredits``; the grant itself is keyed by the
    subscription's ``planId`` (see ``const.PLAN_MONTHLY_CREDITS``, the same
    table the official ``command-code`` CLI uses). The canon ``month`` window
    is therefore *synthesized*:

      cap     = plan grant (USD)
      used    = max(0, cap - credits.monthly_credits)   # drawn from the grant
      reset   = subscription.period_end                 # billing-cycle reset
      percent = used / cap * 100

    ``credits.monthly_credits`` is a *remaining balance*, so it must never be
    used as the cap - doing so made the monthly percentage climb as the grant
    drained. Defensive: returns ``None`` (never a fake number) when the plan is
    unknown, the grant is non-positive, or the remaining monthly credit is
    missing.
    """
    if not isinstance(credits, dict) or not isinstance(subscription, dict):
        return None
    cap = plan_monthly_credits(subscription.get("plan_id"))
    remaining = credits.get("monthly_credits")
    if cap is None:
        return None
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) or remaining < 0:
        return None
    used = max(0.0, float(cap) - float(remaining))
    return {
        "used": used,
        "cap": float(cap),
        "remaining": float(remaining),
        "percent": round(used / cap * 100, 2),
        "resets_at": subscription.get("period_end"),
        "exceeded": used >= cap,
        "key": "month",
        "synthetic": True,
    }


def build_models_block(models: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Normalize a validated model catalog, or None for an unknown payload."""
    if models is None:
        return None
    normalized = []
    for model in models:
        if not isinstance(model, dict):
            return None
        model_id = text(model.get("id"))
        model_name = text(model.get("name"))
        context_length = number(model.get("context_length"))
        if not model_id or not model_name or context_length is None or context_length <= 0:
            return None
        normalized.append({"id": model_id, "name": model_name, "context_length": context_length})
    return {
        "models": normalized,
        "model_count": len(normalized),
        "models_updated_at": datetime.now(UTC).isoformat(),
    }


class CommandCodeApiClient:
    """Small async client for CommandCode's cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"ha-command-gauge/{INTEGRATION_VERSION}",
        }
        self._model_headers = {
            "Accept": "application/json",
            "User-Agent": f"ha-command-gauge/{INTEGRATION_VERSION}",
        }
        self._request_timeout = aiohttp.ClientTimeout(total=15)

    async def _get(
        self,
        path: str,
        *,
        authenticated: bool = True,
        **params: str | None,
    ) -> Any:
        async with self._session.get(
            build_url(self._base_url, path, **params),
            headers=self._headers if authenticated else self._model_headers,
            timeout=self._request_timeout,
        ) as response:
            if response.status >= 400:
                raise CommandCodeApiError(response.status, path)
            if response.status == 204:
                return None
            try:
                return await response.json(content_type=None)
            except Exception:  # noqa: BLE001 - malformed alpha payload is a section miss
                return None

    async def fetch_whoami(self) -> Any:
        return await self._get("/alpha/whoami")

    async def fetch_credits(self, org_id: str | None = None) -> Any:
        return await self._get("/alpha/billing/credits", orgId=org_id)

    async def fetch_subscription(self, org_id: str | None = None) -> Any:
        return await self._get("/alpha/billing/subscriptions", orgId=org_id)

    async def fetch_summary(
        self,
        org_id: str | None = None,
        since: str | None = None,
    ) -> Any:
        return await self._get(
            "/alpha/usage/summary",
            orgId=org_id,
            since=since,
        )

    async def fetch_models(self) -> list[dict[str, Any]] | None:
        """Return a recognized model list, or None for an unknown response shape."""
        payload = await self._get(MODELS_URL, authenticated=False)
        if not isinstance(payload, dict) or payload.get("object") != "list":
            raise UpdateFailed("Unrecognized models response")
        payload = payload.get("data")
        if not isinstance(payload, list) or not payload:
            raise UpdateFailed("Unrecognized models response")
        normalized: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise UpdateFailed("Unrecognized models response")
            model_id = text(item.get("id"))
            name = text(item.get("name"))
            context_length = number(item.get("context_length"))
            if not model_id or not name or context_length is None or context_length <= 0:
                raise UpdateFailed("Unrecognized models response")
            normalized.append(
                {
                    "id": model_id,
                    "name": name,
                    "context_length": context_length,
                }
            )
        return normalized


class CommandGaugeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll account data and models with independent, toggleable cycles."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        options: dict[str, Any] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        options = options or {}
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_BASE_URL
        self._client = CommandCodeApiClient(async_get_clientsession(hass), self.base_url, api_key)
        self.auto_usage = bool(options.get(CONF_AUTO_UPDATE_USAGE, True))
        self.usage_minutes = max(
            1,
            int(
                options.get(
                    CONF_USAGE_REFRESH_MINUTES,
                    DEFAULT_USAGE_REFRESH_MINUTES,
                )
            ),
        )
        self.auto_models = bool(options.get(CONF_AUTO_UPDATE_MODELS, True))
        self.models_minutes = max(
            1,
            int(
                options.get(
                    CONF_MODELS_REFRESH_MINUTES,
                    DEFAULT_MODELS_REFRESH_MINUTES,
                )
            ),
        )
        self.warn_percent = int(options.get(CONF_WARN_PERCENT, DEFAULT_WARN_PERCENT))
        self.pace_red_percent = int(options.get(CONF_PACE_RED_PERCENT, DEFAULT_PACE_RED_PERCENT))
        self.account_name = ""
        self._skip_reload = False
        self._force_refresh = True
        self.last_usage_fetch: datetime | None = None
        self.last_models_fetch: datetime | None = None
        self._usage_samples: dict[str, list[tuple[datetime, float]]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=self._effective_interval(),
        )

    def _effective_interval(self) -> timedelta | None:
        intervals: list[int] = []
        if self.auto_usage:
            intervals.append(self.usage_minutes * 60)
        if self.auto_models:
            intervals.append(self.models_minutes * 60)
        return timedelta(seconds=min(intervals)) if intervals else None

    def recalculate_interval(self) -> None:
        """Apply option changes to the coordinator's scheduled refresh."""
        self.update_interval = self._effective_interval()
        schedule = getattr(self, "_schedule_refresh", None)
        if callable(schedule):
            schedule()

    async def async_manual_refresh(self) -> None:
        """Force both independent cycles and wait for the update."""
        self._force_refresh = True
        await self.async_refresh()

    def log_self_check(self) -> None:
        """Log a one-line health summary of every section after startup.

        A restart should immediately show whether all CommandCode data sources
        answer - the whole reason a silent section failure used to be
        indistinguishable from "sensors stopped updating".
        """
        data = self.data or {}
        statuses = data.get("section_status") or {}
        parts: list[str] = []
        failures: list[str] = []
        for section in SECTION_KEYS:
            status = statuses.get(section)
            if not isinstance(status, dict):
                parts.append(f"{section}=n/a")
                continue
            code = status.get("error_code")
            parts.append(f"{section}={code or 'ok'}")
            if code:
                failures.append(f"{section}:{code}")
        line = "Command Gauge self-check: " + " ".join(parts)
        if failures:
            _LOGGER.warning("%s (%d failing)", line, len(failures))
        else:
            _LOGGER.info("%s", line)

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, CommandCodeApiError):
            return f"http_{error.status}"
        if isinstance(error, (TimeoutError, aiohttp.ClientError)):
            return "network"
        if isinstance(error, UpdateFailed):
            return "schema_unrecognized"
        return "unexpected"

    async def _async_update_data(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        previous = self.data or self.empty_data(
            self.auto_usage,
            self.usage_minutes,
            self.auto_models,
            self.models_minutes,
        )
        data = dict(previous)
        statuses = dict(previous.get("section_status") or {})
        force = self._force_refresh
        self._force_refresh = False

        # The failure record must reach the entities even when the whole
        # update aborts. Home Assistant assigns
        # `self.data = await self._async_update_data()` - so an exception
        # means the coordinator keeps its previous (possibly empty) snapshot
        # and every sensor silently reports "unknown" while the log shows a
        # perfectly clear "CommandCode rejected the API key". Publishing the
        # collected statuses before re-raising is what makes the UI explain
        # the outage instead of going quiet. Verified on HA 2026.9.1.
        try:
            return await self._async_fetch_all(data, statuses, now, force)
        except (ConfigEntryAuthFailed, UpdateFailed):
            self.data = {**data, "section_status": statuses}
            self.last_update_success = False
            raise

    @staticmethod
    def _section_status(
        available: bool,
        now: datetime,
        previous: dict[str, Any] | None = None,
        error: Exception | None = None,
        success: bool = False,
    ) -> dict[str, Any]:
        previous = previous or {}
        return {
            "available": available,
            "stale": bool(error and available),
            "http_status": error.status if isinstance(error, CommandCodeApiError) else None,
            "error_code": CommandGaugeCoordinator._error_code(error) if error else None,
            "last_attempt_at": now.isoformat(),
            "last_success_at": now.isoformat() if success else previous.get("last_success_at"),
        }

    def _record_failure(
        self,
        statuses: dict[str, Any],
        data: dict[str, Any],
        section: str,
        now: datetime,
        error: Exception,
    ) -> None:
        """Record a failed section and log the transition.

        Non-401 failures (network, 429/5xx, schema drift) do not abort the
        update: the section keeps its last known snapshot so the dashboard
        still shows something. That fallback used to be completely silent -
        ``last_update_success`` stayed True, the values froze and *nothing*
        reached the log, so a live outage looked like "sensors stopped
        updating" with no clue. Log the transition (once per error code, not
        every poll) so the cause is always visible.
        """
        previous = statuses.get(section)
        status = self._section_status(data.get(section) is not None, now, previous, error)
        statuses[section] = status
        if previous is None or previous.get("error_code") != status["error_code"]:
            http = status.get("http_status")
            _LOGGER.warning(
                "Command Gauge: %s section unavailable (%s%s) - keeping last known data",
                section,
                status["error_code"],
                f", HTTP {http}" if http else "",
            )

    @staticmethod
    def empty_data(
        auto_usage: bool = True,
        usage_minutes: int = DEFAULT_USAGE_REFRESH_MINUTES,
        auto_models: bool = True,
        models_minutes: int = DEFAULT_MODELS_REFRESH_MINUTES,
    ) -> dict[str, Any]:
        """Return the typed-by-convention empty snapshot used on first failure."""
        return {
            "fetched_at": None,
            "last_usage_fetch": None,
            "last_models_fetch": None,
            "account": None,
            "credits": None,
            "subscription": None,
            "summary": None,
            "models": None,
            "section_status": {},
            "unavailable": list(SECTION_KEYS),
            "auto_usage": auto_usage,
            "auto_models": auto_models,
            "usage_refresh_minutes": usage_minutes,
            "models_refresh_minutes": models_minutes,
        }

    @staticmethod
    def _raise_auth(error: Exception) -> None:
        if isinstance(error, CommandCodeApiError) and error.status in AUTH_STATUSES:
            raise ConfigEntryAuthFailed("CommandCode rejected the API key") from error

    async def _async_fetch_all(
        self,
        data: dict[str, Any],
        statuses: dict[str, Any],
        now: datetime,
        force: bool,
    ) -> dict[str, Any]:
        """Fetch every section, recording a per-section status as it goes.

        Raises ConfigEntryAuthFailed / UpdateFailed so the caller's
        fail-closed behaviour is unchanged; the collected statuses are
        published by _async_update_data before the exception continues.
        """
        identity: dict[str, Any] | None = None

        models_due = (
            force
            or self.last_models_fetch is None
            or (
                self.auto_models
                and now - self.last_models_fetch >= timedelta(minutes=self.models_minutes)
            )
        )
        # A disabled automatic model cycle must not retry an uninitialized fetch.
        models_due = models_due and (
            force or self.auto_models or self.last_models_fetch is not None
        )
        if models_due:
            try:
                raw_models = await self._client.fetch_models()
                models = build_models_block(raw_models)
                if models is None:
                    raise UpdateFailed("Unrecognized models response")
                data["models"] = models
                self.last_models_fetch = now
                statuses["models"] = self._section_status(True, now, success=True)
            except Exception as err:  # noqa: BLE001
                # Record the failure in section_status BEFORE raising the auth
                # error. _raise_auth() throws ConfigEntryAuthFailed, which
                # propagates out of _async_update_data without self.data ever
                # being assigned - the entity then kept reading the empty
                # snapshot (section_status={}) and reported "unknown" forever,
                # hiding the very error that had just been logged. Setting the
                # status first makes the sensor report the real cause even
                # while the entry is failing.
                self._record_failure(statuses, data, "models", now, err)
                self._raise_auth(err)

        usage_due = (
            force
            or self.last_usage_fetch is None
            or (
                self.auto_usage
                and now - self.last_usage_fetch >= timedelta(minutes=self.usage_minutes)
            )
        )
        if usage_due:
            identity = None
            try:
                identity = parse_whoami(await self._client.fetch_whoami())
                if identity is None:
                    raise UpdateFailed("CommandCode returned an unrecognized account response")
                data["account"] = identity
                statuses["account"] = self._section_status(True, now, success=True)
            except Exception as err:  # noqa: BLE001
                # Status first, then raise - see the models block above.
                self._record_failure(statuses, data, "account", now, err)
                self._raise_auth(err)

            if identity is not None:
                org_id = identity.get("org_id")
                credits_raw, subscription_raw = await asyncio.gather(
                    self._client.fetch_credits(org_id),
                    self._client.fetch_subscription(org_id),
                    return_exceptions=True,
                )
                for result, section, parser in (
                    (credits_raw, "credits", parse_credits),
                    (subscription_raw, "subscription", parse_subscription),
                ):
                    if isinstance(result, Exception):
                        # Record the real transport/HTTP failure and keep it:
                        # without the continue the parse branch below would
                        # overwrite the status with "schema_unrecognized" and
                        # mask the actual cause (e.g. http_500/network).
                        self._record_failure(statuses, data, section, now, result)
                        self._raise_auth(result)
                        continue
                    try:
                        parsed = parser(result)
                        if parsed is None:
                            raise UpdateFailed(f"Unrecognized {section} response")
                        data[section] = parsed
                        statuses[section] = self._section_status(True, now, success=True)
                    except Exception as err:  # noqa: BLE001
                        self._record_failure(statuses, data, section, now, err)
                        self._raise_auth(err)

                subscription = data.get("subscription") or {}
                old_period = (self.data or {}).get("subscription", {}).get("period_start")
                new_period = subscription.get("period_start")
                if new_period and old_period and new_period != old_period:
                    self._usage_samples.clear()
                since = subscription.get("period_start_raw") or iso_z(new_period)
                try:
                    try:
                        summary_raw = await self._client.fetch_summary(org_id, since)
                    except CommandCodeApiError as err:
                        # Degraded fallback: if the provider ever rejects our
                        # `since` value (validation error) the endpoint still
                        # returns the billing-period default when `since` is
                        # omitted, so the cost/request/token sensors survive a
                        # contract drift instead of going unavailable.
                        if since is not None and err.status in (400, 422):
                            _LOGGER.warning(
                                "Command Gauge: usage summary rejected since=%s (%s) "
                                "- retrying without it",
                                since,
                                err.status,
                            )
                            summary_raw = await self._client.fetch_summary(org_id, None)
                        else:
                            raise
                    summary = parse_summary(summary_raw)
                    if summary is None:
                        raise UpdateFailed("Unrecognized usage response")
                    data["summary"] = summary
                    statuses["usage"] = self._section_status(True, now, success=True)
                except Exception as err:  # noqa: BLE001
                    self._record_failure(statuses, data, "usage", now, err)
                    self._raise_auth(err)

                credits_block = data.get("credits")
                if (
                    isinstance(credits_block, dict)
                    and statuses.get("credits", {}).get("error_code") is None
                ):
                    # Canon month window: synthesized from the plan's monthly
                    # credit grant (no rolling monthly window in the API).
                    month_window = synthesize_month_window(
                        credits_block,
                        data.get("subscription"),
                    )
                    windows = credits_block.setdefault("windows", {})
                    if month_window is None:
                        windows.pop("month", None)
                    else:
                        windows["month"] = month_window
                    self._record_window_samples(credits_block, now)
            self.last_usage_fetch = now
            data["fetched_at"] = now.isoformat()

        if not any(data.get(key) is not None for key in SECTION_KEYS.values()):
            raise UpdateFailed("CommandCode returned no recognized account data")
        if identity is None and usage_due and data.get("models") is None:
            raise UpdateFailed("CommandCode returned no recognized account data")

        data["section_status"] = statuses
        data["unavailable"] = [
            section for section, key in SECTION_KEYS.items() if data.get(key) is None
        ]
        data["last_usage_fetch"] = (
            self.last_usage_fetch.isoformat() if self.last_usage_fetch else None
        )
        data["last_models_fetch"] = (
            self.last_models_fetch.isoformat() if self.last_models_fetch else None
        )
        data.update(
            {
                "auto_usage": self.auto_usage,
                "auto_models": self.auto_models,
                "usage_refresh_minutes": self.usage_minutes,
                "models_refresh_minutes": self.models_minutes,
            }
        )
        return data

    def _record_window_samples(
        self,
        credits: dict[str, Any],
        now: datetime,
    ) -> None:
        """Record bounded usage samples and reset them on a window rollover."""
        for key, window in credits.get("windows", {}).items():
            percent = window.get("percent")
            if not isinstance(percent, (int, float)):
                continue
            store = self._usage_samples.setdefault(key, [])
            if store and percent < store[-1][1]:
                store.clear()
            store.append((now, float(percent)))
            cutoff = now - timedelta(seconds=BURN_RATE_LOOKBACK_SECONDS)
            self._usage_samples[key] = [item for item in store if item[0] >= cutoff][-64:]
