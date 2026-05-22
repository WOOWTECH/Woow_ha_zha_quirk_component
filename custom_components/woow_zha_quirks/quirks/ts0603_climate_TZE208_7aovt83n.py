"""ZHA Quirk for Tuya TS0603 VRV HVAC Controller (_TZE208_7aovt83n).

VRV (Variable Refrigerant Volume) central HVAC controller that manages
6 indoor air conditioning units via Tuya MCU protocol (cluster 0xEF00).

Device info:
  Model:        TS0603
  Manufacturer: _TZE208_7aovt83n
  IEEE:         A4:C1:38:38:BE:82:02:9C
  Type:         Router (mains powered)
  Modes:        Auto / Cool / Heat / Dry / Fan / F-Heat / S-Heat
  Controls:     Switch, Temperature setpoint, Fan speed (per zone)
  Zones:        6 indoor units

Protocol Notes:
  This device uses an "extended" Tuya protocol where command IDs are offset
  by 0x30 from the standard Tuya UART protocol:
    0x0031 = heartbeat/product-info (standard 0x01)
    0x0032 = network status (standard 0x02)
    0x0033 = DP query (standard 0x03)
    0x0034 = DP report (standard 0x04)

  The device responds to 0x0033 with 0x0034 DP reports. Standard commands
  (0x00-0x03) do NOT work with this device.
"""

from __future__ import annotations

import logging
from typing import Any

from zigpy.profiles import zha
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.hvac import Fan, Thermostat

from zigpy.zcl.clusters.general import Basic

from zhaquirks.tuya import (
    TUYA_MCU_VERSION_REQ,
    NoManufacturerCluster,
    TuyaCommand,
    TuyaData,
    TuyaDatapointData,
    TuyaLocalCluster,
)
from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import TuyaMCUCluster

_LOGGER = logging.getLogger(__name__)

_TUYA_MCU_CLUSTER_ID = 0xEF00

# Extended protocol command IDs (standard + 0x30 offset)
_CMD_EXT_PRODUCT_INFO = 0x0031   # Extended product info / heartbeat
_CMD_EXT_NETWORK_STATUS = 0x0032  # Extended network status (= std 0x02)
_CMD_EXT_DP_QUERY = 0x0033       # Extended DP query (= std 0x03)
_CMD_EXT_DP_REPORT = 0x0034      # Extended DP report (= std 0x04)
_CMD_EXT_DP_SET = 0x0030         # Extended DP set (= std 0x00)
# Gateway / three-level architecture commands (UART protocol)
_CMD_GW_DP_TRIGGER = 0x0028      # Gateway: trigger MCU DP report
_CMD_EXT_GW_DP_TRIGGER = 0x0058  # Extended variant of 0x28
_CMD_GW_DP_TRIGGER_ALT = 0x0038  # Alternative: 0x28 + 0x10 offset

# Module-level set to track which IEEE addresses have been init-triggered.
# This persists across Device object recreation during startup.
_VRV_INIT_TRIGGERED_IEES = set()


# ─────────────────────────────────────────────────────────────────
# Per-zone DP configuration
# ─────────────────────────────────────────────────────────────────

class ZoneDPConfig:
    """DP numbers for a single HVAC zone."""
    __slots__ = ("switch", "target_temp", "current_temp", "mode", "fan_speed")

    def __init__(self, switch, target_temp, current_temp, mode, fan_speed):
        self.switch = switch
        self.target_temp = target_temp
        self.current_temp = current_temp
        self.mode = mode
        self.fan_speed = fan_speed

    @property
    def all_dps(self):
        return {self.switch, self.target_temp, self.current_temp,
                self.mode, self.fan_speed}


_ZONE_DP_MAP = {
    1: ZoneDPConfig(switch=1, target_temp=2, current_temp=3, mode=4, fan_speed=5),
    2: ZoneDPConfig(switch=101, target_temp=102, current_temp=103, mode=104, fan_speed=105),
    3: ZoneDPConfig(switch=106, target_temp=107, current_temp=108, mode=109, fan_speed=110),
    4: ZoneDPConfig(switch=111, target_temp=112, current_temp=113, mode=114, fan_speed=115),
    5: ZoneDPConfig(switch=116, target_temp=117, current_temp=118, mode=119, fan_speed=120),
    6: ZoneDPConfig(switch=121, target_temp=122, current_temp=123, mode=124, fan_speed=125),
}

_DP_TO_ZONE: dict[int, tuple[int, str]] = {}
for _zid, _zcfg in _ZONE_DP_MAP.items():
    _DP_TO_ZONE[_zcfg.switch] = (_zid, "switch")
    _DP_TO_ZONE[_zcfg.target_temp] = (_zid, "target_temp")
    _DP_TO_ZONE[_zcfg.current_temp] = (_zid, "current_temp")
    _DP_TO_ZONE[_zcfg.mode] = (_zid, "mode")
    _DP_TO_ZONE[_zcfg.fan_speed] = (_zid, "fan_speed")

_ALL_CUSTOM_DPS = frozenset(
    dp for cfg in _ZONE_DP_MAP.values() for dp in cfg.all_dps
)


# ─────────────────────────────────────────────────────────────────
# Mode / Fan speed mappings
# ─────────────────────────────────────────────────────────────────

TUYA_MODE_AUTO   = 0
TUYA_MODE_COLD   = 1
TUYA_MODE_HOT    = 2
TUYA_MODE_WET    = 3  # Dry/Dehumidify
TUYA_MODE_WIND   = 4  # Fan only
TUYA_MODE_FHEAT  = 5  # Floor heat
TUYA_MODE_SHEAT  = 6  # Supplemental heat

_TUYA_TO_ZCL_MODE = {
    TUYA_MODE_AUTO:  Thermostat.SystemMode.Auto,
    TUYA_MODE_COLD:  Thermostat.SystemMode.Cool,
    TUYA_MODE_HOT:   Thermostat.SystemMode.Heat,
    TUYA_MODE_WET:   Thermostat.SystemMode.Dry,
    TUYA_MODE_WIND:  Thermostat.SystemMode.Fan_only,
    TUYA_MODE_FHEAT: Thermostat.SystemMode.Heat,       # Map F-Heat to Heat
    TUYA_MODE_SHEAT: Thermostat.SystemMode.Emergency_Heating,  # Map S-Heat
}

_ZCL_TO_TUYA_MODE = {v: k for k, v in _TUYA_TO_ZCL_MODE.items()}

TUYA_FAN_AUTO = 0
TUYA_FAN_LOW  = 1
TUYA_FAN_MID  = 2
TUYA_FAN_HIGH = 3

_TUYA_TO_FAN_MODE = {
    TUYA_FAN_AUTO: Fan.FanMode.Auto,
    TUYA_FAN_LOW:  Fan.FanMode.Low,
    TUYA_FAN_MID:  Fan.FanMode.Medium,
    TUYA_FAN_HIGH: Fan.FanMode.High,
}

_FAN_TO_TUYA_SPEED = {v: k for k, v in _TUYA_TO_FAN_MODE.items()}
_FAN_TO_TUYA_SPEED[Fan.FanMode.On] = TUYA_FAN_AUTO


