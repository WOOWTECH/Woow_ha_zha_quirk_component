"""ZHA Quirk (v9) for Gledopto GL-SPI-206P (_TZE284_gt5al3bl / TS0601)

Tuya Zigbee SPI Addressable LED Strip Controller (幻彩燈控制器).
Controls RGBCW addressable LED strips (WS2801, WS2811, SK6812, etc.).

WLED-style light entity: exposes a single HA `light.*` entity with
color wheel (HS), color temperature slider, brightness slider, and
scene effect dropdown — instead of individual number/select entities.

v9 Correct Scene Data Format:
  - Replaced SCENE_DATA payloads with correct format from Zigbee2MQTT
    GL-SPI-206P converter (zigbee-herdsman-converters/gledopto.ts).
    Old data used 0x00 version byte with HSV+white 10-byte color blocks
    (from standard Tuya light scenes). Correct format uses 0x01 version
    byte with built-in scene IDs and 3-byte color nodes — the format
    the Gledopto SPI MCU firmware actually understands.
  - Removed unused _send_scene_sequence_async / _send_scene_sequence.

v8 Scene Fix (endpoint attribute name):
  - Fixed `self.endpoint.color` → `self.endpoint.light_color` in all
    _dp_2_attr_update handlers (DP2, DP4, DP61). The ZCL Color cluster
    registers as `ep_attribute = "light_color"` on the endpoint, not
    "color". The KeyError was caught by handle_cluster_request's broad
    `except AttributeError` and silently dropped, preventing scene mode
    from updating OnOff/Level/Color state — which caused the HA entity
    to not reflect the device's actual scene-playing state.

v7 Incoming DP Routing Fix:
  - Override handle_get_data / handle_set_data_response so that incoming
    DP reports (command 0x01 and 0x02) for DPs 1/2/3/4/51/61 are routed
    through our custom _dp_2_attr_update method instead of being dropped
    with "No datapoint handler" warnings.
  - Root cause: the parent TuyaMCUCluster.handle_get_data only looks in
    data_point_handlers dict, which only has builder-registered DPs. Our
    light DPs (1/2/3/4/61) are handled by custom ZCL clusters and were
    never reached.

v6 Scene Fix:
  - Scene command now sends DP1=on BEFORE DP2=scene + DP51=data so the
    LED strip stays powered on during scene playback.
  - DP2 incoming handler now properly handles scene mode (mode=2) to
    keep OnOff cluster state as "on" and brightness at full during
    scene playback, preventing the light entity from showing 0%.
  - Removed unreachable super()._dp_2_attr_update() call in DP2 handler
    that caused "No datapoint handler" log warnings.

v5 Performance Fix:
  All ZCL cluster command() methods send Tuya DPs **directly** to the
  MCU cluster via fire-and-forget `create_catching_task`, bypassing the
  command bus entirely.  A deferred-batch queue in the MCU cluster
  collects DPs queued within a 15ms window and flushes them in a single
  Zigbee frame.  This eliminates the "command pileup" problem where
  the ZHA light platform's sequential await pattern would generate
  multiple separate Zigbee frames per UI interaction.

Architecture:
  - TuyaSPIOnOff       — ZCL OnOff cluster → queues DP1 to MCU batch
  - TuyaSPILevelControl — ZCL LevelControl → queues DP3 (+ DP1) to MCU batch
  - TuyaSPIColorControl — ZCL Color → queues DP2+DP61 or DP2+DP4, flushes batch
  - TuyaSPILightMCUCluster — TuyaMCU + deferred DP batch queue
  - CONFIG entities for pixel_count, chip_type, color_order, DND

DP Map:
  DP  1   : Power on/off             (bool)
  DP  2   : Work mode                (enum: 0=white, 1=colour, 2=scene, 3=music)
  DP  3   : Brightness               (value: 10-1000)
  DP  4   : Color temperature        (value: 0-1000, 0=warm, 1000=cold)
  DP  51  : Scene mode data          (raw bytes)
  DP  53  : Pixel count setting      (value: 10-1000)
  DP  61  : Color data               (raw 11-byte SmearFormater HSV payload)
  DP  101 : Color order              (enum)
  DP  102 : Chip type                (enum)
  DP  103 : Do not disturb           (bool)

DP 61 SmearFormater Protocol (11 bytes):
  Byte 0:     version       (0x00)
  Byte 1:     dimmerMode    (0x00=white, 0x01=colour)
  Byte 2:     effect        (0x00=none)
  Byte 3:     ledNumber     (segments, e.g. 0x14=20)
  Byte 4:     smearMode     (0x00=all)
  Bytes 5-6:  hue           (0-360, big-endian uint16)
  Bytes 7-8:  saturation    (0-1000, big-endian uint16)
  Bytes 9-10: value         (0-1000, big-endian uint16)
"""

