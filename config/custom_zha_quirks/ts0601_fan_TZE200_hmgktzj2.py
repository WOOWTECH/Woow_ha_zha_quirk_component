"""ZHA Quirk (v5) for Tuya Ceiling Fan with Light (_TZE200_hmgktzj2 / TS0601).

Monkey-patches ZHA fan constants at import time:
  SPEED_RANGE = (1, 6)          — 6 speed levels via percentage
  PRESET_MODES_TO_NAME = {7: "一般（風量3）", 8: "自然風", 9: "舒眠"}
  DIRECTION support            — native fan.set_direction forward/reverse

Native HA entities:
  - fan.*      : Native fan entity with 6 speeds, 3 presets, direction control
  - light.*    : Simple on/off light (no brightness)
  - select.*   : "Color Temperature" — 3-level (白光/自然光/黃光)

DP Map:
  DP  1   : Fan switch          (Bool)
  DP  3   : Fan speed           (Enum: 0=off, 1-6=speed, 7=natural wind, 8=sleep)
  DP  5   : Light switch        (Bool)
  DP  101 : Fan direction       (Enum: 0=reverse, 1=forward)
  DP  102 : Light color temp    (Enum: 0=warm, 50=neutral, 100=cool)
  DP  103 : (device echoes but NOT real direction — see DP101)

Fan entity (ZCL Fan cluster 0x0202):
  With patched SPEED_RANGE=(1,6), 6 speed levels via percentage:
    fan_mode 1 (16%)   → DP3=1 (Speed 1 / 段速1)
    fan_mode 2 (33%)   → DP3=2 (Speed 2 / 段速2)
    fan_mode 3 (50%)   → DP3=3 (Speed 3 / 段速3)
    fan_mode 4 (66%)   → DP3=4 (Speed 4 / 段速4)
    fan_mode 5 (83%)   → DP3=5 (Speed 5 / 段速5)
    fan_mode 6 (100%)  → DP3=6 (Speed 6 / 段速6)
  Preset modes (fan_mode values 7-9, outside speed_range):
    "一般（風量3）"  (fan_mode 7) → DP3=3 (一般, speed 3)
    "自然風"        (fan_mode 8) → DP3=7 (自然風)
    "舒眠"          (fan_mode 9) → DP3=8 (睡眠)
  On/Off:
    fan_mode 0 → DP1=false (turn off)
    fan_mode > 0 → DP3=value (device auto-turns-on)
  Direction:
    fan.set_direction forward → DP101=1
    fan.set_direction reverse → DP101=0
    Direction change uses stop→set→restart sequence.
    Light state is preserved during direction change.

Light entity:
  OnOff cluster on endpoint 2 bridges DP5.

Color temp SELECT:
  Warm (黃光) → DP102=0
  Natural (自然光) → DP102=50
  White (白光) → DP102=100
"""

from __future__ import annotations

import sys
from typing import Any

from zigpy.profiles import zha
from zigpy.quirks.v2.homeassistant import EntityType
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import OnOff
from zigpy.zcl.clusters.hvac import Fan

from zhaquirks.tuya import (
    NoManufacturerCluster,
    TuyaCommand,
    TuyaData,
    TuyaDatapointData,
    TuyaLocalCluster,
)
from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import TuyaMCUCluster


# ─────────────────────────────────────────────────────────────────
# Monkey-patch ZHA fan constants for 6-speed support.
#
# This runs at quirk import time. The ZHA fan platform module may or
# may not be loaded yet — we patch sys.modules if present, and also
# patch the const module directly. The fan entity's speed_range is a
# @functools.cached_property computed at first access (entity creation),
# which happens AFTER quirk loading, so our patch takes effect.
# ─────────────────────────────────────────────────────────────────

_PATCHED_SPEED_RANGE = (1, 6)
_PATCHED_PRESET_MODES = {7: "一般（風量3）", 8: "自然風", 9: "舒眠"}
_PATCHED_LEGACY_SPEEDS = ["low", "medium", "high", "speed_4", "speed_5", "speed_6"]


