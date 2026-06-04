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
- 需要實際抓取 DP 才能確定完整映射方式

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
| `ts0001_switch_TZ3000_tqlv4ug4.py` | 1路開關 | 標準 ZCL | ✅ 已完成 |
| `ts0002_switch_TZ3000_denobasq.py` | 2路開關 | 標準 ZCL | ✅ 已完成 |

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

## 九、深度技術分析（已驗證的開發模式）

> 以下內容來自對容器上已運作 quirks 的逐行分析，
> 以及 ZHA/zhaquirks 源碼的實際驗證。

### 9.1 ZHA 平台實體發現機制

ZHA 透過兩層條件決定為每個端點建立什麼 HA 實體：

**第一層：`device_type`（端點設備類型）**

```
Profile 260 (ZHA):
  Light 平台接受:
    ON_OFF_LIGHT (0x0100)        → 簡單開關燈
    DIMMABLE_LIGHT (0x0101)      → 可調光燈
    COLOR_DIMMABLE_LIGHT (0x0102)→ 彩色可調光燈
    COLOR_TEMPERATURE_LIGHT (0x010C) → 色溫燈
    EXTENDED_COLOR_LIGHT (0x010D)→ 擴展彩色燈 (RGBCW)
    DIMMABLE_BALLAST (0x0109)    → 可調光鎮流器
    DIMMABLE_PLUG_IN_UNIT (0x010B)

  Cover 平台: 不依賴 device_type，僅匹配 WindowCovering cluster (0x0102)
  Climate 平台: 不依賴 device_type，僅匹配 Thermostat cluster (0x0201)
  Fan 平台: 不依賴 device_type，僅匹配 Fan cluster (0x0202)
```

**第二層：`cluster_handler_match`（cluster 組合匹配）**

| 平台 | 必要 cluster | 可選 cluster | device_type 限制 |
|------|-------------|-------------|-----------------|
| Light | OnOff (0x0006) | Color, LevelControl | 必須在 LIGHT_PROFILE_DEVICE_TYPES 中 |
| Switch | OnOff (0x0006) | — | 排除 Light 類型的 device_type |
| Cover | WindowCovering (0x0102) | — | 無限制 |
| Climate | Thermostat (0x0201) | Fan (0x0202) | 無限制 |
| Fan | Fan (0x0202) | — | 無限制 |

**關鍵結論**：
- 建立 **Light** 實體：端點必須有 `OnOff` cluster + `device_type` 是 Light 類型之一
- 建立 **Cover** 實體：端點只需有 `WindowCovering` cluster
- 建立 **Climate** 實體：端點只需有 `Thermostat` cluster
- 建立 **Fan** 實體：端點只需有 `Fan` cluster
- Light 和 Switch 互斥：同一端點的 OnOff cluster 只會產生一種實體

### 9.2 DP 數據流完整路徑

#### 入站（設備 → HA）

```
物理設備 MCU
  ↓  Zigbee 幀 (Tuya cluster 0xEF00 report)
zigpy 接收原始幀
  ↓  分派到 TuyaMCUCluster (或自訂子類)
TuyaMCUCluster.handle_get_data(command: TuyaCommand)
  ↓  遍歷 command.datapoints
  ↓  查詢 self.data_point_handlers[record.dp]
  ↓  呼叫 self._dp_2_attr_update(record) 或自訂處理器
_dp_2_attr_update(datapoint)
  ↓  查詢 self._dp_to_attributes[dp] → DPToAttributeMapping 列表
  ↓  對每個映射：找到目標 cluster + 屬性
  ↓  呼叫 converter(value) 做值轉換
  ↓  cluster.update_attribute(attr_name, value)
ZCL cluster._update_attribute(attr_id, value)
  ↓  ZHA ClusterHandler 偵測到屬性變化
ZHA Entity 狀態更新
  ↓
HA 前端 UI 更新
```

#### 出站（HA → 設備）

**路徑 A：builder 管理的 DP（tuya_switch/tuya_enum/tuya_number 等）**
```
HA 前端操作
  ↓
ZHA Entity → TuyaMCUCluster.write_attributes({attr: value})
  ↓  建立 TuyaClusterData(attr_value=int)
  ↓  觸發 command_bus TUYA_MCU_COMMAND 事件
  ↓  from_cluster_data() → 查詢 dp_mapping → 建立 TuyaCommand
  ↓  self.command(0x00, tuya_cmd)
  ↓  Zigbee 幀發送到設備
```

