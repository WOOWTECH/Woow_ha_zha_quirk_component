# Simon i7 Smart Zigbee — ZHA Quirk 開發路線圖

> 日期：2026-06-04
> 目標：將 Simon i7 Smart 全系列 Zigbee 設備整合至 Home Assistant ZHA，
> 每款產品都能在 HA/ZHA 設備介面直接設定、操作與調適。

---

## 一、研究結論摘要

### 1.1 Simon i7 Smart 產品線（已確認）

| 類別 | 產品 | Zigbee 模型 | 通訊架構 | 當前狀態 |
|------|------|-------------|----------|----------|
| 開關 | 1-4路智能開關 | S2100-1001~1004 | 標準 ZCL (genOnOff) 多端點 | ✅ 已完成 quirk |
| 調光 | 1-2路調光開關 | 待確認 | Tuya MCU (TS0601) 或 標準ZCL | 🔲 待開發 |
| 窗簾 | 1-2路窗簾開關 | 待確認 | Tuya MCU (TS0601) 或 標準ZCL (0x0102) | 🔲 待開發 |
| 溫控 | 多合一溫控器(空調/地暖/新風) | 待確認 | Tuya MCU (TS0601) | 🔲 待開發 |
| 場景 | 1-4路場景開關 (TY cloud) | 待確認 | Tuya MCU 或標準ZCL | 🔲 待開發 |
| 20A | 1路 20A 大電流開關 | 待確認 | 標準 ZCL | 🔲 待開發 |
| 感測 | 人體感應器 | 待確認 | IAS Zone | 🔲 待開發 |
| 紅外 | 智慧紅外遙控器 | 待確認 | Tuya MCU | 🔲 待開發 |
| 閘道 | Zigbee 閘道 (LAN/WiFi) | N/A | N/A（不需quirk） | — |

### 1.2 架構分類

Simon 設備分兩大架構：

**A. 標準 ZCL 設備（如 S2100 開關）**
- 使用標準 Zigbee Cluster（genOnOff、WindowCovering、LevelControl 等）
- 製造商字串格式：`_TZ2000_xxxxxxxxxxxx`
- Quirk 使用 `QuirkBuilder` + `.replaces(TuyaZBOnOffAttributeCluster)` 模式
- 不經過 Tuya MCU 0xEF00 cluster

**B. Tuya MCU 設備（TS0601）**
- 所有功能通過 cluster 0xEF00 的 DataPoint 傳輸
- 製造商字串格式：`_TZE200_xxx` / `_TZE204_xxx` / `_TZE284_xxx`
- Quirk 使用 `TuyaQuirkBuilder` + DP 映射

### 1.3 TuyaQuirkBuilder API 可用方法

| 方法 | 對應實體平台 | 複雜度 |
|------|-------------|--------|
| `tuya_switch` | Switch | ⭐ 簡單 |
| `tuya_enum` | Select | ⭐ 簡單 |
| `tuya_number` | Number | ⭐ 簡單 |
| `tuya_binary_sensor` | Binary Sensor | ⭐ 簡單 |
| `tuya_sensor` | Sensor | ⭐ 簡單 |
| `tuya_cover` | Cover (WindowCovering) | ⭐⭐ 中等 |
| `tuya_onoff` | Switch (OnOff) | ⭐ 簡單 |
| `tuya_dp_attribute` | 自訂屬性（無HA實體） | ⭐⭐ 中等 |
| `tuya_dp` / `tuya_dp_multi` | 底層DP映射 | ⭐⭐⭐ 進階 |
| ❌ `tuya_light` | — | 不存在，需自建 |
| ❌ `tuya_climate` | — | 不存在，需自建 |
| ❌ `tuya_fan` | — | 不存在，需自建 |

---

## 二、各類設備 Quirk 開發方案

### 2.1 調光開關 (Dimmer) — 優先級 🔴 高

**預期 Simon 型號**：S2100-10xx 調光版（或獨立產品線）

#### 方案 A：標準 ZCL 調光（如果設備使用 LevelControl cluster）
```
QuirkBuilder(manufacturer, model)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    # LevelControl cluster 可能已原生支援
    .add_to_registry()
```
- 若設備在端點上已有 `0x0008 LevelControl` cluster → ZHA 自動識別為燈
- 只需替換 OnOff cluster 加入 backlight_mode 等製造商屬性