def _apply_fan_patch():
    """Patch ZHA fan constants for 6-speed support.

    Works whether the ZHA fan modules are already loaded or not:
    - If loaded: patches in-place via sys.modules
    - If not yet loaded: imports const module (safe — no circular deps)
      and patches it so later imports pick up the patched values
    """
    import importlib
    import logging

    _log = logging.getLogger(__name__)
    _name_to_preset = {v: k for k, v in _PATCHED_PRESET_MODES.items()}

    # 1) Patch the const module (import it if needed — it has no circular deps)
    _const_name = "zha.application.platforms.fan.const"
    _const_mod = sys.modules.get(_const_name)
    if _const_mod is None:
        try:
            _const_mod = importlib.import_module(_const_name)
        except ImportError:
            _log.warning("Cannot import %s — fan speed patch not applied", _const_name)
            return

    _const_mod.SPEED_RANGE = _PATCHED_SPEED_RANGE
    _const_mod.PRESET_MODES_TO_NAME = _PATCHED_PRESET_MODES
    _const_mod.NAME_TO_PRESET_MODE = _name_to_preset
    _const_mod.PRESET_MODES = list(_name_to_preset)
    _const_mod.LEGACY_SPEED_LIST = _PATCHED_LEGACY_SPEEDS
    _log.info("Patched ZHA fan const: SPEED_RANGE=%s", _PATCHED_SPEED_RANGE)

    # 2) Patch the fan __init__ module if it's already loaded
    #    (it imports SPEED_RANGE etc. at module level)
    _fan_name = "zha.application.platforms.fan"
    _fan_mod = sys.modules.get(_fan_name)
    if _fan_mod is not None:
        _fan_mod.SPEED_RANGE = _PATCHED_SPEED_RANGE
        _fan_mod.PRESET_MODES_TO_NAME = _PATCHED_PRESET_MODES
        if hasattr(_fan_mod, "LEGACY_SPEED_LIST"):
            _fan_mod.LEGACY_SPEED_LIST = _PATCHED_LEGACY_SPEEDS
        _log.info("Patched ZHA fan __init__ imported references")

    # 3) Add PRESET_MODE + DIRECTION to BaseFan._attr_supported_features
    #    so the HA frontend shows the preset mode selector and direction
    #    controls in the fan card.
    try:
        from homeassistant.components.fan import FanEntityFeature
        _base_fan = None
        if _fan_mod is not None and hasattr(_fan_mod, "BaseFan"):
            _base_fan = _fan_mod.BaseFan
        if _base_fan is not None:
            _current = _base_fan._attr_supported_features
            _needed = FanEntityFeature.PRESET_MODE | FanEntityFeature.DIRECTION
            if (_current & _needed) != _needed:
                _base_fan._attr_supported_features = _current | _needed
                _log.info(
                    "Patched BaseFan._attr_supported_features: added PRESET_MODE+DIRECTION (now %s)",
                    _base_fan._attr_supported_features,
                )
    except ImportError:
        _log.warning("Cannot import FanEntityFeature — PRESET_MODE/DIRECTION patch not applied")

    # 4) Patch HA's ZhaFan entity class to support direction via Tuya DP101.
    #    ZhaFan bridges ZHA's Fan entity to HA's FanEntity. We add:
    #    - current_direction property (reads from ZHA fan entity)
    #    - async_set_direction method (calls into the Tuya MCU cluster)
    _apply_direction_patch(_log)


