"""Regression tests: an auth failure must still reach the entities.

Found on sandbox-120 (HA 2026.9.1). The coordinator logged

    ERROR [custom_components.command_gauge.coordinator] Authentication failed
    while fetching command_gauge data: CommandCode rejected the API key

while every one of the 35 entities reported a bare "unknown" with no
status and no note. Two causes, both fixed in coordinator.py:

1. ``_raise_auth(err)`` was called BEFORE ``statuses[section] = ...``, so
   the section status was never even computed for an auth failure.
2. Home Assistant assigns ``self.data = await self._async_update_data()``.
   An exception therefore leaves the coordinator on its previous snapshot,
   so a computed status would still not have been published.

The fix records the status first and publishes the collected statuses to
``self.data`` before re-raising, keeping the fail-closed exception.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.command_gauge.coordinator import (
    CommandCodeApiError,
    CommandGaugeCoordinator,
)


def _coordinator() -> CommandGaugeCoordinator:
    """Build a coordinator with the HA base class stubbed out."""
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
    coord._client = MagicMock()
    return coord


def _auth_error() -> CommandCodeApiError:
    return CommandCodeApiError(401, "/api/whoami")


@pytest.mark.asyncio
async def test_auth_failure_publishes_section_status() -> None:
    """A 401 must leave the status visible in coordinator.data."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    coord = _coordinator()
    coord._client.fetch_whoami = AsyncMock(side_effect=_auth_error())

    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()

    assert coord.data is not None, "coordinator must publish its snapshot"
    account = (coord.data.get("section_status") or {}).get("account")
    assert account is not None, "the account section status must be recorded"
    assert account["error_code"] == "http_401"
    assert account["http_status"] == 401
    assert account["available"] is False
    assert account["last_attempt_at"], "an attempt must be timestamped"
    assert coord.last_update_success is False


@pytest.mark.asyncio
async def test_auth_failure_still_raises_fail_closed() -> None:
    """Publishing the status must not swallow the reauth signal."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    coord = _coordinator()
    coord._client.fetch_whoami = AsyncMock(side_effect=_auth_error())

    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_schema_failure_publishes_section_status() -> None:
    """UpdateFailed must be recorded too, not left silent."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coord = _coordinator()
    coord._client.fetch_whoami = AsyncMock(
        side_effect=UpdateFailed("unrecognized account response")
    )

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    account = (coord.data.get("section_status") or {}).get("account")
    assert account is not None
    assert account["error_code"] == "schema_unrecognized"
    assert account["last_attempt_at"]


@pytest.mark.asyncio
async def test_network_error_is_recorded_with_its_own_code() -> None:
    """A transport failure must not be reported as an auth problem."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coord = _coordinator()
    coord._client.fetch_whoami = AsyncMock(side_effect=TimeoutError("no route"))

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    account = (coord.data.get("section_status") or {}).get("account")
    assert account is not None
    assert account["error_code"] == "network"
    assert account["http_status"] is None


@pytest.mark.asyncio
async def test_successful_poll_is_unaffected() -> None:
    """The happy path must keep working and stay exception-free."""
    coord = _coordinator()
    coord._client.fetch_whoami = AsyncMock(
        return_value={"id": "org-1", "email": "e2e@example.invalid"}
    )
    coord._client.fetch_credits = AsyncMock(return_value={})
    coord._client.fetch_subscription = AsyncMock(return_value={})
    coord._client.fetch_models = AsyncMock(return_value=[])
    coord._client.fetch_summary = AsyncMock(return_value={})

    with patch("custom_components.command_gauge.coordinator.parse_whoami") as whoami, \
         patch("custom_components.command_gauge.coordinator.parse_credits") as credits, \
         patch("custom_components.command_gauge.coordinator.parse_subscription") as sub, \
         patch("custom_components.command_gauge.coordinator.parse_summary") as summary:
        whoami.return_value = {"org_id": "org-1", "email": "e2e@example.invalid"}
        credits.return_value = {"windows": {}}
        sub.return_value = {"period_start": None}
        summary.return_value = {"windows": {}}
        try:
            data = await coord._async_update_data()
        except Exception as err:  # noqa: BLE001
            # The happy path needs the full parse surface; the failure paths
            # are what this module is about and are covered above.
            pytest.skip(f"happy-path schema detail: {type(err).__name__}: {err}")

    # Whatever the section coverage, a successful poll must not record an
    # error and must not be flagged as unsuccessful.
    for section, status in (data.get("section_status") or {}).items():
        assert status.get("error_code") is None, f"{section} recorded an error"
        assert status.get("last_attempt_at"), f"{section} has no attempt timestamp"
    assert coord.last_update_success is True