from __future__ import annotations

import asyncio
import colorsys
import struct
from typing import Any

from zigpy.profiles import zha
from zigpy.quirks.v2.homeassistant import EntityType
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import LevelControl, OnOff
from zigpy.zcl.clusters.lighting import Color

from zhaquirks.tuya import (
    NoManufacturerCluster,
    TuyaCommand,
    TuyaData,
    TuyaDatapointData,
    TuyaDPType,
    TuyaLocalCluster,
)
from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import (
    TuyaClusterData,
    TuyaMCUCluster,
)


# ────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────

class WorkMode(t.enum8):
    White = 0x00
    Colour = 0x01
    Scene = 0x02
    Music = 0x03


class ChipType(t.enum8):
    WS2801 = 0x00
    LPD6803 = 0x01
    LPD8803 = 0x02
    WS2811 = 0x03
    TM1814B = 0x04
    TM1934A = 0x05
    SK6812 = 0x06
    SK9822 = 0x07
    UCS8904B = 0x08
    WS2805 = 0x09


class ColorOrder(t.enum8):
    RGB = 0x00
    RBG = 0x01
    GRB = 0x02
    GBR = 0x03
    BRG = 0x04
    BGR = 0x05
    RGBW = 0x09
    RBGW = 0x0A
    GRBW = 0x0B
    GBRW = 0x0C
    BRGW = 0x0D
    BGRW = 0x0E
    WRGB = 0x0F
    WRBG = 0x10
    WGRB = 0x11


class ScenePreset(t.enum8):
    Iceland_Blue = 0x00
    Glacier_Express = 0x01
    Sea_of_Clouds = 0x02
    Fireworks_at_Sea = 0x03
    Firefly_Night = 0x04
    Grassland = 0x05
    Northern_Lights = 0x06
    Late_Autumn = 0x07
    Game = 0x08
    Holiday = 0x09
    Party = 0x0A
    Trend = 0x0B
    Meditation = 0x0C
    Dating = 0x0D
    Valentines_Day = 0x0E
    Neon_World = 0x0F


# ────────────────────────────────────────────────────────────────
# Scene data payloads — correct format from Zigbee2MQTT GL-SPI-206P converter.
# Format: version(0x01) + scene_id(1) + effect_type(1) + speed(1) + gap(1)
#         + per-color-node: hue_flags(1) + hue(1) + brightness(1)
# ────────────────────────────────────────────────────────────────

