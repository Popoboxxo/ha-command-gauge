"""Tests for redaction, endpoint contract, and entity availability."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import conftest  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "command_gauge"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"command_gauge.{name}", COMPONENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


const = load("const")
coordinator = load("coordinator")
entity = load("entity")
binary_sensor = load("binary_sensor")
diagnostics = load("diagnostics")


def test_diagnostics_redact_secret_shaped_data_and_url_query():
    hass = MagicMock()
    hass.data = {
        const.DOMAIN: {
            "e1": MagicMock(
                data={
                    "account": {"login": "user", "scope_key": "organization:org"},
                    "section_status": {"account": {"error_code": "network"}},
                    "token": "never-export",
                }
            )
        }
    }
    entry = MagicMock(
        entry_id="e1",
        data={
            "account_name": "Test",
            "api_key": "real-secret-never-export",
            "base_url": "https://api.example.test/path?token=leak",
        },
        options={"access_token": "never-export"},
    )
    result = asyncio.run(diagnostics.async_get_config_entry_diagnostics(hass, entry))
    encoded = json.dumps(result)
    assert "real-secret-never-export" not in encoded
    assert "never-export" not in encoded
    assert "Bearer abc123" not in encoded
    assert result["entry"]["data"]["api_key_fingerprint"] == const.token_fingerprint(
        "real-secret-never-export"
    )
    assert result["entry"]["data"]["base_url"] == "https://api.example.test/path"
    assert result["coordinator"]["account"]["scope_fingerprint"]


def test_missing_credit_component_stays_unknown_not_zero():
    result = coordinator.parse_credits({"credits": {"monthlyCredits": 10}})
    assert result is not None
    assert result["monthly_credits"] == 10
    assert result["purchased_credits"] is None
    assert result["free_credits"] is None
    assert result["remaining_credits"] is None


def test_section_entities_follow_global_failure() -> None:
    coordinator_stub = MagicMock()
    coordinator_stub.data = {"credits": {"monthly_credits": 1}, "unavailable": []}
    coordinator_stub.last_update_success = False
    entry = MagicMock(entry_id="e1", data={"account_name": "Test"}, options={})
    sensor = binary_sensor.CreditsBelowThresholdSensor(coordinator_stub, entry)
    assert sensor.available is False


def test_reachability_entity_is_available_when_account_is_unavailable():
    coordinator_stub = MagicMock()
    coordinator_stub.data = {"account": None, "unavailable": ["account"]}
    entry = MagicMock(entry_id="e1", data={"account_name": "Test"}, options={})
    sensor = binary_sensor.AccountReachableSensor(coordinator_stub, entry)
    assert sensor.available is True
    assert sensor.is_on is None