#### 方案 B：Tuya MCU 調光（TS0601）— 參考現有 `ts0601_dimmer.py`
```python
# 現有 zhaquirks 模式：V1 legacy quirk
# 使用 TuyaInWallLevelControl + TuyaOnOff 替換 clusters
# 設備類型改為 ON_OFF_LIGHT
replacement = {
    ENDPOINTS: {
        1: {
            DEVICE_TYPE: zha.DeviceType.ON_OFF_LIGHT,
            INPUT_CLUSTERS: [
                Basic, Groups, Scenes,
                TuyaLevelControlManufCluster,  # 0xEF00
                TuyaOnOff,                     # 虛擬 OnOff
                TuyaInWallLevelControl,        # 虛擬 LevelControl
            ],
        },
        # 多路調光：每路一個額外端點
        2: {INPUT_CLUSTERS: [TuyaOnOff, TuyaInWallLevelControl]},
    }
}
```

**涂鴉調光 DP 標準**（供對照用）：
| DP Code | 功能 | 類型 | 範圍 |
|---------|------|------|------|
| switch_led_N | 開關 N | Bool | — |
| bright_value_N | 亮度 N | Value | 10-1000 |
| brightness_min_N | 最低亮度 N | Value | 10-1000 |
| brightness_max_N | 最高亮度 N | Value | 10-1000 |
| countdown_N | 倒計時 N | Value | 0-86400 |
| led_type_N | 光源類型 N | Enum | led/incandescent/halogen |
| light_mode | 指示燈模式 | Enum | none/relay/pos |
| relay_status | 上電狀態 | Enum | off/on/memory |

**開發步驟**：
1. 取得設備，用 `zha-toolkit` 掃描端點/cluster 結構
2. 判斷架構 A 或 B
3. 如果 B：抓取 DP ID 映射（透過涂鴉開發者平台或串口監聽）
4. 建立 quirk 並部署測試

---

### 2.2 窗簾開關 (Cover) — 優先級 🔴 高

**預期 Simon 型號**：窗簾開關（1路/2路）

#### 方案 A：標準 ZCL WindowCovering（如果有 cluster 0x0102）
- ZHA 原生支援 WindowCovering cluster
- 可能只需加入製造商屬性即可

#### 方案 B：Tuya MCU 窗簾（TS0601）— `tuya_cover()` 方法
```python
TuyaQuirkBuilder(manufacturer, "TS0601")
    .tuya_cover(
        control_dp=1,           # 開/停/關 (enum: 0=open, 1=stop, 2=close)
        position_state_dp=3,    # 當前位置回報 (0-100)
        position_control_dp=2,  # 目標位置設定 (0-100)
        invert=True,            # Tuya 0=關 100=開 → ZCL 0=開 100=關
    )
    # 可選配置 DPs
    .tuya_switch(dp_id=5, attribute_name="motor_direction", ...)
    .tuya_enum(dp_id=8, attribute_name="motor_direction", ...)
    .skip_configuration()
    .add_to_registry()
```

**涂鴉窗簾 DP 標準**：
| DPID | 功能 | 類型 |
|------|------|------|
| 1 | 窗簾控制 1 (open/stop/close) | Enum |
| 2 | 百分比 1 (0-100) | Value |
| 3 | 精確校準 1 | Config |
| 4 | 窗簾控制 2 | Enum |
| 5 | 百分比 2 | Value |
| 7 | 背光開關 | Bool |
| 8 | 電機方向 1 | Enum |
| 14 | 指示燈狀態 | Enum |

**現有參考**：`ts0601_cover_TZE284_qxjkdfyt.py`（已部署，可直接參考）

---

### 2.3 溫控器 / HVAC 控制 (Thermostat) — 優先級 🟡 中

**預期 Simon 型號**：多合一溫控器（空調/地暖/新風）

#### 架構：幾乎確定是 Tuya MCU (TS0601)

**⚠️ 重要限制**：`TuyaQuirkBuilder` 沒有 `tuya_climate` 方法。
需要自建完整的 Thermostat cluster 子類。

