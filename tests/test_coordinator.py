"""Tests for CommandCode response parsing and derived gauge values."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import conftest  # noqa: F401 - installs offline HA stubs
import pytest

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "command_gauge"


def load(name: str):
    path = BASE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"command_gauge.{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


const = load("const")
coordinator = load("coordinator")


def test_build_url_omits_empty_params_and_preserves_org_id():
    assert const.build_url("https://example.test/", "/x", a="1", b=None) == (
        "https://example.test/x?a=1"
    )
    assert const.build_url("https://api.test", "/credits", orgId="org-1") == (
        "https://api.test/credits?orgId=org-1"
    )


def test_api_key_unique_id_is_stable_and_hashed():
    first = const.api_key_unique_id("secret-token")
    assert first == const.api_key_unique_id("secret-token")
    assert "secret" not in first
    assert const.token_fingerprint("secret-token") == const.token_fingerprint("secret-token")


def test_account_unique_id_uses_organization_scope_first():
    account = {"scope_key": "organization:org-42"}
    assert const.account_unique_id(account) == const.account_unique_id(
        {"scope_key": "organization:org-42"}
    )
    assert const.account_unique_id(account) != const.account_unique_id({"scope_key": "user:org-42"})


def test_parse_timestamp_accepts_epoch_iso_and_milliseconds():
    now = datetime.now(UTC).replace(microsecond=0)
    assert coordinator.parse_timestamp(int(now.timestamp())) == now
    assert coordinator.parse_timestamp(now.isoformat()) == now
    assert coordinator.parse_timestamp(int(now.timestamp() * 1000)) == now
    assert coordinator.parse_timestamp("not-a-date") is None


def test_parse_credits_and_windows():
    reset = datetime.now(UTC) + timedelta(hours=2)
    payload = {
        "credits": {
            "monthlyCredits": 20,
            "purchasedCredits": 3,
            "freeCredits": 2,
            "belowThreshold": True,
        },
        "windowLimits": {
            "fiveHour": {
                "used": 25,
                "cap": 100,
                "resetAt": int(reset.timestamp()),
                "exceeded": False,
            },
            "weekly": {
                "used": 40,
                "cap": 100,
                "resetAt": int((reset + timedelta(days=2)).timestamp()),
            },
        },
    }
    result = coordinator.parse_credits(payload)
    assert result is not None
    assert result["remaining_credits"] == 25
    assert result["windows"]["5h"]["percent"] == 25
    assert result["windows"]["5h"]["key"] == "5h"


def test_parse_credits_does_not_turn_missing_values_into_success():
    assert coordinator.parse_credits({"credits": {}}) is None
    assert coordinator.parse_credits({}) is None
    assert (
        coordinator.parse_credits({"credits": {"monthlyCredits": 0}})["remaining_credits"] is None
    )


def test_parse_whoami_prefers_organization_identity():
    account = coordinator.parse_whoami(
        {
            "org": {"id": "org-1", "login": "example-org"},
            "user": {"id": "user-1", "userName": "example-user"},
        }
    )
    assert account is not None
    assert account["org_id"] == "org-1"
    assert account["scope_key"] == "organization:org-1"
    assert account["login"] == "example-org"


def test_whoami_requires_login_and_rejects_success_false() -> None:
    assert coordinator.parse_whoami({"org": {"id": "org-1"}}) is None
    assert (
        coordinator.parse_whoami({"success": False, "org": {"id": "org-1", "login": "x"}}) is None
    )


def test_credit_threshold_is_preserved() -> None:
    result = coordinator.parse_credits({"credits": {"monthlyCredits": 1, "creditThreshold": 2}})
    assert result is not None
    assert result["credit_threshold"] == 2


def test_parse_summary_is_defensive():
    assert coordinator.parse_summary({"totalCost": "1.5", "totalCount": 4}) is None
    assert coordinator.parse_summary({"totalCost": 1}) is None
    assert coordinator.parse_summary({"totalCost": 1, "totalCount": 4, "totalTokens": 0}) == {
        "total_cost": 1.0,
        "total_count": 4.0,
        "total_tokens": 0.0,
    }


def test_forecast_and_reset_values():
    now = datetime.now(UTC)
    window = {"key": "5h", "percent": 50, "resets_at": now + timedelta(hours=2)}
    assert coordinator.forecast_percent(window, now) == pytest.approx(83.3)
    assert coordinator.seconds_until_reset(window, now) == pytest.approx(7200)


def test_burn_rate_requires_two_distant_samples():
    now = datetime.now(UTC)
    assert coordinator.burn_rate_per_hour([(now, 1)], now) is None
    assert coordinator.burn_rate_per_hour(
        [(now - timedelta(hours=1), 10), (now, 20)], now
    ) == pytest.approx(10)
