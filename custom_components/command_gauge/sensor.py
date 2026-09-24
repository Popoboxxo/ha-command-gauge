"""Command Gauge sensor platform."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, WINDOW_LABELS
from .coordinator import (
    CommandGaugeCoordinator,
    burn_rate_per_hour,
    forecast_percent,
    pace_status,
    remaining_percent,
    seconds_until_reset,
)
from .entity import CommandGaugeEntityBase


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all credit, window, summary, plan, and catalog sensors."""
    coordinator: CommandGaugeCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for key in WINDOW_LABELS:
        entities.extend(
            [
                WindowUsageSensor(coordinator, entry, key),
                WindowResetSensor(coordinator, entry, key),
                WindowForecastSensor(coordinator, entry, key),
                WindowPaceSensor(coordinator, entry, key),
                WindowRemainingSensor(coordinator, entry, key),
                WindowTimeToResetSensor(coordinator, entry, key),
                WindowBurnRateSensor(coordinator, entry, key),
            ]
        )
    entities.extend(
        [
            MonthlyCreditsSensor(coordinator, entry),
            PurchasedCreditsSensor(coordinator, entry),
            FreeCreditsSensor(coordinator, entry),
            TotalCreditsSensor(coordinator, entry),
            TotalCostSensor(coordinator, entry),
            RequestCountSensor(coordinator, entry),
            TokenCountSensor(coordinator, entry),
            PlanSensor(coordinator, entry),
            ModelsSensor(coordinator, entry),
        ]
    )
    async_add_entities(entities)


class _CreditsSensor(CommandGaugeEntityBase, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "USD"
    _section = "credits"
    _key = ""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        return (data.get("credits") or {}).get(self._key)


class MonthlyCreditsSensor(_CreditsSensor):
    _attr_icon = "mdi:calendar-month"
    _key = "monthly_credits"
    _attr_translation_key = "monthly_credits"


class PurchasedCreditsSensor(_CreditsSensor):
    _attr_icon = "mdi:shopping"
    _key = "purchased_credits"
    _attr_translation_key = "purchased_credits"


class FreeCreditsSensor(_CreditsSensor):
    _attr_icon = "mdi:gift-outline"
    _key = "free_credits"
    _attr_translation_key = "free_credits"


class TotalCreditsSensor(_CreditsSensor):
    _attr_icon = "mdi:wallet"
    _key = "remaining_credits"
    _attr_translation_key = "remaining_credits"


class _WindowSensor(CommandGaugeEntityBase, SensorEntity):
    _section = "credits"
    _attr_translation_placeholders: dict[str, str]

    def __init__(self, coordinator, entry, key: str):
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_translation_placeholders = {"window": WINDOW_LABELS.get(key, key)}


class WindowUsageSensor(_WindowSensor):
    _attr_translation_key = "window_usage"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_usage"

    @property
    def native_value(self) -> float | None:
        window = self._window(self._key)
        percent = window.get("percent") if window else None
        return float(percent) if percent is not None else None


class WindowResetSensor(_WindowSensor):
    _attr_translation_key = "window_reset"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-reset"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_reset"

    @property
    def native_value(self):
        window = self._window(self._key)
        return window.get("resets_at") if window else None


class WindowForecastSensor(_WindowSensor):
    _attr_translation_key = "window_forecast"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:trending-up"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_forecast"

    @property
    def native_value(self) -> float | None:
        return forecast_percent(self._window(self._key))


class WindowPaceSensor(_WindowSensor):
    _attr_translation_key = "window_pace"
    _attr_icon = "mdi:speedometer-medium"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_pace"

    @property
    def native_value(self) -> str | None:
        return pace_status(
            forecast_percent(self._window(self._key)),
            self.coordinator.warn_percent,
            self.coordinator.pace_red_percent,
        )


class WindowRemainingSensor(_WindowSensor):
    _attr_translation_key = "window_remaining"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_remaining"

    @property
    def native_value(self) -> float | None:
        return remaining_percent(self._window(self._key))


class WindowTimeToResetSensor(_WindowSensor):
    _attr_translation_key = "window_time_to_reset"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_time_to_reset"

    @property
    def native_value(self) -> float | None:
        seconds = seconds_until_reset(self._window(self._key))
        return seconds / 3600 if seconds is not None else None


class WindowBurnRateSensor(_WindowSensor):
    _attr_translation_key = "window_burn_rate"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%/h"
    _attr_icon = "mdi:fire"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_burn_rate"

    @property
    def native_value(self) -> float | None:
        return burn_rate_per_hour(self.coordinator._usage_samples.get(self._key, []))


class _SummarySensor(CommandGaugeEntityBase, SensorEntity):
    _section = "usage"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def native_value(self) -> float | None:
        return ((self.coordinator.data or {}).get("summary") or {}).get(self._key)


class TotalCostSensor(_SummarySensor):
    _attr_translation_key = "total_cost"
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_cost")


class RequestCountSensor(_SummarySensor):
    _attr_translation_key = "request_count"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_count")


class TokenCountSensor(_SummarySensor):
    _attr_translation_key = "token_count"
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_tokens")


class PlanSensor(CommandGaugeEntityBase, SensorEntity):
    _section = "subscription"
    _attr_translation_key = "plan"
    _attr_icon = "mdi:shield-account-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_plan"

    @property
    def native_value(self) -> str | None:
        return ((self.coordinator.data or {}).get("subscription") or {}).get("plan_id")


class ModelsSensor(CommandGaugeEntityBase, SensorEntity):
    _section = "models"
    _attr_translation_key = "models"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_models"

    @property
    def native_value(self) -> int | None:
        models = (self.coordinator.data or {}).get("models") or {}
        count = models.get("model_count")
        return int(count) if count is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        models = (self.coordinator.data or {}).get("models") or {}
        return {
            "catalog_json": json.dumps(models.get("models") or [], ensure_ascii=False),
            "models_updated_at": models.get("models_updated_at"),
        }