# ─────────────────────────────────────────────────────────────────
# Helper: find MCU cluster
# ─────────────────────────────────────────────────────────────────

def _find_mcu(device):
    """Find the MCU cluster (0xEF00) on endpoint 1."""
    ep1 = device.endpoints.get(1)
    if ep1 is None:
        return None
    mcu = getattr(ep1, "tuya_manufacturer", None)
    if mcu is not None:
        return mcu
    for cluster in ep1.in_clusters.values():
        if cluster.cluster_id == _TUYA_MCU_CLUSTER_ID:
            return cluster
    return None


# ─────────────────────────────────────────────────────────────────
# Tuya VRV Thermostat Cluster (ZCL 0x0201)
# ─────────────────────────────────────────────────────────────────

class TuyaVRVThermostat(Thermostat, TuyaLocalCluster):
    """Thermostat cluster bridging Tuya DPs for one VRV HVAC zone."""

    _zone_id: int = 1

    _CONSTANT_ATTRIBUTES = {
        Thermostat.AttributeDefs.ctrl_sequence_of_oper.id:
            Thermostat.ControlSequenceOfOperation.Cooling_and_Heating,
        Thermostat.AttributeDefs.min_heat_setpoint_limit.id: 1600,
        Thermostat.AttributeDefs.min_cool_setpoint_limit.id: 1600,
        Thermostat.AttributeDefs.max_heat_setpoint_limit.id: 3000,
        Thermostat.AttributeDefs.max_cool_setpoint_limit.id: 3000,
    }

    class AttributeDefs(Thermostat.AttributeDefs):
        pass

    class ServerCommandDefs(Thermostat.ServerCommandDefs):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zone_id = self.endpoint.endpoint_id
        self._update_attribute(
            Thermostat.AttributeDefs.ctrl_sequence_of_oper.id,
            Thermostat.ControlSequenceOfOperation.Cooling_and_Heating,
        )
        self._update_attribute(
            Thermostat.AttributeDefs.system_mode.id,
            Thermostat.SystemMode.Off,
        )
        for attr_name in ("min_heat_setpoint_limit", "min_cool_setpoint_limit"):
            self._update_attribute(
                getattr(Thermostat.AttributeDefs, attr_name).id, 1600
            )
        for attr_name in ("max_heat_setpoint_limit", "max_cool_setpoint_limit"):
            self._update_attribute(
                getattr(Thermostat.AttributeDefs, attr_name).id, 3000
            )

    @property
    def _zone_cfg(self) -> ZoneDPConfig:
        return _ZONE_DP_MAP.get(self._zone_id, _ZONE_DP_MAP[1])

    async def write_attributes(
        self, attributes: dict, manufacturer: int | None = None, **kwargs
    ) -> list:
        """Intercept attribute writes to send Tuya DP commands."""
        mcu = _find_mcu(self.endpoint.device)
        if not mcu:
            _LOGGER.error("[TS0603 Z%d] MCU cluster not found", self._zone_id)
            return [[foundation.WriteAttributesStatusRecord(
                foundation.Status.SUCCESS)]]

        cfg = self._zone_cfg

        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attributes_by_name[attrid].id

            if attrid == Thermostat.AttributeDefs.system_mode.id:
                mode = Thermostat.SystemMode(value)
                if mode == Thermostat.SystemMode.Off:
                    mcu.send_dp(TuyaDatapointData(
                        cfg.switch, TuyaData(t.Bool(False))))
                else:
                    tuya_mode = _ZCL_TO_TUYA_MODE.get(mode)
                    if tuya_mode is not None:
                        mcu.send_dp(TuyaDatapointData(
                            cfg.switch, TuyaData(t.Bool(True))))
                        mcu.send_dp(TuyaDatapointData(
                            cfg.mode, TuyaData(t.enum8(tuya_mode))))
                self._update_attribute(
                    Thermostat.AttributeDefs.system_mode.id, mode)

            elif attrid in (
                Thermostat.AttributeDefs.occupied_cooling_setpoint.id,
                Thermostat.AttributeDefs.occupied_heating_setpoint.id,
            ):
                temp_tuya = int(value / 100)
                mcu.send_dp(TuyaDatapointData(
                    cfg.target_temp, TuyaData(t.uint32_t(temp_tuya))))
                self._update_attribute(attrid, value)

        return [[foundation.WriteAttributesStatusRecord(
            foundation.Status.SUCCESS)]]


class TuyaVRVThermostatNM(NoManufacturerCluster, TuyaVRVThermostat):
    pass


# ─────────────────────────────────────────────────────────────────
# Tuya VRV Fan Cluster (ZCL 0x0202)
# ─────────────────────────────────────────────────────────────────

class TuyaVRVFan(Fan, TuyaLocalCluster):
    """Fan cluster for HVAC fan speed control per zone."""

    _zone_id: int = 1

    _CONSTANT_ATTRIBUTES = {
        Fan.AttributeDefs.fan_mode_sequence.id:
            Fan.FanModeSequence.Low_Med_High_Auto,
    }

    class AttributeDefs(Fan.AttributeDefs):
        pass

    class ServerCommandDefs(Fan.ServerCommandDefs):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zone_id = self.endpoint.endpoint_id
        self._update_attribute(
            Fan.AttributeDefs.fan_mode_sequence.id,
            Fan.FanModeSequence.Low_Med_High_Auto,
        )
        self._update_attribute(Fan.AttributeDefs.fan_mode.id, 0)

    @property
    def _zone_cfg(self) -> ZoneDPConfig:
        return _ZONE_DP_MAP.get(self._zone_id, _ZONE_DP_MAP[1])

    async def write_attributes(
        self, attributes: dict, manufacturer: int | None = None, **kwargs
    ) -> list:
        mcu = _find_mcu(self.endpoint.device)
        if not mcu:
            return [[foundation.WriteAttributesStatusRecord(
                foundation.Status.SUCCESS)]]

        cfg = self._zone_cfg

        for attrid, value in attributes.items():
            if isinstance(attrid, str):
                attrid = self.attributes_by_name[attrid].id

            if attrid == Fan.AttributeDefs.fan_mode.id:
                fan_mode = Fan.FanMode(value)
                tuya_speed = _FAN_TO_TUYA_SPEED.get(fan_mode)
                if tuya_speed is not None:
                    mcu.send_dp(TuyaDatapointData(
                        cfg.fan_speed, TuyaData(t.enum8(tuya_speed))))
                self._update_attribute(attrid, value)

        return [[foundation.WriteAttributesStatusRecord(
            foundation.Status.SUCCESS)]]


class TuyaVRVFanNM(NoManufacturerCluster, TuyaVRVFan):
    pass


# ─────────────────────────────────────────────────────────────────
# Custom Basic Cluster — intercept attribute reports to trigger init
# ─────────────────────────────────────────────────────────────────

