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
    migrate_unique_id,
    validate_base_url,
)
from .coordinator import CommandGaugeCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "binary_sensor", "button", "switch", "number"]

# Config-entry schema version. v2 = Gauge Entity Canon v1.1 convergence.
MIGRATION_VERSION = 2


def _unique_id_migration_callback(registry_entry: object) -> dict[str, str] | None:
    """Map a legacy entity-registry unique_id to its canon suffix (v2).

    Only the trailing suffix token changes (``usage`` -> ``percent`` etc.);
    the entry is updated in place by HA, so entity_id and recorded history
    stay intact. Returns ``None`` when nothing needs to migrate (idempotent).
    """
    current = getattr(registry_entry, "unique_id", None)
    target = migrate_unique_id(current)
    if target is None:
        return None
    return {"new_unique_id": target}


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rewrite legacy unique_id suffixes in the entity registry (v2).

    Returns ``False`` on failure so the caller keeps the old version and HA
    retries on the next start (no silent half-migration).
    """
    try:
        from homeassistant.helpers.entity_registry import async_migrate_entries

        await async_migrate_entries(hass, entry.entry_id, _unique_id_migration_callback)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Command Gauge: unique_id migration for %s failed (%s) - "
            "ids stay unchanged, retried on the next start",
            entry.entry_id,
            err,
        )
        return False
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to the current schema version (VERSION = 2).

    v1 -> v2: Gauge Entity Canon v1.1 convergence. Legacy unique_id suffixes
    are rewritten to the canon suffixes in the entity registry
    (``_usage`` -> ``_percent``, ``_exceeded`` -> ``_limited``,
    ``_models`` -> ``_model_catalog``, ``_account_reachable`` ->
    ``_api_reachable``). The registry entry itself is preserved, so the
    entity_id and its history/statistics survive.
    """
    if entry.version > MIGRATION_VERSION:
        return False

    if entry.version < MIGRATION_VERSION:
        _LOGGER.info(
            "Command Gauge: migrating config entry %s from version %s to %s",
            entry.entry_id,
            entry.version,
            MIGRATION_VERSION,
        )
        if not await _async_migrate_unique_ids(hass, entry):
            _LOGGER.warning(
                "Command Gauge: migration for %s incomplete - entry stays on "
                "version %s, HA retries on the next start",
                entry.entry_id,
                entry.version,
            )
            return False
        hass.config_entries.async_update_entry(entry, version=MIGRATION_VERSION)
    return True


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
