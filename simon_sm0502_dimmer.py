"""ZHA Quirk for Simon SM0502 Dual-Gang Dimmer Switch.

Device info:
  - Model:        SM0502
  - Manufacturer: _TZ2000_qc1ntn3c
  - Chip:         Silicon Labs EFR32MG24
  - Firmware:     0x00000087
  - Zigbee IEEE:  7C:C6:B6:FF:FE:82:6C:CF

This is a standard ZCL dimmer (NOT Tuya MCU / TS0601).
The device exposes 4 endpoints (device_type=DIMMABLE_LIGHT 0x0101),
but only endpoints 1 & 2 are real physical gangs.
Endpoints 3 & 4 are phantom/virtual and must be removed.

Each real endpoint has:
  - OnOff        (0x0006)  on/off control
  - LevelControl (0x0008)  brightness (0-254)

Tuya features from app:
  - Dual-gang dimming (Switch1 + Switch2)
  - All On / All Off
  - Min/max brightness limits per gang (30-100% in Tuya app)
  - Indicator LED mode (Off / Switch Status / Switch Position)

Quirk adds:
  1. Remove phantom endpoints 3 & 4
  2. TuyaZBOnOffAttributeCluster on EP1 & EP2 for backlight_mode
  3. AllOnOff virtual cluster on EP200 for all-on/all-off
  4. Min/max brightness attributes (0xFC03/0xFC04) on LevelControl
"""

import logging
from typing import Final

import zigpy.types as t
from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import LevelControl, OnOff
from zigpy.zcl.foundation import ZCLAttributeDef

from zhaquirks import LocalDataCluster
from zhaquirks.tuya import (
    NoManufacturerCluster,
    SwitchBackLight,
    TuyaZBOnOffAttributeCluster,
)

_LOGGER = logging.getLogger(__name__)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id  # 0x0006
ALL_ONOFF_EP = 200  # virtual endpoint for All On/Off

# Tuya manufacturer-specific LevelControl attributes
TUYA_MIN_LEVEL_ATTR = 0xFC03
TUYA_MAX_LEVEL_ATTR = 0xFC04
TUYA_BULB_TYPE_ATTR = 0xFC02


class TuyaBulbType(t.enum8):
    """Tuya bulb type / dimming curve."""

    LED = 0x00
    Incandescent = 0x01
    Halogen = 0x02


class SimonLevelControlCluster(NoManufacturerCluster, LevelControl):
    """LevelControl with Tuya manufacturer-specific min/max brightness.

    Extends LevelControl to add attributes 0xFC03 (min_level) and
    0xFC04 (max_level) which control the dimming range.
    Values are in the 10-1000 range (Tuya scale).

    Also adds 0xFC02 (bulb_type) for dimming curve selection.
    """

    class AttributeDefs(LevelControl.AttributeDefs):
        """Extended attributes with Tuya min/max brightness."""

        bulb_type: Final = ZCLAttributeDef(
            id=TUYA_BULB_TYPE_ATTR, type=TuyaBulbType
        )
        manufacturer_min_level: Final = ZCLAttributeDef(
            id=TUYA_MIN_LEVEL_ATTR, type=t.uint16_t
        )
        manufacturer_max_level: Final = ZCLAttributeDef(
            id=TUYA_MAX_LEVEL_ATTR, type=t.uint16_t
        )


