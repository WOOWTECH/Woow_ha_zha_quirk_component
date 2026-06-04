# WOOW ZHA Quirks

集中管理自訂 ZHA Quirks 的 Home Assistant 套件。

透過 HACS 一鍵安裝，自動載入所有自訂 Zigbee 裝置 quirks，不需要手動設定 `custom_quirks_path`。

## 支援裝置

| 裝置 | Manufacturer ID | 說明 |
|------|----------------|------|
| Simon i7 S2100 | `_TZ2000_sayvzx8w`, `_TZ2000_vvxwtxzf` | 智慧開關（含 AllOnOff 虛擬端點） |
| Tuya TS0001 | `_TZ3000_tqlv4ug4` | 單路開關 |
| Tuya TS0002 | `_TZ3000_denobasq` | 雙路開關 |
| Tuya TS0601 | `_TZE284_qxjkdfyt` | 捲簾電機（含馬達方向、限位、模式設定） |
| Tuya TS0601 | `_TZE200_hmgktzj2` | 吊扇+燈 6速3模式 |
| Tuya TS0601 | `_TZE284_gt5al3bl` | Gledopto SPI LED 幻彩燈控制器 |
| Tuya TS0601 | `_TZE204_wwaeqnrf` | Zemismart 4路觸控開關（含螢幕標籤寫入） |
| Tuya TS0601 | `_TZE208_7aovt83n` | VRV 多聯機空調控制器 6區域 |
| Tuya TS0601 | `_TZE200_nogaemzt` | 窗簾軌道電機（含馬達方向、限位、模式設定） |

另外包含 `patch_zha_climate.py`，修補 ZHA Climate 平台的 fan_mode 和 HVAC 模式擴充。

## 安裝

### 透過 HACS（推薦）

1. 開啟 HACS
2. 點選右上角選單 → **自訂倉庫**
3. 輸入 `https://github.com/WOOWTECH/Woow_ha_zha_quirk_component`
4. 類別選 **Integration**
5. 搜尋 **WOOW ZHA Quirks** → 安裝
6. 在 `configuration.yaml` 加入：

```yaml
woow_zha_quirks:
```

7. 重啟 Home Assistant

### 手動安裝

1. 下載此倉庫
2. 複製 `custom_components/woow_zha_quirks/` 到你的 HA `config/custom_components/`
3. 在 `configuration.yaml` 加入上述設定
4. 重啟 Home Assistant

## 注意事項

- 安裝此套件後，**不需要** 再設定 `zha: custom_quirks_path:`
- 如果之前有設定 `custom_quirks_path`，可以移除該設定（除非你還有其他不在此套件內的 quirks）
- 原 `tuya_dp_sender` 的功能已全部整合進各 quirk 的 CONFIG 實體中，不再需要額外安裝
- 需要 ZHA integration 已正常運作
- 相依套件：`zha`, `zha-quirks`, `zigpy`

## 授權

MIT License - WOOWTECH
