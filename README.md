<p align="center">
  <img src="https://brands.home-assistant.io/_/zha/icon.png" alt="ZHA" width="120" />
</p>

<h1 align="center">WOOW ZHA Quirks</h1>

<p align="center">
  <strong>Centralized custom ZHA quirks package for Tuya & Simon Zigbee devices with full HA entity support</strong>
</p>

<p align="center">
  <a href="#supported-devices">Supported Devices</a> &bull;
  <a href="#dp-map-reference">DP Map Reference</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#installation">Installation</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#project-structure">Project Structure</a> &bull;
  <a href="#development">Development</a> &bull;
  <a href="#license">License</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.1+-blue?logo=homeassistant" alt="Home Assistant 2025.1+" />
  <img src="https://img.shields.io/badge/Python-3.12+-yellow?logo=python" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/HACS-Compatible-green?logo=homeassistantcommunitystore" alt="HACS Compatible" />
  <img src="https://img.shields.io/badge/License-MIT-red" alt="MIT License" />
  <img src="https://img.shields.io/badge/Quirks-13%20files-blue" alt="13 Quirk Files" />
  <img src="https://img.shields.io/badge/Devices-15%20models-brightgreen" alt="15 Device Models" />
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=WOOWTECH&repository=Woow_ha_zha_quirk_component&category=integration">
    <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." />
  </a>
</p>

<p align="center">
  <a href="README_zh-TW.md">繁體中文</a>
</p>

---

## Supported Devices

| # | Device | Model | Manufacturer ID | HA Platform | Key Features |
|---|--------|-------|-----------------|-------------|--------------|
| 1 | Simon i7 S2100-1001 | 1-Gang Smart Switch | `_TZ2000_sayvzx8w` | `switch` | Indicator LED mode |
| 2 | Simon i7 S2100-1002 | 2-Gang Smart Switch | `_TZ2000_vvxwtxzf` | `switch` | Indicator LED + All On/Off virtual endpoint |
| 3 | Simon i7 S2100-1003 | 3-Gang Smart Switch | `_TZ2000_bi57zoca` | `switch` | Indicator LED + All On/Off virtual endpoint |
| 4 | Simon i7 S2100-1004 | 4-Gang Smart Switch | `_TZ2000_o1yvtxph` | `switch` | Indicator LED + All On/Off virtual endpoint |
| 5 | Tuya TS0001 | 1-Gang Switch Module | `_TZ3000_tqlv4ug4` | `switch` | Light-to-switch fix, external switch type, power-on state |
| 6 | Tuya TS0002 | 2-Gang Switch Module | `_TZ3000_denobasq` | `switch` | Light-to-switch fix, per-endpoint power-on state |
| 7 | Tuya TS0601 Roller Shade | Roller Shade Motor | `_TZE284_qxjkdfyt` | `cover` | Motor direction, limit switches, motor mode |
| 8 | Tuya TS0601 Ceiling Fan | Ceiling Fan + Light | `_TZE200_hmgktzj2` | `fan` + `light` + `select` | 6-speed fan, 3 presets, direction control, 3-level color temp |
| 9 | Gledopto GL-SPI-206P | SPI LED Controller | `_TZE284_gt5al3bl` | `light` + `select` | RGBCW color, 16 scene effects, pixel count, chip type config |
| 10 | Zemismart 4-Gang Screen Switch | 4-Gang Touch Switch | `_TZE204_wwaeqnrf` | `switch` | Screen label auto-sync, countdown timer, child lock, LED colors |
| 11 | Tuya Curtain Track | Curtain Track Motor | `_TZE200_nogaemzt` | `cover` | Motor direction, limit switches, motor mode |
| 12 | Simon SM0502 | 2-Gang Dimmer Switch | `_TZ2000_qc1ntn3c` | `light` + `number` | Min/max brightness split, All On/Off virtual endpoint, indicator LED |
| 13 | Tuya TS0502B | CCT Dimmable Light | `_TZ3000_yeygk4hw` | `light` | Kelvin↔mireds auto-conversion, CCT-only mode fix (2500-6500K) |
| 14 | Simon SM0301 | 1-CH Curtain Controller | `_TYZB01_koulgwmy` | `cover` + `number` + `button` | Phantom EP2-4 removal, position control, travel limit calibration, ZCL start/end calibration buttons |
| 15 | Tuya 3-Gang Screen Switch | 3-Gang Touch Switch | `_TZE204_k7v0eqke` | `switch` | Screen label auto-sync, countdown timer, child lock, LED colors |