class TuyaVRVBasicCluster(Basic):
    """Custom Basic cluster that triggers 0xEF00 init on attribute reports.

    The VRV device sends periodic Basic:Report_Attributes with app_version
    and 0xFFE4. We use these as a signal that the device is online and
    proactively send extended DP queries on cluster 0xEF00.

    Report_Attributes is a general/foundation command (not cluster-specific),
    so we must override handle_message to intercept it.

    NOTE: _init_triggered is stored on the device object (not per-cluster
    instance) because multiple endpoints each get their own Basic cluster
    instance, and we only want to trigger once across all of them.
    """

    def handle_message(self, hdr, args):
        """Intercept all messages to detect attribute reports."""
        super().handle_message(hdr, args)

        # Use module-level set to track init across Device object recreations.
        device = self.endpoint.device
        ieee = str(device.ieee)
        if ieee in _VRV_INIT_TRIGGERED_IEES:
            return

        _VRV_INIT_TRIGGERED_IEES.add(ieee)
        _LOGGER.warning(
            "[TS0603 BASIC] First message received (cmd=0x%02x ep=%d "
            "ieee=%s), triggering 0xEF00 init",
            hdr.command_id,
            self.endpoint.endpoint_id,
            ieee,
        )
        mcu = _find_mcu(device)
        if mcu is None:
            _LOGGER.warning("[TS0603 BASIC] MCU cluster not found (ep=%d)",
                            self.endpoint.endpoint_id)
            _VRV_INIT_TRIGGERED_IEES.discard(ieee)  # Allow retry
            return
        # Use __dict__ to bypass zigpy Cluster.__getattr__ command lookup
        if not mcu.__dict__.get("_proactive_sent", False):
            mcu.__dict__["_proactive_sent"] = True
            mcu.create_catching_task(mcu._proactive_init())


# ─────────────────────────────────────────────────────────────────
# Custom TuyaMCU Cluster — extended protocol handshake + DP routing
# ─────────────────────────────────────────────────────────────────

