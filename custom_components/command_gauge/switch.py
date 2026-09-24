"""Switches for automatic CommandCode updates."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_AUTO_UPDATE_MODELS, CONF_AUTO_UPDATE_USAGE, DOMAIN
from .entity import CommandGaugeEntityBase, persist_options


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create independent usage and model auto-update switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UsageAutoSwitch(coordinator, entry), ModelsAutoSwitch(coordinator, entry)])


class _AutoSwitch(CommandGaugeEntityBase, SwitchEntity):
    _option = ""
    _attr_icon = "mdi:autorenew"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._option}"

    @property
    def is_on(self) -> bool:
        if self._option == CONF_AUTO_UPDATE_USAGE:
            return self.coordinator.auto_usage
        if self._option == CONF_AUTO_UPDATE_MODELS:
            return self.coordinator.auto_models
        return bool((self.coordinator.data or {}).get(self._option, True))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        if self._option == CONF_AUTO_UPDATE_USAGE:
            self.coordinator.auto_usage = value
        elif self._option == CONF_AUTO_UPDATE_MODELS:
            self.coordinator.auto_models = value
        persist_options(
            self.hass,
            self._entry,
            self.coordinator,
            **{self._option: value},
        )
        self.coordinator.async_set_updated_data(
            {**(self.coordinator.data or {}), self._option: value}
        )
        self.coordinator.recalculate_interval()


class UsageAutoSwitch(_AutoSwitch):
    _option = CONF_AUTO_UPDATE_USAGE
    _attr_translation_key = "auto_usage"


class ModelsAutoSwitch(_AutoSwitch):
    _option = CONF_AUTO_UPDATE_MODELS
    _attr_translation_key = "auto_models"