---

## DP Map Reference

### Simon i7 S2100 Series

Standard ZCL switches (genOnOff), NOT Tuya MCU devices.

| Feature | Cluster | Attribute | Entity Type | Description |
|---------|---------|-----------|-------------|-------------|
| Switch (per gang) | 0x0006 | `on_off` | Standard | On/Off control |
| Indicator Mode | 0x0006 | `backlight_mode` (0x8001) | Config | Off / Normal / Inverted |
| All On/Off | 0x0006 (EP 200) | `on_off` | Standard | Virtual endpoint, multi-gang only |

---

### Simon SM0502 (`_TZ2000_qc1ntn3c`)

Standard ZCL 2-gang dimmer (NOT Tuya MCU). Silicon Labs EFR32MG24 chip. Device exposes 4 endpoints but only EP1 & EP2 are real physical gangs; EP3 & EP4 are phantom and removed by the quirk.

| Feature | Cluster | Attribute | EP | Entity Type | Description |
|---------|---------|-----------|-----|-------------|-------------|
| Light (per gang) | 0x0006 + 0x0008 | `on_off` + `current_level` | 1, 2 | Standard (light) | Dimmable light, brightness 0-254 |
| Indicator Mode | 0x0006 | `backlight_mode` (0x8001) | 1 | Config | Off / Normal / Inverted |
| Min Brightness | 0x0008 | `min_brightness` (virtual 0xFC10) | 1, 2 | Config (number) | Per-gang min brightness (0-255) |
| Max Brightness | 0x0008 | `max_brightness` (virtual 0xFC11) | 1, 2 | Config (number) | Per-gang max brightness (0-255) |
| All On/Off | 0x0006 (EP 200) | `on_off` | 200 | Standard | Virtual endpoint, controls both gangs |

**Min/Max Brightness Technical Detail:**

The device stores min and max brightness in a single packed uint16 attribute `0xFC00`:
- High byte = min brightness (0x00-0xFF)
- Low byte = max brightness (0x00-0xFF)
- Example: `0x4DFF` = min 77 (~30%), max 255 (100%)

The quirk splits this into two virtual attributes (`0xFC10` / `0xFC11`) as separate number entities. Writes to either virtual attribute perform read-modify-write on the underlying `0xFC00`.

---

### Tuya TS0502B (`_TZ3000_yeygk4hw`)

Standard ZCL CCT dimmable light (NOT Tuya MCU). Silicon Labs EFR32MG24 chip. The device reports color temperature attributes in **Kelvin** instead of ZCL-standard **mireds**; the quirk converts automatically.

| Feature | Cluster | Attribute | Entity Type | Description |
|---------|---------|-----------|-------------|-------------|
| Light | 0x0006 + 0x0008 | `on_off` + `current_level` | Standard (light) | Dimmable CCT light, brightness 0-254 |
| Color Temperature | 0x0300 | `color_temperature` (0x0007) | Standard (light) | 2500-6500K, auto Kelvin↔mireds conversion |
| Color Capabilities | 0x0300 | `color_capabilities` (0x400A) | — | Forced to 0x10 (CCT only, removes xy mode) |

**Kelvin↔Mireds Conversion:**

The device stores color temperature in Kelvin but ZCL expects mireds (1,000,000 / K). The quirk converts transparently:
- **Reads**: Kelvin (from device) → mireds (to ZHA/HA)
- **Writes**: mireds (from HA) → Kelvin (to device)
- **Commands**: `move_to_color_temperature` command also converted

