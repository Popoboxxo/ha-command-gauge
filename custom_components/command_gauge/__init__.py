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
    CONF_OFFLINE_PENDING,
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
    # "Save without validating" (skip_validation) must survive into setup,
    # not just the config flow. Without this the checkbox silently loses:
    # the flow stores CONF_OFFLINE_PENDING=True, but the first refresh below
    # still authenticated and raised ConfigEntryAuthFailed - so the entry
    # ended in setup_error and the user's explicit "don't validate" was
    # ignored. Only an offline-pending entry skips the blocking first
    # refresh; everything else keeps the fail-closed behaviour.
    offline_pending = bool(entry.data.get(CONF_OFFLINE_PENDING, False))
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
    if offline_pending:
        # The user explicitly chose "save without validating" (e.g. the API
        # is temporarily unreachable). Do NOT block setup on a first
        # refresh - the coordinator still runs on its normal update
        # interval and will surface the real state as soon as the API
        # answers. Entities come up unavailable instead of the whole entry
        # failing with setup_error.
        _LOGGER.info(
            "Command Gauge entry set up without validation "
            "(offline_pending); waiting for the first successful update"
        )
    else:
        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryAuthFailed:
            hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
            raise
        except ConfigEntryNotReady:
            hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
            raise
        except Exception as err:
            _LOGGER.error(
                "Command Gauge initial refresh failed: %s", type(err).__name__
            )
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
