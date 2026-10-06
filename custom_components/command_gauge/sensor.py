"""Command Gauge sensor platform."""

from __future__ import annotations

import json
from datetime import datetime
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
    usage_status,
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
            ModelCatalogSensor(coordinator, entry),
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
    """Percent usage of one account window.

    Canon parity (go_gauge ``UsagePercentSensor``): on ``no_subscription`` or
    ``error`` the state is ``None`` (never a string - current HA rejects a
    string state on a MEASUREMENT-% sensor). The cause stays visible through
    the ``mdi:shield-off-outline`` icon and the ``status``/``note`` attributes.
    """

    _attr_translation_key = "usage"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry, key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_percent"

    def _status(self) -> str:
        return usage_status(self.coordinator.data)

    @property
    def native_value(self) -> float | None:
        if self._status() in ("no_subscription", "error"):
            return None
        window = self._window(self._key)
        percent = window.get("percent") if window else None
        return float(percent) if percent is not None else None

    @property
    def icon(self) -> str:
        """Shield-off while the subscription is missing, else the speedometer."""
        if self._status() == "no_subscription":
            return "mdi:shield-off-outline"
        return "mdi:speedometer"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self._window(self._key)
        reset = window.get("resets_at") if window else None
        subscription = (self.coordinator.data or {}).get("subscription") or {}
        return {
            "workspace_key": self.scope_key,
            "window": self._key,
            "status": self._status(),
            "note": subscription.get("status") if isinstance(subscription, dict) else None,
            "resets_at_iso": reset.isoformat() if isinstance(reset, datetime) else None,
        }


class WindowResetSensor(_WindowSensor):
    _attr_translation_key = "reset"
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
    _attr_translation_key = "forecast"
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
    _attr_translation_key = "pace"

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

    @property
    def icon(self) -> str:
        """Traffic-light icon matching the current pace status."""
        return {
            "green": "mdi:check-circle-outline",
            "yellow": "mdi:alert-circle-outline",
            "red": "mdi:close-circle-outline",
        }.get(self.native_value or "", "mdi:speedometer-medium")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the forecast and the thresholds behind the status."""
        return {
            "forecast_percent": forecast_percent(self._window(self._key)),
            "green_below": self.coordinator.warn_percent,
            "red_above": self.coordinator.pace_red_percent,
        }


class WindowRemainingSensor(_WindowSensor):
    _attr_translation_key = "remaining"
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
    _attr_translation_key = "time_to_reset"
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
    _attr_translation_key = "burn_rate"
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


class ModelCatalogSensor(CommandGaugeEntityBase, SensorEntity):
    """ONE sensor carries the whole model catalog as dynamic JSON attributes.

    Canon ``model_catalog``. CommandCode's ``/provider/v1/models`` delivers only
    id/name/context_length (no pricing/live/free metadata), so the live/
    cheapest/free canon attributes stay API-blocked (canon CG-C1/CG-C2); the
    catalog itself is fully represented here.
    """

    _section = "models"
    _attr_translation_key = "model_catalog"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_model_catalog"

    @property
    def native_value(self) -> int | None:
        models = (self.coordinator.data or {}).get("models") or {}
        count = models.get("model_count")
        return int(count) if count is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        models = (self.coordinator.data or {}).get("models") or {}
        entries = models.get("models") or []
        return {
            "count": len(entries),
            "catalog_json": json.dumps(entries, ensure_ascii=False),
            "models_updated_at": models.get("models_updated_at"),
        }
