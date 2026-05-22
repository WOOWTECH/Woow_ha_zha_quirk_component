"""ZHA Quirk (v2) for Zemismart ZMS-206US-4 (_TZE204_wwaeqnrf / TS0601)

4-Gang Zigbee Smart Screen Switch with full feature support.
All settings exposed as native HA entities via TuyaQuirkBuilder.

Verified DP Map (tested 2026-04-23 via zha-toolkit):
  DP  1-4   : Switch 1-4 on/off          (bool)
  DP  13    : All switches on/off        (bool)
  DP  7-10  : Countdown timer 1-4        (value, uint32 seconds)
  DP  15    : Indicator LED mode          (enum: 0=off, 1=relay, 2=position)
  DP  16    : Backlight master switch     (bool)
  DP  29-32 : Relay power-on state 1-4   (enum: 0=off, 1=on, 2=memory)
  DP  101   : Child lock                  (bool)
  DP  102   : Backlight brightness        (value, 0-100%)
  DP  103   : ON indicator color          (enum: 0-6)
  DP  104   : OFF indicator color         (enum: 0-6)
  DP  105-108: Switch 1-4 screen label    (string, write-only)

Device Signature (from scan_device):
  Endpoint 1:
    Input:  [0x0000 Basic, 0x0004 Groups, 0x0005 Scenes, 0xEF00 Tuya MCU]
    Output: [0x000A Time, 0x0019 OTA]
  Endpoint 242 (GreenPower proxy):
    Profile: 0xA1E0, Device Type: 0x0061
    Input:  []
    Output: [0x0021 GreenPower]
"""

import zigpy.types as t
from zigpy.quirks.v2 import EntityType
from zigpy.zcl import foundation
from zhaquirks.tuya.builder import TuyaQuirkBuilder


# ────────────────────────────────────────────────────────────────
# Custom Enums
# ────────────────────────────────────────────────────────────────

class IndicatorMode(t.enum8):
    """Indicator LED mode."""

    Off = 0x00
    Relay = 0x01
    Position = 0x02


class LEDColor(t.enum8):
    """LED indicator color."""

    Red = 0x00
    Blue = 0x01
    Green = 0x02
    White = 0x03
    Yellow = 0x04
    Magenta = 0x05
    Cyan = 0x06


class PowerOnState(t.enum8):
    """Power-on state after power loss."""

    Off = 0x00
    On = 0x01
    Memory = 0x02


# ────────────────────────────────────────────────────────────────
# Quirk V2 — TuyaQuirkBuilder
# ────────────────────────────────────────────────────────────────