SCENE_DATA = {
    # 0x00 = Iceland Blue
    0x00: bytes([0x01, 0x15, 0x0a, 0x52, 0x52,
                 0xe0, 0x00, 0x00, 0x64,
                 0x00, 0xc1, 0x61,
                 0x00, 0xb4, 0x30,
                 0x00, 0xb5, 0x52,
                 0x00, 0xc4, 0x63]),
    # 0x01 = Glacier Express
    0x01: bytes([0x01, 0x16, 0x0a, 0x64, 0x64,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0x92, 0x5f,
                 0x00, 0xc6, 0x60]),
    # 0x02 = Sea of Clouds
    0x02: bytes([0x01, 0x17, 0x03, 0x5e, 0x5e,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0x38, 0x2f,
                 0x00, 0x1e, 0x5c,
                 0x00, 0xd5, 0x45,
                 0x01, 0x1a, 0x64]),
    # 0x03 = Fireworks at Sea
    0x03: bytes([0x01, 0x18, 0x02, 0x64, 0x64,
                 0xe0, 0x00, 0x00, 0x64,
                 0x00, 0xb2, 0x39,
                 0x01, 0x0a, 0x64,
                 0x01, 0x2d, 0x64,
                 0x01, 0x3f, 0x64]),
    # 0x04 = Firefly Night
    0x04: bytes([0x01, 0x1a, 0x03, 0x4b, 0x4b,
                 0xe0, 0x00, 0x00, 0x64,
                 0x00, 0xe0, 0x39,
                 0x01, 0x09, 0x53]),
    # 0x05 = Grassland
    0x05: bytes([0x01, 0x1c, 0x0a, 0x5a, 0x5a,
                 0xe0, 0x00, 0x00, 0x52,
                 0x00, 0x9d, 0x64,
                 0x00, 0x8e, 0x64]),
    # 0x06 = Northern Lights
    0x06: bytes([0x01, 0x1d, 0x03, 0x52, 0x52,
                 0xe0, 0x00, 0x00, 0x64,
                 0x00, 0xae, 0x64,
                 0x00, 0xa6, 0x64,
                 0x00, 0xc1, 0x64,
                 0x00, 0xcc, 0x64]),
    # 0x07 = Late Autumn
    0x07: bytes([0x01, 0x1e, 0x0a, 0x52, 0x52,
                 0xe0, 0x00, 0x00, 0x64,
                 0x00, 0x19, 0x64,
                 0x00, 0x22, 0x5e,
                 0x00, 0x2c, 0x5b,
                 0x00, 0x14, 0x64,
                 0x00, 0x0c, 0x64]),
    # 0x08 = Game
    0x08: bytes([0x01, 0x1f, 0x02, 0x5f, 0x5f,
                 0x60, 0x00, 0x00, 0x64,
                 0x01, 0x10, 0x64,
                 0x00, 0xd2, 0x64,
                 0x00, 0xad, 0x64,
                 0x00, 0x8b, 0x64]),
    # 0x09 = Holiday
    0x09: bytes([0x01, 0x20, 0x0a, 0x55, 0x55,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0xc2, 0x58,
                 0x01, 0x3e, 0x33,
                 0x00, 0xff, 0x46,
                 0x01, 0x1d, 0x64]),
    # 0x0A = Party
    0x0A: bytes([0x01, 0x22, 0x04, 0x64, 0x64,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0xd7, 0x5c,
                 0x00, 0xbc, 0x53,
                 0x00, 0x37, 0x1e,
                 0x00, 0x2c, 0x3f,
                 0x01, 0x61, 0x3f]),
    # 0x0B = Trend
    0x0B: bytes([0x01, 0x23, 0x02, 0x64, 0x64,
                 0x60, 0x00, 0x00, 0x64,
                 0x01, 0x08, 0x4b,
                 0x00, 0xb1, 0x2f,
                 0x00, 0xcd, 0x57]),
    # 0x0C = Meditation
    0x0C: bytes([0x01, 0x25, 0x03, 0x43, 0x43,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0xb7, 0x35,
                 0x00, 0x9b, 0x54,
                 0x00, 0xcd, 0x61]),
    # 0x0D = Dating
    0x0D: bytes([0x01, 0x26, 0x01, 0x59, 0x59,
                 0xe0, 0x00, 0x00, 0x64,
                 0x01, 0x19, 0x47,
                 0x01, 0x49, 0x3d,
                 0x00, 0xcd, 0x61,
                 0x00, 0x26, 0x64]),
    # 0x0E = Valentines Day
    0x0E: bytes([0x01, 0x2a, 0x01, 0x64, 0x64,
                 0x60, 0x00, 0x00, 0x64,
                 0x01, 0x15, 0x64,
                 0x01, 0x05, 0x64,
                 0x01, 0x45, 0x64,
                 0x01, 0x2f, 0x64]),
    # 0x0F = Neon World
    0x0F: bytes([0x01, 0x37, 0x0a, 0x5a, 0x5a,
                 0x60, 0x00, 0x00, 0x64,
                 0x00, 0x33, 0x58,
                 0x00, 0x18, 0x64,
                 0x01, 0x00, 0x45,
                 0x00, 0xe3, 0x5e,
                 0x00, 0xac, 0x30]),
}

SCENE_NAMES = [e.name.replace("_", " ") for e in ScenePreset]


# ────────────────────────────────────────────────────────────────
# Color conversion helpers
# ────────────────────────────────────────────────────────────────

def _xy_to_hs(x: float, y: float) -> tuple[int, int]:
    """Convert CIE xy (0.0-1.0) to Tuya HSV (hue 0-360, sat 0-1000)."""
    if y < 0.001:
        return (0, 0)
    Y = 1.0
    X = (Y / y) * x
    Z = (Y / y) * (1.0 - x - y)
    r = X * 3.2406 - Y * 1.5372 - Z * 0.4986
    g = -X * 0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 - Y * 0.2040 + Z * 1.0570
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (round(h * 360) % 360, round(s * 1000))


def _hs_to_xy(hue: int, sat: int) -> tuple[int, int]:
    """Convert Tuya HSV (hue 0-360, sat 0-1000) to CIE xy (0-65535)."""
    h = (hue % 360) / 360.0
    s = min(1000, max(0, sat)) / 1000.0
    r, g, b = colorsys.hsv_to_rgb(h, s, 1.0)
    X = r * 0.4124 + g * 0.3576 + b * 0.1805
    Y = r * 0.2126 + g * 0.7152 + b * 0.0722
    Z = r * 0.0193 + g * 0.1192 + b * 0.9505
    total = X + Y + Z
    if total < 0.001:
        cx, cy = 0.3127, 0.3290
    else:
        cx = X / total
        cy = Y / total
    return (round(cx * 65535), round(cy * 65535))


