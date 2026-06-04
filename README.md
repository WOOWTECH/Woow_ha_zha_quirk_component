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
  <img src="https://img.shields.io/badge/Quirks-9%20files-blue" alt="9 Quirk Files" />
  <img src="https://img.shields.io/badge/Devices-8%20models-brightgreen" alt="8 Device Models" />
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
| 10 | Zemismart 4-Gang Screen Switch | 4-Gang Touch Switch | `_TZE204_wwaeqnrf` | `switch` | Screen label write, countdown timer, child lock, LED colors |
| 11 | Tuya Curtain Track | Curtain Track Motor | `_TZE200_nogaemzt` | `cover` | Motor direction, limit switches, motor mode |

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
| 105-108 | RAW | `screen_label_1` - `screen_label_4` | Write-only | Screen text (UTF-8, 12-char max) |

**Screen Label Write Example:**

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
        QUIRKS["Quirk Modules<br/>(9 files)"]
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

### HACS (Recommended)

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
            └── ... (8 more quirk files)
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
│           ├── ts0001_switch_TZ3000_tqlv4ug4.py      # TS0001 single switch
│           ├── ts0002_switch_TZ3000_denobasq.py      # TS0002 dual switch
│           ├── ts0601_cover_TZE284_qxjkdfyt.py       # Roller shade motor
│           ├── ts0601_fan_TZE200_hmgktzj2.py         # Ceiling fan + light
│           ├── ts0601_light_TZE284_gt5al3bl.py       # SPI LED controller
│           ├── ts0601_switch_TZE204_wwaeqnrf.py      # 4-gang screen switch
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
| Ceiling fan quirk | v5 | 6-speed + direction + preset |
| SPI LED quirk | v9 | Batch queue + correct scene format |
| Screen switch quirk | v2 | Screen label write support |

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  Made with &#10084; by <a href="https://github.com/WOOWTECH">WOOWTECH</a>
</p>