**開發模式**（參考 `ts0601_trv.py` 和 `tuya_thermostat.py`）：
```python
class SimonThermostatCluster(TuyaThermostatCluster):
    """Custom Thermostat cluster mapping Tuya DPs to ZCL Thermostat attributes."""

    class AttributeDefs(TuyaThermostatCluster.AttributeDefs):
        # 自訂屬性...
        pass

    # 覆寫 handle_cluster_request 處理 DP 更新
    # 覆寫 write_attributes 處理 HA 設定變更

class SimonThermostat(TuyaThermostat):
    """V1 legacy quirk 定義 signature + replacement."""
    signature = { ... }
    replacement = {
        ENDPOINTS: {
            1: {
                DEVICE_TYPE: zha.DeviceType.THERMOSTAT,
                INPUT_CLUSTERS: [
                    Basic, Identify, Groups, Scenes,
                    SimonThermostatCluster,
                    TuyaUserInterfaceCluster,
                ],
            }
        }
    }
```

**涂鴉空調控制器 DP 標準 (ktkzq)**：
| DP Code | 功能 | 類型 | 範圍 |
|---------|------|------|------|
| switch | 開關 | Bool | — |
| temp_set | 設定溫度 | Value | 0-40°C |
| mode | 工作模式 | Enum | hot/cold/wet/wind |
| fan_speed_enum | 風速 | Enum | level_1~4 |
| child_lock | 童鎖 | Bool | — |
| countdown_set | 定時 | Enum | cancel/0.5h/1h/.../12h |

**⚠️ 注意事項**：
- Simon 溫控器可能是多合一型（空調+地暖+新風），DP 結構可能比標準更複雜
- 需要實際抓取 DP 才能確定完整映射
- 現有 `ts0603_climate_TZE208_7aovt83n.py` (57KB) 可作為複雜 climate quirk 的參考
- 同時參考 `patch_zha_climate.py` 了解 ZHA climate 平台的限制與修補方式

---

### 2.4 雙色溫燈 (CCT Light) — 優先級 🟡 中

**不是 Simon 面板產品，但可能搭配使用（如可調色溫吸頂燈）**

#### 架構：Tuya MCU (TS0601)

**⚠️ 重要限制**：`TuyaQuirkBuilder` 沒有 `tuya_light` 方法。
需要自建 OnOff + LevelControl + Color cluster 子類。

**開發模式**（參考 `ts0601_light_TZE284_gt5al3bl.py`）：
```python
# 需要三個自訂 cluster：
class TuyaCCTOnOff(LocalDataCluster, OnOff):
    """橋接 DP → ZCL OnOff"""
    # command() 攔截 on/off → 傳送 DP1

class TuyaCCTLevelControl(LocalDataCluster, LevelControl):
    """橋接 DP → ZCL LevelControl"""
    # move_to_level_with_on_off → DP(亮度)

class TuyaCCTColorControl(LocalDataCluster, Color):
    """橋接 DP → ZCL Color (色溫模式)"""
    # move_to_color_temperature → DP(色溫)

# TuyaQuirkBuilder 或 V1 quirk：
# endpoint 1: ON_OFF_LIGHT / COLOR_TEMPERATURE_LIGHT
# INPUT_CLUSTERS: [Basic, TuyaMCU, TuyaCCTOnOff, TuyaCCTLevelControl, TuyaCCTColorControl]
```

**涂鴉 CCT 燈 DP 標準**：
| DP | 功能 | 類型 | 範圍 |
|----|------|------|------|
| 1 (20) | 開關 | Bool | — |
| 2 (21) | 工作模式 | Enum | white/colour/scene/music |
| 3 (22) | 亮度 | Value | 10-1000 |
| 4 (23) | 色溫 | Value | 0-1000 (0=暖, 1000=冷) |

**現有參考**：`ts0601_light_TZE284_gt5al3bl.py`（v9, 40KB, SPI LED控制器）
※ 該 quirk 是 RGBCW 全彩控制器，CCT 燈只需子集功能

---

### 2.5 場景按鈕開關 (Scene Switch) — 優先級 🟢 低

**預期 Simon 型號**：1-4路場景開關 (TY cloud)

#### 可能架構

**A. 純雲端場景開關（TY cloud）**
- 按鈕按下 → Zigbee 發送事件到閘道 → 雲端觸發場景
- 這類設備可能不需要 quirk，只需在 ZHA 中做自動化觸發
- 按鈕事件通常透過 cluster 0x0006 或 0x0005 的命令