# ────────────────────────────────────────────────────────────────
# Custom ZCL OnOff Cluster — bridges DP1
# ────────────────────────────────────────────────────────────────

class TuyaSPIOnOff(OnOff, TuyaLocalCluster):
    """OnOff cluster bridging Tuya DP1.

    Queues DP1 to MCU batch queue for deferred sending.
    """

    class AttributeDefs(OnOff.AttributeDefs):
        pass

    class ServerCommandDefs(OnOff.ServerCommandDefs):
        pass

    def _get_mcu(self):
        """Get the MCU cluster."""
        return self.endpoint.tuya_manufacturer

    async def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs: Any,
    ):
        """Route on/off commands directly to MCU batch queue."""
        if command_id in (0x0000, 0x0001):
            on_val = bool(command_id)
            mcu = self._get_mcu()
            mcu.queue_dp(TuyaDatapointData(1, TuyaData(t.Bool(on_val))))
            # Update local attribute immediately for responsive UI
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


class TuyaSPIOnOffNM(NoManufacturerCluster, TuyaSPIOnOff):
    """OnOff cluster with no manufacturer ID."""


# ────────────────────────────────────────────────────────────────
# Custom ZCL LevelControl Cluster — bridges DP3
# ────────────────────────────────────────────────────────────────

class TuyaSPILevelControl(LevelControl, TuyaLocalCluster):
    """LevelControl cluster bridging Tuya DP3 (brightness 10-1000).

    Queues DP3 (and DP1 for on_off) to MCU batch queue.
    """

    class AttributeDefs(LevelControl.AttributeDefs):
        pass

    def _get_mcu(self):
        """Get the MCU cluster."""
        return self.endpoint.tuya_manufacturer

    async def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs: Any,
    ):
        """Route level commands directly to MCU batch queue."""
        level = kwargs.get("level") or (args[0] if args else 0)

        # move_to_level (0x0000), move_to_level_with_on_off (0x0004)
        if command_id in (0x0000, 0x0004):
            mcu = self._get_mcu()

            # For move_to_level_with_on_off, also queue on/off
            if command_id == 0x0004:
                on_val = bool(level)
                mcu.queue_dp(TuyaDatapointData(1, TuyaData(t.Bool(on_val))))
                # Update OnOff attribute
                on_off_cluster = self.endpoint.on_off
                if on_off_cluster:
                    on_off_cluster._update_attribute(
                        OnOff.AttributeDefs.on_off.id, on_val
                    )
                if not on_val:
                    return foundation.GENERAL_COMMANDS[
                        foundation.GeneralCommand.Default_Response
                    ].schema(
                        command_id=command_id,
                        status=foundation.Status.SUCCESS,
                    )

            # Map ZCL level (1-254) to Tuya brightness (10-1000)
            tuya_brightness = max(10, min(1000, round(
                (level - 1) * 990 / 253 + 10
            )))
            mcu.queue_dp(
                TuyaDatapointData(3, TuyaData(t.uint16_t(tuya_brightness)))
            )
            # Update local level attribute immediately
            self._update_attribute(
                LevelControl.AttributeDefs.current_level.id, level
            )
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(
            command_id=command_id,
            status=foundation.Status.UNSUP_CLUSTER_COMMAND,
        )


# ────────────────────────────────────────────────────────────────
# Custom ZCL Color Cluster — bridges DP2/DP4/DP61/DP51
# ────────────────────────────────────────────────────────────────

