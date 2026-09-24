"""Number entities for CommandCode refresh and warning thresholds."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MODELS_REFRESH_MINUTES,
    CONF_PACE_RED_PERCENT,
    CONF_USAGE_REFRESH_MINUTES,
    CONF_WARN_PERCENT,
    DEFAULT_MODELS_REFRESH_MINUTES,
    DEFAULT_PACE_RED_PERCENT,
    DEFAULT_USAGE_REFRESH_MINUTES,
    DEFAULT_WARN_PERCENT,
    DOMAIN,
)
from .entity import CommandGaugeEntityBase, persist_options


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create live refresh and threshold controls."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            UsageIntervalNumber(coordinator, entry),
            ModelsIntervalNumber(coordinator, entry),
            WarnPercentNumber(coordinator, entry),
            PaceRedPercentNumber(coordinator, entry),
        ]
    )


class _SettingsNumber(CommandGaugeEntityBase, NumberEntity):
    _option = ""
    _minimum = 1
    _maximum = 1440
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._option}"
        self._attr_native_min_value = self._minimum
        self._attr_native_max_value = self._maximum

    @property
    def native_value(self) -> float:
        data = self.coordinator.data or {}
        return float(data.get(self._option, self._default_value()))

    def _default_value(self) -> int:
        raise NotImplementedError

    async def async_set_native_value(self, value: float) -> None:
        ivalue = int(value)
        if not self._minimum <= ivalue <= self._maximum:
            raise ValueError("value is outside the supported range")
        if self._option == CONF_USAGE_REFRESH_MINUTES:
            self.coordinator.usage_minutes = ivalue
        elif self._option == CONF_MODELS_REFRESH_MINUTES:
            self.coordinator.models_minutes = ivalue
        elif self._option == CONF_WARN_PERCENT:
            self.coordinator.warn_percent = ivalue
        elif self._option == CONF_PACE_RED_PERCENT:
            self.coordinator.pace_red_percent = ivalue
        persist_options(
            self.hass,
            self._entry,
            self.coordinator,
            **{self._option: ivalue},
        )
        self.coordinator.async_set_updated_data(
            {**(self.coordinator.data or {}), self._option: ivalue}
        )
        self.coordinator.recalculate_interval()
        self.async_write_ha_state()


class UsageIntervalNumber(_SettingsNumber):
    _option = CONF_USAGE_REFRESH_MINUTES
    _minimum = 5
    _attr_translation_key = "usage_refresh_minutes"
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer-refresh"

    def _default_value(self) -> int:
        return DEFAULT_USAGE_REFRESH_MINUTES


class ModelsIntervalNumber(_SettingsNumber):
    _option = CONF_MODELS_REFRESH_MINUTES
    _minimum = 60
    _attr_translation_key = "models_refresh_minutes"
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer-refresh-outline"

    def _default_value(self) -> int:
        return DEFAULT_MODELS_REFRESH_MINUTES


class WarnPercentNumber(_SettingsNumber):
    _option = CONF_WARN_PERCENT
    _minimum = 1
    _maximum = 100
    _attr_translation_key = "warn_percent"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:alert"

    def _default_value(self) -> int:
        return DEFAULT_WARN_PERCENT


class PaceRedPercentNumber(_SettingsNumber):
    _option = CONF_PACE_RED_PERCENT
    _minimum = 1
    _maximum = 1000
    _attr_translation_key = "pace_red_percent"
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:alert-circle-outline"

    def _default_value(self) -> int:
        return DEFAULT_PACE_RED_PERCENT