(
    TuyaQuirkBuilder("_TZE204_wwaeqnrf", "TS0601")
    # ── 4 main switches (DP 1-4) ─────────────────────────────
    .tuya_switch(
        dp_id=1,
        attribute_name="on_off_1",
        entity_type=EntityType.STANDARD,
        translation_key="on_off_1",
        fallback_name="Switch 1",
    )
    .tuya_switch(
        dp_id=2,
        attribute_name="on_off_2",
        entity_type=EntityType.STANDARD,
        translation_key="on_off_2",
        fallback_name="Switch 2",
    )
    .tuya_switch(
        dp_id=3,
        attribute_name="on_off_3",
        entity_type=EntityType.STANDARD,
        translation_key="on_off_3",
        fallback_name="Switch 3",
    )
    .tuya_switch(
        dp_id=4,
        attribute_name="on_off_4",
        entity_type=EntityType.STANDARD,
        translation_key="on_off_4",
        fallback_name="Switch 4",
    )
    # ── All on/off (DP 13) → Switch entity ─────────────────
    .tuya_switch(
        dp_id=13,
        attribute_name="on_off_all",
        entity_type=EntityType.STANDARD,
        translation_key="on_off_all",
        fallback_name="All On/Off",
    )
    # ── Countdown timers (DP 7-10) → Number entities ─────────
    .tuya_number(
        dp_id=7,
        attribute_name="countdown_1",
        type=t.uint32_t,
        min_value=0,
        max_value=86400,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="countdown_1",
        fallback_name="Countdown 1",
    )
    .tuya_number(
        dp_id=8,
        attribute_name="countdown_2",
        type=t.uint32_t,
        min_value=0,
        max_value=86400,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="countdown_2",
        fallback_name="Countdown 2",
    )
    .tuya_number(
        dp_id=9,
        attribute_name="countdown_3",
        type=t.uint32_t,
        min_value=0,
        max_value=86400,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="countdown_3",
        fallback_name="Countdown 3",
    )
    .tuya_number(
        dp_id=10,
        attribute_name="countdown_4",
        type=t.uint32_t,
        min_value=0,
        max_value=86400,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="countdown_4",
        fallback_name="Countdown 4",
    )
    # ── Indicator LED mode (DP 15) → Select entity ───────────
    .tuya_enum(
        dp_id=15,
        attribute_name="indicator_mode",
        enum_class=IndicatorMode,
        entity_type=EntityType.CONFIG,
        translation_key="indicator_mode",
        fallback_name="Indicator Mode",
    )
    # ── Backlight switch (DP 16) → Switch entity ─────────────
    .tuya_switch(
        dp_id=16,
        attribute_name="backlight_switch",
        entity_type=EntityType.CONFIG,
        translation_key="backlight_switch",
        fallback_name="Backlight",
    )
    # ── Power-on states (DP 29-32) → Select entities ─────────
    .tuya_enum(
        dp_id=29,
        attribute_name="power_on_state_1",
        enum_class=PowerOnState,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state_1",
        fallback_name="Power On State 1",
    )
    .tuya_enum(
        dp_id=30,
        attribute_name="power_on_state_2",
        enum_class=PowerOnState,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state_2",
        fallback_name="Power On State 2",
    )
    .tuya_enum(
        dp_id=31,
        attribute_name="power_on_state_3",
        enum_class=PowerOnState,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state_3",
        fallback_name="Power On State 3",
    )
    .tuya_enum(
        dp_id=32,
        attribute_name="power_on_state_4",
        enum_class=PowerOnState,
        entity_type=EntityType.CONFIG,
        translation_key="power_on_state_4",
        fallback_name="Power On State 4",
    )
    # ── Child lock (DP 101) → Switch entity ───────────────────
    .tuya_switch(
        dp_id=101,
        attribute_name="child_lock",
        entity_type=EntityType.CONFIG,
        translation_key="child_lock",
        fallback_name="Child Lock",
    )
    # ── Backlight brightness (DP 102) → Number entity ────────
    .tuya_number(
        dp_id=102,
        attribute_name="backlight_level",
        type=t.uint32_t,
        min_value=0,
        max_value=100,
        step=1,
        entity_type=EntityType.CONFIG,
        translation_key="backlight_level",
        fallback_name="Backlight Level",
    )
    # ── ON/OFF indicator colors (DP 103-104) → Select entities
    .tuya_enum(
        dp_id=103,
        attribute_name="on_color",
        enum_class=LEDColor,
        entity_type=EntityType.CONFIG,
        translation_key="on_color",
        fallback_name="ON Indicator Color",
    )
    .tuya_enum(
        dp_id=104,
        attribute_name="off_color",
        enum_class=LEDColor,
        entity_type=EntityType.CONFIG,
        translation_key="off_color",
        fallback_name="OFF Indicator Color",
    )
    # ── Screen labels (DP 105-108) → write-only string DPs ──
    .tuya_dp_attribute(
        dp_id=105,
        attribute_name="screen_label_1",
        type=t.CharacterString,
    )
    .tuya_dp_attribute(
        dp_id=106,
        attribute_name="screen_label_2",
        type=t.CharacterString,
    )
    .tuya_dp_attribute(
        dp_id=107,
        attribute_name="screen_label_3",
        type=t.CharacterString,
    )
    .tuya_dp_attribute(
        dp_id=108,
        attribute_name="screen_label_4",
        type=t.CharacterString,
    )
    .skip_configuration()
    .add_to_registry()
)