| Device Attribute | Device Value | Quirk Output |
|------------------|-------------|--------------|
| `color_temperature` (0x0007) | 5499 (Kelvin) | 181 (mireds) → HA shows 5524K |
| `color_temp_physical_min` (0x400B) | 2500 (Kelvin) | 400 (mireds) → HA shows 2500K |
| `color_temp_physical_max` (0x400C) | 6500 (Kelvin) | 153 (mireds) → HA shows 6535K |

---

### Simon SM0301 (`_TYZB01_koulgwmy`)

1-channel curtain controller with forward/reverse relay output. Standard ZCL Shade device (device_type 0x0200) using OnOff + LevelControl clusters.

**Problem:** Device reports 4 identical endpoints (EP1-EP4) but only EP1 is functional. Creates 22 entities without quirk. Quirk removes EP2-4 and suppresses config entities, leaving 5 clean entities.

| Feature | Cluster | Attribute | Entity Type | Description |
|---------|---------|-----------|-------------|-------------|
| Cover | 0x0006 + 0x0008 | `on_off` + `current_level` | Standard (cover) | Open/close/stop/set_position, device_class=shade |
| Opening State | 0x0006 | `on_off` | binary_sensor | Indicates if curtain is currently moving |
| Travel Limit | 0x0100 | `closed_limit` (0x0010) | Config (number) | Motor travel distance in steps (100-65534, step 100) |
| Reset Travel Limit | 0x0100 | `closed_limit` = 65534 | Config (button) | Removes travel restriction (writes max value) |
| Start Calibration | 0x0100 | `calibration_mode` (0x0011) = 1 | Config (button) | Enters configure/calibration mode |
| End Calibration | 0x0100 | `calibration_mode` (0x0011) = 0 | Config (button) | Exits calibration mode, saves closed_limit |

**Tuya Cloud DP Map (for reference):**

| DP ID | Name | Identifier | Type | Values |
|-------|------|-----------|------|--------|
| 1 | Curtain Control | `control` | Enum | open, stop, close |
| 2 | Position | `percent_control` | Value | 0-100, step 10, unit % |
| 3 | Calibration | `cur_calibration` | Enum | start, end |
| 7 | Backlight Switch | `switch_backlight` | Bool | — |
| 14 | Indicator LED | `light_mode` | Enum | none, enable_white, enable_yellow |
| 101 | Backlight Number | `backlight_num` | Value | 50000-60000 |

**ZCL Calibration Workflow:**

This device has NO physical calibration button. Calibration is done entirely over ZCL using Shade Configuration attribute 0x0011 (an undocumented enum8):

1. Press **Start Calibration** button (writes attr 0x0011 = 1) — device enters configure mode
2. Open the cover to the desired fully-open position, then stop — device records the zero point
3. Close the cover to the desired fully-closed position, then stop — device measures motor steps
4. Press **End Calibration** button (writes attr 0x0011 = 0) — device saves the new closed_limit

The Travel Limit number entity shows the recorded motor steps and can also be written directly to fine-tune without full recalibration. The **Reset Travel Limit** button writes closed_limit=65534 to remove any travel restriction.

---

### Tuya TS0001 (`_TZ3000_tqlv4ug4`)

Fixes device_type from `ON_OFF_LIGHT` to `ON_OFF_OUTPUT` so HA creates switch entities instead of light entities.

| Feature | Cluster | Attribute | Entity Type | Description |
|---------|---------|-----------|-------------|-------------|
| Switch | 0x0006 | `on_off` | Standard | On/Off control |
| Power On State | 0x0006 | `power_on_state` (0x8002) | Config | Off / On / Memory |
| Switch Type | 0xE001 | `external_switch_type` | Config | Toggle / State / Momentary |

Also covers `_TZ3000_tuucc0f5` and `_TZ3000_voy7mbpw` (switch panels, with `backlight_mode` instead of `external_switch_type`).

---

### Tuya TS0002 (`_TZ3000_denobasq`)