def _apply_direction_patch(_log):
    """Patch HA ZhaFan + ZHA Fan to support fan.set_direction via Tuya DP101.

    Patches two classes:
    1. ZHA Fan entity (zha.application.platforms.fan.Fan):
       - _tuya_direction: tracks current direction ("forward" / "reverse")
       - _async_tuya_set_direction(): sends DP101 via MCU cluster
    2. HA ZhaFan bridge (homeassistant.components.zha.fan.ZhaFan):
       - current_direction property
       - async_set_direction method
    """
    import importlib

    # --- Patch ZHA Fan entity ---
    _zha_fan_init = sys.modules.get("zha.application.platforms.fan")
    if _zha_fan_init is None:
        try:
            _zha_fan_init = importlib.import_module("zha.application.platforms.fan")
        except ImportError:
            pass
    _ZhaFanEntity = getattr(_zha_fan_init, "Fan", None) if _zha_fan_init else None
    if _ZhaFanEntity is not None and not hasattr(_ZhaFanEntity, "_async_tuya_set_direction"):

        @property
        def _tuya_direction_prop(self):
            """Read direction from the cluster's stored state."""
            cluster = self._fan_cluster_handler.cluster
            return getattr(cluster, "_tuya_last_direction", "forward")

        async def _async_tuya_set_direction(self, direction: str) -> None:
            """Send direction change to Tuya MCU cluster."""
            cluster = self._fan_cluster_handler.cluster
            if hasattr(cluster, "tuya_set_direction"):
                await cluster.tuya_set_direction(direction)
                cluster._tuya_last_direction = direction
                self.maybe_emit_state_changed_event()

        _ZhaFanEntity._tuya_direction = _tuya_direction_prop
        _ZhaFanEntity._async_tuya_set_direction = _async_tuya_set_direction
        _log.info("Patched ZHA Fan entity: added _tuya_direction + _async_tuya_set_direction")

    # --- Patch HA ZhaFan bridge ---
    try:
        _ha_zha_fan_mod = sys.modules.get("homeassistant.components.zha.fan")
        if _ha_zha_fan_mod is None:
            _ha_zha_fan_mod = importlib.import_module("homeassistant.components.zha.fan")
        _ZhaFan = getattr(_ha_zha_fan_mod, "ZhaFan", None)
    except ImportError:
        _ZhaFan = None

    if _ZhaFan is not None and not hasattr(_ZhaFan, "_direction_patched"):
        @property
        def _current_direction(self):
            """Return the current direction of the fan."""
            entity = self.entity_data.entity
            # _tuya_direction is a property on the patched ZHA Fan entity
            # that reads from the cluster's _tuya_last_direction
            try:
                return entity._tuya_direction
            except (AttributeError, TypeError):
                return "forward"

        async def _async_set_direction(self, direction: str) -> None:
            """Set the direction of the fan via Tuya DP101."""
            entity = self.entity_data.entity
            if hasattr(entity, "_async_tuya_set_direction"):
                await entity._async_tuya_set_direction(direction)
                self.async_write_ha_state()

        _ZhaFan.current_direction = _current_direction
        _ZhaFan.async_set_direction = _async_set_direction
        _ZhaFan._direction_patched = True
        _log.info("Patched HA ZhaFan: added current_direction + async_set_direction")


_apply_fan_patch()


# ─────────────────────────────────────────────────────────────────
# Enums for SELECT entities
# ─────────────────────────────────────────────────────────────────

class ColorTempLevel(t.enum8):
    """3-level color temperature. Enum values = DP102 values."""
    Warm = 0x00        # 黃光 (warm white) → DP102=0
    Natural = 0x32     # 自然光 (neutral) → DP102=50
    White = 0x64       # 白光 (cool white) → DP102=100


# ─────────────────────────────────────────────────────────────────
# Fan mode mapping: ZCL fan_mode ↔ Tuya DP3
#
# With patched SPEED_RANGE=(1,6):
#   fan_mode 0   = Off
#   fan_mode 1-6 = Speed 1-6 (mapped to DP3 1-6)
#   fan_mode 7   = "一般（風量3）" preset → DP3=3 (一般, speed 3)
#   fan_mode 8   = "自然風" preset → DP3=7 (自然風)
#   fan_mode 9   = "舒眠" preset → DP3=8 (睡眠)
# ─────────────────────────────────────────────────────────────────

# ZCL fan_mode → DP3 value
_FAN_MODE_TO_DP3 = {
    0: 0,   # Off
    1: 1,   # Speed 1
    2: 2,   # Speed 2
    3: 3,   # Speed 3
    4: 4,   # Speed 4
    5: 5,   # Speed 5
    6: 6,   # Speed 6
    7: 3,   # "一般（風量3）" preset → 一般 (speed 3)
    8: 7,   # "自然風" preset → 自然風
    9: 8,   # "舒眠" preset → 睡眠
}

