"""ZHA Quirk for Simon SM0502 Dual-Gang Dimmer Switch.

Device info:
  - Model:        SM0502
  - Manufacturer: _TZ2000_qc1ntn3c
  - Chip:         Silicon Labs EFR32MG24
  - Firmware:     0x00000087

This is a standard ZCL dimmer (NOT Tuya MCU / TS0601).
The device exposes 4 endpoints (device_type=DIMMABLE_LIGHT 0x0101),
but only endpoints 1 & 2 are real physical gangs.
Endpoints 3 & 4 are phantom/virtual and must be removed.

Each real endpoint has:
  - OnOff        (0x0006)  on/off control
  - LevelControl (0x0008)  brightness (0-254)

The device does NOT support Tuya manufacturer-specific LevelControl
attributes (0xFC00-0xFC05). Min/max brightness in the Tuya app is
a software-only feature of the Tuya gateway/cloud.

Quirk adds:
  1. Remove phantom endpoints 3 & 4
  2. TuyaZBOnOffAttributeCluster on EP1 & EP2 for backlight_mode
  3. AllOnOff virtual cluster on EP200 for all-on/all-off
  4. Suppress useless default LevelControl entities
"""

import logging

from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import LevelControl, OnOff

from zhaquirks import LocalDataCluster
from zhaquirks.tuya import (
    SwitchBackLight,
    TuyaZBOnOffAttributeCluster,
)

_LOGGER = logging.getLogger(__name__)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id  # 0x0006
LEVEL = LevelControl.cluster_id  # 0x0008
ALL_ONOFF_EP = 200  # virtual endpoint for All On/Off


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
    # ── EP2: Gang 2 dimmer ──
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    # ── Remove phantom endpoints 3 & 4 ──
    .removes_endpoint(endpoint_id=3)
    .removes_endpoint(endpoint_id=4)
    # ── Suppress useless default LevelControl entities (EP1) ──
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
    # ── Suppress useless default LevelControl entities (EP2) ──
    .prevent_default_entity_creation(
        endpoint_id=2, cluster_id=LEVEL,
        unique_id_suffix="on_off_transition_time",
    )
    .prevent_default_entity_creation(
        endpoint_id=2, cluster_id=LEVEL,
        unique_id_suffix="on_level",
    )
    .prevent_default_entity_creation(
        endpoint_id=2, cluster_id=LEVEL,
        unique_id_suffix="default_move_rate",
    )
    .prevent_default_entity_creation(
        endpoint_id=2, cluster_id=LEVEL,
        unique_id_suffix="start_up_current_level",
    )
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
    # ── AllOnOff virtual endpoint ──
    .adds_endpoint(endpoint_id=ALL_ONOFF_EP)
    .adds(AllOnOffCluster, endpoint_id=ALL_ONOFF_EP)
    .add_to_registry()
)