2-gang version with both endpoints fixed from `ON_OFF_LIGHT` to `ON_OFF_OUTPUT`.

| Feature | Cluster | Attribute | EP | Entity Type | Description |
|---------|---------|-----------|-----|-------------|-------------|
| Switch 1 | 0x0006 | `on_off` | 1 | Standard | Gang 1 On/Off |
| Switch 2 | 0x0006 | `on_off` | 2 | Standard | Gang 2 On/Off |
| Indicator Mode | 0x0006 | `backlight_mode` | 1 | Config | Off / Normal / Inverted |
| Power On State 1 | 0x0006 | `power_on_state` | 1 | Config | Off / On / Memory |
| Power On State 2 | 0x0006 | `power_on_state` | 2 | Config | Off / On / Memory |

---

### Tuya TS0601 Roller Shade (`_TZE284_qxjkdfyt`)

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1 | ENUM | `tuya_cover_command` | Standard | Open (0) / Stop (1) / Close (2) |
| 2 | VALUE | `position_control` | Standard | Set target position (0-100) |
| 3 | VALUE | `current_position` | Standard | Position report (0-100) |
| 5 | ENUM | `motor_direction` | Config | Forward (0) / Reversed (1) |
| 101 | BOOL | `remote_register` | Config | Remote pairing toggle |
| 102 | BOOL | `reset_all_limits` | Config | Reset all limit positions |
| 103 | BOOL | `upper_limit_set` | Config | Set/Reset upper limit |
| 104 | BOOL | `middle_limit_set` | Config | Set/Reset middle limit |
| 105 | BOOL | `lower_limit_set` | Config | Set/Reset lower limit |
| 106 | ENUM | `motor_mode` | Config | Linkage (0) / Inching (1) |

---

### Tuya TS0601 Ceiling Fan (`_TZE200_hmgktzj2`)

Monkey-patches ZHA fan platform at import time: `SPEED_RANGE=(1,6)`, 3 preset modes, direction support.

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1 | BOOL | Fan switch | Standard (fan) | Fan on/off |
| 3 | ENUM | Fan speed | Standard (fan) | 0=off, 1-6=speed, 7=natural, 8=sleep |
| 5 | BOOL | Light switch | Standard (light) | Light on/off (EP 2) |
| 101 | ENUM | Fan direction | Standard (fan) | Forward (1) / Reverse (0) |
| 102 | ENUM | `color_temp_level` | Standard (select) | Warm (0) / Natural (50) / White (100) |

**Fan Speed Mapping:**

| fan_mode | DP3 Value | Display Name |
|----------|-----------|-------------|
| 1-6 | 1-6 | Speed 1-6 |
| 7 | 3 | Preset: Normal |
| 8 | 7 | Preset: Natural Wind |
| 9 | 8 | Preset: Sleep |

---

### Gledopto GL-SPI-206P (`_TZE284_gt5al3bl`)

WLED-style light entity with deferred DP batch queue (15ms window) for single-frame Zigbee commands.

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1 | BOOL | Power on/off | Standard (light) | On/Off via OnOff cluster |
| 2 | ENUM | Work mode | Standard (light) | White (0) / Colour (1) / Scene (2) / Music (3) |
| 3 | VALUE | Brightness | Standard (light) | 10-1000 mapped to ZCL 1-254 |
| 4 | VALUE | Color temperature | Standard (light) | 0-1000 mapped to 153-370 mireds |
| 51 | RAW | Scene data | Standard (select) | 16 built-in scene effects |
| 53 | VALUE | `pixel_count` | Config | LED pixel count (10-1000) |
| 61 | RAW | Color data | Standard (light) | SmearFormater 11-byte HSV payload |
| 101 | ENUM | `color_order` | Config | RGB/RBG/GRB/... (16 options) |
| 102 | ENUM | `chip_type` | Config | WS2801/WS2811/SK6812/... (10 options) |
| 103 | BOOL | `do_not_disturb` | Config | DND mode toggle |

**Scene Presets:**