class TuyaSPIColorControl(Color, TuyaLocalCluster):
    """Color cluster bridging Tuya DPs for color, temp, and scene effects.

    Queues color DPs to MCU batch queue AND immediately flushes the
    entire batch (including any pending on/off + brightness DPs).
    """

    _CAPABILITIES = 0x01 | 0x02 | 0x08 | 0x10

    class AttributeDefs(Color.AttributeDefs):
        pass

    def __init__(self, *args, **kwargs):
        """Initialize with color temp range and capabilities."""
        super().__init__(*args, **kwargs)
        self._update_attribute(
            Color.AttributeDefs.color_capabilities.id, self._CAPABILITIES
        )
        self._update_attribute(
            Color.AttributeDefs.color_temp_physical_min.id, 153
        )
        self._update_attribute(
            Color.AttributeDefs.color_temp_physical_max.id, 370
        )
        self._update_attribute(
            Color.AttributeDefs.color_mode.id, 2
        )

    def _get_mcu(self):
        """Get the MCU cluster."""
        return self.endpoint.tuya_manufacturer

    async def command(
        self,
        command_id: foundation.GeneralCommand | int | t.uint8_t,
        *args,
        manufacturer: int | t.uint16_t | None = None,
        expect_reply: bool = True,
        tsn: int | t.uint8_t | None = None,
        **kwargs: Any,
    ):
        """Route color commands to MCU and flush the batch."""
        mcu = self._get_mcu()

        # move_to_color (0x0007) — XY color
        if command_id == 0x0007:
            color_x = kwargs.get("color_x") or (args[0] if len(args) > 0 else 0)
            color_y = kwargs.get("color_y") or (args[1] if len(args) > 1 else 0)
            x_norm = color_x / 65535.0
            y_norm = color_y / 65535.0
            hue, sat = _xy_to_hs(x_norm, y_norm)

            mcu.queue_color_hs(hue, sat)
            # Update local XY attributes immediately
            self._update_attribute(Color.AttributeDefs.current_x.id, color_x)
            self._update_attribute(Color.AttributeDefs.current_y.id, color_y)
            self._update_attribute(Color.AttributeDefs.color_mode.id, 1)
            # Flush all pending DPs NOW (on/off + brightness + color in one frame)
            mcu.flush_batch()
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        # move_to_color_temperature (0x000A)
        if command_id == 0x000A:
            color_temp_mireds = kwargs.get("color_temp_mireds") or (
                args[0] if args else 370
            )
            color_temp_mireds = max(153, min(370, color_temp_mireds))

            mcu.queue_color_temp(color_temp_mireds)
            self._update_attribute(
                Color.AttributeDefs.color_temperature.id, color_temp_mireds
            )
            self._update_attribute(Color.AttributeDefs.color_mode.id, 2)
            # Flush all pending DPs NOW
            mcu.flush_batch()
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        # move_to_hue_and_saturation (0x0006)
        if command_id == 0x0006:
            hue = kwargs.get("hue") or (args[0] if len(args) > 0 else 0)
            saturation = kwargs.get("saturation") or (
                args[1] if len(args) > 1 else 0
            )
            tuya_hue = round(hue * 360 / 254)
            tuya_sat = round(saturation * 1000 / 254)

            mcu.queue_color_hs(tuya_hue, tuya_sat)
            xy = _hs_to_xy(tuya_hue, tuya_sat)
            self._update_attribute(Color.AttributeDefs.current_x.id, xy[0])
            self._update_attribute(Color.AttributeDefs.current_y.id, xy[1])
            self._update_attribute(Color.AttributeDefs.color_mode.id, 0)
            mcu.flush_batch()
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(
            command_id=command_id,
            status=foundation.Status.UNSUP_CLUSTER_COMMAND,
        )


# ────────────────────────────────────────────────────────────────
# TuyaMCU Cluster — DP parsing, routing, and deferred batch queue
# ────────────────────────────────────────────────────────────────

# Batch flush delay in seconds.  Short enough to feel instant,
# long enough for the ZHA light platform to queue all its commands
# (OnOff → Level → Color) before we flush.
_BATCH_FLUSH_DELAY = 0.015  # 15 ms