**路徑 B：自訂 cluster 的 command()（用於 Light/Climate/Fan）**
```
HA 前端操作（如 light.turn_on）
  ↓
ZHA Light Entity → ZCL command (如 move_to_level)
  ↓
自訂 cluster.command(cmd_id, *args)
  ↓  攔截命令，轉換為 Tuya DP
  ↓  mcu = self.endpoint.tuya_manufacturer（或跨端點取得）
  ↓  mcu.send_dp(TuyaDatapointData(...))  或  mcu.write_attributes(...)
  ↓  _update_attribute() 立即更新本地狀態（UI即時回饋）
  ↓  返回 Default_Response(SUCCESS)
```

**⚠️ 關鍵差異**：
- 路徑 A 經過 `TuyaClusterData`（`attr_value: int`），只能傳整數
- 路徑 B 直接建構 `TuyaDatapointData`，可傳任何類型（字串、raw bytes 等）
- 已驗證的繞過方式：`ScreenLabelTuyaMCUCluster` 覆寫 `write_attributes` 直接建構 `TuyaCommand`

### 9.3 TuyaQuirkBuilder 完整方法清單（57 個方法）

#### Tuya 專用 DP 映射方法（20 個）
```python
# 基礎設備控制
tuya_switch(dp_id, attribute_name="on_off", ...)     → Switch 實體
tuya_onoff(dp_id, onoff_cfg=TuyaOnOffNM, ...)        → OnOff cluster
tuya_cover(control_dp, position_state_dp, position_control_dp, invert=True) → Cover 實體
tuya_enum(dp_id, attribute_name, enum_class, ...)     → Select 實體
tuya_number(dp_id, type, attribute_name, min/max/step/unit, ...) → Number 實體
tuya_binary_sensor(dp_id, attribute_name, ...)        → Binary Sensor 實體
tuya_sensor(dp_id, attribute_name, type, converter, ...) → Sensor 實體

# 環境感測
tuya_temperature(dp_id, scale=100, ...)               → 溫度感測器
tuya_humidity(dp_id, scale=100, ...)                  → 濕度感測器
tuya_co2(dp_id, scale=1e-06, ...)                     → CO2 濃度
tuya_pm25(dp_id, scale=1, ...)                        → PM2.5
tuya_voc(dp_id, scale=1e-06, ...)                     → VOC
tuya_formaldehyde(dp_id, converter=lambda, ...)       → 甲醛
tuya_illuminance(dp_id, converter=lambda, ...)        → 光照
tuya_soil_moisture(dp_id, scale=100, ...)             → 土壤濕度
tuya_electrical_conductivity(dp_id, scale=1, ...)     → 電導率

# 安全/二元感測
tuya_ias(dp_id, ias_cfg, converter, ...)              → IAS Zone
tuya_contact(dp_id, ...)                              → 門窗感測器
tuya_gas(dp_id, ...)                                  → 瓦斯偵測
tuya_smoke(dp_id, ...)                                → 煙霧偵測
tuya_vibration(dp_id, ...)                            → 振動偵測

# 電源
tuya_battery(dp_id, power_cfg, battery_type, ...)     → 電池電量
tuya_metering(dp_id, metering_cfg, scale, ...)        → 計量

# 底層 DP 映射
tuya_dp(dp_id, ep_attribute, attribute_name, converter, dp_converter) → 底層映射
tuya_dp_attribute(dp_id, attribute_name, type, ...)   → 純屬性（無實體）
tuya_dp_multi(dp_id, attribute_mapping, ...)          → 多屬性映射
tuya_attribute(dp_id, attribute_name, type, access)   → 添加屬性定義
```

