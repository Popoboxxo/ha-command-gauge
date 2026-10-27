"""Canon 1.8.0 entity-category policy for the settings platforms."""

from __future__ import annotations

from custom_components.command_gauge import button, number, switch


def test_settings_numbers_are_config() -> None:
    for cls in (
        number.UsageIntervalNumber,
        number.ModelsIntervalNumber,
        number.WarnPercentNumber,
        number.PaceRedPercentNumber,
    ):
        assert cls._attr_entity_category == "config", cls.__name__


def test_auto_update_switches_are_config() -> None:
    for cls in (switch.UsageAutoSwitch, switch.ModelsAutoSwitch):
        assert cls._attr_entity_category == "config", cls.__name__


def test_refresh_button_stays_primary() -> None:
    assert getattr(button.RefreshButton, "_attr_entity_category", None) is None