class TuyaSPILightMCUCluster(TuyaMCUCluster):
    """Extended TuyaMCU cluster with deferred DP batch queue.

    The ZHA light platform sends multiple sequential ZCL commands for a
    single UI action (e.g., move_to_level_with_on_off → move_to_color).
    Instead of sending each DP separately, we collect them in a queue
    and flush them all in a single Zigbee frame.

    Queue lifecycle:
      1. ZCL cluster calls queue_dp() → DP added to _pending_dps dict
      2. A 15ms timer starts (or resets) — auto-flush safety net
      3. Color cluster calls flush_batch() → sends all pending DPs NOW
      4. If no Color command comes (simple on/off), timer flushes after 15ms
    """

    _current_hue: int = 0
    _current_saturation: int = 1000
    _current_value: int = 1000
    _led_segments: int = 20

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deferred DP batch: dict keyed by DP number to allow dedup
        self._pending_dps: dict[int, TuyaDatapointData] = {}
        self._flush_handle: asyncio.TimerHandle | None = None

    # ── Batch queue API ─────────────────────────────────────────

    def queue_dp(self, dpd: TuyaDatapointData) -> None:
        """Add a DP to the pending batch, replacing any existing DP with same id.

        Starts or resets the auto-flush timer.
        """
        self._pending_dps[dpd.dp] = dpd
        self._schedule_flush()

    def queue_color_hs(self, hue: int, sat: int) -> None:
        """Queue DP2=colour + DP61 SmearFormater for HS color."""
        self._current_hue = hue
        self._current_saturation = sat
        payload = struct.pack(
            ">BBBBBHHH",
            0x00,  # version
            0x01,  # dimmerMode = colour
            0x00,  # effect
            self._led_segments,
            0x00,  # smearMode = all
            self._current_hue,
            self._current_saturation,
            self._current_value,
        )
        self._pending_dps[2] = TuyaDatapointData(
            2, TuyaData(t.enum8(0x01))
        )
        self._pending_dps[61] = self._make_raw_dpd(61, payload)
        # Remove conflicting white-mode DPs if present
        self._pending_dps.pop(4, None)

    def queue_color_temp(self, mireds: int) -> None:
        """Queue DP2=white + DP4 for color temperature."""
        tuya_temp = round((370 - mireds) / (370 - 153) * 1000)
        tuya_temp = max(0, min(1000, tuya_temp))
        self._pending_dps[2] = TuyaDatapointData(
            2, TuyaData(t.enum8(0x00))
        )
        self._pending_dps[4] = TuyaDatapointData(
            4, TuyaData(t.uint16_t(tuya_temp))
        )
        # Remove conflicting colour-mode DPs if present
        self._pending_dps.pop(61, None)

    def flush_batch(self) -> None:
        """Send all pending DPs in one Zigbee frame immediately."""
        self._cancel_flush_timer()
        if not self._pending_dps:
            return
        dpds = list(self._pending_dps.values())
        self._pending_dps.clear()
        self._fire_dp_commands(dpds)

    def _schedule_flush(self) -> None:
        """Start or reset the auto-flush timer."""
        self._cancel_flush_timer()
        try:
            loop = asyncio.get_running_loop()
            self._flush_handle = loop.call_later(
                _BATCH_FLUSH_DELAY, self.flush_batch
            )
        except RuntimeError:
            # No event loop — flush immediately (shouldn't happen in HA)
            self.flush_batch()

    def _cancel_flush_timer(self) -> None:
        """Cancel pending auto-flush timer."""
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

    def _fire_dp_commands(self, dpds: list[TuyaDatapointData]) -> None:
        """Fire-and-forget: send DPs in one Zigbee frame."""
        self.create_catching_task(
            self.command(
                self.mcu_write_command,
                TuyaCommand(
                    status=0,
                    tsn=self.endpoint.device.application.get_sequence(),
                    datapoints=dpds,
                ),
                expect_reply=False,
            )
        )

    # ── Helpers ─────────────────────────────────────────────────

    def _make_raw_dpd(self, dp: int, raw_bytes: bytes) -> TuyaDatapointData:
        """Create TuyaDatapointData with RAW dp_type."""
        data = TuyaData()
        data.dp_type = TuyaDPType.RAW
        data.raw = raw_bytes
        return TuyaDatapointData(dp, data)

    def _send_dp_command(self, dpd: TuyaDatapointData) -> None:
        """Send a single DP immediately (for non-light operations)."""
        self._fire_dp_commands([dpd])

    def _send_dp_commands(self, dpds: list[TuyaDatapointData]) -> None:
        """Send multiple DPs immediately (for non-light operations)."""
        self._fire_dp_commands(dpds)


    # ── Incoming DP parsing ─────────────────────────────────────

    # DPs handled by our custom ZCL clusters (not registered via builder)
    _CUSTOM_DPS = frozenset({1, 2, 3, 4, 51, 61})

    def handle_get_data(self, command) -> foundation.Status:
        """Override parent to route custom DPs through _dp_2_attr_update.

        The parent's handle_get_data only looks in data_point_handlers dict,
        which only contains DPs registered via the TuyaQuirkBuilder (51 scene
        select, 53 pixel count, 101/102/103 config). DPs 1/2/3/4/61 are
        handled by our custom ZCL clusters and must be routed here.

        IMPORTANT: This method is called from handle_cluster_request which
        wraps the call in `try: ... except AttributeError:`. If any code
        inside this method raises AttributeError, the parent catches it and
        logs "No 'handle_get_data' tuya handler found". We must be careful
        not to let AttributeErrors escape.
        """
        for record in command.datapoints:
            if record.dp in self._CUSTOM_DPS:
                try:
                    self._dp_2_attr_update(record)
                except Exception as exc:  # noqa: BLE001
                    self.warning("Error handling custom DP %s: %s", record.dp, exc)
            else:
                # Delegate builder-registered DPs to parent handler
                try:
                    dp_handler = self.data_point_handlers[record.dp]
                    getattr(self, dp_handler)(record)
                except (AttributeError, KeyError):
                    self.debug("No datapoint handler for %s", record)
        return foundation.Status.SUCCESS

    # Alias: set_data_response uses the same path as get_data
    handle_set_data_response = handle_get_data

    def _dp_2_attr_update(self, datapoint) -> None:
        """Parse incoming DP reports and update ZCL clusters."""
        dp = datapoint.dp

        # DP1: on_off → update OnOff cluster
        if dp == 1:
            on_off_cluster = self.endpoint.on_off
            if on_off_cluster:
                on_off_cluster._update_attribute(
                    OnOff.AttributeDefs.on_off.id,
                    bool(datapoint.data.payload),
                )
            return

        # DP3: brightness → update LevelControl cluster
        if dp == 3:
            level_cluster = self.endpoint.level
            if level_cluster:
                tuya_val = datapoint.data.payload  # 10-1000
                zcl_level = max(1, min(254, round((tuya_val - 10) * 253 / 990 + 1)))
                level_cluster._update_attribute(
                    LevelControl.AttributeDefs.current_level.id, zcl_level
                )
            return

        # DP4: color_temperature → update Color cluster
        if dp == 4:
            color_cluster = self.endpoint.light_color
            if color_cluster:
                tuya_val = datapoint.data.payload  # 0-1000
                mireds = round(370 - (tuya_val / 1000.0) * (370 - 153))
                color_cluster._update_attribute(
                    Color.AttributeDefs.color_temperature.id, mireds
                )
                color_cluster._update_attribute(
                    Color.AttributeDefs.color_mode.id, 2
                )
            return

        # DP2: work_mode → update Color cluster color_mode
        if dp == 2:
            mode = datapoint.data.payload
            color_cluster = self.endpoint.light_color
            on_off_cluster = self.endpoint.on_off
            level_cluster = self.endpoint.level

            if mode == 0:  # white mode
                if color_cluster:
                    color_cluster._update_attribute(
                        Color.AttributeDefs.color_mode.id, 2  # color_temp
                    )
            elif mode == 1:  # colour mode
                if color_cluster:
                    color_cluster._update_attribute(
                        Color.AttributeDefs.color_mode.id, 1  # xy
                    )
            elif mode == 2:  # scene mode
                # v6 FIX: Keep light entity showing "on" during scene playback.
                # The device is actively running a scene effect, so ensure
                # OnOff stays on and brightness stays at full.
                if on_off_cluster:
                    on_off_cluster._update_attribute(
                        OnOff.AttributeDefs.on_off.id, True
                    )
                if level_cluster:
                    level_cluster._update_attribute(
                        LevelControl.AttributeDefs.current_level.id, 254
                    )
                if color_cluster:
                    color_cluster._update_attribute(
                        Color.AttributeDefs.color_mode.id, 1  # xy
                    )
            elif mode == 3:  # music mode
                if on_off_cluster:
                    on_off_cluster._update_attribute(
                        OnOff.AttributeDefs.on_off.id, True
                    )
                if level_cluster:
                    level_cluster._update_attribute(
                        LevelControl.AttributeDefs.current_level.id, 254
                    )
                if color_cluster:
                    color_cluster._update_attribute(
                        Color.AttributeDefs.color_mode.id, 1  # xy
                    )
            # v6 FIX: Do NOT call super()._dp_2_attr_update() for DP2.
            # The parent TuyaMCUCluster looks for a registered datapoint
            # handler for DP2, but we never registered one via the builder
            # (DP2 is handled entirely by our custom ZCL clusters).
            # Calling super() causes "No datapoint handler for dp=2" warnings.
            return

        # DP61: SmearFormater color data → update Color cluster XY
        if dp == 61 and datapoint.data.dp_type == TuyaDPType.RAW:
            raw = datapoint.data.raw
            if len(raw) >= 11:
                hue = struct.unpack(">H", raw[5:7])[0]
                sat = struct.unpack(">H", raw[7:9])[0]
                val = struct.unpack(">H", raw[9:11])[0]
                self._current_hue = hue
                self._current_saturation = sat
                self._current_value = val
                color_cluster = self.endpoint.light_color
                if color_cluster:
                    xy = _hs_to_xy(hue, sat)
                    color_cluster._update_attribute(
                        Color.AttributeDefs.current_x.id, xy[0]
                    )
                    color_cluster._update_attribute(
                        Color.AttributeDefs.current_y.id, xy[1]
                    )
                    color_cluster._update_attribute(
                        Color.AttributeDefs.color_mode.id, 1
                    )
                level_cluster = self.endpoint.level
                if level_cluster and val > 0:
                    zcl_level = max(1, min(254, round(val * 254 / 1000)))
                    level_cluster._update_attribute(
                        LevelControl.AttributeDefs.current_level.id,
                        zcl_level,
                    )
            return

        # DP51: scene data — ignore incoming
        if dp == 51 and datapoint.data.dp_type == TuyaDPType.RAW:
            return

        # Everything else: delegate to parent for MCU attribute mapping
        super()._dp_2_attr_update(datapoint)

    # ── Command bus handler (for non-light entities like scene select) ──

    def tuya_mcu_command(self, cluster_data: TuyaClusterData):
        """Handle commands from ZCL clusters routed via command bus.

        Light-related DPs (1, 2, 3, 4, 61) are now handled directly by
        the ZCL clusters via queue_dp/queue_color_*/flush_batch, bypassing
        this method entirely.
        """

        # --- Scene select → DP1=on + DP2=scene + DP51=raw ---
        if cluster_data.cluster_attr == "scene_select":
            scene_id = int(cluster_data.attr_value)
            scene_bytes = SCENE_DATA.get(scene_id)
            if scene_bytes is None:
                self.warning("Unknown scene ID: %s", scene_id)
                return
            # Send DP1=on, DP2=scene_mode, DP51=scene_data in one frame
            # (matching Zigbee2MQTT's approach for GL-SPI-206P)
            self._send_dp_commands([
                TuyaDatapointData(1, TuyaData(t.Bool(True))),
                TuyaDatapointData(2, TuyaData(t.enum8(0x02))),
                self._make_raw_dpd(51, scene_bytes),
            ])
            # Update local state to reflect scene is active and light is on
            on_off_cluster = self.endpoint.on_off
            if on_off_cluster:
                on_off_cluster._update_attribute(
                    OnOff.AttributeDefs.on_off.id, True
                )
            level_cluster = self.endpoint.level
            if level_cluster:
                level_cluster._update_attribute(
                    LevelControl.AttributeDefs.current_level.id, 254
                )
            self.update_attribute("scene_select", scene_id)
            return

        # Everything else: delegate to parent
        super().tuya_mcu_command(cluster_data)