| # | Name | # | Name |
|---|------|---|------|
| 0 | Iceland Blue | 8 | Game |
| 1 | Glacier Express | 9 | Holiday |
| 2 | Sea of Clouds | 10 | Party |
| 3 | Fireworks at Sea | 11 | Trend |
| 4 | Firefly Night | 12 | Meditation |
| 5 | Grassland | 13 | Dating |
| 6 | Northern Lights | 14 | Valentine's Day |
| 7 | Late Autumn | 15 | Neon World |

---

### Zemismart 4-Gang Screen Switch (`_TZE204_wwaeqnrf`)

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1-4 | BOOL | `on_off_1` - `on_off_4` | Standard | Switch 1-4 on/off |
| 13 | BOOL | `on_off_all` | Standard | All switches on/off |
| 7-10 | VALUE | `countdown_1` - `countdown_4` | Config | Countdown timer (0-86400 sec) |
| 15 | ENUM | `indicator_mode` | Config | Off (0) / Relay (1) / Position (2) |
| 16 | BOOL | `backlight_switch` | Config | Backlight master switch |
| 29-32 | ENUM | `power_on_state_1` - `power_on_state_4` | Config | Off (0) / On (1) / Memory (2) |
| 101 | BOOL | `child_lock` | Config | Child lock toggle |
| 102 | VALUE | `backlight_level` | Config | Backlight brightness (0-100%) |
| 103 | ENUM | `on_color` | Config | ON indicator color (7 colors) |
| 104 | ENUM | `off_color` | Config | OFF indicator color (7 colors) |
| 105-108 | RAW | `screen_label_1` - `screen_label_4` | Write-only | Screen text (UTF-8, 12-char max, auto-synced) |

**Screen Label Auto-Sync:**

Screen labels are automatically synced from HA entity `friendly_name` on device startup and whenever an entity is renamed. No external automation needed — the sync logic is built into the quirk cluster itself.

Manual write is also supported:

```yaml
service: zha.set_zigbee_cluster_attribute
data:
  ieee: "XX:XX:XX:XX:XX:XX:XX:XX"
  endpoint_id: 1
  cluster_id: 0xEF00
  cluster_type: in
  attribute: screen_label_1
  value: "Living Room"
```

---

### Tuya 3-Gang Screen Switch (`_TZE204_k7v0eqke`)

Same MCU firmware as the 4-gang `_TZE204_wwaeqnrf` but with 3 physical gangs. DP 4/10/32/108 are phantom (MCU accepts but no physical hardware).

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1-3 | BOOL | `on_off_1` - `on_off_3` | Standard | Switch 1-3 on/off |
| 13 | BOOL | `on_off_all` | Standard | All switches on/off |
| 7-9 | VALUE | `countdown_1` - `countdown_3` | Config | Countdown timer (0-86400 sec) |
| 15 | ENUM | `indicator_mode` | Config | Off (0) / Relay (1) / Position (2) |
| 16 | BOOL | `backlight_switch` | Config | Backlight master switch |
| 29-31 | ENUM | `power_on_state_1` - `power_on_state_3` | Config | Off (0) / On (1) / Memory (2) |
| 101 | BOOL | `child_lock` | Config | Child lock toggle |
| 102 | VALUE | `backlight_level` | Config | Backlight brightness (0-100%) |
| 103 | ENUM | `on_color` | Config | ON indicator color (7 colors) |
| 104 | ENUM | `off_color` | Config | OFF indicator color (7 colors) |
| 105-107 | RAW | `screen_label_1` - `screen_label_3` | Write-only | Screen text (UTF-8, 12-char max, auto-synced) |

Screen label auto-sync behavior is identical to the 4-gang version above.

---

### Tuya Curtain Track (`_TZE200_nogaemzt`)

Uses single DP2 for both position set and position report.

