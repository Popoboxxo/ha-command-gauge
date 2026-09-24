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
    assert len(added) == 23
    usage = [entity for entity in added if isinstance(entity, sensor.WindowUsageSensor)]
    assert {entity._key: entity.native_value for entity in usage} == {
        "5h": 12.0,
        "week": 40.0,
    }
    assert all(entity._attr_unique_id.startswith("e1_") for entity in added)
