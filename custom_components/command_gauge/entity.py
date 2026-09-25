"""Shared entity base and runtime option persistence for Command Gauge."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import CommandGaugeCoordinator


class CommandGaugeEntityBase(CoordinatorEntity):
    """Common device, availability, and data access for all platforms."""

    _attr_has_entity_name = True
    coordinator: CommandGaugeCoordinator
    _section: str | None = None

    def __init__(self, coordinator: CommandGaugeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        account_name = coordinator.account_name or entry.data.get("account_name") or "CommandCode"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Command Gauge {account_name}",
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def available(self) -> bool:
        """Preserve section availability while respecting global coordinator health."""
        if self._section is None:
            return True
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data or {}
        return self._section not in data.get("unavailable", [])

    def _window(self, key: str) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        credits = data.get("credits") or {}
        windows = credits.get("windows") or {}
        return windows.get(key)


def persist_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: CommandGaugeCoordinator,
    **changes: Any,
) -> bool:
    """Persist a live option without forcing an unnecessary entry reload."""
    coordinator._skip_reload = True
    changed = hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, **changes},
    )
    if not changed:
        coordinator._skip_reload = False
    return changed