#### 通用 QuirkBuilder 方法（37 個）
```python
# 端點管理
adds_endpoint(endpoint_id, profile_id=260, device_type=255)
removes_endpoint(endpoint_id)
replaces_endpoint(endpoint_id, profile_id=260, device_type=255)

# Cluster 管理
adds(cluster, cluster_type=Server, endpoint_id=1, constant_attributes=None)
removes(cluster_id, cluster_type=Server, endpoint_id=1)
replaces(replacement_cluster, cluster_id=None, cluster_type=Server, endpoint_id=1)
replace_cluster_occurrences(replacement_cluster, server=True, client=True)

# 實體自訂
enum(attribute_name, enum_class, cluster_id, ...)
number(attribute_name, cluster_id, min/max/step, ...)
sensor(attribute_name, cluster_id, divisor, multiplier, ...)
binary_sensor(attribute_name, cluster_id, ...)
switch(attribute_name, cluster_id, ...)
command_button(command_name, cluster_id, ...)
write_attr_button(attribute_name, attribute_value, cluster_id, ...)

# 實體修改
change_entity_metadata(endpoint_id, cluster_id, ...)
prevent_default_entity_creation(endpoint_id, cluster_id, ...)

# 設備觸發
device_automation_triggers(triggers_dict)

# 註冊
add_to_registry(replacement_cluster=TuyaMCUCluster, force_add_cluster=False,
                mcu_write_command=0)
also_applies_to(manufacturer, model)
applies_to(manufacturer, model)

# 配置
skip_configuration(skip=True)
tuya_enchantment(read_attr_spell=True, data_query_spell=False)
friendly_name(model, manufacturer)
device_class(custom_device_class)
device_alert(level, message)
filter(filter_function)
firmware_version_filter(min_version, max_version, allow_missing)
node_descriptor(node_descriptor)
clone(omit_man_model_data=True)
exposes_feature(feature, config)
```

### 9.4 已驗證的開發模式清單

基於容器上 9 個 quirk 的分析，歸納出 6 種經過驗證的開發模式：

#### 模式 1：純 Builder 聲明式（最簡單）
**適用**：只需要 switch/select/number/sensor/binary_sensor 的設備
```python
TuyaQuirkBuilder(mfr, "TS0601")
    .tuya_switch(dp_id=1, ...)
    .tuya_enum(dp_id=4, ...)
    .skip_configuration()
    .add_to_registry()
```
**範例**：簡單開關（ts0001_switch_TZ3000_tqlv4ug4.py）

#### 模式 2：Builder + tuya_cover()
**適用**：窗簾設備（3-DP 標準模式）
```python
TuyaQuirkBuilder(mfr, "TS0601")
    .tuya_cover(control_dp=1, position_state_dp=3, position_control_dp=2, invert=True)
    .skip_configuration()
    .add_to_registry()
```
**範例**：ts0601_cover_TZE284_qxjkdfyt.py

#### 模式 3：Builder + tuya_dp() + .adds(custom_cluster)
**適用**：窗簾（非標準 DP）、特殊感測器
```python
TuyaQuirkBuilder(mfr, "TS0601")
    .tuya_dp(dp_id=1, ep_attribute="window_covering", attribute_name="tuya_cover_command")
    .tuya_dp(dp_id=2, ..., converter=lambda x: 100-x, dp_converter=lambda x: 100-x)
    .adds(TuyaWindowCovering)
    .replaces_endpoint(1, device_type=WINDOW_COVERING_DEVICE)
    .add_to_registry()
```
**範例**：tuya_cover_nogaemzt.py

#### 模式 4：自訂 ZCL cluster + Builder + replacement_cluster
**適用**：Light、Fan、需要攔截 ZCL 命令的複雜設備

**核心架構**：
```python
class MyOnOff(OnOff, TuyaLocalCluster):       # 攔截 on/off
class MyOnOffNM(NoManufacturerCluster, MyOnOff): # 加入 NM mixin
class MyMCU(TuyaMCUCluster):                  # 自訂入站 DP 路由
    def handle_get_data(self, command):
        for record in command.datapoints:
            if record.dp in CUSTOM_DPS:
                self._dp_2_attr_update(record)  # 自訂路由
            else:
                # builder 管理的 DP 走 super()
    def _dp_2_attr_update(self, datapoint):
        # 跨端點更新屬性

TuyaQuirkBuilder(mfr, "TS0601")
    .adds(MyOnOffNM)
    .adds_endpoint(2, device_type=ON_OFF_LIGHT)
    .adds(MyLightNM, endpoint_id=2)
    .tuya_enum(dp_id=102, ...)  # builder 管理的簡單 DP
    .skip_configuration()
    .add_to_registry(replacement_cluster=MyMCU)
```
**範例**：
- ts0601_fan_TZE200_hmgktzj2.py（風扇+燈光+色溫）
- ts0601_light_TZE284_gt5al3bl.py（RGBCW LED 控制器）

