"""ZHA Quirk for Tuya TS0502B CCT (Color Temperature) LED Light.

Device info:
  - Model:        TS0502B
  - Manufacturer: _TZ3000_yeygk4hw
  - Chip:         Silicon Labs EFR32MG24
  - IEEE:         40:30:59:ff:fe:55:96:96
  - Type:         CCT dimmable light (2500-6500K)

This is a standard ZCL color-temperature light (device_type 0x0102).
Single endpoint (EP1) with OnOff, LevelControl, and Color clusters.

Problem: The device reports color temperature attributes in **Kelvin**
instead of the ZCL-standard **mireds** (1,000,000 / K):
  - 0x0007 (color_temperature) = Kelvin (e.g. 5499 instead of ~182 mireds)
  - 0x400B (color_temp_physical_min) = 2500 (Kelvin, should be 400 mireds)
  - 0x400C (color_temp_physical_max) = 6500 (Kelvin, should be 153 mireds)
  - 0x4010 (start_up_color_temperature) = Kelvin

It also incorrectly reports color_capabilities, causing HA to expose
xy color mode for what is purely a CCT light.

Quirk fixes:
  1. Convert color_temperature between Kelvin (device) and mireds (ZCL/HA)
  2. Set correct color_temp_physical_min/max in mireds
  3. Force color_capabilities = 0x10 (CCT only, no xy/hs)
  4. Convert startup color temperature Kelvin → mireds
  5. Suppress unnecessary LevelControl config entities
"""

import logging

from zigpy.quirks.v2 import QuirkBuilder
from zigpy.zcl.clusters.lighting import Color

from zigpy.quirks import CustomCluster

_LOGGER = logging.getLogger(__name__)

# Kelvin ↔ mireds conversion
MIREDS_FACTOR = 1_000_000

# Device's physical range (Kelvin, from 0x400B / 0x400C)
DEVICE_MIN_KELVIN = 2500  # warm white
DEVICE_MAX_KELVIN = 6500  # cool white

# Converted to mireds (note: min K → max mireds, max K → min mireds)
PHYSICAL_MIN_MIREDS = MIREDS_FACTOR // DEVICE_MAX_KELVIN  # 153
PHYSICAL_MAX_MIREDS = MIREDS_FACTOR // DEVICE_MIN_KELVIN  # 400

# Color cluster attribute IDs
COLOR_TEMP = Color.AttributeDefs.color_temperature.id  # 0x0007
COLOR_CAPABILITIES = Color.AttributeDefs.color_capabilities.id  # 0x400A
COLOR_TEMP_MIN = Color.AttributeDefs.color_temp_physical_min.id  # 0x400B
COLOR_TEMP_MAX = Color.AttributeDefs.color_temp_physical_max.id  # 0x400C
STARTUP_COLOR_TEMP = Color.AttributeDefs.start_up_color_temperature.id  # 0x4010

# Kelvin-reporting attributes that need conversion on read (by ID)
KELVIN_ATTR_IDS = {COLOR_TEMP, STARTUP_COLOR_TEMP}
# Same attributes by name (ZHA accesses via name strings)
KELVIN_ATTR_NAMES = {"color_temperature", "start_up_color_temperature"}

LEVEL = 0x0008  # LevelControl cluster id


def _kelvin_to_mireds(kelvin: int) -> int:
    """Convert Kelvin to mireds, clamped to physical range."""
    if kelvin <= 0:
        return PHYSICAL_MAX_MIREDS
    mireds = MIREDS_FACTOR // kelvin
    return max(PHYSICAL_MIN_MIREDS, min(PHYSICAL_MAX_MIREDS, mireds))


def _mireds_to_kelvin(mireds: int) -> int:
    """Convert mireds to Kelvin, clamped to device range."""
    if mireds <= 0:
        return DEVICE_MAX_KELVIN
    kelvin = MIREDS_FACTOR // mireds
    return max(DEVICE_MIN_KELVIN, min(DEVICE_MAX_KELVIN, kelvin))


