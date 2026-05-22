"""ZHA Quirk for Tuya TS0001 switches (light→switch fix).

Covers:
  - _TZ3000_tqlv4ug4  (switch module — has metering clusters to remove,
                        needs external_switch_type for wired switch config)
  - _TZ3000_tuucc0f5  (switch panel — no metering, no external_switch_type)
  - _TZ3000_voy7mbpw  (switch panel — same as tuucc0f5)

These devices report as ON_OFF_LIGHT (0x0100), causing HA to create a light
entity instead of a switch.

This quirk:
  1. Changes device_type to ON_OFF_OUTPUT so HA shows a switch entity.
  2. Drops phantom metering clusters if present.
  3. Replaces OnOff with TuyaZBOnOffAttributeCluster to expose:
       - backlight_mode  (0x8001) — indicator LED mode
       - power_on_state  (0x8002) — relay status on power-up
  4. (_TZ3000_tqlv4ug4 only) Replaces 0xE001 with
     TuyaZBExternalSwitchTypeCluster to expose external_switch_type.
"""

from zigpy.profiles import zha
from zigpy.quirks.v2 import EntityType, QuirkBuilder

from zhaquirks.tuya import (
    ExternalSwitchType,
    PowerOnState,
    SwitchBackLight,
    TuyaZBExternalSwitchTypeCluster,
    TuyaZBOnOffAttributeCluster,
)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id          # 0x0006
EXT_SW = TuyaZBExternalSwitchTypeCluster.cluster_id     # 0xE001

# ────────────────────────────────────────────────────────────────
# _TZ3000_tqlv4ug4  TS0001  (with metering clusters to remove)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ3000_tqlv4ug4", "TS0001")
    .replaces_endpoint(
        endpoint_id=1,
        device_type=zha.DeviceType.ON_OFF_OUTPUT,
    )
    .removes(cluster_id=0x0702, endpoint_id=1)       # Metering
    .removes(cluster_id=0x0B04, endpoint_id=1)       # Electrical Measurement
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(TuyaZBExternalSwitchTypeCluster, endpoint_id=1)
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.power_on_state.name,
        PowerOnState,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state",
        fallback_name="Relay Status",
    )
    .enum(
        TuyaZBExternalSwitchTypeCluster.AttributeDefs.external_switch_type.name,
        ExternalSwitchType,
        EXT_SW,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="external_switch_type",
        fallback_name="Switch Type",
    )
    .add_to_registry()
)


# ────────────────────────────────────────────────────────────────
# _TZ3000_tuucc0f5  TS0001  (no metering clusters)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ3000_tuucc0f5", "TS0001")
    .replaces_endpoint(
        endpoint_id=1,
        device_type=zha.DeviceType.ON_OFF_OUTPUT,
    )
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
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.power_on_state.name,
        PowerOnState,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state",
        fallback_name="Power On State",
    )
    .add_to_registry()
)


# ────────────────────────────────────────────────────────────────
# _TZ3000_voy7mbpw  TS0001  (switch panel, same pattern as tuucc0f5)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TZ3000_voy7mbpw", "TS0001")
    .replaces_endpoint(
        endpoint_id=1,
        device_type=zha.DeviceType.ON_OFF_OUTPUT,
    )
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
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.power_on_state.name,
        PowerOnState,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state",
        fallback_name="Power On State",
    )
    .add_to_registry()
)
