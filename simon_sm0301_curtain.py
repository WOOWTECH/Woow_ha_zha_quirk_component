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
  WindowCovering (0x0100), and Tuya private clusters (0xFC55-FC57).

Problem: The device reports 4 identical endpoints but it is a
single-channel curtain controller. Only EP1 is functional.
This creates 22 entities (4 covers, 4 binary_sensors, 4 numbers,
4 selects, 4 firmware updates, 1 identify, 1 RSSI/LQI) when only
~4 are needed.

Calibration: Travel time is set by pressing the device "Next" button
twice; the interval between presses defines the travel time.
Tuya DP3 (cur_calibration: start/end) can also trigger calibration.

Tuya DP map (cloud):
  DP1   - control         - Enum (open/stop/close)  → mapped to OnOff
  DP2   - percent_control - Value 0-100              → mapped to LevelControl
  DP3   - cur_calibration - Enum (start/end)         → 0xFC55/FC56/FC57
  DP7   - switch_backlight - Bool                    → 0xFC55/FC56/FC57
  DP14  - light_mode      - Enum (none/enable_white/enable_yellow)
  DP101 - backlight_num   - Value 50000-60000

Quirk fixes:
  1. Remove phantom endpoints EP2-EP4 (only EP1 is real)
  2. Suppress useless OnOff config entities (StartUpOnOff, binary_sensor)
  3. Suppress useless LevelControl config entities (start_up_current_level)
"""

from zigpy.quirks.v2 import QuirkBuilder

ONOFF = 0x0006
LEVEL = 0x0008

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
    .skip_configuration()
    .add_to_registry()
)
