"""Regression tests for the offline-pending ("save without validating") path.

Found on sandbox-120 (HA 2026.9.1): a config entry created with
skip_validation=True ended in state=setup_error with

    [homeassistant.config_entries] Config entry '...' for command_gauge
    integration could not authenticate: CommandCode rejected the API key

Root cause: config_flow stored CONF_OFFLINE_PENDING=True, but
async_setup_entry never read it and still ran
async_config_entry_first_refresh(), which raised ConfigEntryAuthFailed.
The checkbox was accepted by the form and then silently ignored.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.command_gauge import DOMAIN, async_setup_entry
from custom_components.command_gauge.const import (
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_OFFLINE_PENDING,
    DEFAULT_BASE_URL,
)


def _entry(offline_pending: bool | None) -> MagicMock:
    """Build a ConfigEntry fake with the given offline-pending state."""
    data: dict[str, object] = {
        CONF_ACCOUNT_NAME: "E2E Test",
        CONF_API_KEY: "e2e-invalid-key-for-error-path-test",
        CONF_BASE_URL: DEFAULT_BASE_URL,
    }
    if offline_pending is not None:
        data[CONF_OFFLINE_PENDING] = offline_pending
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = data
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    return hass


@pytest.mark.asyncio
async def test_offline_pending_skips_the_blocking_first_refresh() -> None:
    """skip_validation must survive the config flow into setup."""
    hass = _hass()
    entry = _entry(offline_pending=True)

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        coordinator = coordinator_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=AssertionError(
                "first refresh must not run for an offline-pending entry"
            )
        )
        assert await async_setup_entry(hass, entry) is True
        coordinator.async_config_entry_first_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_offline_pending_still_forwards_all_platforms() -> None:
    """Skipping validation must not silently skip the platforms."""
    hass = _hass()
    entry = _entry(offline_pending=True)

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        coordinator_cls.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry) is True
        forwarded = hass.config_entries.async_forward_entry_setups.await_args
        assert forwarded is not None
        assert forwarded.args[1] == ["sensor", "binary_sensor", "button", "switch", "number"]


@pytest.mark.asyncio
async def test_offline_pending_entry_is_registered_in_hass_data() -> None:
    """The coordinator is stored even without a successful first refresh."""
    hass = _hass()
    entry = _entry(offline_pending=True)

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        coordinator = coordinator_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry) is True
        assert hass.data[DOMAIN][entry.entry_id] is coordinator


@pytest.mark.asyncio
async def test_validated_entry_still_fails_closed_on_auth_error() -> None:
    """Without offline_pending the first refresh stays mandatory."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    hass = _hass()
    entry = _entry(offline_pending=False)

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        coordinator = coordinator_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=ConfigEntryAuthFailed
        )
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
        # A failed entry must not linger in hass.data.
        assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_entry_without_the_key_defaults_to_validating() -> None:
    """Entries written before offline_pending existed must keep validating.

    An absent key must not be read as "skip validation" - that would turn
    every legacy entry into an unauthenticated one.
    """
    from homeassistant.exceptions import ConfigEntryAuthFailed

    hass = _hass()
    entry = _entry(offline_pending=None)

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        coordinator = coordinator_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=ConfigEntryAuthFailed
        )
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
        coordinator.async_config_entry_first_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_invalid_base_url_still_blocks_even_when_offline_pending() -> None:
    """A malformed base URL is a typo, not a temporary outage."""
    from homeassistant.exceptions import ConfigEntryNotReady

    hass = _hass()
    entry = _entry(offline_pending=True)
    entry.data[CONF_BASE_URL] = "ftp://not-allowed.example"

    with patch(
        "custom_components.command_gauge.CommandGaugeCoordinator"
    ) as coordinator_cls:
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
        coordinator_cls.assert_not_called()