class AllOnOffCluster(LocalDataCluster, OnOff):
    """Virtual OnOff cluster that controls all real dimmer endpoints.

    Placed on virtual endpoint 200. Intercepts on/off commands and
    fans them out to endpoints 1 and 2.
    """

    cluster_id = OnOff.cluster_id  # 0x0006

    async def command(
        self,
        command_id: foundation.GeneralCommand | int,
        *args,
        manufacturer=None,
        expect_reply: bool = True,
        **kwargs,
    ):
        """Intercept on/off/toggle and send to all real endpoints."""
        if command_id not in (0x00, 0x01, 0x02):
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        for ep_id, ep in sorted(self.endpoint.device.endpoints.items()):
            if ep_id in (0, ALL_ONOFF_EP, 242):
                continue
            onoff = ep.in_clusters.get(OnOff.cluster_id)
            if onoff is None:
                continue
            try:
                await onoff.command(command_id)
                _LOGGER.debug(
                    "AllOnOff EP%d cmd=0x%02x OK", ep_id, command_id,
                )
            except Exception:
                _LOGGER.warning(
                    "AllOnOff EP%d cmd=0x%02x failed",
                    ep_id, command_id, exc_info=True,
                )

        if command_id == 0x01:
            self._update_attribute(OnOff.AttributeDefs.on_off.id, True)
        elif command_id == 0x00:
            self._update_attribute(OnOff.AttributeDefs.on_off.id, False)

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(command_id=command_id, status=foundation.Status.SUCCESS)


# ────────────────────────────────────────────────────────────────
# SM0502 — 2-gang dimmer (_TZ2000_qc1ntn3c)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_qc1ntn3c", "SM0502")
    # ── EP1: Gang 1 dimmer ──
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(SimonLevelControlCluster, endpoint_id=1)
    # ── EP2: Gang 2 dimmer ──
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    .replaces(SimonLevelControlCluster, endpoint_id=2)
    # ── Remove phantom endpoints 3 & 4 ──
    .removes_endpoint(endpoint_id=3)
    .removes_endpoint(endpoint_id=4)
    # ── Indicator LED mode (config entity on EP1) ──
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    # ── Min/Max brightness for Gang 1 ──
    .number(
        SimonLevelControlCluster.AttributeDefs.manufacturer_min_level.name,
        LevelControl.cluster_id,
        endpoint_id=1,
        min_value=10,
        max_value=1000,
        step=10,
        entity_type=EntityType.CONFIG,
        translation_key="min_brightness",
        fallback_name="Minimum Brightness",
    )
    .number(
        SimonLevelControlCluster.AttributeDefs.manufacturer_max_level.name,
        LevelControl.cluster_id,
        endpoint_id=1,
        min_value=10,
        max_value=1000,
        step=10,
        entity_type=EntityType.CONFIG,
        translation_key="max_brightness",
        fallback_name="Maximum Brightness",
    )
    .number(
        SimonLevelControlCluster.AttributeDefs.manufacturer_min_level.name,
        LevelControl.cluster_id,
        endpoint_id=2,
        min_value=10,
        max_value=1000,
        step=10,
        entity_type=EntityType.CONFIG,
        translation_key="min_brightness",
        fallback_name="Minimum Brightness",
    )
    .number(
        SimonLevelControlCluster.AttributeDefs.manufacturer_max_level.name,
        LevelControl.cluster_id,
        endpoint_id=2,
        min_value=10,
        max_value=1000,
        step=10,
        entity_type=EntityType.CONFIG,
        translation_key="max_brightness",
        fallback_name="Maximum Brightness",
    )
    # ── Bulb type / dimming curve for each gang ──
    .enum(
        SimonLevelControlCluster.AttributeDefs.bulb_type.name,
        TuyaBulbType,
        LevelControl.cluster_id,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="bulb_type",
        fallback_name="Light Source Type",
    )
    .enum(
        SimonLevelControlCluster.AttributeDefs.bulb_type.name,
        TuyaBulbType,
        LevelControl.cluster_id,
        endpoint_id=2,
        entity_type=EntityType.CONFIG,
        translation_key="bulb_type",
        fallback_name="Light Source Type",
    )
    # ── AllOnOff virtual endpoint ──
    .adds_endpoint(endpoint_id=ALL_ONOFF_EP)
    .adds(AllOnOffCluster, endpoint_id=ALL_ONOFF_EP)
    .add_to_registry()
)