class TuyaVRVMCUCluster(TuyaMCUCluster):
    """Extended TuyaMCU cluster for VRV HVAC controller.

    This device uses an "extended" Tuya protocol with command IDs offset
    by 0x30 from the standard Tuya UART protocol:
      0x0031 = product info / heartbeat (std 0x01)
      0x0032 = network status (std 0x02)
      0x0033 = DP query (std 0x03)
      0x0034 = DP report (std 0x04)

    The device responds to 0x0033 with 0x0034 DP reports.
    """

    _CUSTOM_DPS = _ALL_CUSTOM_DPS

    class ClientCommandDefs(TuyaMCUCluster.ClientCommandDefs):
        ext_product_info = foundation.ZCLCommandDef(
            id=_CMD_EXT_PRODUCT_INFO,
            schema={"payload": t.Bytes},
            is_manufacturer_specific=True,
        )
        ext_dp_report = foundation.ZCLCommandDef(
            id=_CMD_EXT_DP_REPORT,
            schema={"payload": t.Bytes},
            is_manufacturer_specific=True,
        )

    class ServerCommandDefs(TuyaMCUCluster.ServerCommandDefs):
        mcu_version_req = foundation.ZCLCommandDef(
            id=TUYA_MCU_VERSION_REQ,
            schema={"param": t.uint16_t},
            is_manufacturer_specific=False,
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Instance attributes — bypass zigpy Cluster.__getattr__ by
        # writing directly to __dict__ so they don't get intercepted
        # as command name lookups.
        self.__dict__["_heartbeat_count"] = 0
        self.__dict__["_dp_received"] = False
        self.__dict__["_init_done"] = False
        self.__dict__["_spell_cast"] = False
        self.__dict__["_proactive_sent"] = False
        self.__dict__["_dp_samples"] = []  # Collect raw 0x0034 payloads
        self.__dict__["_last_query_fmt"] = "none"  # Track query format

    def _is_controller_running(self) -> bool:
        """Check if the Zigbee ApplicationController is ready."""
        try:
            app = self.endpoint.device.application
            return app is not None and getattr(app, "_running", True)
        except (AttributeError, RuntimeError):
            return False

    async def bind(self):
        """Override bind to start proactive initialization."""
        result = await super().bind()
        if not self.__dict__.get("_proactive_sent", False):
            self.__dict__["_proactive_sent"] = True
            self.create_catching_task(self._proactive_init())
        return result

    async def _proactive_init(self):
        """Proactively initialize device communication.

        Don't wait for 0x0031 heartbeats — send extended commands
        immediately since the device may only send 0x0031 briefly at join.
        """
        import asyncio
        try:
            _LOGGER.warning("[TS0603 PROACTIVE] Starting proactive init")
            await asyncio.sleep(5)  # Wait for device to settle after join

            if not self._is_controller_running():
                _LOGGER.warning("[TS0603 PROACTIVE] Controller not ready, waiting more")
                await asyncio.sleep(10)
                if not self._is_controller_running():
                    _LOGGER.warning("[TS0603 PROACTIVE] Controller still not ready, abort")
                    # Allow re-trigger
                    self.__dict__["_proactive_sent"] = False
                    return

            # Step 1a: Send extended network status (0x0032) — we always do this
            await self._send_raw_cmd(_CMD_EXT_NETWORK_STATUS, bytes([0x01]))
            _LOGGER.warning("[TS0603 PROACTIVE] Sent ext nwk status 0x0032")
            await asyncio.sleep(1)

            # Step 1b: Also send STANDARD network status (0x0002)
            await self._send_raw_cmd(0x02, bytes([0x01]))
            _LOGGER.warning("[TS0603 PROACTIVE] Sent std nwk status 0x0002")
            await asyncio.sleep(1)

            # Step 2: Send extended DP query (0x0033)
            await self._send_ext_dp_query("init-q1")
            _LOGGER.warning("[TS0603 PROACTIVE] Sent ext DP query 0x0033")
            await asyncio.sleep(3)

            # Step 3: Also send STANDARD DP query (0x0003)
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            await self._send_raw_cmd(0x03, bytes([0x00, tsn]))
            _LOGGER.warning("[TS0603 PROACTIVE] Sent std DP query 0x0003")
            await asyncio.sleep(3)

            # Step 4: Start monitoring
            self.create_catching_task(self._periodic_poll())

        except Exception as exc:
            _LOGGER.warning("[TS0603 PROACTIVE] Init error: %s", exc)
            # Allow re-trigger on failure
            self.__dict__["_proactive_sent"] = False

    async def _periodic_poll(self):
        """Monitor 0x0034 response byte patterns over time.

        RESULTS SO FAR (all dead ends):
        - cmd 0x0033 → 0x0034 ACK only (byte 4 varies: FF/01/F8)
        - cmd 0x0030 (ext SET) → no response
        - cmd 0x00 (std SET) → no response
        - TuyaCommand via command(0x00, ...) → no response
        - cmd 0x28/0x38/0x58/0x08 (gateway triggers) → no response
        - cmd 0x0035-0x003A, 0x04-0x0A (probes) → no response

        NEW STRATEGY: Monitor byte-4 of 0x0034 over long period with
        frequent queries. Also try std 0x0003 query and 0x0024 MCU reset.
        """
        import asyncio
        d = self.__dict__
        d["_byte4_history"] = []

        _LOGGER.warning("[TS0603 POLL] === Monitoring mode (15s intervals) ===")

        # Quick test: standard DP query 0x0003 (non-extended)
        _LOGGER.warning("[TS0603 POLL] Sending std DP query 0x0003")
        try:
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            d["_last_query_fmt"] = "std-q-0x03"
            await self._send_raw_cmd(0x03, bytes([0x00, tsn]))
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] std 0x03 failed: %s", exc)
        await asyncio.sleep(5)

        # Quick test: Tuya MCU version query (0x0010 / 0x0040)
        _LOGGER.warning("[TS0603 POLL] Sending MCU version query 0x0010")
        try:
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            d["_last_query_fmt"] = "mcu-ver-0x10"
            await self._send_raw_cmd(0x10, bytes([0x00, tsn]))
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] 0x10 failed: %s", exc)
        await asyncio.sleep(3)

        _LOGGER.warning("[TS0603 POLL] Sending ext MCU version query 0x0040")
        try:
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            d["_last_query_fmt"] = "mcu-ver-0x40"
            await self._send_raw_cmd(0x40, bytes([0x00, tsn]))
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] 0x40 failed: %s", exc)
        await asyncio.sleep(3)

        # Quick test: Tuya time sync request (0x0024)
        _LOGGER.warning("[TS0603 POLL] Sending time sync 0x0024")
        try:
            import time
            ts = int(time.time())
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            d["_last_query_fmt"] = "time-0x24"
            # Tuya time sync payload: [status, tsn, utc_seconds(4bytes)]
            payload = bytes([0x00, tsn,
                             (ts >> 24) & 0xFF, (ts >> 16) & 0xFF,
                             (ts >> 8) & 0xFF, ts & 0xFF])
            await self._send_raw_cmd(0x24, payload)
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] 0x24 failed: %s", exc)
        await asyncio.sleep(3)

        # Extended time sync 0x0054
        _LOGGER.warning("[TS0603 POLL] Sending ext time sync 0x0054")
        try:
            import time
            ts = int(time.time())
            tsn = self.endpoint.device.application.get_sequence() & 0xFF
            d["_last_query_fmt"] = "time-0x54"
            payload = bytes([0x00, tsn,
                             (ts >> 24) & 0xFF, (ts >> 16) & 0xFF,
                             (ts >> 8) & 0xFF, ts & 0xFF])
            await self._send_raw_cmd(0x54, payload)
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] 0x54 failed: %s", exc)
        await asyncio.sleep(3)

        # ── Test: Send raw ZCL Read Attributes to Thermostat cluster ──
        # The quirk uses LocalDataCluster so normal reads don't go OTA.
        # Bypass by calling the base Cluster._read_attributes directly.
        _LOGGER.warning("[TS0603 POLL] === ZCL Thermostat/Fan OTA read test ===")
        try:
            from zigpy.zcl import Cluster as BaseCluster

            device = self.endpoint.device
            attrs_to_read = [0x0000, 0x0011, 0x0012, 0x001C, 0x001E]
            # 0x0000=local_temp, 0x0011=cool_sp, 0x0012=heat_sp,
            # 0x001C=system_mode, 0x001E=running_mode

            for ep_id in [1, 2]:
                ep = device.endpoints.get(ep_id)
                if ep is None:
                    continue
                thermo = ep.in_clusters.get(0x0201)
                if thermo is None:
                    continue
                _LOGGER.warning(
                    "[TS0603 POLL] EP %d: Thermostat cluster type=%s, "
                    "forcing OTA read of %s",
                    ep_id, type(thermo).__name__, attrs_to_read)
                try:
                    # Call the base Cluster._read_attributes to bypass LocalDataCluster
                    result = await BaseCluster._read_attributes(
                        thermo, attrs_to_read, manufacturer=None)
                    _LOGGER.warning(
                        "[TS0603 POLL] EP %d Thermostat OTA result: %s",
                        ep_id, result)
                except Exception as exc:
                    _LOGGER.warning(
                        "[TS0603 POLL] EP %d Thermostat OTA error: %s (%s)",
                        ep_id, exc, type(exc).__name__)
                await asyncio.sleep(5)

            # Fan cluster read
            for ep_id in [1, 2]:
                ep = device.endpoints.get(ep_id)
                if ep is None:
                    continue
                fan = ep.in_clusters.get(0x0202)
                if fan is None:
                    continue
                _LOGGER.warning(
                    "[TS0603 POLL] EP %d: Fan cluster type=%s, OTA read",
                    ep_id, type(fan).__name__)
                try:
                    result = await BaseCluster._read_attributes(
                        fan, [0x0000], manufacturer=None)
                    _LOGGER.warning(
                        "[TS0603 POLL] EP %d Fan OTA result: %s",
                        ep_id, result)
                except Exception as exc:
                    _LOGGER.warning(
                        "[TS0603 POLL] EP %d Fan OTA error: %s (%s)",
                        ep_id, exc, type(exc).__name__)
                await asyncio.sleep(5)

            # Unknown cluster 0xEB00
            ep1 = device.endpoints.get(1)
            if ep1:
                eb00 = ep1.in_clusters.get(0xEB00)
                if eb00:
                    _LOGGER.warning(
                        "[TS0603 POLL] EP 1: cluster 0xEB00 type=%s",
                        type(eb00).__name__)
                    try:
                        result = await BaseCluster._read_attributes(
                            eb00, [0, 1, 2, 3, 4, 5], manufacturer=None)
                        _LOGGER.warning(
                            "[TS0603 POLL] EP 1 0xEB00 OTA result: %s", result)
                    except Exception as exc:
                        _LOGGER.warning(
                            "[TS0603 POLL] EP 1 0xEB00 OTA error: %s (%s)",
                            exc, type(exc).__name__)
                    await asyncio.sleep(5)
        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] ZCL read test error: %s", exc)

        # ── Test: Discover Attributes + manuf-specific scan ──
        _LOGGER.warning("[TS0603 POLL] === Discover Attributes on EP1 ===")
        try:
            from zigpy.zcl import Cluster as BaseCluster
            from zigpy.zcl import foundation

            device = self.endpoint.device
            ep1 = device.endpoints.get(1)

            for cluster_id, cluster_name in [
                (0x0201, "Thermostat"),
                (0x0202, "Fan"),
                (0xEB00, "0xEB00"),
            ]:
                cluster = ep1.in_clusters.get(cluster_id)
                if cluster is None:
                    continue

                # ZCL Discover Attributes command (0x0C)
                # Start from attr 0x0000, max 20 results
                _LOGGER.warning(
                    "[TS0603 POLL] EP1 %s: Discover Attributes (0x0000-)",
                    cluster_name)
                try:
                    result = await cluster.discover_attributes(0x0000, 40)
                    _LOGGER.warning(
                        "[TS0603 POLL] EP1 %s discover result: %s",
                        cluster_name, result)
                except Exception as exc:
                    _LOGGER.warning(
                        "[TS0603 POLL] EP1 %s discover error: %s (%s)",
                        cluster_name, exc, type(exc).__name__)
                await asyncio.sleep(3)

                # Also discover from 0xE000 (Tuya manufacturer-specific range)
                _LOGGER.warning(
                    "[TS0603 POLL] EP1 %s: Discover Attributes (0xE000-)",
                    cluster_name)
                try:
                    result = await cluster.discover_attributes(0xE000, 40)
                    _LOGGER.warning(
                        "[TS0603 POLL] EP1 %s discover 0xE000+ result: %s",
                        cluster_name, result)
                except Exception as exc:
                    _LOGGER.warning(
                        "[TS0603 POLL] EP1 %s discover 0xE000+ error: %s",
                        cluster_name, exc)
                await asyncio.sleep(3)

            # Try reading Tuya-specific attr ranges on Thermostat
            thermo = ep1.in_clusters.get(0x0201)
            if thermo:
                for start_attr, label in [
                    (0xE000, "0xE000-0xE00F"),
                    (0xF000, "0xF000-0xF00F"),
                    (0x4000, "0x4000-0x400F"),
                    (0xFF00, "0xFF00-0xFF0F"),
                ]:
                    attrs = list(range(start_attr, start_attr + 16))
                    _LOGGER.warning(
                        "[TS0603 POLL] EP1 Thermostat: read %s", label)
                    try:
                        result = await BaseCluster._read_attributes(
                            thermo, attrs, manufacturer=None)
                        # Filter out UNSUPPORTED to find any real values
                        real = [r for r in result
                                if hasattr(r, 'status') and
                                r.status != foundation.Status.UNSUPPORTED_ATTRIBUTE]
                        if real:
                            _LOGGER.warning(
                                "[TS0603 POLL] EP1 Thermostat %s FOUND: %s",
                                label, real)
                        else:
                            _LOGGER.warning(
                                "[TS0603 POLL] EP1 Thermostat %s: all unsupported",
                                label)
                    except Exception as exc:
                        _LOGGER.warning(
                            "[TS0603 POLL] EP1 Thermostat %s error: %s",
                            label, exc)
                    await asyncio.sleep(3)

        except Exception as exc:
            _LOGGER.warning("[TS0603 POLL] Discover/scan error: %s", exc)

        # Now enter long monitoring loop — query every 15s for ~15 min
        for i in range(60):
            await asyncio.sleep(15)
            try:
                d["_last_query_fmt"] = f"mon-{i}"
                await self._send_ext_dp_query(f"mon-{i}")
            except Exception:
                pass

            # Print byte4 history summary every 10 queries
            if (i + 1) % 10 == 0:
                hist = d.get("_byte4_history", [])
                _LOGGER.warning(
                    "[TS0603 POLL] byte4 history (last %d): %s",
                    len(hist), " ".join(hist[-20:])
                )

    def handle_cluster_request(self, hdr, args, *, dst_addressing=None):
        """Handle incoming commands on cluster 0xEF00."""
        d = self.__dict__
        d["_heartbeat_count"] = d.get("_heartbeat_count", 0) + 1
        hb = d["_heartbeat_count"]

        cmd = hdr.command_id
        raw = self._extract_raw_bytes(args)

        # Log all non-heartbeat commands, and heartbeat at start + every 30th
        if (cmd != _CMD_EXT_PRODUCT_INFO or hb <= 5 or hb % 30 == 0):
            _LOGGER.warning(
                "[TS0603 RX] cmd=0x%04x hb#%d dp_ok=%s raw=%s args=%s",
                cmd, hb,
                d.get("_dp_received", False),
                raw.hex() if raw else "empty",
                str(args)[:200],
            )

        if cmd == _CMD_EXT_PRODUCT_INFO:
            self._handle_heartbeat(hdr, args, raw)
            return

        if cmd == _CMD_EXT_DP_REPORT:
            self._handle_ext_dp_report(hdr, args, raw)
            return

        # Log ALL other commands with full details — we're looking for
        # responses to SET commands and probes
        if cmd != _CMD_EXT_PRODUCT_INFO:
            _LOGGER.warning(
                "[TS0603 CMD] cmd=0x%04x raw=%s len=%d "
                "qfmt=%s — %s",
                cmd, raw.hex() if raw else "empty", len(raw),
                self.__dict__.get("_last_query_fmt", "?"),
                "EXTENDED" if cmd >= 0x0030 else "STANDARD",
            )

        # Try to let base class handle standard commands too
        if cmd < 0x0030:
            try:
                return super().handle_cluster_request(
                    hdr, args, dst_addressing=dst_addressing)
            except Exception as exc:
                _LOGGER.warning(
                    "[TS0603 CMD] Base handler error for 0x%04x: %s", cmd, exc)

    @staticmethod
    def _extract_raw_bytes(args) -> bytes:
        """Extract raw payload bytes from command args."""
        if not args:
            return b""
        first = args[0] if isinstance(args, (list, tuple)) else args
        p = getattr(first, "payload", None)
        if isinstance(p, (bytes, bytearray)):
            return bytes(p)
        if isinstance(first, (bytes, bytearray)):
            return bytes(first)
        return b""

    def _handle_heartbeat(self, hdr, args, raw):
        """Handle extended heartbeat (cmd 0x0031).

        CRITICAL: Respond FAST — the device only sends ~3 heartbeats before
        giving up if we don't respond correctly.
        """
        if not self._is_controller_running():
            return

        hb = self.__dict__.get("_heartbeat_count", 0)

        # FAST PATH: Respond immediately with network status + DP query
        self.create_catching_task(
            self._send_raw_cmd(_CMD_EXT_NETWORK_STATUS, bytes([0x01]))
        )
        self.create_catching_task(self._send_ext_dp_query())

        if hb == 1:
            self.create_catching_task(self._delayed_extended_init())
        elif hb % 10 == 0:
            self.create_catching_task(self._send_ext_dp_query())

    def _handle_ext_dp_report(self, hdr, args, raw):
        """Handle extended DP report (cmd 0x0034).

        Collect raw samples for format analysis. Try multiple parse strategies.
        Only mark _dp_received = True when we successfully parse at least one DP.

        Known samples so far:
          00 DD 01 20 80 00  (session 1)
          00 DE 01 00 FF 00  (session 2)
        Pattern: [status=00] [tsn] [???] [???] [???] [???]
        """
        samples = self.__dict__.get("_dp_samples", [])
        qfmt = self.__dict__.get("_last_query_fmt", "?")
        entry = f"{raw.hex() if raw else 'empty'}({qfmt})"
        samples.append(entry)
        self.__dict__["_dp_samples"] = samples

        # Track byte-4 (index 4) which varies: 0xFF, 0x01, 0xF8
        byte4_hist = self.__dict__.get("_byte4_history", [])
        if len(raw) >= 5:
            b4 = raw[4]
            byte4_hist.append(f"{b4:02x}")
            self.__dict__["_byte4_history"] = byte4_hist

        _LOGGER.warning(
            "[TS0603 DP REPORT 0x0034] #%d qfmt=%s raw=%s len=%d "
            "bytes=[%s] byte4=0x%s",
            len(samples), qfmt,
            raw.hex() if raw else "empty",
            len(raw),
            " ".join(f"0x{b:02x}" for b in raw) if raw else "",
            f"{raw[4]:02x}" if len(raw) >= 5 else "??",
        )

        # Log ALL collected samples every 5th report for easy comparison
        if len(samples) % 5 == 0 or len(samples) <= 3:
            _LOGGER.warning(
                "[TS0603 SAMPLES] %d collected: %s",
                len(samples), samples,
            )
        # Log byte4 history every 10 reports
        if len(byte4_hist) % 10 == 0:
            _LOGGER.warning(
                "[TS0603 BYTE4] history (%d): %s",
                len(byte4_hist), " ".join(byte4_hist[-30:]),
            )

        if len(raw) < 3:
            _LOGGER.warning("[TS0603 DP] Payload too short: %s", raw.hex())
            return

        # Try multiple parse strategies
        parsed = False

        # Strategy 1: Standard Tuya DP format after 2-byte header
        # [status, tsn, dp_id, dp_type, len_hi, len_lo, data...]
        parsed = self._try_parse_tuya_dp(raw)

        # Strategy 2: Maybe the format is [status, tsn, dp_id, value_hi, value_lo, 0x00]
        # where dp_type is implicit (no type byte)?
        if not parsed and len(raw) >= 5:
            self._try_parse_compact_dp(raw)

        # Strategy 3: Maybe the entire payload after status+tsn is one big DP block
        if not parsed and len(raw) >= 4:
            self._try_parse_single_value(raw)

    def _try_parse_tuya_dp(self, raw: bytes) -> bool:
        """Try to parse raw bytes as standard Tuya DP report format.

        Standard format: [status, tsn, dp_id, dp_type, len_hi, len_lo, data...]
        Returns True if at least one DP was successfully parsed with sane values.
        """
        if len(raw) < 6:
            return False

        status_byte = raw[0]
        tsn = raw[1]
        dp_data = raw[2:]

        _LOGGER.warning(
            "[TS0603 PARSE-STD] status=0x%02x tsn=0x%02x dp_payload=%s",
            status_byte, tsn, dp_data.hex(),
        )

        pos = 0
        dp_count = 0
        while pos < len(dp_data):
            if pos + 4 > len(dp_data):
                _LOGGER.warning(
                    "[TS0603 PARSE-STD] Remaining %d bytes at pos %d: %s",
                    len(dp_data) - pos, pos, dp_data[pos:].hex(),
                )
                break

            dp_id = dp_data[pos]
            dp_type = dp_data[pos + 1]
            dp_len = (dp_data[pos + 2] << 8) | dp_data[pos + 3]
            pos += 4

            # Sanity check: dp_len should be reasonable (0-255 for most DPs)
            if dp_len > 255 or pos + dp_len > len(dp_data):
                _LOGGER.warning(
                    "[TS0603 PARSE-STD] INVALID dp=%d type=%d len=%d "
                    "(remaining=%d) — standard format doesn't fit",
                    dp_id, dp_type, dp_len, len(dp_data) - pos,
                )
                return False

            dp_value_bytes = dp_data[pos:pos + dp_len]
            pos += dp_len
            dp_count += 1

            value = self._decode_dp_value(dp_type, dp_value_bytes)
            _LOGGER.warning(
                "[TS0603 PARSE-STD] OK dp=%d type=%d len=%d raw=%s value=%s",
                dp_id, dp_type, dp_len, dp_value_bytes.hex(), value,
            )

            zone_info = _DP_TO_ZONE.get(dp_id)
            if zone_info:
                zone_id, dp_func = zone_info
                self._update_zone_from_dp(zone_id, dp_func, value)
            else:
                _LOGGER.warning(
                    "[TS0603 PARSE-STD] UNKNOWN dp=%d type=%d value=%s",
                    dp_id, dp_type, value,
                )

        if dp_count > 0:
            _LOGGER.warning("[TS0603 PARSE-STD] SUCCESS: %d DPs parsed", dp_count)
            self.__dict__["_dp_received"] = True
            return True
        return False

    def _try_parse_compact_dp(self, raw: bytes):
        """Try compact format: [status, tsn, dp_id, value_byte(s), 0x00].

        Some devices send DPs without a type+length header. The trailing 0x00
        may be padding. Log the interpretation for analysis.
        """
        if len(raw) < 4:
            return
        status_byte = raw[0]
        tsn = raw[1]
        dp_id = raw[2]
        value_bytes = raw[3:]

        # Try reading remaining bytes as the value
        # If last byte is 0x00, it might be padding
        if len(value_bytes) >= 2:
            val_16 = (value_bytes[0] << 8) | value_bytes[1]
        else:
            val_16 = value_bytes[0] if value_bytes else 0

        _LOGGER.warning(
            "[TS0603 PARSE-COMPACT] dp=%d value_bytes=%s val_u16=%d "
            "val_u8=%d trailing=%s",
            dp_id,
            value_bytes.hex(),
            val_16,
            value_bytes[0] if value_bytes else 0,
            value_bytes[2:].hex() if len(value_bytes) > 2 else "none",
        )

    def _try_parse_single_value(self, raw: bytes):
        """Try treating bytes 2+ as a single value block.

        Some devices use: [status, tsn, dp_id, dp_type, value_byte]
        (3-byte DP with implicit len=1).
        """
        if len(raw) < 5:
            return
        status_byte = raw[0]
        tsn = raw[1]
        dp_id = raw[2]
        dp_type = raw[3]
        value_bytes = raw[4:]

        _LOGGER.warning(
            "[TS0603 PARSE-SINGLE] dp=%d type=%d value=%s (len=%d)",
            dp_id, dp_type, value_bytes.hex(), len(value_bytes),
        )

    @staticmethod
    def _decode_dp_value(dp_type, data: bytes):
        """Decode DP value from raw bytes based on Tuya DP type."""
        if not data:
            return None
        if dp_type == 0x01:  # raw/bytes
            return data.hex()
        if dp_type == 0x02:  # bool
            return bool(data[0])
        if dp_type == 0x04:  # enum
            return data[0]
        if dp_type == 0x05:  # value (uint32 big-endian)
            val = 0
            for b in data:
                val = (val << 8) | b
            return val
        if dp_type == 0x03:  # string
            return data.decode("utf-8", errors="replace")
        # Unknown type — return raw hex
        return f"type{dp_type}:{data.hex()}"

    def _update_zone_from_dp(self, zone_id: int, dp_func: str, value):
        """Update zone cluster attributes from decoded DP value."""
        ep = self.endpoint.device.endpoints.get(zone_id)
        if not ep:
            return

        thermostat = getattr(ep, "thermostat", None)
        fan_cluster = getattr(ep, "fan", None)

        if dp_func == "switch":
            is_on = bool(value)
            if thermostat and not is_on:
                thermostat._update_attribute(
                    Thermostat.AttributeDefs.system_mode.id,
                    Thermostat.SystemMode.Off)
            _LOGGER.warning("[TS0603 Z%d] switch=%s", zone_id, is_on)
            return

        if dp_func == "target_temp":
            temp_value = int(value)
            zcl_temp = temp_value * 10 if temp_value > 100 else temp_value * 100
            if thermostat:
                thermostat._update_attribute(
                    Thermostat.AttributeDefs.occupied_cooling_setpoint.id, zcl_temp)
                thermostat._update_attribute(
                    Thermostat.AttributeDefs.occupied_heating_setpoint.id, zcl_temp)
            _LOGGER.warning("[TS0603 Z%d] target_temp=%s (zcl=%d)", zone_id, value, zcl_temp)
            return

        if dp_func == "current_temp":
            temp_value = int(value)
            zcl_temp = temp_value * 10 if temp_value > 100 else temp_value * 100
            if thermostat:
                thermostat._update_attribute(
                    Thermostat.AttributeDefs.local_temperature.id, zcl_temp)
            _LOGGER.warning("[TS0603 Z%d] current_temp=%s (zcl=%d)", zone_id, value, zcl_temp)
            return

        if dp_func == "mode":
            mode_val = int(value)
            zcl_mode = _TUYA_TO_ZCL_MODE.get(mode_val, Thermostat.SystemMode.Auto)
            if thermostat:
                thermostat._update_attribute(
                    Thermostat.AttributeDefs.system_mode.id, zcl_mode)
            _LOGGER.warning("[TS0603 Z%d] mode=%s (zcl=%s)", zone_id, value, zcl_mode)
            return

        if dp_func == "fan_speed":
            speed_val = int(value)
            fan_mode = _TUYA_TO_FAN_MODE.get(speed_val, Fan.FanMode.Auto)
            if fan_cluster:
                fan_cluster._update_attribute(
                    Fan.AttributeDefs.fan_mode.id, fan_mode)
            _LOGGER.warning("[TS0603 Z%d] fan=%s (zcl=%s)", zone_id, value, fan_mode)
            return

    async def _delayed_extended_init(self):
        """Run full init with a 2-second delay to let fast responses go first."""
        import asyncio
        await asyncio.sleep(2)
        await self._do_extended_init()

    async def _cast_tuya_magic_spell(self):
        """Cast the Tuya 'magic spell' — read Basic attrs + write 0xFFDE."""
        import asyncio
        try:
            ep1 = self.endpoint.device.endpoints.get(1)
            if ep1 is None:
                _LOGGER.warning("[TS0603 SPELL] No endpoint 1!")
                return

            basic = ep1.in_clusters.get(Basic.cluster_id)
            if basic is None:
                _LOGGER.warning("[TS0603 SPELL] No Basic cluster!")
                return

            # Step 1: Read the magic attributes
            magic_attrs = [4, 0, 1, 5, 7, 0xFFFE]
            _LOGGER.warning("[TS0603 SPELL] Reading Basic attrs %s", magic_attrs)
            try:
                result = await basic.read_attributes(magic_attrs)
                _LOGGER.warning("[TS0603 SPELL] Read result: %s", result)
            except Exception as exc:
                _LOGGER.warning("[TS0603 SPELL] Read attrs failed: %s", exc)

            await asyncio.sleep(0.5)

            # Step 2: Write 0xFFDE = 19 (uint8) using raw write
            _LOGGER.warning("[TS0603 SPELL] Writing Basic attr 0xFFDE = 19")
            try:
                attr = foundation.Attribute(
                    attrid=0xFFDE,
                    value=foundation.TypeValue(
                        type=t.uint8_t(0x20),  # uint8 ZCL type
                        value=t.uint8_t(19),
                    ),
                )
                result = await basic.write_attributes_raw([attr])
                _LOGGER.warning("[TS0603 SPELL] Write 0xFFDE=19 result: %s", result)
            except Exception as exc:
                _LOGGER.warning("[TS0603 SPELL] Write 0xFFDE=19 failed: %s", exc)

            await asyncio.sleep(0.5)

            # Step 3: Read 0xFFE2 and 0xFFE4 for diagnostic
            for attr_id in (0xFFE2, 0xFFE4):
                try:
                    result = await basic.read_attributes_raw([attr_id])
                    _LOGGER.warning(
                        "[TS0603 SPELL] Read 0x%04X result: %s", attr_id, result)
                except Exception as exc:
                    _LOGGER.warning(
                        "[TS0603 SPELL] Read 0x%04X failed: %s", attr_id, exc)

            self.__dict__["_spell_cast"] = True
            _LOGGER.warning("[TS0603 SPELL] Magic spell cast complete")

        except Exception as exc:
            _LOGGER.warning("[TS0603 SPELL] Fatal error: %s", exc)

    async def _do_extended_init(self):
        """Full initialization using extended protocol (0x30+ commands)."""
        import asyncio
        import time as _time
        import datetime as _dt
        try:
            _LOGGER.warning("[TS0603 INIT] === EXTENDED PROTOCOL INIT ===")

            # ── Phase 1: Cast the Tuya magic spell ──
            await self._cast_tuya_magic_spell()
            await asyncio.sleep(1)

            # ── Phase 2: Extended protocol handshake ──
            _LOGGER.warning("[TS0603 INIT] Starting extended handshake")

            # 1. Extended network status (0x0032 = "gateway connected")
            await self._send_raw_cmd(_CMD_EXT_NETWORK_STATUS, bytes([0x01]))
            _LOGGER.warning("[TS0603 INIT] ext network status 0x0032 sent")
            await asyncio.sleep(0.5)

            # 2. Also send standard network status (cmd 0x02)
            await self._send_raw_cmd(0x02, bytes([0x01]))
            _LOGGER.warning("[TS0603 INIT] std network status 0x02 sent")
            await asyncio.sleep(0.5)

            # 3. Standard connection status (cmd 0x25)
            await self._send_conn_status()
            await asyncio.sleep(0.5)

            # 4. Time sync (cmd 0x24)
            try:
                now_utc = _time.gmtime()
                now_local = _dt.datetime.now()
                time_payload = bytes([
                    now_utc.tm_year - 2000, now_utc.tm_mon, now_utc.tm_mday,
                    now_utc.tm_hour, now_utc.tm_min, now_utc.tm_sec,
                    now_local.year - 2000, now_local.month, now_local.day,
                    now_local.hour, now_local.minute, now_local.second,
                ])
                await self._send_raw_cmd(0x24, time_payload)
                _LOGGER.warning("[TS0603 INIT] time sync sent")
            except Exception as exc:
                _LOGGER.warning("[TS0603 INIT] time sync failed: %s", exc)

            await asyncio.sleep(0.5)

            # 5. Extended DP query (0x0033) — THIS IS THE KEY COMMAND
            await self._send_ext_dp_query()
            await asyncio.sleep(3)

            # 6. Send another extended DP query
            await self._send_ext_dp_query()
            await asyncio.sleep(3)

            # 7. Try standard DP query too (cmd 0x03)
            try:
                await self.command(0x03)
                _LOGGER.warning("[TS0603 INIT] std DP_QUERY 0x03 sent")
            except Exception as exc:
                _LOGGER.warning("[TS0603 INIT] std DP_QUERY failed: %s", exc)

            await asyncio.sleep(2)

            # 8. Try extended DP set (cmd 0x0030) — set DP 1 = True
            try:
                # Extended set_data: same DP format but with cmd 0x0030
                tsn = self.endpoint.device.application.get_sequence()
                # DP 1 (switch), type 0x02 (bool), len 0x0001, value 0x01
                dp_payload = bytes([0x00, tsn & 0xFF, 0x01, 0x02, 0x00, 0x01, 0x01])
                await self._send_raw_cmd(_CMD_EXT_DP_SET, dp_payload)
                _LOGGER.warning("[TS0603 INIT] ext set_data 0x0030 dp1=True sent")
            except Exception as exc:
                _LOGGER.warning("[TS0603 INIT] ext set_data failed: %s", exc)

            await asyncio.sleep(2)

            # 9. Final extended DP query
            await self._send_ext_dp_query()

            self.__dict__["_init_done"] = True
            _LOGGER.warning("[TS0603 INIT] === EXTENDED INIT COMPLETE ===")

        except Exception as exc:
            _LOGGER.warning("[TS0603 INIT] Init error: %s", exc)

    async def _send_conn_status(self):
        """Send TuyaConnectionStatus (cmd 0x25) = connected."""
        try:
            conn = self.TuyaConnectionStatus()
            conn.tsn = self.endpoint.device.application.get_sequence()
            conn.status = b"\x01"
            await super(TuyaVRVMCUCluster, self).command(
                0x25, conn, expect_reply=False)
        except Exception as exc:
            _LOGGER.debug("[TS0603] conn status send error: %s", exc)

    async def _send_ext_dp_query(self, label="status+tsn"):
        """Send extended DP query (cmd 0x0033)."""
        try:
            tsn = self.endpoint.device.application.get_sequence()
            self.__dict__["_last_query_fmt"] = label
            await self._send_raw_cmd(_CMD_EXT_DP_QUERY, bytes([0x00, tsn & 0xFF]))
            _LOGGER.warning("[TS0603] EXT DP_QUERY 0x0033 sent (tsn=%d fmt=%s)", tsn, label)
        except Exception as exc:
            _LOGGER.warning("[TS0603] EXT DP_QUERY failed: %s", exc)

    async def _send_raw_cmd(self, cmd_id: int, payload: bytes):
        """Send a raw ZCL frame on cluster 0xEF00."""
        seq = self.endpoint.device.application.get_sequence()
        raw_frame = bytes([0x11, seq & 0xFF, cmd_id & 0xFF]) + payload
        await self.endpoint.device.request(
            profile=260,
            cluster=self.cluster_id,
            src_ep=self.endpoint.endpoint_id,
            dst_ep=self.endpoint.endpoint_id,
            sequence=seq,
            data=raw_frame,
            expect_reply=False,
        )

    def handle_mcu_version_response(self, payload) -> foundation.Status:
        """Handle MCU version response (cmd 0x11)."""
        _LOGGER.warning("[TS0603] MCU version response: %s", payload)
        return super().handle_mcu_version_response(payload)

    def handle_mcu_connection_status(self, payload) -> foundation.Status:
        """Handle MCU connection status request (cmd 0x25 from device)."""
        _LOGGER.warning("[TS0603] MCU connection status request: %s", payload)
        return super().handle_mcu_connection_status(payload)

    def send_dp(self, dpd: TuyaDatapointData) -> None:
        """Send a single DP command using extended protocol (cmd 0x0030)."""
        _LOGGER.warning(
            "[TS0603 DP SEND] dp=%s type=%s payload=%s",
            dpd.dp,
            getattr(dpd.data, "dp_type", "?"),
            getattr(dpd.data, "payload", "?"),
        )
        # Use extended set_data (0x0030) instead of standard (0x00)
        tsn = self.endpoint.device.application.get_sequence()
        try:
            data_bytes = dpd.data.serialize() if hasattr(dpd.data, "serialize") else b""
            dp_payload = bytes([0x00, tsn & 0xFF, dpd.dp]) + data_bytes
            self.create_catching_task(
                self._send_raw_cmd(_CMD_EXT_DP_SET, dp_payload)
            )
        except Exception:
            # Fallback to standard command
            self.create_catching_task(
                self.command(
                    self.mcu_write_command,
                    TuyaCommand(
                        status=0,
                        tsn=tsn,
                        datapoints=[dpd],
                    ),
                    expect_reply=False,
                )
            )

    # ── Incoming DP parsing (standard protocol fallback) ──────────

    def handle_get_data(self, command) -> foundation.Status:
        """Handle standard DP reports (cmd 0x01/0x02) from the device."""
        if not self.__dict__.get("_dp_received", False):
            _LOGGER.warning(
                "[TS0603] *** FIRST DP (std) RECEIVED! *** hb#%d",
                self.__dict__.get("_heartbeat_count", 0),
            )
            self.__dict__["_dp_received"] = True

        for record in command.datapoints:
            dp = record.dp
            dp_type = record.data.dp_type
            payload = record.data.payload

            _LOGGER.warning(
                "[TS0603 STD DP] dp=%d type=%s payload=%s raw=%s",
                dp, dp_type, payload,
                record.data.serialize().hex()
                if hasattr(record.data, "serialize") else "N/A",
            )

            value = payload
            zone_info = _DP_TO_ZONE.get(dp)
            if zone_info:
                zone_id, dp_func = zone_info
                self._update_zone_from_dp(zone_id, dp_func, value)
            else:
                _LOGGER.warning(
                    "[TS0603 STD DP] UNKNOWN dp=%d type=%s payload=%s",
                    dp, dp_type, payload,
                )

        return foundation.Status.SUCCESS

    handle_set_data_response = handle_get_data


# ─────────────────────────────────────────────────────────────────
# Quirk Registration — 6 climate entities (1 per zone)
# ─────────────────────────────────────────────────────────────────

_builder = TuyaQuirkBuilder("_TZE208_7aovt83n", "TS0603")

# Custom Basic cluster to trigger 0xEF00 init on device heartbeat
_builder.adds(TuyaVRVBasicCluster)

# Zone 1 on endpoint 1
_builder.adds(TuyaVRVThermostatNM)
_builder.adds(TuyaVRVFanNM)

# Zones 2-6 on endpoints 2-6
for _ep_id in range(2, 7):
    _builder.adds_endpoint(_ep_id, device_type=zha.DeviceType.THERMOSTAT)
    _builder.adds(TuyaVRVThermostatNM, endpoint_id=_ep_id)
    _builder.adds(TuyaVRVFanNM, endpoint_id=_ep_id)

(
    _builder
    .tuya_enchantment(read_attr_spell=True, data_query_spell=True)
    .skip_configuration()
    .add_to_registry(
        replacement_cluster=TuyaVRVMCUCluster,
        force_add_cluster=True,
    )
)
