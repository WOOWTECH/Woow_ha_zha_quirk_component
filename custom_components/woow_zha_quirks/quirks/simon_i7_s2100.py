"""ZHA Quirk (v3) for Simon i7 Smart Switches (S2100 series).

Covers four models:
  - S2100-1001  1-gang  (_TZ2000_sayvzx8wgxqoxfuj)
  - S2100-1002  2-gang  (_TZ2000_vvxwtxzf96vvarzj)
  - S2100-1003  3-gang  (_TZ2000_bi57zocaqionffns)
  - S2100-1004  4-gang  (_TZ2000_o1yvtxphiwt5cwif)

These are standard ZCL switches (genOnOff on multiple endpoints),
NOT Tuya MCU (TS0601) devices.  Each endpoint has:
  Cluster 0x0006 OnOff  — standard on/off
  Cluster 0xFC56         — Tuya manufacturer cluster (unused)

Replacing OnOff with TuyaZBOnOffAttributeCluster adds:
  backlight_mode  (0x8001)  indicator LED mode  (enum: Off/Normal/Inverted)

Multi-gang models (2/3/4-gang) get a virtual endpoint 200 with an
AllOnOff cluster that sends OnOff commands to every real endpoint,
providing a single "All On/Off" switch entity.

Note: Endpoint 242 cannot be used for the virtual endpoint because
the device already has a real endpoint 242 (Green Power, profile 0xA1E0)
which ZHA skips for cluster handler creation.
"""

import logging

from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff

from zhaquirks import LocalDataCluster
from zhaquirks.tuya import (
    SwitchBackLight,
    TuyaZBOnOffAttributeCluster,
)

_LOGGER = logging.getLogger(__name__)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id  # 0x0006
ALL_ONOFF_EP = 200  # virtual endpoint for All On/Off


class AllOnOffCluster(LocalDataCluster, OnOff):
    """Virtual OnOff cluster that controls all real endpoints simultaneously.

    Placed on virtual endpoint 200, this cluster intercepts on/off commands
    and fans them out to every real endpoint's OnOff cluster.

    ZHA auto-discovers a standard Switch entity for this cluster. The Switch
    entity calls OnOffClusterHandler.turn_on() → cluster.on() → command(0x01),
    which we intercept here to fan out.
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
# S2100-1001  —  1-gang  (_TZ2000_sayvzx8wgxqoxfuj)
# (no All On/Off — only 1 gang)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_sayvzx8wgxqoxfuj", "S2100-1001")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    .add_to_registry()
)


# ────────────────────────────────────────────────────────────────
# S2100-1002  —  2-gang  (_TZ2000_vvxwtxzf96vvarzj)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_vvxwtxzf96vvarzj", "S2100-1002")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    .adds_endpoint(endpoint_id=ALL_ONOFF_EP)
    .adds(AllOnOffCluster, endpoint_id=ALL_ONOFF_EP)
    .add_to_registry()
)


# ────────────────────────────────────────────────────────────────
# S2100-1003  —  3-gang  (_TZ2000_bi57zocaqionffns)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_bi57zocaqionffns", "S2100-1003")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=3)
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    .adds_endpoint(endpoint_id=ALL_ONOFF_EP)
    .adds(AllOnOffCluster, endpoint_id=ALL_ONOFF_EP)
    .add_to_registry()
)


# ────────────────────────────────────────────────────────────────
# S2100-1004  —  4-gang  (_TZ2000_o1yvtxphiwt5cwif)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_o1yvtxphiwt5cwif", "S2100-1004")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=3)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=4)
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    .adds_endpoint(endpoint_id=ALL_ONOFF_EP)
    .adds(AllOnOffCluster, endpoint_id=ALL_ONOFF_EP)
    .add_to_registry()
)