# DP3 value → ZCL fan_mode
_DP3_TO_FAN_MODE = {
    0: 0,   # Off
    1: 1,   # Speed 1
    2: 2,   # Speed 2
    3: 3,   # Speed 3
    4: 4,   # Speed 4
    5: 5,   # Speed 5
    6: 6,   # Speed 6
    7: 8,   # Natural Wind → "自然風" preset
    8: 9,   # Sleep → "舒眠" preset
}


# ─────────────────────────────────────────────────────────────────
# Custom ZCL Fan Cluster — bridges DP1 + DP3
# ─────────────────────────────────────────────────────────────────

class TuyaCeilingFanCluster(Fan, TuyaLocalCluster):
    """Fan Control cluster bridging Tuya DPs for ceiling fan.

    Intercepts write_attributes to send Tuya DPs.
    With patched ZHA, fan_mode values:
      0=Off, 1-6=Speed, 7=一般(preset), 8=自然風(preset), 9=舒眠(preset)
    Also handles direction via tuya_set_direction → DP101.
    """

    class AttributeDefs(Fan.AttributeDefs):
        pass

    class ServerCommandDefs(Fan.ServerCommandDefs):
        pass

    def __init__(self, *args, **kwargs):
        """Initialize with fan mode sequence."""
        super().__init__(*args, **kwargs)
        self._update_attribute(
            Fan.AttributeDefs.fan_mode_sequence.id,
            Fan.FanModeSequence.Low_Med_High_Auto,
        )
        self._update_attribute(Fan.AttributeDefs.fan_mode.id, 0)

    def _get_mcu(self):
        """Get the MCU cluster."""
        return self.endpoint.tuya_manufacturer

    async def write_attributes(self, attributes, manufacturer=None, **kwargs):
        """Intercept write_attributes to route to Tuya DPs."""
        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attributes_by_name[attrid].id
            if attrid == Fan.AttributeDefs.fan_mode.id:
                mode = int(value)
                self._send_fan_mode(mode)
        return [[foundation.WriteAttributesStatusRecord(foundation.Status.SUCCESS)]]

    def _send_fan_mode(self, mode: int) -> None:
        """Send fan mode as Tuya DPs.

        NOTE: Device ignores DP3 if sent in the same frame as DP1.
        DP3 alone is sufficient to turn the fan on at the specified speed.
        Only DP1=false is needed for turning off.
        """
        mcu = self._get_mcu()
        dp3_val = _FAN_MODE_TO_DP3.get(mode)

        if dp3_val is None:
            # Unknown mode — just turn on
            mcu.send_dp(TuyaDatapointData(1, TuyaData(t.Bool(True))))
            self._update_attribute(Fan.AttributeDefs.fan_mode.id, mode)
            return

        if mode == 0:
            # Off: send DP1=false
            mcu.send_dp(TuyaDatapointData(1, TuyaData(t.Bool(False))))
        else:
            # On with speed/preset: send DP3 only (device auto-turns-on)
            mcu.send_dp(TuyaDatapointData(3, TuyaData(t.enum8(dp3_val))))
        self._update_attribute(Fan.AttributeDefs.fan_mode.id, mode)

    async def tuya_set_direction(self, direction: str) -> None:
        """Set fan direction via DP101 with stop→set→restart sequence.

        Only touches fan DPs (1, 3, 101, 103). Never touches DP5 (light).
        Sets _direction_changing flag so DP5 reports from MCU are ignored
        during the sequence (the MCU echoes DP5 when fan stops/starts).
        Called from the patched ZHA Fan entity's _async_tuya_set_direction.
        """
        import asyncio

        mcu = self._get_mcu()
        dir_val = 1 if direction == "forward" else 0

        # Save current fan speed
        current_mode = self.get(Fan.AttributeDefs.fan_mode.id, 0)
        was_running = current_mode > 0
        dp3_val = _FAN_MODE_TO_DP3.get(current_mode, 1)

        # Save current light state — we'll force-restore it after unblocking
        light_was_on = False
        ep2 = self.endpoint.device.endpoints.get(2)
        if ep2 and ep2.on_off:
            light_was_on = bool(ep2.on_off.get(
                OnOff.AttributeDefs.on_off.id, False
            ))

        # Block DP5 reports on the MCU cluster during direction change.
        # _dp_2_attr_update runs on the MCU cluster (TuyaFanMCUCluster),
        # not on this fan cluster, so set the flag there.
        mcu._direction_changing = True

        # Step 1: Stop the fan
        mcu.send_dp(TuyaDatapointData(1, TuyaData(t.Bool(False))))
        await asyncio.sleep(3)

        # Step 2: Send direction on DP101
        mcu.send_dp(TuyaDatapointData(101, TuyaData(t.enum8(dir_val))))
        await asyncio.sleep(0.5)
        mcu.send_dp(TuyaDatapointData(101, TuyaData(t.Bool(bool(dir_val)))))
        await asyncio.sleep(1)

        # Step 3: Also send DP103
        mcu.send_dp(TuyaDatapointData(103, TuyaData(t.enum8(dir_val))))
        await asyncio.sleep(1)

        # Step 4: Restart fan at previous speed (if it was running)
        if was_running:
            mcu.send_dp(TuyaDatapointData(3, TuyaData(t.enum8(dp3_val))))

        # Schedule delayed unblock + light restore.
        # The MCU sends late DP5 echoes after fan restart, so we keep
        # blocking for 15 seconds then force-restore the light state.
        async def _delayed_unblock():
            await asyncio.sleep(15)
            mcu._direction_changing = False
            if ep2 and ep2.on_off:
                ep2.on_off._update_attribute(
                    OnOff.AttributeDefs.on_off.id, light_was_on
                )

        asyncio.ensure_future(_delayed_unblock())