**B. Tuya MCU 場景開關 (TS0601)**
- 按鈕狀態透過 DP 傳輸
- 使用 `tuya_enum` 或 `tuya_sensor` 映射按鈕事件

**C. 標準 ZCL 場景控制**
- 使用 Scenes cluster (0x0005) 或自訂命令
- ZHA 原生支援場景 cluster

**開發步驟**：
等待取得實際設備後再決定架構

---

### 2.6 其他設備（20A開關、感應器、紅外遙控）

**20A 開關**：可能與 S2100 相同架構（標準 ZCL genOnOff），
直接添加製造商字串到現有 `simon_i7_s2100.py` 即可。

**人體感應器**：可能使用 IAS Zone cluster，
TuyaQuirkBuilder 提供 `tuya_ias` / `tuya_contact` 等方法。

**紅外遙控器**：較複雜的學習型 IR，需要自訂 cluster。

---

## 三、開發優先順序

```
階段 1（立即可做）── 有設備即可開發
  ├── 調光開關 (Dimmer)      — 高頻使用，客戶需求強
  └── 窗簾開關 (Cover)       — 高頻使用，tuya_cover() 可直接用

階段 2（中期）── 需要完整 DP 映射
  ├── 溫控器 (Thermostat)    — 最複雜，需自建 Thermostat cluster
  └── CCT 燈控 (Light)       — 需自建 Color cluster

階段 3（後期）── 等待設備
  ├── 場景開關 (Scene)        — 需確認架構
  ├── 20A 開關               — 可能直接復用 S2100 quirk
  └── 感應器/紅外遙控        — 待確認
```

---

## 四、每種設備的 Quirk 模板

### 4.1 模板 A：標準 ZCL 設備（QuirkBuilder）

適用：開關、調光（若為標準ZCL）、20A開關

```python
"""ZHA Quirk for Simon i7 {DeviceName} ({model})."""

from zigpy.quirks.v2 import EntityType, QuirkBuilder
from zhaquirks.tuya import TuyaZBOnOffAttributeCluster

# 單路
(
    QuirkBuilder("{manufacturer}", "{model}")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .add_to_registry()
)

# 多路 + AllOnOff
(
    QuirkBuilder("{manufacturer}", "{model}")
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=1)
    .replaces(TuyaZBOnOffAttributeCluster, endpoint_id=2)
    # ... 更多端點
    .adds_endpoint(endpoint_id=200)
    .adds(AllOnOffCluster, endpoint_id=200)
    .add_to_registry()
)
```

### 4.2 模板 B：Tuya MCU 簡單設備（TuyaQuirkBuilder）

適用：窗簾開關

```python
"""ZHA Quirk for Simon i7 {DeviceName} ({manufacturer} / TS0601)."""

import zigpy.types as t
from zigpy.quirks.v2 import EntityType
from zhaquirks.tuya.builder import TuyaQuirkBuilder

(
    TuyaQuirkBuilder("{manufacturer}", "TS0601")
    .tuya_cover(
        control_dp=1,
        position_state_dp=3,
        position_control_dp=2,
        invert=True,
    )
    # 配置項 DPs
    .tuya_enum(dp_id=5, attribute_name="motor_direction", ...)
    .tuya_switch(dp_id=7, attribute_name="backlight", ...)
    .skip_configuration()
    .add_to_registry()
)
```

### 4.3 模板 C：Tuya MCU 複雜設備（自訂 Cluster + TuyaQuirkBuilder）

適用：調光（MCU版）、溫控器、CCT燈

