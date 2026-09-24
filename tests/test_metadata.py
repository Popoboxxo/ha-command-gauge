"""Tests for Command Gauge integration metadata and manifest wiring."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "command_gauge"


def test_hacs_manifest_and_platforms_are_present():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert hacs["name"] == "Command Gauge"
    assert hacs["render_readme"] is True
    assert manifest["domain"] == "command_gauge"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
    for name in ("sensor", "binary_sensor", "button", "switch", "number"):
        assert (COMPONENT / f"{name}.py").is_file()


def test_translations_are_valid_and_have_config_flow_keys():
    for locale in ("en", "de"):
        data = json.loads((COMPONENT / "translations" / f"{locale}.json").read_text())
        assert data["config"]["step"]["user"]["data"]["api_key"]
        assert data["config"]["step"]["reauth_confirm"]["data"]["api_key"]
        assert data["config"]["step"]["reconfigure"]["data"]["api_key"]
        assert data["options"]["step"]["init"]["data"]["usage_refresh_minutes"]
        expected = {
            "sensor": {
                "monthly_credits",
                "purchased_credits",
                "free_credits",
                "remaining_credits",
                "window_usage",
                "window_reset",
                "window_forecast",
                "window_pace",
                "window_remaining",
                "window_time_to_reset",
                "window_burn_rate",
                "total_cost",
                "request_count",
                "token_count",
                "plan",
                "models",
            },
            "binary_sensor": {
                "account_reachable",
                "subscription_active",
                "credits_below_threshold",
                "window_exceeded",
            },
            "number": {
                "usage_refresh_minutes",
                "models_refresh_minutes",
                "warn_percent",
                "pace_red_percent",
            },
            "button": {"refresh"},
            "switch": {"auto_usage", "auto_models"},
        }
        for domain, keys in expected.items():
            assert set(data["entity"][domain]) == keys
        for key in (
            "forbidden",
            "invalid_base_url",
        ):
            assert data["config"]["error"][key]
        for key in (
            "reauth_failed",
            "reconfigure_failed",
        ):
            assert data["config"]["abort"][key]
        for key in (
            "window_usage",
            "window_reset",
            "window_forecast",
            "window_pace",
            "window_remaining",
            "window_time_to_reset",
            "window_burn_rate",
        ):
            assert "{window}" in data["entity"]["sensor"][key]["name"]
        assert "{window}" in data["entity"]["binary_sensor"]["window_exceeded"]["name"]


def test_manifest_and_project_version_are_consistent():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    project = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{manifest["version"]}"' in project
