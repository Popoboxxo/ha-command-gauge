"""Shared Home Assistant module fakes for offline unit tests."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock


class FlexibleModule(types.ModuleType):
    """Module whose missing attributes become harmless fake classes."""

    def __getattr__(self, name: str) -> Any:
        value = type(name, (), {})
        setattr(self, name, value)
        return value


class ConfigFlowStub:
    """Small subset of ConfigFlow used by offline tests."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    @property
    def source(self) -> str:
        return "user"

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "abort", **kwargs}

    def _abort_if_unique_id_configured(self) -> None:
        return None

    async def async_set_unique_id(self, unique_id: str) -> None:
        self.unique_id = unique_id


class OptionsFlowStub:
    """Small subset of OptionsFlow used by offline tests."""

    @property
    def config_entry(self):
        return getattr(self, "_config_entry", None)


class CoordinatorStub:
    """Minimal coordinator contract for entity constructors."""

    __class_getitem__ = classmethod(lambda cls, item: cls)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.data = None
        self.last_update_success = True
        self.async_set_updated_data = MagicMock()
        self.async_add_listener = MagicMock(return_value=lambda: None)

    async def async_config_entry_first_refresh(self) -> None:
        return None


class CoordinatorEntityStub:
    """Minimal CoordinatorEntity contract for entity constructors."""

    def __init__(self, coordinator, context=None) -> None:
        self.coordinator = coordinator
        self.coordinator_context = context

    def __class_getitem__(cls, item):
        return cls

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success)


class ConfigEntryStub:
    """Config entry shape used by the fake Home Assistant modules."""

    entry_id = "e1"
    data = {}
    options = {}
    unique_id = None

    def add_update_listener(self, listener):
        return lambda: None


class HomeAssistantStub:
    """Home Assistant shape used by setup tests."""

    def __init__(self) -> None:
        self.data = {}
        self.config_entries = MagicMock()


class HomeAssistantRuntimeStub(HomeAssistantStub):
    """Runtime HA stub whose coordinator registration can be asserted."""

    def __init__(self) -> None:
        super().__init__()
        self.config_entries.async_forward_entry_setups = MagicMock(return_value=None)
        self.config_entries.async_on_unload = MagicMock(return_value=None)
        self.config_entries.async_unload_platforms = MagicMock(return_value=True)


class TextSelectorStub:
    """Stand-in for Home Assistant's text selector."""

    def __init__(self, config=None) -> None:
        self.config = config or {}

    def __call__(self, value):
        return value


class SelectorConfigStub:
    """Stand-in for selector configuration values."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def install_ha_stubs() -> None:
    """Install deterministic fake Home Assistant modules for offline tests."""
    fake_modules = {
        "homeassistant",
        "homeassistant.core",
        "homeassistant.config_entries",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.selector",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.binary_sensor",
        "homeassistant.components.button",
        "homeassistant.components.number",
        "homeassistant.components.switch",
    }
    for name in fake_modules:
        sys.modules.setdefault(name, FlexibleModule(name))
    sys.modules["homeassistant"].__path__ = []
    for name in fake_modules:
        parent_name, _, leaf = name.rpartition(".")
        if parent_name:
            setattr(sys.modules[parent_name], leaf, sys.modules[name])

    config_entries = sys.modules["homeassistant.config_entries"]
    config_entries.ConfigFlow = ConfigFlowStub
    config_entries.ConfigFlowResult = dict
    config_entries.ConfigEntry = ConfigEntryStub
    config_entries.ConfigEntries = MagicMock()
    config_entries.OptionsFlow = OptionsFlowStub

    core = sys.modules["homeassistant.core"]
    core.HomeAssistant = HomeAssistantStub
    core.callback = lambda function: function

    exceptions = sys.modules["homeassistant.exceptions"]
    exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})

    update_coordinator = sys.modules["homeassistant.helpers.update_coordinator"]
    update_coordinator.DataUpdateCoordinator = CoordinatorStub
    update_coordinator.CoordinatorEntity = CoordinatorEntityStub
    update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})

    aiohttp_client = sys.modules["homeassistant.helpers.aiohttp_client"]
    aiohttp_client.async_get_clientsession = lambda hass: None

    selector = sys.modules["homeassistant.helpers.selector"]
    selector.TextSelector = TextSelectorStub
    selector.TextSelectorConfig = SelectorConfigStub

    def make_enum(*names: str) -> type:
        return type("EnumStub", (), {name: name.lower() for name in names})

    sensor = sys.modules["homeassistant.components.sensor"]
    sensor.SensorStateClass = make_enum("MEASUREMENT")
    sensor.SensorDeviceClass = make_enum("TIMESTAMP", "DURATION")

    binary_sensor = sys.modules["homeassistant.components.binary_sensor"]
    binary_sensor.BinarySensorDeviceClass = make_enum("CONNECTIVITY", "RUNNING", "PROBLEM")

    number = sys.modules["homeassistant.components.number"]
    number.NumberMode = make_enum("BOX")


def config_entry(
    entry_id: str = "e1",
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> ConfigEntryStub:
    """Create a small ConfigEntry test double."""
    return type(
        "Entry",
        (ConfigEntryStub,),
        {
            "entry_id": entry_id,
            "data": dict(data or {}),
            "options": dict(options or {}),
        },
    )()


def install_fake_aiohttp(session: Any) -> None:
    """Install a fake aiohttp module for a single isolated client test."""
    module = types.ModuleType("aiohttp")
    module.ClientError = type("ClientError", (Exception,), {})
    module.ClientResponseError = type("ClientResponseError", (Exception,), {})
    module.ClientTimeout = MagicMock
    module.ContentTypeError = type("ContentTypeError", (Exception,), {})
    sys.modules["aiohttp"] = module


install_ha_stubs()