class TuyaCeilingFanClusterNM(NoManufacturerCluster, TuyaCeilingFanCluster):
    """Fan cluster with no manufacturer ID."""


# ─────────────────────────────────────────────────────────────────
# Custom ZCL OnOff Cluster for Light — bridges DP5
# ─────────────────────────────────────────────────────────────────

class TuyaFanLightOnOff(OnOff, TuyaLocalCluster):
    """OnOff cluster bridging Tuya DP5 (light switch).

    Creates a simple on/off light entity on endpoint 2.
    """

    class AttributeDefs(OnOff.AttributeDefs):
        pass

    class ServerCommandDefs(OnOff.ServerCommandDefs):
        pass

    def _get_mcu(self):
        """Get the MCU cluster from endpoint 1."""
        return self.endpoint.device.endpoints[1].tuya_manufacturer

    async def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs: Any,
    ):
        """Route on/off commands to Tuya DP5."""
        if command_id in (0x0000, 0x0001):
            on_val = bool(command_id)
            mcu = self._get_mcu()
            mcu.send_dp(TuyaDatapointData(5, TuyaData(t.Bool(on_val))))
            self._update_attribute(OnOff.AttributeDefs.on_off.id, on_val)
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)
        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(
            command_id=command_id,
            status=foundation.Status.UNSUP_CLUSTER_COMMAND,
        )


class TuyaFanLightOnOffNM(NoManufacturerCluster, TuyaFanLightOnOff):
    """OnOff cluster with no manufacturer ID for light endpoint."""


# ─────────────────────────────────────────────────────────────────
# Custom TuyaMCU Cluster — DP routing and command handling
# ─────────────────────────────────────────────────────────────────