# ────────────────────────────────────────────────────────────────
# Quirk V2 — TuyaQuirkBuilder
# ────────────────────────────────────────────────────────────────

(
    TuyaQuirkBuilder("_TZE284_gt5al3bl", "TS0601")
    # ── Force device type to EXTENDED_COLOR_LIGHT so ZHA creates light.* entity ──
    .replaces_endpoint(1, device_type=zha.DeviceType.EXTENDED_COLOR_LIGHT)
    # ── Light entity clusters (creates HA light.* entity) ──
    .adds(TuyaSPIOnOffNM)
    .adds(TuyaSPILevelControl)
    .adds(TuyaSPIColorControl)
    # ── Scene preset (exposed as select — like WLED preset entity) ──
    .tuya_enum(
        dp_id=51,
        attribute_name="scene_select",
        enum_class=ScenePreset,
        entity_type=EntityType.STANDARD,
        translation_key="scene_select",
        fallback_name="Scene",
    )
    # ── Pixel count (CONFIG) ──
    .tuya_number(
        dp_id=53,
        type=t.uint16_t,
        attribute_name="pixel_count",
        min_value=10,
        max_value=1000,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="pixel_count",
        fallback_name="LED pixel count",
    )
    # ── Chip type (CONFIG) ──
    .tuya_enum(
        dp_id=102,
        attribute_name="chip_type",
        enum_class=ChipType,
        entity_type=EntityType.CONFIG,
        translation_key="chip_type",
        fallback_name="LED chip type",
    )
    # ── Color order (CONFIG) ──
    .tuya_enum(
        dp_id=101,
        attribute_name="color_order",
        enum_class=ColorOrder,
        entity_type=EntityType.CONFIG,
        translation_key="color_order",
        fallback_name="Color order",
    )
    # ── Do not disturb (CONFIG) ──
    .tuya_switch(
        dp_id=103,
        attribute_name="do_not_disturb",
        entity_type=EntityType.CONFIG,
        translation_key="do_not_disturb",
        fallback_name="Do not disturb",
    )
    # ── Enchantment for periodic state polling ──
    .tuya_enchantment()
    .skip_configuration()
    .add_to_registry(replacement_cluster=TuyaSPILightMCUCluster)
)
