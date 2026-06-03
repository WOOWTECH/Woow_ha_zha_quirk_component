"""ZHA Quirk for Tuya TS0002 2-gang switch module (light→switch fix).

Covers:
  - _TZ3000_denobasq  TS0002  2-gang

Both endpoints report as ON_OFF_LIGHT (0x0100), causing HA to create light
entities instead of switches.

This quirk:
  1. Changes device_type on EP1+EP2 to ON_OFF_OUTPUT → switch entities.
  2. Replaces OnOff with TuyaZBOnOffAttributeCluster to expose:
       - backlight_mode  (0x8001) — indicator LED mode
       - power_on_state  (0x8002) — relay status on power-up (per endpoint)
"""

from zigpy.profiles import zha
from zigpy.quirks.v2 import EntityType, QuirkBuilder

from zhaquirks.tuya import (
    PowerOnState,
    SwitchBackLight,
    TuyaZBOnOffAttributeCluster,
)

ONOFF = TuyaZBOnOffAttributeCluster.cluster_id          # 0x0006

(
    QuirkBuilder("_TZ3000_denobasq", "TS0002")
    # ── Force device_type on both endpoints ──
    .replaces_endpoint(endpoint_id=1, device_type=zha.DeviceType.ON_OFF_OUTPUT)
    .replaces_endpoint(endpoint_id=2, device_type=zha.DeviceType.ON_OFF_OUTPUT)
    # ── Replace OnOff across all endpoints ──
    .replace_cluster_occurrences(
        TuyaZBOnOffAttributeCluster,
        replace_client_instances=False,
    )
    # ── EP1: backlight_mode ──
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.backlight_mode.name,
        SwitchBackLight,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_mode",
        fallback_name="Indicator Mode",
    )
    # ── EP1: power_on_state ──
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.power_on_state.name,
        PowerOnState,
        ONOFF,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state",
        fallback_name="Power On State 1",
    )
    # ── EP2: power_on_state ──
    .enum(
        TuyaZBOnOffAttributeCluster.AttributeDefs.power_on_state.name,
        PowerOnState,
        ONOFF,
        endpoint_id=2,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state",
        fallback_name="Power On State 2",
    )
    .add_to_registry()
)
