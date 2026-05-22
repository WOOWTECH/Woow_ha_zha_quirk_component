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
"""

from zigpy.quirks.v2 import EntityType, QuirkBuilder

from zhaquirks.tuya import (
    SwitchBackLight,
    TuyaZBOnOffAttributeCluster,
)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id  # 0x0006


# ────────────────────────────────────────────────────────────────
# S2100-1003  —  3-gang  (_TZ2000_bi57zocaqionffns)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_bi57zocaqionffns", "S2100-1003")
    .replace_cluster_occurrences(
        TuyaZBOnOffAttributeCluster,
        replace_client_instances=False,
    )
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
    .replace_cluster_occurrences(
        TuyaZBOnOffAttributeCluster,
        replace_client_instances=False,
    )
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
# S2100-1001  —  1-gang  (_TZ2000_sayvzx8wgxqoxfuj)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_sayvzx8wgxqoxfuj", "S2100-1001")
    .replace_cluster_occurrences(
        TuyaZBOnOffAttributeCluster,
        replace_client_instances=False,
    )
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
# S2100-1004  —  4-gang  (_TZ2000_o1yvtxphiwt5cwif)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ2000_o1yvtxphiwt5cwif", "S2100-1004")
    .replace_cluster_occurrences(
        TuyaZBOnOffAttributeCluster,
        replace_client_instances=False,
    )
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