```python
"""ZHA Quirk for Simon i7 {DeviceName} ({manufacturer} / TS0601)."""

import zigpy.types as t
from zigpy.quirks.v2 import EntityType
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import LevelControl, OnOff
from zigpy.zcl.clusters.hvac import Thermostat
from zhaquirks import LocalDataCluster
from zhaquirks.tuya import TuyaLocalCluster
from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import TuyaMCUCluster


class CustomOnOff(LocalDataCluster, OnOff):
    """Bridge DP→ZCL OnOff commands."""
    cluster_id = OnOff.cluster_id

    async def command(self, command_id, *args, **kwargs):
        # 攔截 on/off/toggle → 傳送對應 DP
        mcu = self.endpoint.tuya_manufacturer
        if command_id == 0x01:  # on
            await mcu.write_attributes({"on_off_dp": True})
        elif command_id == 0x00:  # off
            await mcu.write_attributes({"on_off_dp": False})
        # 更新本地狀態
        self._update_attribute(OnOff.AttributeDefs.on_off.id, command_id == 0x01)
        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(command_id=command_id, status=foundation.Status.SUCCESS)


class CustomLevelControl(LocalDataCluster, LevelControl):
    """Bridge DP→ZCL LevelControl commands."""
    cluster_id = LevelControl.cluster_id

    async def command(self, command_id, *args, **kwargs):
        # move_to_level / move_to_level_with_on_off
        if command_id in (0x00, 0x04):
            level = args[0] if args else 0
            # ZCL level 0-254 → Tuya level 10-1000
            tuya_level = max(10, int(level / 254 * 1000))
            mcu = self.endpoint.tuya_manufacturer
            await mcu.write_attributes({"brightness_dp": tuya_level})
            self._update_attribute(
                LevelControl.AttributeDefs.current_level.id, level
            )
        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(command_id=command_id, status=foundation.Status.SUCCESS)


# 方式一：配合 TuyaQuirkBuilder（推薦）
(
    TuyaQuirkBuilder("{manufacturer}", "TS0601")
    # DP 映射（用於接收設備回報）
    .tuya_dp(dp_id=1, ep_attribute="on_off", attribute_name="on_off")
    .tuya_dp(
        dp_id=2,
        ep_attribute="level",
        attribute_name="current_level",
        converter=lambda x: int(x / 1000 * 254),  # Tuya→ZCL
        dp_converter=lambda x: max(10, int(x / 254 * 1000)),  # ZCL→Tuya
    )
    # 配置項
    .tuya_enum(dp_id=14, attribute_name="indicator_mode", ...)
    .tuya_switch(dp_id=16, attribute_name="child_lock", ...)
    # 添加自訂 clusters
    .adds(CustomOnOff)
    .adds(CustomLevelControl)
    .skip_configuration()
    .add_to_registry()
)
```

---

## 五、開發工作流程（通用步驟）

### 5.1 設備發現
```bash
# 1. 配對設備到 ZHA
# 2. 使用 zha-toolkit 掃描設備結構
service: zha_toolkit.scan_device
data:
  ieee: "{device_ieee}"

# 3. 如果是 TS0601：抓取 DP 列表
service: zha_toolkit.get_tuya_dp
data:
  ieee: "{device_ieee}"
```

### 5.2 DP 探測（Tuya MCU 設備）
```bash
# 透過涂鴉開發者平台 + 涂鴉閘道
# 或直接使用 zha_toolkit 發送/監聽：
service: zha_toolkit.tuya_command
data:
  ieee: "{device_ieee}"
  # dp_type: 1=bool, 2=value, 4=enum
  dp: 1
  dp_type: 1
  data: 1
```

### 5.3 部署測試
```bash
# 複製 quirk 到容器
sshpass -p 'woowtech' scp -o StrictHostKeyChecking=no \
  quirk_file.py \
  woowtechopenclaw@192.168.2.197:/opt/homeassistant/config/custom_zha_quirks/

# 重啟 HA
sshpass -p 'woowtech' ssh ... \
  "podman exec homeassistant python3 -c \"
    import requests
    TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
    requests.post('http://localhost:8123/api/services/homeassistant/restart',
                  headers={'Authorization': f'Bearer {TOKEN}'})
  \""

# 移除設備並重新配對（如果 quirk 改變了端點結構）
```

---

## 六、已完成的 Quirk 清單

| 檔案 | 設備 | 架構 | 狀態 |
|------|------|------|------|
| `simon_i7_s2100.py` | S2100 1-4路開關 | 標準 ZCL | ✅ 已完成 |
| `ts0601_switch_TZE204_wwaeqnrf.py` | DIY 4路螢幕開關 | Tuya MCU | ✅ 已完成 |
| `ts0601_cover_TZE284_qxjkdfyt.py` | 捲簾電機 | Tuya MCU | ✅ 已完成 |
| `ts0601_light_TZE284_gt5al3bl.py` | Gledopto SPI LED | Tuya MCU | ✅ 已完成 |
| `ts0601_fan_TZE200_hmgktzj2.py` | 吊扇燈 | Tuya MCU | ✅ 已完成 |
| `ts0603_climate_TZE208_7aovt83n.py` | 溫控器 | Tuya MCU | ✅ 已完成 |
| `ts0001_switch_TZ3000_tqlv4ug4.py` | 1路開關 | 標準 ZCL | ✅ 已完成 |
| `ts0002_switch_TZ3000_denobasq.py` | 2路開關 | 標準 ZCL | ✅ 已完成 |
| `patch_zha_climate.py` | ZHA Climate 修補 | — | ✅ 輔助 |

