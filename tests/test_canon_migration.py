"""Tests for the v1 -> v2 Gauge Entity Canon convergence migration."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import conftest  # noqa: F401
import pytest

from custom_components.command_gauge import (
    MIGRATION_VERSION,
    _unique_id_migration_callback,
    async_migrate_entry,
)
from custom_components.command_gauge.const import migrate_unique_id

REGISTRY_MODULE = "homeassistant.helpers.entity_registry"


def _install_registry(monkeypatch, unique_ids, applied):
    """Install a fake entity_registry whose migration applies our callback."""
    module = types.ModuleType(REGISTRY_MODULE)

    async def async_migrate_entries(hass, entry_id, callback):
        for unique_id in unique_ids:
            result = callback(types.SimpleNamespace(unique_id=unique_id))
            if result is not None:
                applied.append(result)

    module.async_migrate_entries = async_migrate_entries
    monkeypatch.setitem(sys.modules, REGISTRY_MODULE, module)
    monkeypatch.setattr(
        sys.modules["homeassistant.helpers"], "entity_registry", module, raising=False
    )


def test_migrate_unique_id_maps_legacy_suffixes():
    assert migrate_unique_id("e1_5h_usage") == "e1_5h_percent"
    assert migrate_unique_id("e1_5h_exceeded") == "e1_5h_limited"
    assert migrate_unique_id("e1_models") == "e1_model_catalog"
    assert migrate_unique_id("e1_account_reachable") == "e1_api_reachable"
    # Already canonical or unrelated ids stay untouched.
    assert migrate_unique_id("e1_5h_pace") is None
    assert migrate_unique_id("e1_5h_percent") is None
    assert migrate_unique_id(None) is None


def test_callback_only_rewrites_legacy_ids():
    assert _unique_id_migration_callback(types.SimpleNamespace(unique_id="e1_week_usage")) == {
        "new_unique_id": "e1_week_percent"
    }
    assert _unique_id_migration_callback(types.SimpleNamespace(unique_id="e1_week_percent")) is None


@pytest.mark.asyncio
async def test_migration_advances_version_and_rewrites_ids(monkeypatch):
    applied: list[dict[str, str]] = []
    _install_registry(monkeypatch, ["e1_5h_usage", "e1_5h_pace"], applied)
    entry = MagicMock(version=1, entry_id="e1", unique_id="command_gauge_deadbeef")
    hass = MagicMock()

    assert await async_migrate_entry(hass, entry) is True
    hass.config_entries.async_update_entry.assert_called_once_with(entry, version=MIGRATION_VERSION)
    assert applied == [{"new_unique_id": "e1_5h_percent"}]


@pytest.mark.asyncio
async def test_migration_keeps_version_when_registry_pass_fails(monkeypatch):
    module = types.ModuleType(REGISTRY_MODULE)

    async def boom(*args, **kwargs):
        raise RuntimeError("registry unavailable")

    module.async_migrate_entries = boom
    monkeypatch.setitem(sys.modules, REGISTRY_MODULE, module)
    monkeypatch.setattr(
        sys.modules["homeassistant.helpers"], "entity_registry", module, raising=False
    )
    entry = MagicMock(version=1, entry_id="e1")
    hass = MagicMock()

    assert await async_migrate_entry(hass, entry) is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_current_entry_is_a_noop():
    entry = MagicMock(version=MIGRATION_VERSION, entry_id="e1")
    hass = MagicMock()

    assert await async_migrate_entry(hass, entry) is True
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_future_entry_version_is_rejected():
    entry = MagicMock(version=MIGRATION_VERSION + 1, entry_id="e1")
    hass = MagicMock()

    assert await async_migrate_entry(hass, entry) is False