class TuyaCCTColorCluster(CustomCluster, Color):
    """Color cluster that converts Kelvin ↔ mireds for Tuya CCT lights.

    The device stores color temperature in Kelvin but ZCL expects mireds.
    This cluster transparently converts:
      - Reads:  Kelvin (from device) → mireds (to ZHA/HA)
      - Writes: mireds (from HA)     → Kelvin (to device)

    Also forces:
      - color_capabilities = 0x10 (color_temperature only)
      - color_temp_physical_min/max in correct mireds
    """

    # Force correct constant attributes
    _CONSTANT_ATTRIBUTES = {
        COLOR_CAPABILITIES: 0x10,  # CCT only (bit 4)
        COLOR_TEMP_MIN: PHYSICAL_MIN_MIREDS,  # 153 mireds (6500K)
        COLOR_TEMP_MAX: PHYSICAL_MAX_MIREDS,  # 400 mireds (2500K)
    }

    def _update_attribute(self, attrid: int, value) -> None:
        """Convert Kelvin → mireds when device reports color temperature."""
        if attrid in KELVIN_ATTR_IDS and isinstance(value, int) and value > 0:
            mireds = _kelvin_to_mireds(value)
            _LOGGER.debug(
                "TS0502B 0x%04X: Kelvin %d → mireds %d",
                attrid, value, mireds,
            )
            super()._update_attribute(attrid, mireds)
            return
        super()._update_attribute(attrid, value)

    async def write_attributes(self, attributes, manufacturer=None, **kwargs):
        """Convert mireds → Kelvin when HA writes color temperature."""
        converted = {}
        for attr, value in attributes.items():
            attr_id = attr if isinstance(attr, int) else getattr(
                self.AttributeDefs, attr, None
            )
            if attr_id is not None and not isinstance(attr_id, int):
                attr_id = attr_id.id

            if attr_id in KELVIN_ATTR_IDS and isinstance(value, int) and value > 0:
                kelvin = _mireds_to_kelvin(value)
                _LOGGER.debug(
                    "TS0502B write 0x%04X: mireds %d → Kelvin %d",
                    attr_id, value, kelvin,
                )
                converted[attr] = kelvin
            else:
                converted[attr] = value

        return await super().write_attributes(converted, manufacturer, **kwargs)

    async def command(self, command_id, *args, manufacturer=None, **kwargs):
        """Convert mireds → Kelvin in move_to_color_temperature command."""
        # Command 0x0A = move_to_color_temperature(color_temp_mireds, transition_time)
        if command_id == 0x0A and args:
            args_list = list(args)
            if isinstance(args_list[0], int) and args_list[0] > 0:
                kelvin = _mireds_to_kelvin(args_list[0])
                _LOGGER.debug(
                    "TS0502B cmd 0x0A: mireds %d → Kelvin %d",
                    args_list[0], kelvin,
                )
                args_list[0] = kelvin
                args = tuple(args_list)
        return await super().command(command_id, *args, manufacturer=manufacturer, **kwargs)

    def get(self, key, default=None):
        """Convert cached Kelvin values to mireds on read.

        ZHA accesses attributes by name (string), while zigpy uses int IDs.
        Handle both cases.
        """
        is_kelvin_attr = (
            (isinstance(key, int) and key in KELVIN_ATTR_IDS)
            or (isinstance(key, str) and key in KELVIN_ATTR_NAMES)
        )
        if is_kelvin_attr:
            val = super().get(key)
            if val is not None and isinstance(val, int) and val > 1000:
                # Value is still in Kelvin (> 1000 means it hasn't been
                # converted yet — mireds for this device are 153-400)
                return _kelvin_to_mireds(val)
            return val if val is not None else default
        return super().get(key, default)


# ────────────────────────────────────────────────────────────────
# TS0502B — CCT dimmable light (_TZ3000_yeygk4hw)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ3000_yeygk4hw", "TS0502B")
    .replaces(TuyaCCTColorCluster, endpoint_id=1)
    # ── Suppress useless default LevelControl entities ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="on_off_transition_time",
    )
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="on_level",
    )
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="default_move_rate",
    )
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="start_up_current_level",
    )
    # ── Suppress Color cluster config entities (shown in mireds, not useful) ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=0x0300,
        unique_id_suffix="start_up_color_temperature",
    )
    .add_to_registry()
)
