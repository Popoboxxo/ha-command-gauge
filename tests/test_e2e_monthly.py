"""End-to-end monthly-window tests against realistic CommandCode alpha payloads.

Regression for the live defect in command_gauge 1.1.0: the monthly window was
synthesized with ``cap = credits.monthly_credits``, but ``/alpha/billing/credits``
returns the *remaining* monthly credit, not the grant (the grant lives in a plan
catalog keyed by the subscription's ``planId`` - the same model the official
``command-code`` CLI uses). Using the remaining balance as the cap made the
monthly percentage climb as the grant drained (nonsense values).

These tests do not touch internal helpers: they drive the real coordinator
(``_async_update_data``) with the exact payload shapes and then build every
sensor/binary-sensor through the real platform ``async_setup_entry``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.command_gauge import binary_sensor, sensor
from custom_components.command_gauge.const import DOMAIN, WINDOW_LABELS
from custom_components.command_gauge.coordinator import (
    CommandGaugeCoordinator,
)

NOW = datetime.now(UTC).replace(microsecond=0)
PERIOD_START = NOW - timedelta(days=12)
PERIOD_END = NOW + timedelta(days=18)

WHOAMI = {
    "org": {"id": "org-1", "login": "example-org"},
    "user": {"id": "user-1", "userName": "example-user"},
}
# /alpha/billing/credits: monthlyCredits is the REMAINING grant ($4 of $10 Go).
CREDITS = {
    "credits": {"monthlyCredits": 4.0, "purchasedCredits": 3.0, "freeCredits": 2.0},
    "windowLimits": {
        "fiveHour": {
            "used": 25,
            "cap": 100,
            "resetAt": int((NOW + timedelta(hours=2)).timestamp()),
        },
        "weekly": {
            "used": 40,
            "cap": 100,
            "resetAt": int((NOW + timedelta(days=3)).timestamp()),
        },
    },
}
# /alpha/billing/subscriptions: planId + billing period boundaries.
# The provider emits Z-suffixed UTC timestamps; the summary endpoint rejects
# the "+00:00" form, so the raw value must be forwarded verbatim.
SUBSCRIPTION = {
    "success": True,
    "data": {
        "planId": "individual-go",
        "status": "active",
        "currentPeriodStart": PERIOD_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "currentPeriodEnd": PERIOD_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
    },
}
# total_cost (30) is deliberately unrelated to grant - remaining (6).
SUMMARY = {"totalCost": 30.0, "totalCount": 12, "totalTokens": 500}
MODELS = [{"id": "deepseek-v4.1-flash", "name": "DeepSeek V4.1 Flash", "context_length": 1_000_000}]


def _coordinator() -> CommandGaugeCoordinator:
    with patch("custom_components.command_gauge.coordinator.DataUpdateCoordinator"):
        coord = CommandGaugeCoordinator.__new__(CommandGaugeCoordinator)
    coord.auto_usage = True
    coord.usage_minutes = 10
    coord.auto_models = True
    coord.models_minutes = 60
    coord._force_refresh = True
    coord._skip_reload = False
    coord._usage_samples = {}
    coord.last_models_fetch = None
    coord.last_usage_fetch = None
    coord.data = None  # type: ignore[assignment]
    coord.last_update_success = True
    coord.account_name = "Test"
    coord.warn_percent = 80
    coord.pace_red_percent = 100
    coord._client = MagicMock()
    coord._client.fetch_whoami = AsyncMock(return_value=WHOAMI)
    coord._client.fetch_credits = AsyncMock(return_value=CREDITS)
    coord._client.fetch_subscription = AsyncMock(return_value=SUBSCRIPTION)
    coord._client.fetch_summary = AsyncMock(return_value=SUMMARY)
    coord._client.fetch_models = AsyncMock(return_value=MODELS)
    return coord


def _entry():
    return MagicMock(
        entry_id="e1",
        unique_id="command_gauge_deadbeef",
        data={"account_name": "Test"},
        options={},
    )


def _run_update(coord) -> dict:
    coord.data = asyncio.run(coord._async_update_data())
    return coord.data


def _build_entities(coord):
    hass = MagicMock()
    hass.data = {DOMAIN: {"e1": coord}}
    entry = _entry()
    sensors: list = []
    binaries: list = []
    asyncio.run(sensor.async_setup_entry(hass, entry, sensors.extend))
    asyncio.run(binary_sensor.async_setup_entry(hass, entry, binaries.extend))
    return sensors, binaries


def test_month_window_uses_plan_grant_and_remaining_credits():
    coord = _coordinator()
    data = _run_update(coord)

    windows = data["credits"]["windows"]
    assert set(windows) == {"5h", "week", "month"}

    month = windows["month"]
    # Go plan grants $10; $4 remain -> $6 used -> 60%.
    assert month["cap"] == 10.0
    assert month["used"] == 6.0
    assert month["remaining"] == 4.0
    assert month["percent"] == 60.0
    assert month["exceeded"] is False
    assert month["resets_at"] == PERIOD_END


def test_summary_request_forwards_the_raw_provider_timestamp():
    """The summary 400s on the '+00:00' form; the raw 'Z' value must be sent."""
    coord = _coordinator()
    _run_update(coord)

    # fetch_summary(org_id, since) - the raw currentPeriodStart, not an isoformat.
    args, _ = coord._client.fetch_summary.await_args
    assert args[-1] == SUBSCRIPTION["data"]["currentPeriodStart"]
    assert args[-1].endswith("Z")
    assert "+00:00" not in args[-1]


def test_all_month_sensors_resolve_from_the_synthetic_window():
    coord = _coordinator()
    _run_update(coord)
    sensors, binaries = _build_entities(coord)

    assert len(sensors) == len(WINDOW_LABELS) * 7 + 10

    def month(cls, key="month"):
        return next(
            entity
            for entity in sensors
            if isinstance(entity, cls) and getattr(entity, "_key", None) == key
        )

    usage = month(sensor.WindowUsageSensor)
    assert usage.available is True
    assert usage.native_value == 60.0
    assert usage.extra_state_attributes["status"] == "ok"
    assert usage.extra_state_attributes["window"] == "month"

    remaining = month(sensor.WindowRemainingSensor)
    assert remaining.native_value == 40.0

    reset = month(sensor.WindowResetSensor)
    assert reset.native_value == PERIOD_END

    # 18 days until reset, in hours.
    time_to_reset = month(sensor.WindowTimeToResetSensor)
    assert time_to_reset.native_value == pytest.approx(18 * 24, abs=0.1)

    # 60% used 12 days into a 30-day window -> projected 150%.
    forecast = month(sensor.WindowForecastSensor)
    assert forecast.native_value == pytest.approx(150.0, abs=1.0)

    pace = month(sensor.WindowPaceSensor)
    assert pace.native_value == "red"

    limited = next(
        entity
        for entity in binaries
        if isinstance(entity, binary_sensor.RateLimitedSensor) and entity._key == "month"
    )
    assert limited.is_on is False

    status = next(entity for entity in sensors if isinstance(entity, sensor.ApiStatusSensor))
    assert status.available is True
    assert status.native_value == "ok"
    attrs = status.extra_state_attributes
    assert attrs["raw_status"] == "active"
    assert attrs["note"] is None
    assert attrs["last_update_success"] is True
    assert attrs["workspace_key"] == "command_gauge_deadbeef"


def test_month_window_survives_missing_billing_period_start():
    """The API only guarantees currentPeriodEnd; the window must not vanish."""
    coord = _coordinator()
    coord._client.fetch_subscription = AsyncMock(
        return_value={"success": True, "data": {"planId": "individual-goat", "status": "active"}}
    )
    coord._client.fetch_credits = AsyncMock(return_value={"credits": {"monthlyCredits": 35.0}})
    data = _run_update(coord)

    month = data["credits"]["windows"]["month"]
    assert month["cap"] == 70.0
    assert month["used"] == 35.0
    assert month["percent"] == 50.0
    assert month["resets_at"] is None

    sensors, _ = _build_entities(coord)

    def month(cls):
        return next(
            entity
            for entity in sensors
            if isinstance(entity, cls) and getattr(entity, "_key", None) == "month"
        )

    # Percentage-based sensors keep working without a reset timestamp.
    assert month(sensor.WindowUsageSensor).native_value == 50.0
    assert month(sensor.WindowRemainingSensor).native_value == 50.0
    # The reset-dependent ones degrade to unknown instead of faking a value.
    assert month(sensor.WindowResetSensor).native_value is None
    assert month(sensor.WindowForecastSensor).native_value is None
    assert month(sensor.WindowTimeToResetSensor).native_value is None


def test_unknown_plan_drops_the_month_window_instead_of_faking_numbers():
    coord = _coordinator()
    coord._client.fetch_subscription = AsyncMock(
        return_value={
            "success": True,
            "data": {
                "planId": "individual-mystery",
                "status": "active",
                "currentPeriodEnd": PERIOD_END.isoformat(),
            },
        }
    )
    data = _run_update(coord)
    assert "month" not in data["credits"]["windows"]

    sensors, _ = _build_entities(coord)
    usage = next(
        entity
        for entity in sensors
        if isinstance(entity, sensor.WindowUsageSensor) and entity._key == "month"
    )
    # The window is absent, so the entity reports unknown - never a fake number.
    assert usage.native_value is None
