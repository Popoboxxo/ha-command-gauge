"""Binary sensors for CommandCode account health and windows."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIVE_SUBSCRIPTION_STATUSES, DOMAIN, WINDOW_LABELS
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
            ApiReachableSensor(coordinator, entry),
            SubscriptionActiveSensor(coordinator, entry),
            CreditsBelowThresholdSensor(coordinator, entry),
            *[RateLimitedSensor(coordinator, entry, key) for key in WINDOW_LABELS],
        ]
    )


class ApiReachableSensor(CommandGaugeEntityBase, BinarySensorEntity):
    """ON while the CommandCode API delivers fresh account data."""

    _section = "account"
    _attr_translation_key = "api_reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_api_reachable"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.last_update_success and bool(
            (self.coordinator.data or {}).get("fetched_at")
        )

    @property
    def available(self) -> bool:
        """Always report connectivity state, including an unreachable API."""
        return True


class SubscriptionActiveSensor(CommandGaugeEntityBase, BinarySensorEntity):
    """ON when the account has an active subscription.

    Canon: no device_class (CONNECTIVITY rendered as "disconnected" and was
    misread as an API outage - connection is owned by ``api_reachable``).
    """

    _section = "subscription"
    _attr_translation_key = "subscription_active"
    _attr_icon = "mdi:shield-check-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_subscription_active"

    def _status(self) -> str | None:
        subscription = (self.coordinator.data or {}).get("subscription") or {}
        status = subscription.get("status")
        return status if isinstance(status, str) and status else None

    @property
    def is_on(self) -> bool | None:
        status = self._status()
        if status is None:
            return None
        return status.lower() in ACTIVE_SUBSCRIPTION_STATUSES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"workspace_key": self.scope_key, "note": self._status()}


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


class RateLimitedSensor(CommandGaugeEntityBase, BinarySensorEntity):
    """ON when CommandCode reports the window limit as exceeded (rate-limited)."""

    _section = "credits"
    _attr_translation_key = "rate_limited"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:block-helper"

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}_limited"
        self._attr_translation_placeholders = {"window": WINDOW_LABELS.get(key, key)}

    @property
    def is_on(self) -> bool | None:
        window = self._window(self._key)
        if not window or not isinstance(window.get("exceeded"), bool):
            return None
        return window["exceeded"]

    @property
    def available(self) -> bool:
        """Unavailable (not OFF) when no subscription is active or data is stale."""
        subscription = (self.coordinator.data or {}).get("subscription") or {}
        status = subscription.get("status")
        if (
            isinstance(status, str)
            and status
            and status.lower() not in ACTIVE_SUBSCRIPTION_STATUSES
        ):
            return False
        return super().available
