# 部署與測試計畫：woow_zha_quirks 套件 → 192.168.2.12 HAOS

## 目標環境

| 項目 | 值 |
|------|-----|
| Host | 192.168.2.12 |
| OS | Home Assistant OS 17.2 (RPi5-64) |
| HA Version | 2026.4.4 |
| Python | 3.14.2 |
| zha | 1.1.2 |
| zha-quirks | 1.1.1 |
| zigpy | 1.2.2 |
| SSH 指令 | `sshpass -p 'woowtech' ssh root@192.168.2.12` |
| 容器操作 | `docker exec homeassistant <cmd>` |
| ZHA 狀態 | 未啟用（無 Zigbee 協調器） |

## 部署步驟

### Step 1: 部署套件檔案到 HAOS
- 透過 scp 複製 `custom_components/woow_zha_quirks/` 到 `/config/custom_components/`
- 透過 scp 複製 `custom_components/tuya_dp_sender/` 到 `/config/custom_components/`
- 驗證檔案完整性（檔案數量、大小）

### Step 2: 修改 configuration.yaml
- 加入 `woow_zha_quirks:` 設定
- 加入 `tuya_dp_sender:` 設定
- 驗證 YAML 語法正確

### Step 3: 重啟 HA
- 呼叫 HA API 或 ha core restart 重啟
- 等待啟動完成

## 測試計畫

### 測試 1: Integration 載入驗證
- 檢查 HA log 有無 `woow_zha_quirks` 相關訊息
- 確認 "WOOW ZHA Quirks: 成功載入 X 個 quirk 模組" 日誌出現
- 確認無 ERROR 或 EXCEPTION

### 測試 2: Quirks 模組載入驗證
- 透過 HA log 確認每個 quirk 模組都被載入
- 預期載入 10 個模組（不含 __init__.py）
- 特別注意 patch_zha_climate.py 的 monkey-patch 是否成功（因為 ZHA 未啟用可能會 import 失敗）

### 測試 3: tuya_dp_sender 載入驗證
- 確認 tuya_dp_sender integration 成功載入
- 確認服務 `tuya_dp_sender.send_dp` 和 `tuya_dp_sender.send_dp_string` 已註冊
- 注意：因為 ZHA 未啟用，平台實體可能不會建立（這是預期行為）

### 測試 4: 錯誤容忍度測試
- ZHA 未啟用情境下，套件不應該讓 HA 啟動失敗
- 應該優雅地處理 ZHA 不可用的狀況（log warning 而非 crash）

### 測試 5: manifest.json 驗證
- 確認 HA 可正確解析兩個 manifest.json
- 確認 version 欄位存在（HACS 需求）
- 確認 dependencies 正確

### 測試 6: 檔案結構完整性
- 確認所有檔案都正確部署
- 確認 quirks/ 目錄下有 11 個 .py 檔案
- 確認 tuya_dp_sender/ 目錄下有 7 個檔案

## 預期問題和處理

1. **ZHA 未啟用** → quirks 載入可能部分失敗（依賴 zhaquirks 的模組）
   - 處理：檢查哪些模組失敗，分析原因
   - 如果是 import 階段就失敗，需要加 try-except

2. **patch_zha_climate.py** → monkey-patch ZHA 內部模組，ZHA 未啟用時可能找不到目標
   - 處理：確認是否需要在無 ZHA 時跳過

3. **tuya_dp_sender 依賴 ZHA** → manifest 宣告 dependencies: ["zha"]
   - 處理：如果 ZHA 未設定，HA 可能拒絕載入此 integration

## 成功標準

- [ ] 兩個 integration 都出現在 HA 的 integration 列表中
- [ ] woow_zha_quirks 日誌顯示成功載入 quirk 模組
- [ ] 無 critical/fatal 錯誤導致 HA 啟動失敗
- [ ] 所有檔案正確部署
- [ ] configuration.yaml 語法正確