class TuyaFanMCUCluster(TuyaMCUCluster):
    """Extended TuyaMCU cluster for ceiling fan + light.

    Handles:
      - Incoming DP reports → updates Fan/OnOff cluster attributes
      - Outgoing DP commands via send_dp
      - Direction (DP101/DP103) incoming reports → stored on fan cluster
    """

    # DPs handled by custom ZCL clusters (not registered via builder)
    _CUSTOM_DPS = frozenset({1, 3, 5, 101, 103})

    def send_dp(self, dpd: TuyaDatapointData) -> None:
        """Send a single DP command immediately."""
        self.create_catching_task(
            self.command(
                self.mcu_write_command,
                TuyaCommand(
                    status=0,
                    tsn=self.endpoint.device.application.get_sequence(),
                    datapoints=[dpd],
                ),
                expect_reply=False,
            )
        )

    # ── Incoming DP parsing ─────────────────────────────────────

    def handle_get_data(self, command) -> foundation.Status:
        """Route incoming DP reports to appropriate cluster updates."""
        for record in command.datapoints:
            if record.dp in self._CUSTOM_DPS:
                try:
                    self._dp_2_attr_update(record)
                except Exception as exc:  # noqa: BLE001
                    self.warning("Error handling custom DP %s: %s", record.dp, exc)
            else:
                # Delegate builder-registered DPs (102) to parent
                try:
                    dp_handler = self.data_point_handlers[record.dp]
                    getattr(self, dp_handler)(record)
                except (AttributeError, KeyError):
                    self.debug("No datapoint handler for %s", record)
        return foundation.Status.SUCCESS

    handle_set_data_response = handle_get_data

    def _dp_2_attr_update(self, datapoint) -> None:
        """Parse incoming DP reports and update ZCL clusters."""
        dp = datapoint.dp

        # DP1: Fan on/off → update Fan cluster fan_mode
        if dp == 1:
            fan_on = bool(datapoint.data.payload)
            fan_cluster = self.endpoint.fan
            if fan_cluster and not fan_on:
                fan_cluster._update_attribute(
                    Fan.AttributeDefs.fan_mode.id, 0
                )
            # If turning on, don't update fan_mode — wait for DP3
            return

        # DP3: Fan speed → update Fan cluster fan_mode
        if dp == 3:
            dp3_val = datapoint.data.payload  # 0-8
            fan_cluster = self.endpoint.fan
            if fan_cluster:
                fan_mode = _DP3_TO_FAN_MODE.get(dp3_val, 0)
                fan_cluster._update_attribute(
                    Fan.AttributeDefs.fan_mode.id, fan_mode
                )
            return

        # DP5: Light on/off → update OnOff cluster on endpoint 2
        # Skip if direction change is in progress (MCU echoes DP5 during
        # fan stop/start but we don't want the light entity to flicker)
        if dp == 5:
            if getattr(self, "_direction_changing", False):
                return
            light_on = bool(datapoint.data.payload)
            ep2 = self.endpoint.device.endpoints.get(2)
            if ep2:
                on_off_cluster = ep2.on_off
                if on_off_cluster:
                    on_off_cluster._update_attribute(
                        OnOff.AttributeDefs.on_off.id, light_on
                    )
            return

        # DP101/DP103: Direction report → store on fan cluster for entity to read
        if dp in (101, 103):
            dir_val = int(datapoint.data.payload)
            direction = "forward" if dir_val else "reverse"
            # Store on the fan cluster instance — the patched ZHA Fan entity
            # reads this via cluster._tuya_last_direction
            fan_cluster = self.endpoint.fan
            if fan_cluster:
                fan_cluster._tuya_last_direction = direction
            return

        # Everything else: delegate to parent
        super()._dp_2_attr_update(datapoint)


# ─────────────────────────────────────────────────────────────────
# Quirk V5 — TuyaQuirkBuilder registration
# ─────────────────────────────────────────────────────────────────

(
    TuyaQuirkBuilder("_TZE200_hmgktzj2", "TS0601")
    # ── Endpoint 1: Fan entity (Fan cluster 0x0202 → fan.* domain) ──
    .adds(TuyaCeilingFanClusterNM)
    # ── Endpoint 2: Light entity (OnOff cluster → light.* domain) ──
    .adds_endpoint(2, device_type=zha.DeviceType.ON_OFF_LIGHT)
    .adds(TuyaFanLightOnOffNM, endpoint_id=2)
    # ── Color Temperature SELECT (白光/自然光/黃光) ──
    .tuya_enum(
        dp_id=102,
        attribute_name="color_temp_level",
        enum_class=ColorTempLevel,
        entity_type=EntityType.STANDARD,
        translation_key="color_temp_level",
        fallback_name="Color Temperature",
    )
    .tuya_enchantment()
    .skip_configuration()
    .add_to_registry(replacement_cluster=TuyaFanMCUCluster)
)
