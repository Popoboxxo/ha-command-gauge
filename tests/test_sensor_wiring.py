"""Test entity setup wires each window to its own data."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import conftest  # noqa: F401

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "command_gauge"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"command_gauge.{name}", BASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


const = load("const")
load("coordinator")
load("entity")
sensor = load("sensor")


def test_sensor_platform_creates_windows_and_credits():
    coordinator = MagicMock()
    coordinator.data = {
        "credits": {
            "monthly_credits": 10,
            "purchased_credits": 2,
            "free_credits": 1,
            "remaining_credits": 13,
            "windows": {
                "5h": {"key": "5h", "percent": 12},
                "week": {"key": "week", "percent": 40},
            },
        },
        "summary": {"total_cost": 3.5, "total_count": 8, "total_tokens": 100},
    }
    entry = MagicMock(entry_id="e1", data={"account_name": "Test"}, options={})
    hass = MagicMock()
    hass.data = {const.DOMAIN: {"e1": coordinator}}
    added = []
    asyncio.run(sensor.async_setup_entry(hass, entry, added.extend))
    assert len(added) == 30
    usage = [entity for entity in added if isinstance(entity, sensor.WindowUsageSensor)]
    assert {entity._key: entity.native_value for entity in usage} == {
        "5h": 12.0,
        "week": 40.0,
        "month": None,
    }
    assert all(entity._attr_unique_id.startswith("e1_") for entity in added)


def test_pace_sensor_icon_and_attributes_follow_status():
    """Parity with go_gauge: traffic-light icon + threshold attributes."""
    from datetime import UTC, datetime, timedelta

    coordinator = MagicMock()
    coordinator.warn_percent = 80
    coordinator.pace_red_percent = 100
    coordinator.data = {
        "credits": {
            "windows": {
                "5h": {
                    "key": "5h",
                    "percent": 10,
                    "resets_at": datetime.now(UTC) + timedelta(hours=1),
                },
            },
        },
    }
    entry = MagicMock(entry_id="e1", data={"account_name": "Test"}, options={})
    pace = sensor.WindowPaceSensor(coordinator, entry, "5h")

    assert pace.native_value == "green"
    assert pace.icon == "mdi:check-circle-outline"

    attrs = pace.extra_state_attributes
    assert attrs["green_below"] == 80
    assert attrs["red_above"] == 100
    # 10% used with 4 of 5 hours elapsed extrapolates to ~12.5% - safely green.
    assert attrs["forecast_percent"] is not None
    assert abs(attrs["forecast_percent"] - 12.5) < 0.2


def test_pace_sensor_icon_defaults_when_status_unknown():
    coordinator = MagicMock()
    coordinator.warn_percent = 80
    coordinator.pace_red_percent = 100
    coordinator.data = {"credits": {"windows": {}}}
    entry = MagicMock(entry_id="e1", data={"account_name": "Test"}, options={})
    pace = sensor.WindowPaceSensor(coordinator, entry, "5h")

    assert pace.native_value is None
    assert pace.icon == "mdi:speedometer-medium"
    assert pace.extra_state_attributes["forecast_percent"] is None


def test_usage_workspace_key_is_hashed_not_raw_scope():
    """The canon workspace_key must not leak the raw provider org id."""
    coordinator = MagicMock()
    coordinator.data = {
        "subscription": {"status": "active"},
        "credits": {"windows": {"5h": {"key": "5h", "percent": 10}}},
    }
    entry = MagicMock(
        entry_id="e1",
        unique_id="command_gauge_deadbeef",
        data={"account_name": "Test", "account_scope_key": "organization:secret-org"},
        options={},
    )
    usage = sensor.WindowUsageSensor(coordinator, entry, "5h")

    attrs = usage.extra_state_attributes
    assert attrs["workspace_key"] == "command_gauge_deadbeef"
    assert "secret-org" not in attrs["workspace_key"]
    assert attrs["window"] == "5h"
    assert attrs["status"] == "ok"
    assert usage.native_value == 10.0
    assert usage.icon == "mdi:speedometer"


def test_usage_is_none_without_subscription():
    coordinator = MagicMock()
    coordinator.data = {
        "subscription": {"status": "canceled"},
        "credits": {"windows": {"5h": {"key": "5h", "percent": 42}}},
    }
    entry = MagicMock(entry_id="e1", unique_id="command_gauge_x", data={}, options={})
    usage = sensor.WindowUsageSensor(coordinator, entry, "5h")

    assert usage.native_value is None
    assert usage.icon == "mdi:shield-off-outline"
    assert usage.extra_state_attributes["status"] == "no_subscription"