---

## 七、關鍵技術筆記

### 7.1 已知的 zhaquirks/ZHA 限制

1. **ZHA 無 Text Entity 平台** — EntityPlatform 只支援 6 種：
   BINARY_SENSOR, BUTTON, NUMBER, SELECT, SENSOR, SWITCH

2. **TuyaClusterData.attr_value 只能是 int** — 字串 DP 需自建 MCU cluster 子類繞過

3. **TuyaQuirkBuilder 不提供 light/climate/fan 高階方法** — 需手動建立 ZCL cluster 子類

4. **`add_to_registry()` 會覆蓋先前的 `.replaces()`** — 需使用 `replacement_cluster=` 參數

5. **Standard ZCL 設備不需要 TuyaQuirkBuilder** — 直接用 `QuirkBuilder`

### 7.2 Simon 特有注意事項

1. Simon 製造商字串很長（`_TZ2000_xxxxxxxxxxxx`），不同設備間不共用
2. Simon 開關不是 TS0601，是標準 ZCL 設備
3. Simon 調光/窗簾/溫控 可能是 TS0601 也可能是標準 ZCL — 需要實際掃描確認
4. Simon 使用 PIC16F MCU + EFR32 MG13 ZigBee 模組，MCU-ZigBee 之間可能用私有協議
5. Zigbee2MQTT issue #23354 和 discussion #26491 有社群成員的初步適配工作

### 7.3 命名慣例

```
檔案命名：
  {zigbee_model}_{type}_{tuya_manufacturer}.py
  例：ts0601_dimmer_TZE204_xxxxxx.py
  例：simon_i7_s3100_cover.py  （如果是標準ZCL）

Quirk 內部命名：
  attribute_name:  snake_case（如 motor_direction）
  translation_key: 與 attribute_name 相同
  fallback_name:   人類可讀名稱（如 "Motor Direction"）
```

---

## 八、下一步行動

1. **取得 Simon 調光開關和窗簾開關實體設備**
2. 配對到 ZHA → `zha-toolkit scan_device` → 確定架構（標準 ZCL 或 Tuya MCU）
3. 如為 TS0601：探測完整 DP 列表
4. 根據本路線圖的模板，建立對應的 quirk
5. 部署測試 → 驗證所有功能
6. 提交到 git 版本控制

---

## 參考資源

- [TuyaQuirkBuilder Wiki](https://github.com/zigpy/zha-device-handlers/wiki/Tuya-%E2%80%90-v2-Quirk-with-TuyaQuirkBuilder)
- [tuya.md 文件](https://github.com/zigpy/zha-device-handlers/blob/dev/tuya.md)
- [TuyaQuirkBuilder 源碼](https://github.com/zigpy/zha-device-handlers/blob/dev/zhaquirks/tuya/builder/__init__.py)
- [Zigbee2MQTT Simon 支援 Issue #23354](https://github.com/Koenkk/zigbee2mqtt/issues/23354)
- [Zigbee2MQTT Simon 支援 Discussion #26491](https://github.com/Koenkk/zigbee2mqtt/discussions/26491)
- [涂鴉調光開關 DP 標準](https://developer.tuya.com/en/docs/iot/f?id=K9t2a5li5awj8)
- [涂鴉窗簾開關 Zigbee 接入標準](https://developer.tuya.com/en/docs/iot-device-dev/zigbee-curtain-switch-access-standard?id=K9ik6zvra3twv)
- [涂鴉空調控制器 DP 標準](https://developer.tuya.com/en/docs/iot/f?id=K9gf46veir2mu)
- [Simon 官網 i7 Smart](https://www.simon-apac.com/contents/products/simon-smart.html)
- [Simon 智能新風開關拆解（CSDN）](https://blog.csdn.net/DPSmart/article/details/137814862)
- [Threecubes Simon i7 產品頁](https://www.threecubes.com.sg/collections/simon)
