"""Binary sensors for CommandCode account health and windows."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, WINDOW_LABELS
from .entity import CommandGaugeEntityBase


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create connectivity, subscription, credit, and limit sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AccountReachableSensor(coordinator, entry),
            SubscriptionActiveSensor(coordinator, entry),
            CreditsBelowThresholdSensor(coordinator, entry),
            *[WindowExceededSensor(coordinator, entry, key) for key in WINDOW_LABELS],
        ]
    )


class AccountReachableSensor(CommandGaugeEntityBase, BinarySensorEntity):
    _section = "account"
    _attr_translation_key = "account_reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_account_reachable"

    @property
    def is_on(self) -> bool | None:
        status = ((self.coordinator.data or {}).get("section_status") or {}).get("account")
        if not isinstance(status, dict) or status.get("last_attempt_at") is None:
            return None
        if status.get("error_code") is not None:
            return False
        return bool(status.get("available"))

    @property
    def available(self) -> bool:
        """Always report connectivity state, including an unreachable API."""
        return True


class SubscriptionActiveSensor(CommandGaugeEntityBase, BinarySensorEntity):
    _section = "subscription"
    _attr_translation_key = "subscription_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_subscription_active"

    @property
    def is_on(self) -> bool | None:
        subscription = (self.coordinator.data or {}).get("subscription") or {}
        status = subscription.get("status")
        if not isinstance(status, str) or not status:
            return None
        return status.lower() in {
            "active",
            "trialing",
            "paid",
        }


class CreditsBelowThresholdSensor(CommandGaugeEntityBase, BinarySensorEntity):
    _section = "credits"
    _attr_translation_key = "credits_below_threshold"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_credits_below_threshold"

    @property
    def is_on(self) -> bool | None:
        credits = (self.coordinator.data or {}).get("credits") or {}
        value = credits.get("below_threshold")
        return value if isinstance(value, bool) else None


class WindowExceededSensor(CommandGaugeEntityBase, BinarySensorEntity):
    _section = "credits"
    _attr_translation_key = "window_exceeded"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_exceeded"
        self._attr_translation_placeholders = {"window": WINDOW_LABELS.get(key, key)}

    @property
    def is_on(self) -> bool | None:
        window = self._window(self._key)
        if not window or not isinstance(window.get("exceeded"), bool):
            return None
        return window["exceeded"]
