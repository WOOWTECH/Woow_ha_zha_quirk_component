"""Load climate.py without a Home Assistant install.

This repository ships ZHA quirks, not a Home Assistant development environment, and
climate.py is the only module with logic worth testing in isolation. Rather than pull in
homeassistant (and pytest-homeassistant-custom-component) for one file, the handful of
Home Assistant names climate.py imports are stubbed here.

The stubs are deliberately dumb: enums, string constants and empty base classes. Nothing
under test lives in them -- _recompute(), _state(), _raw() and available are entirely our
own code, and they only ever touch hass.states.get() and the DeviceSpec dataclass.

climate.py is loaded straight from its path so that custom_components/woow_zha_quirks/
__init__.py (which pulls in the whole integration) never runs.
"""

from __future__ import annotations

import enum
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIMATE_PY = REPO_ROOT / "custom_components" / "woow_zha_quirks" / "climate.py"


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _HVACMode(enum.StrEnum):
    OFF = "off"
    COOL = "cool"
    HEAT = "heat"
    FAN_ONLY = "fan_only"


class _HVACAction(enum.StrEnum):
    OFF = "off"
    COOLING = "cooling"
    HEATING = "heating"
    FAN = "fan"
    IDLE = "idle"


class _ClimateEntityFeature(enum.IntFlag):
    TARGET_TEMPERATURE = 1
    FAN_MODE = 8
    PRESET_MODE = 16
    TURN_OFF = 128
    TURN_ON = 256


class _UnitOfTemperature(enum.StrEnum):
    CELSIUS = "\N{DEGREE SIGN}C"


def _install_stubs() -> None:
    def passthrough(func):
        return func

    def noop(*_args, **_kwargs):
        return lambda: None

    def slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")

    _module("homeassistant")
    _module("homeassistant.components")
    _module(
        "homeassistant.components.climate",
        # available defaults to True, as homeassistant.helpers.entity.Entity does -- that
        # default is precisely the behaviour the availability tests exist to reject.
        ClimateEntity=type("ClimateEntity", (), {"available": True}),
        ClimateEntityFeature=_ClimateEntityFeature,
    )
    _module(
        "homeassistant.components.climate.const",
        ATTR_HVAC_MODE="hvac_mode",
        HVACAction=_HVACAction,
        HVACMode=_HVACMode,
    )
    _module(
        "homeassistant.const",
        ATTR_ENTITY_ID="entity_id",
        ATTR_TEMPERATURE="temperature",
        SERVICE_TURN_OFF="turn_off",
        SERVICE_TURN_ON="turn_on",
        STATE_ON="on",
        STATE_UNAVAILABLE="unavailable",
        STATE_UNKNOWN="unknown",
        UnitOfTemperature=_UnitOfTemperature,
    )
    _module(
        "homeassistant.core",
        Event=type("Event", (), {}),
        HomeAssistant=type("HomeAssistant", (), {}),
        callback=passthrough,
    )
    _module("homeassistant.helpers")
    _module(
        "homeassistant.helpers.device_registry",
        CONNECTION_ZIGBEE="zigbee",
        EVENT_DEVICE_REGISTRY_UPDATED="device_registry_updated",
        async_get=noop,
    )
    _module(
        "homeassistant.helpers.entity_registry",
        EVENT_ENTITY_REGISTRY_UPDATED="entity_registry_updated",
        RegistryEntry=type("RegistryEntry", (), {}),
        RegistryEntryDisabler=enum.Enum("RegistryEntryDisabler", {"DEVICE": "device"}),
        RegistryEntryHider=enum.Enum("RegistryEntryHider", {"INTEGRATION": "integration"}),
        EntityRegistry=type("EntityRegistry", (), {}),
        async_entries_for_device=noop,
        async_get=noop,
    )
    _module(
        "homeassistant.helpers.event",
        async_track_state_change_event=noop,
        async_track_time_interval=noop,
    )
    _module(
        "homeassistant.helpers.restore_state",
        RestoreEntity=type("RestoreEntity", (), {}),
    )
    _module("homeassistant.helpers.start", async_at_start=noop)
    _module("homeassistant.helpers.typing", ConfigType=dict, DiscoveryInfoType=dict)
    _module("homeassistant.util", slugify=slugify)


@pytest.fixture(scope="session")
def climate_module():
    """The real climate.py, loaded against the stubs above."""
    _install_stubs()
    spec = importlib.util.spec_from_file_location("woow_climate_under_test", CLIMATE_PY)
    module = importlib.util.module_from_spec(spec)
    # Register before executing: climate.py uses `from __future__ import annotations`, so
    # @dataclass resolves its field types by looking the module up in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeState:
    """Just enough of homeassistant.core.State for _raw()."""

    def __init__(self, state: str) -> None:
        self.state = state


class FakeStates:
    """A state machine where an entity can be present, absent, or explicitly unavailable."""

    def __init__(self) -> None:
        self._states: dict[str, FakeState] = {}

    def get(self, entity_id: str) -> FakeState | None:
        return self._states.get(entity_id)

    def set(self, entity_id: str, state: str) -> None:
        self._states[entity_id] = FakeState(state)

    def remove(self, entity_id: str) -> None:
        """Take the entity out of the state machine entirely -- ZHA rebuilding it."""
        self._states.pop(entity_id, None)


class FakeHass:
    def __init__(self) -> None:
        self.states = FakeStates()
