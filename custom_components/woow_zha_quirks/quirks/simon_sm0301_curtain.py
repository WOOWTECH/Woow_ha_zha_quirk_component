"""ZHA Quirk for Simon SM0301 Curtain Controller.

Device info:
  - Model:        SM0301
  - Manufacturer: _TYZB01_koulgwmy
  - Chip:         Silicon Labs EFR32MG24
  - Firmware:     0x00000083
  - IEEE:         18:69:0a:ff:fe:25:8a:95
  - Type:         1-channel curtain controller (forward/reverse output)

This is a standard ZCL Shade device (device_type 0x0200) that uses
OnOff + LevelControl clusters for cover open/close/position.

Endpoint structure (original):
  EP1-EP4: profile=0x0104, device_type=0x0200 (SHADE)
  Each EP has: Basic, Identify, Groups, Scenes, OnOff, LevelControl,
  Shade Configuration (0x0100), and Tuya private clusters (0xFC55-FC57).

Problem: The device reports 4 identical endpoints but it is a
single-channel curtain controller. Only EP1 is functional.

Calibration:
  This device has NO physical calibration button.  Calibration is
  done entirely over ZCL using Shade Configuration attribute 0x0011
  (an undocumented enum8 — NOT the standard ZCL mode attr 0x0012,
  which this firmware ignores).

  Auto-calibration workflow:
    1. Press "Start Calibration" button  (writes attr 0x0011 = 1)
       → device enters Configure mode
    2. Open the cover to the desired fully-open position, then stop
       → device records the zero point
    3. Close the cover to the desired fully-closed position, then stop
       → device measures and records closed_limit (motor steps)
    4. Press "End Calibration" button  (writes attr 0x0011 = 0)
       → device exits Configure mode and saves the new closed_limit

  The travel distance is stored in Shade Configuration (0x0100)
  attribute closed_limit (0x0010) as uint16 motor steps (e.g. 17800).
  This value can also be written directly via the "Travel Limit"
  number entity.

  The "Reset Travel Limit" button writes closed_limit=65534 (max),
  which removes any travel restriction so the motor can run its full
  range.

  NOTE: The Tuya cloud DP3 (cur_calibration) is mapped to private
  clusters FC55/FC56/FC57 which accept ZCL writes at the protocol
  level but the device firmware does not act on them.

Tuya DP map (cloud):
  DP1   - control         - Enum (open/stop/close)  → OnOff
  DP2   - percent_control - Value 0-100              → LevelControl
  DP3   - cur_calibration - Enum (start/end)         → FC56 (FW-locked)
  DP7   - switch_backlight - Bool                    → FC56
  DP14  - light_mode      - Enum                     → FC56
  DP101 - backlight_num   - Value 50000-60000        → FC56

Quirk fixes:
  1. Remove phantom endpoints EP2-EP4 (only EP1 is real)
  2. Suppress useless OnOff config entities (StartUpOnOff)
  3. Suppress useless LevelControl config entities (start_up_current_level)
  4. Expose Shade closed_limit as a Number entity for travel calibration
  5. Expose "Reset Travel Limit" button (writes closed_limit=65534)
  6. Expose "Start Calibration" / "End Calibration" buttons (attr 0x0011)
"""

import asyncio
import logging
from typing import Any, Final

import zigpy.types as t
from zigpy.quirks import CustomCluster
from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zigpy.zcl.clusters.closures import Shade as ShadeConfiguration
from zigpy.zcl.foundation import ZCLAttributeDef

_LOGGER = logging.getLogger(__name__)

ONOFF = 0x0006
LEVEL = 0x0008
SHADE = 0x0100


class TuyaShadeConfigCluster(CustomCluster, ShadeConfiguration):
    """Shade Configuration with Tuya-specific calibration attribute.

    The standard ZCL mode attribute (0x0012) is present but this
    device's firmware ignores it.  Instead, the undocumented attribute
    0x0011 (enum8) controls calibration mode:
      0 = Normal operation
      1 = Configure / calibration mode
    """

    class AttributeDefs(ShadeConfiguration.AttributeDefs):
        """Extended attributes including undocumented 0x0011."""

        calibration_mode: Final = ZCLAttributeDef(
            id=0x0011,
            type=t.enum8,
            access="rw",
        )

    async def write_attributes(
        self,
        attributes: dict[str | int, Any],
        manufacturer: int | None = None,
        **kwargs,
    ) -> list:
        """Auto-read closed_limit after calibration ends (calibration_mode→0)."""
        result = await super().write_attributes(attributes, manufacturer, **kwargs)

        # Detect calibration_mode = 0 (end calibration)
        for attr, value in attributes.items():
            attr_id = self.find_attribute(attr).id if not isinstance(attr, int) else attr
            if attr_id == 0x0011 and int(value) == 0:
                # Schedule a delayed read so device has time to finalize
                asyncio.ensure_future(self._read_closed_limit_after_calibration())
                break

        return result

    async def _read_closed_limit_after_calibration(self) -> None:
        """Read closed_limit from device after calibration completes."""
        await asyncio.sleep(2)
        success, failure = await self.read_attributes(
            [self.AttributeDefs.closed_limit.id],
        )
        if self.AttributeDefs.closed_limit.id in success:
            _LOGGER.info(
                "SM0301 calibration done, closed_limit=%s",
                success[self.AttributeDefs.closed_limit.id],
            )
        else:
            _LOGGER.warning(
                "SM0301 failed to read closed_limit after calibration: %s",
                failure,
            )


# ────────────────────────────────────────────────────────────────
# SM0301 — 1-channel curtain controller (_TYZB01_koulgwmy)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TYZB01_koulgwmy", "SM0301")
    # ── Replace Shade cluster with our extended version ──
    .replaces(TuyaShadeConfigCluster, endpoint_id=1)
    # ── Remove phantom endpoints (only EP1 is real) ──
    .removes_endpoint(2)
    .removes_endpoint(3)
    .removes_endpoint(4)
    # ── Suppress OnOff StartUpOnOff select ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=ONOFF,
        unique_id_suffix="StartUpOnOff",
    )
    # ── Suppress LevelControl start_up_current_level number ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="start_up_current_level",
    )
    # ── Expose Shade closed_limit for travel calibration ──
    .number(
        attribute_name="closed_limit",
        cluster_id=SHADE,
        endpoint_id=1,
        min_value=100,
        max_value=65534,
        step=100,
        entity_type=EntityType.CONFIG,
        translation_key="closed_limit",
        fallback_name="Travel Limit",
    )
    # ── Reset Travel Limit button (writes max value) ──
    .write_attr_button(
        attribute_name="closed_limit",
        attribute_value=65534,
        cluster_id=SHADE,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="reset_travel_limit",
        fallback_name="Reset Travel Limit",
    )
    # ── Start Calibration button (enters configure mode) ──
    .write_attr_button(
        attribute_name="calibration_mode",
        attribute_value=1,
        cluster_id=SHADE,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        unique_id_suffix="start_calibration",
        translation_key="start_calibration",
        fallback_name="Start Calibration",
    )
    # ── End Calibration button (exits configure mode) ──
    .write_attr_button(
        attribute_name="calibration_mode",
        attribute_value=0,
        cluster_id=SHADE,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        unique_id_suffix="end_calibration",
        translation_key="end_calibration",
        fallback_name="End Calibration",
    )
    .skip_configuration()
    .add_to_registry()
)