#### 模式 5：V2 Builder + TuyaThermostatV2（溫控器最佳實踐）
**適用**：溫控器/TRV
```python
class MyThermostat(TuyaThermostatV2):
    _CONSTANT_ATTRIBUTES = {
        abs_min_heat_setpoint_limit: 500,   # 5.00°C
        abs_max_heat_setpoint_limit: 3000,  # 30.00°C
        ctrl_sequence_of_oper: Heating_Only,
    }

TuyaQuirkBuilder(mfr, "TS0601")
    .adds(MyThermostat)
    .tuya_dp(dp_id=1, ep_attribute="thermostat",
             attribute_name="system_mode",
             converter=lambda x: {True: Heat, False: Off}[x],
             dp_converter=lambda x: {Heat: True, Off: False}[x])
    .tuya_dp(dp_id=2, ep_attribute="thermostat",
             attribute_name="occupied_heating_setpoint",
             converter=lambda x: x * 10,
             dp_converter=lambda x: x // 10)
    .skip_configuration()
    .add_to_registry()
```
**來源**：zhaquirks/tuya/tuya_trv.py（官方 V2 模式）

#### 模式 6：完全自訂 MCU + 多端點路由（最複雜）
**適用**：多區溫控、多功能面板
```python
class MyMCU(TuyaMCUCluster):
    # 完全覆寫 handle_cluster_request
    # 自建跨端點 DP 路由邏輯
    # 自建 send_dp() 方法
    # 可能需要自建通訊協議處理

class MyThermostat(Thermostat, TuyaLocalCluster):
    _CONSTANT_ATTRIBUTES = {...}
    async def write_attributes(self, attrs, ...):
        mcu = _find_mcu(self.endpoint.device)
        # 直接建構 DP 並發送

TuyaQuirkBuilder(mfr, "TS0601")
    .adds(MyThermostat)
    .adds_endpoint(2, device_type=THERMOSTAT)
    .adds(MyThermostat, endpoint_id=2)
    # ... 更多端點
    .tuya_enchantment(read_attr_spell=True, data_query_spell=True)
    .skip_configuration()
    .add_to_registry(replacement_cluster=MyMCU, force_add_cluster=True)
```

### 9.5 常見陷阱與解決方案

| 陷阱 | 症狀 | 解決方案 |
|------|------|----------|
| `TuyaClusterData.attr_value: int` | 字串 DP 寫入報 ValueError | 自訂 MCU cluster 覆寫 write_attributes，直接建構 TuyaCommand |
| `.replaces()` 被 `add_to_registry()` 覆蓋 | 自訂 MCU cluster 不生效 | 使用 `add_to_registry(replacement_cluster=MyMCU)` |
| Light/Switch 互斥衝突 | OnOff cluster 產生 Switch 而非 Light | 使用 `.replaces_endpoint(device_type=ON_OFF_LIGHT)` 強制 Light |
| 跨端點 DP 路由 | 端點 2 的 cluster 無法存取 MCU | `self.endpoint.device.endpoints[1].tuya_manufacturer` |
| MCU 忽略同幀多 DP | 第二個 DP 被忽略 | 分開發送或使用 batch queue 延遲合併 |
| ZHA fan 只有 3 速 | 6 速風扇只顯示 Low/Med/High | 模組載入時 monkey-patch SPEED_RANGE |
| ZHA fan 無方向支援 | 無法設定風扇正反轉 | monkey-patch ZHA Fan entity 和 HA ZhaFan bridge |
| `Default_Response` 大小寫 | `AttributeError` 導致 HTTP 500 | 使用 `GeneralCommand.Default_Response`（注意大小寫）|
| `NoManufacturerCluster` 遺漏 | 設備不回應 ZCL 命令 | 自訂 cluster 用 NM 變體：`class MyNM(NoManufacturerCluster, My)` |
| `TuyaLocalCluster` 遺漏 | ZHA 嘗試 OTA 讀取不存在的屬性 | 自訂 cluster 繼承 `TuyaLocalCluster` mixin |

### 9.6 `send_dp` 幫手方法模式

所有自訂 MCU cluster 共用的 DP 發送模式：

```python
async def send_dp(self, dpd: TuyaDatapointData):
    """發送單個 DP 到設備。"""
    cmd = TuyaCommand(
        status=0,
        tsn=self.endpoint.device.application.get_sequence(),
        datapoints=[dpd],
    )
    # Fire-and-forget（不等回應，靠設備回報確認）
    asyncio.get_running_loop().call_soon(
        functools.partial(
            self.create_catching_task,
            self.command(TUYA_MCU_COMMAND, cmd, expect_reply=False),
        )
    )
```