| DP | Type | Attribute | Entity Type | Description |
|----|------|-----------|-------------|-------------|
| 1 | ENUM | `tuya_cover_command` | Standard | Open (0) / Stop (1) / Close (2) |
| 2 | VALUE | `current_position_lift_percentage` | Standard | Position set AND report (0-100) |
| 5 | ENUM | `motor_direction` | Config | Normal (0) / Reversed (1) |
| 101 | BOOL | `remote_register` | Config | Remote pairing toggle |
| 102 | BOOL | `reset_all_limits` | Config | Reset all limit positions |
| 103 | BOOL | `upper_limit_set` | Config | Set/Reset upper limit |
| 104 | BOOL | `middle_limit_set` | Config | Set/Reset middle limit |
| 105 | BOOL | `lower_limit_set` | Config | Set/Reset lower limit |
| 106 | ENUM | `motor_mode` | Config | Linkage (0) / Inching (1) |

---

## Architecture

```mermaid
graph TB
    subgraph "Home Assistant"
        HA_ZHA[ZHA Integration]
        HA_ENTITIES["HA Entities<br/>(switch / cover / fan / light / select / number)"]
    end

    subgraph "WOOW ZHA Quirks"
        INIT["__init__.py<br/>Auto-loader"]
        QUIRKS["Quirk Modules<br/>(12 files)"]
    end

    subgraph "ZHA + zigpy"
        ZIGPY_REG["zigpy DEVICE_REGISTRY"]
    end

    subgraph "Zigbee Network"
        DEVICES["Zigbee Devices<br/>(Tuya MCU / ZCL)"]
    end

    HA_ZHA --> HA_ENTITIES
    INIT -->|"pkgutil.walk_packages()"| QUIRKS
    QUIRKS -->|"QuirkBuilder.add_to_registry()"| ZIGPY_REG
    ZIGPY_REG --> HA_ZHA
    HA_ZHA <--> DEVICES
```

### How It Works

1. **Auto-loading**: `__init__.py` uses `pkgutil.walk_packages()` to discover and import all quirk modules under `quirks/` directory at HA startup.

2. **Quirk Registration**: Each quirk module uses `QuirkBuilder` or `TuyaQuirkBuilder` fluent chain API to define device behavior and register into zigpy's `DEVICE_REGISTRY`.

3. **Entity Creation**: ZHA reads the quirk metadata (clusters, attributes, entity types) and creates appropriate HA entities (switches, covers, fans, lights, selects, numbers).

4. **Tuya MCU Bridge**: For TS0601 devices, custom ZCL clusters bridge between standard ZCL protocol and Tuya MCU DP commands on cluster `0xEF00`.

---

## Installation

### Quick Install (One-Click)

Click the button below to add this repository directly to HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=WOOWTECH&repository=Woow_ha_zha_quirk_component&category=integration)

After adding, search for **WOOW ZHA Quirks** in HACS and click **Install**, then add `woow_zha_quirks:` to `configuration.yaml` and restart.

### HACS (Manual Steps)

1. Open **HACS** in your Home Assistant
2. Click the top-right menu &rarr; **Custom repositories**
3. Enter `https://github.com/WOOWTECH/Woow_ha_zha_quirk_component`
4. Select category **Integration**
5. Search for **WOOW ZHA Quirks** &rarr; Install
6. Add to `configuration.yaml`:

```yaml
woow_zha_quirks:
```

7. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy `custom_components/woow_zha_quirks/` to your HA `config/custom_components/`:

```
config/
└── custom_components/
    └── woow_zha_quirks/
        ├── __init__.py
        ├── manifest.json
        └── quirks/
            ├── __init__.py
            ├── simon_i7_s2100.py
            ├── ts0001_switch_TZ3000_tqlv4ug4.py
            └── ... (12 more quirk files)
```

3. Add `woow_zha_quirks:` to `configuration.yaml`
4. Restart Home Assistant

---

## Configuration

After installation, add the following to your `configuration.yaml`:

```yaml
woow_zha_quirks:
```

That's it. No additional configuration is needed. The component automatically:

- Discovers and loads all quirk modules at startup
- Registers them into zigpy's device registry
- ZHA will match your devices to the correct quirk on next restart

