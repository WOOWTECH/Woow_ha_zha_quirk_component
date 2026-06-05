"""ZHA Quirk for Simon SM0301 Curtain Controller.

Device info:
  - Model:        SM0301
  - Manufacturer: _TYZB01_koulgwmy
  - Chip:         Silicon Labs EFR32MG24
  - Firmware:     0x00000083
  - IEEE:         18:69:0a:ff:fe:25:8a:95
  - Type:         1-channel curtain controller (forward/reverse output)

This is a standard ZCL Shade device (device_type 0x0200) that uses
OnOff + LevelControl clusters for cover open/close/position.

Endpoint structure (original):
  EP1-EP4: profile=0x0104, device_type=0x0200 (SHADE)
  Each EP has: Basic, Identify, Groups, Scenes, OnOff, LevelControl,
  Shade Configuration (0x0100), and Tuya private clusters (0xFC55-FC57).

Problem: The device reports 4 identical endpoints but it is a
single-channel curtain controller. Only EP1 is functional.

Calibration:
  Physical: Press the device "Next" button twice to auto-calibrate.
  ZCL: The travel distance is stored in Shade Configuration (0x0100)
  attribute closed_limit (0x0010) as uint16 motor steps (e.g. 17800).
  Writing this attribute adjusts the travel limit directly.

  The "Reset Travel Limit" button writes closed_limit=65534 (max),
  which removes any travel restriction so the motor can run its full
  range.  Use the "Travel Limit" number entity to fine-tune the value.

  NOTE: The Tuya cloud DP3 (cur_calibration) is mapped to private
  clusters FC55/FC56/FC57 which accept ZCL writes at the protocol
  level but the device firmware does not act on them.  Auto-calibration
  can only be triggered via the physical button.

Tuya DP map (cloud):
  DP1   - control         - Enum (open/stop/close)  → OnOff
  DP2   - percent_control - Value 0-100              → LevelControl
  DP3   - cur_calibration - Enum (start/end)         → FC56 (FW-locked)
  DP7   - switch_backlight - Bool                    → FC56
  DP14  - light_mode      - Enum                     → FC56
  DP101 - backlight_num   - Value 50000-60000        → FC56

Quirk fixes:
  1. Remove phantom endpoints EP2-EP4 (only EP1 is real)
  2. Suppress useless OnOff config entities (StartUpOnOff)
  3. Suppress useless LevelControl config entities (start_up_current_level)
  4. Expose Shade closed_limit as a Number entity for travel calibration
  5. Expose "Reset Travel Limit" button (writes closed_limit=65534)
"""

from zigpy.quirks.v2 import QuirkBuilder
from zigpy.quirks.v2 import EntityType

ONOFF = 0x0006
LEVEL = 0x0008
SHADE = 0x0100

# ────────────────────────────────────────────────────────────────
# SM0301 — 1-channel curtain controller (_TYZB01_koulgwmy)
# ────────────────────────────────────────────────────────────────
(
    QuirkBuilder("_TYZB01_koulgwmy", "SM0301")
    # ── Remove phantom endpoints (only EP1 is real) ──
    .removes_endpoint(2)
    .removes_endpoint(3)
    .removes_endpoint(4)
    # ── Suppress OnOff StartUpOnOff select ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=ONOFF,
        unique_id_suffix="StartUpOnOff",
    )
    # ── Suppress LevelControl start_up_current_level number ──
    .prevent_default_entity_creation(
        endpoint_id=1, cluster_id=LEVEL,
        unique_id_suffix="start_up_current_level",
    )
    # ── Expose Shade closed_limit for travel calibration ──
    .number(
        attribute_name="closed_limit",
        cluster_id=SHADE,
        endpoint_id=1,
        min_value=100,
        max_value=65534,
        step=100,
        entity_type=EntityType.CONFIG,
        translation_key="closed_limit",
        fallback_name="Travel Limit",
    )
    # ── Reset Travel Limit button (writes max value) ──
    .write_attr_button(
        attribute_name="closed_limit",
        attribute_value=65534,
        cluster_id=SHADE,
        endpoint_id=1,
        entity_type=EntityType.CONFIG,
        translation_key="reset_travel_limit",
        fallback_name="Reset Travel Limit",
    )
    .skip_configuration()
    .add_to_registry()
)
