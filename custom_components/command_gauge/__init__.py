"""Command Gauge setup and platform forwarding."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import (
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_BASE_URL,
    DEFAULT_BASE_URL,
    DOMAIN,
    validate_base_url,
)
from .coordinator import CommandGaugeCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "button", "switch", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one CommandCode account and forward all entity platforms."""
    api_key = str(entry.data.get(CONF_API_KEY) or "")
    base_url = str(entry.data.get(CONF_BASE_URL) or DEFAULT_BASE_URL)
    try:
        base_url = validate_base_url(base_url)
    except ValueError as err:
        _LOGGER.error("Command Gauge rejected an invalid API base URL")
        raise ConfigEntryNotReady("Invalid CommandCode API base URL") from err
    coordinator = CommandGaugeCoordinator(
        hass,
        api_key,
        dict(entry.options),
        base_url,
        config_entry=entry,
    )
    coordinator.account_name = (
        str(entry.data.get(CONF_ACCOUNT_NAME) or "CommandCode").strip() or "CommandCode"
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    except ConfigEntryNotReady:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    except Exception as err:
        _LOGGER.error("Command Gauge initial refresh failed: %s", type(err).__name__)
        raise

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after Options/Reauth/Reconfigure changes, except live writes."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and getattr(coordinator, "_skip_reload", False):
        coordinator._skip_reload = False
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and remove the per-entry coordinator."""
    domain_data = hass.data.get(DOMAIN)
    coordinator = domain_data.get(entry.entry_id) if domain_data is not None else None
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    if coordinator is not None:
        await coordinator.async_shutdown()
    if domain_data is not None:
        domain_data.pop(entry.entry_id, None)
        if not domain_data:
            hass.data.pop(DOMAIN, None)
    return True