### Important Notes

- **No `custom_quirks_path` needed** — This component handles quirk loading automatically
- If you previously set `zha: custom_quirks_path:`, you can remove it (unless you have other quirks outside this package)
- Requires ZHA integration to be installed and configured
- Dependencies: `zha`, `zha-quirks`, `zigpy`

---

## Project Structure

```
Woow_ha_zha_quirk_component/
├── custom_components/
│   └── woow_zha_quirks/
│       ├── __init__.py                              # Auto-loader (pkgutil)
│       ├── manifest.json                            # HA component manifest
│       └── quirks/
│           ├── __init__.py
│           ├── simon_i7_s2100.py                     # Simon i7 1-4 gang switches
│           ├── simon_sm0301_curtain.py                  # Simon SM0301 curtain controller
│           ├── simon_sm0502_dimmer.py                 # Simon SM0502 2-gang dimmer
│           ├── ts0001_switch_TZ3000_tqlv4ug4.py      # TS0001 single switch
│           ├── ts0502b_cct_TZ3000_yeygk4hw.py         # TS0502B CCT dimmable light
│           ├── ts0002_switch_TZ3000_denobasq.py      # TS0002 dual switch
│           ├── ts0601_cover_TZE284_qxjkdfyt.py       # Roller shade motor
│           ├── ts0601_fan_TZE200_hmgktzj2.py         # Ceiling fan + light
│           ├── ts0601_light_TZE284_gt5al3bl.py       # SPI LED controller
│           ├── ts0601_switch_TZE204_wwaeqnrf.py      # 4-gang screen switch
│           ├── ts0601_switch_TZE204_k7v0eqke.py      # 3-gang screen switch
│           └── tuya_cover_nogaemzt.py                # Curtain track motor
│
├── config/
│   └── automations.yaml                             # Screen label sync automation
│
├── docs/
│   ├── plans/
│   │   └── 2026-05-25-deploy-test-haos-plan.md
│   └── simon_zigbee_quirk_roadmap.md
│
├── hacs.json                                        # HACS metadata
├── LICENSE                                          # MIT License
└── README.md                                        # This file
```

---

## Development

### Prerequisites

- Home Assistant 2025.1+
- Python 3.12+
- ZHA integration configured with a Zigbee coordinator
- `zha-quirks` and `zigpy` packages

### Adding a New Quirk

1. Create a new Python file in `custom_components/woow_zha_quirks/quirks/`
2. Use the `QuirkBuilder` or `TuyaQuirkBuilder` fluent API:

```python
from zigpy.quirks.v2 import EntityType
from zhaquirks.tuya.builder import TuyaQuirkBuilder

(
    TuyaQuirkBuilder("_MANUFACTURER_ID", "MODEL")
    .tuya_switch(dp_id=1, attribute_name="on_off", ...)
    .tuya_enum(dp_id=2, attribute_name="mode", enum_class=MyEnum, ...)
    .skip_configuration()
    .add_to_registry()
)
```

3. Restart Home Assistant — the auto-loader picks up new files automatically

### Component Versions

| Component | Version | Description |
|-----------|---------|-------------|
| `woow_zha_quirks` | 1.0.0 | Main quirks package |
| Simon i7 quirk | v3 | AllOnOff virtual endpoint |
| Simon SM0502 quirk | v5 | Min/max brightness split + AllOnOff |
| TS0502B CCT quirk | v1 | Kelvin↔mireds conversion + CCT-only fix |
| SM0301 curtain quirk | v3 | Phantom EP removal + travel limit + ZCL calibration buttons |
| Ceiling fan quirk | v5 | 6-speed + direction + preset |
| SPI LED quirk | v9 | Batch queue + correct scene format |
| 4-gang screen switch quirk | v3 | Screen label auto-sync from entity names |
| 3-gang screen switch quirk | v1 | 3-gang variant with screen label auto-sync |

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Made with &#10084; by <a href="https://github.com/WOOWTECH">WOOWTECH</a>
</p>