或更完整的 batch 版本（用於 Light quirk 的批量 DP）：
```python
# 累積 DPs
self._pending_dps[dp_id] = TuyaDatapointData(dp=dp_id, data=tuya_data)
# 排程合併發送（15ms 防抖）
self._schedule_flush()

async def flush_batch(self):
    """合併所有待發 DP 為一個幀。"""
    dps = list(self._pending_dps.values())
    self._pending_dps.clear()
    cmd = TuyaCommand(
        status=0, tsn=..., datapoints=dps
    )
    await self.command(TUYA_MCU_COMMAND, cmd, expect_reply=False)
```

### 9.7 Simon 設備對照：預期架構判斷依據

| 判斷標準 | 標準 ZCL (如 S2100) | Tuya MCU (TS0601) |
|----------|---------------------|-------------------|
| Zigbee 模型 | S2100-XXXX | TS0601 |
| 製造商字串 | `_TZ2000_xxxxx` | `_TZE200/204/284_xxxxx` |
| endpoint 結構 | 每路一個 endpoint，各有獨立 cluster | 通常只有 endpoint 1 + 0xEF00 |
| cluster 0xEF00 | 無 | 有 |
| 功能 cluster | 標準 ZCL (OnOff/LevelControl/...) | 虛擬（需 quirk 建立） |
| 操作方式 | 直接 ZCL 命令 | 透過 DP 協議 |
| quirk 框架 | `QuirkBuilder` | `TuyaQuirkBuilder` |

**配對後立即可判斷**：看 endpoint 1 是否有 cluster 0xEF00。

---

## 參考資源

- [TuyaQuirkBuilder Wiki](https://github.com/zigpy/zha-device-handlers/wiki/Tuya-%E2%80%90-v2-Quirk-with-TuyaQuirkBuilder)
- [tuya.md 文件](https://github.com/zigpy/zha-device-handlers/blob/dev/tuya.md)
- [TuyaQuirkBuilder 源碼](https://github.com/zigpy/zha-device-handlers/blob/dev/zhaquirks/tuya/builder/__init__.py)
- [tuya_trv.py V2 溫控器範例](https://github.com/zigpy/zha-device-handlers/blob/dev/zhaquirks/tuya/tuya_trv.py)
- [ts0601_dimmer.py V1 調光範例](https://github.com/zigpy/zha-device-handlers/blob/dev/zhaquirks/tuya/ts0601_dimmer.py)
- [ts0601_electric_heating.py 電暖氣範例](https://github.com/zigpy/zha-device-handlers/blob/dev/zhaquirks/tuya/ts0601_electric_heating.py)
- [Zigbee2MQTT Simon 支援 Issue #23354](https://github.com/Koenkk/zigbee2mqtt/issues/23354)
- [Zigbee2MQTT Simon 支援 Discussion #26491](https://github.com/Koenkk/zigbee2mqtt/discussions/26491)
- [涂鴉調光開關 DP 標準](https://developer.tuya.com/en/docs/iot/f?id=K9t2a5li5awj8)
- [涂鴉窗簾開關 Zigbee 接入標準](https://developer.tuya.com/en/docs/iot-device-dev/zigbee-curtain-switch-access-standard?id=K9ik6zvra3twv)
- [涂鴉空調控制器 DP 標準](https://developer.tuya.com/en/docs/iot/f?id=K9gf46veir2mu)
- [Simon 官網 i7 Smart](https://www.simon-apac.com/contents/products/simon-smart.html)
- [Simon 智能新風開關拆解（CSDN）](https://blog.csdn.net/DPSmart/article/details/137814862)
- [Threecubes Simon i7 產品頁](https://www.threecubes.com.sg/collections/simon)
- [ZHA 實體匹配機制 DeepWiki](https://deepwiki.com/home-assistant/core/6.2-zha-(zigbee-home-automation))
- [HA Community: 如何建立 Tuya Quirk](https://community.home-assistant.io/t/my-tuya-device-doesnt-work-with-zha-or-how-to-build-a-tuya-quirk/806728)
- [Writing ZHA Quirks Blog](https://semolex.online/post/writing-zha-quirks/)
