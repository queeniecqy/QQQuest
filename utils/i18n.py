"""
QQQuest UI internationalization helpers.
"""
from __future__ import annotations

from functools import wraps
import re
from typing import Any, Callable

import streamlit as st
from streamlit import column_config as st_column_config
from streamlit.delta_generator import DeltaGenerator


LANGUAGE_SESSION_KEY = "ui_language"
DEFAULT_LANGUAGE = "zh-TW"
SUPPORTED_LANGUAGES = ("zh-TW", "en")

LANGUAGE_DISPLAY = {
    "zh-TW": {
        "zh-TW": "繁體中文",
        "en": "Traditional Chinese",
    },
    "en": {
        "zh-TW": "英文",
        "en": "English",
    },
}


EXACT_TRANSLATIONS = {
    "Language / 語言": "Language",
    """
## 歡迎使用 QQQuest！

這是一個基於 ADB 和 scrcpy 的 Quest 設備群組管理系統，支援多設備同步控制、時間碼同步和操作排程。

### 功能特色

- 📱 **設備管理**：WiFi ADB 連接、設備狀態監控
- 🏠 **房間管理**：創建房間、設備分配、批量控制
- ⚡ **動作管理**：預設動作（休眠、開啟/關閉程式、傳送訊息）
- ⏱️ **時間碼同步**：房間時間碼、高精度設備同步
- 📅 **CUE 排程**：時間軸編輯、自動執行操作序列
- 🖥️ **scrcpy 整合**：多設備螢幕鏡像

### 快速開始

1. 前往 **📱 設備管理** 頁面連接你的 Quest 設備
2. 在 **🏠 房間管理** 頁面建立房間並分配設備
3. 使用 **⚡ 動作管理** 頁面設定和執行操作

---

### 系統狀態
""": """
## Welcome to QQQuest!

This is a Quest device group management system built on ADB and scrcpy, supporting multi-device synchronized control, timeline sync, and operation scheduling.

### Key Features

- 📱 **Device Management**: Wi-Fi ADB connection and device status monitoring
- 🏠 **Room Management**: Create rooms, assign devices, and batch control
- ⚡ **Action Management**: Reusable actions for sleep, app launch/stop, and messaging
- ⏱️ **Timeline Sync**: Room timeline management and high-precision device synchronization
- 📅 **CUE Scheduling**: Timeline editing and automated action sequences
- 🖥️ **scrcpy Integration**: Multi-device screen mirroring

### Quick Start

1. Go to **📱 Device Management** to connect your Quest devices
2. Create a room and assign devices in **🏠 Room Management**
3. Use **⚡ Action Management** to configure and run operations

---

### System Status
""",
    """
            ### 網路監控功能說明
            
            1. **Ping 監控**
               - 系統會定期 Ping 設備的 IP 地址
               - 記錄響應時間來評估網路品質
               - 只有 WiFi 連接的設備需要 Ping
            
            2. **自動連接**
               - 當設備 Ping 通但未連接時，自動嘗試連接
               - 如果連接失敗，會重試指定次數
               - 超過重試次數後，標記為「無法連線」（需要手動開啟 WiFi ADB）
            
            3. **設備狀態**
               - **在線**：已連接並可用
               - **離線**：已連接但狀態異常
               - **未連接**：Ping 不通，設備可能關機
               - **無法連線**：Ping 通但無法連接（WiFi ADB 未開啟）
            
""": """
            ### Network Monitoring Overview
            
            1. **Ping Monitoring**
               - The system regularly pings each device IP address
               - Response time is recorded to evaluate network quality
               - Only Wi-Fi connected devices need ping monitoring
            
            2. **Auto Connect**
               - When a device responds to ping but is not connected, the system tries to reconnect automatically
               - If reconnection fails, it retries the configured number of times
               - After the retry limit is exceeded, the device is marked as **Unreachable** (Wi-Fi ADB must be enabled manually)
            
            3. **Device Status**
               - **Online**: Connected and available
               - **Offline**: Connected but in an abnormal state
               - **Not Connected**: Ping failed, the device may be powered off
               - **Unreachable**: Ping works but ADB connection fails (Wi-Fi ADB is not enabled)
            
""",
    """
                **height_calibration**: 
                輸入三個高度參數 (int) 並發送給指定的 Quest 客戶端 (或廣播)。
                
""": """
                **height_calibration**:
                Enter three height parameters (int) and send them to the specified Quest client, or broadcast them to all clients.
                
""",
}


PHRASE_TRANSLATIONS = [
    ("QQQuest - Quest 設備同步管理系統", "QQQuest - Quest Device Sync Management"),
    ("這是一個基於 ADB 和 scrcpy 的 Quest 設備群組管理系統，支援多設備同步控制、時間碼同步和操作排程。", "This is a Quest device group management system built on ADB and scrcpy, supporting multi-device synchronized control, timeline sync, and operation scheduling."),
    ("房間管理功能開發中...", "Room management is still under development..."),
    ("動作管理功能開發中...", "Action management is still under development..."),
    ("尚無活動記錄", "No recent activity"),
    ("建立和管理房間，批量控制多台設備", "Create and manage rooms and batch-control multiple devices"),
    ("建立和管理可重複使用的設備動作", "Create and manage reusable device actions"),
    ("請先前往動作管理頁面創建動作", "Please create an action in Action Management first"),
    ("點擊「新增動作」開始創建", "Click \"Add Action\" to get started"),
    ("請點擊「新增設備」來連接 Quest 設備", "Click \"Add Device\" to connect a Quest device"),
    ("點擊「新增房間」創建房間，然後在房間中加入設備", "Click \"Add Room\" to create a room, then add devices to it"),
    ("此房間內沒有在線設備可供監看", "There are no online devices in this room available for monitoring"),
    ("沒有發現運行的監控視窗", "No running monitor windows found"),
    ("已關閉所有監控視窗", "All monitor windows have been closed"),
    ("請輸入設備代號", "Please enter a device alias"),
    ("請輸入房間名稱", "Please enter a room name"),
    ("請輸入動作名稱", "Please enter an action name"),
    ("系統 UI 接管", "System UI took focus"),
    ("設備沒有 IP 地址", "Device has no IP address"),
    ("沒有 IP 地址", "has no IP address"),
    ("目前沒有活躍玩家連接", "No active player connections"),
    ("目前沒有設備報告狀態", "No devices are currently reporting status"),
    ("尚未載入提醒事件，請展開上方設定進行新增", "No reminder events have been loaded yet. Expand the settings above to add them."),
    ("共用 z 值格式無效", "The shared z value format is invalid"),
    ("送出位置調整失敗", "Failed to send position adjustment"),
    ("同步房間位置設定失敗", "Failed to sync room position settings"),
    ("儲存房間位置設定失敗", "Failed to save room position settings"),
    ("已儲存房間位置設定", "Room position setting saved"),
    ("已同步房間位置設定", "Room position setting synced"),
    ("目前記憶位置 z", "Saved position z"),
    ("批量修改會送到目前連線中的設備，之後 client 重新連線並回到 chapter 0，或再次進入 chapter 5 時，也會自動套用這個值。", "Bulk updates will be sent to currently connected devices. After the client reconnects and returns to chapter 0, or re-enters chapter 5, this value will be applied automatically."),
    ("若穿透模式或系統覆蓋層擋住畫面，可嘗試先送一次 BACK，再喚回 App", "If Passthrough mode or a system overlay is blocking the view, send BACK once before bringing the app to the foreground."),
    ("適合 Quest 誤觸穿透模式時，把仍在背景運行的遊戲帶回前景，不會先關閉或重啟。", "Useful when Quest accidentally enters Passthrough mode and you want to bring the game back to the foreground without stopping or restarting it."),
    ("先送 BACK，再用 explicit VR activity/monkey 將", "Send BACK first, then use explicit VR activity/monkey to bring"),
    ("帶回前景，並檢查 Quest 畫面焦點", "back to the foreground and verify Quest focus"),
    ("前往 **📱 設備管理** 頁面連接你的 Quest 設備", "Go to **📱 Device Management** to connect your Quest devices"),
    ("在 **🏠 房間管理** 頁面建立房間並分配設備", "Create a room and assign devices in **🏠 Room Management**"),
    ("使用 **⚡ 動作管理** 頁面設定和執行操作", "Use **⚡ Action Management** to configure and run operations"),
    ("歡迎使用 QQQuest！", "Welcome to QQQuest!"),
    ("功能特色", "Key Features"),
    ("快速開始", "Quick Start"),
    ("快速操作", "Quick Actions"),
    ("最近活動", "Recent Activity"),
    ("系統狀態", "System Status"),
    ("設備總數", "Total Devices"),
    ("在線設備", "Online Devices"),
    ("房間數量", "Room Count"),
    ("房間總數", "Total Rooms"),
    ("總設備數", "Total Devices"),
    ("有設備的房間", "Rooms With Devices"),
    ("空房間", "Empty Rooms"),
    ("管理設備", "Manage Devices"),
    ("管理房間", "Manage Rooms"),
    ("管理動作", "Manage Actions"),
    ("設備管理", "Device Management"),
    ("房間管理", "Room Management"),
    ("動作管理", "Action Management"),
    ("系統設定", "System Settings"),
    ("新增設備", "Add Device"),
    ("新增房間", "Add Room"),
    ("新增動作", "Add Action"),
    ("新增參數", "Add Parameter"),
    ("編輯設備", "Edit Device"),
    ("編輯房間", "Edit Room"),
    ("編輯動作", "Edit Action"),
    ("編輯參數", "Edit Parameter"),
    ("刪除房間", "Delete Room"),
    ("刪除動作", "Delete Action"),
    ("確認刪除", "Confirm Delete"),
    ("確認移除設備", "Confirm Device Removal"),
    ("移除設備", "Remove Device"),
    ("房間視圖", "Room View"),
    ("Socket Server 監控", "Socket Server Monitor"),
    ("時間提醒", "Time Reminder"),
    ("即時狀態 (Real-time Status)", "Real-time Status"),
    ("即時狀態", "Real-time Status"),
    ("操作", "Actions"),
    ("位置調整", "Position Adjust"),
    ("切回遊戲", "Return to Game"),
    ("使用者位置", "User Position"),
    ("批量修改位置", "Apply Position to All"),
    ("重新調整位置", "Reposition"),
    ("房間內設備", "Devices in Room"),
    ("群控管理", "Group Control"),
    ("群控面板", "Control Panel"),
    ("日誌監看", "Log Monitor"),
    ("命令發送", "Command Sending"),
    ("發送命令到 Socket Server", "Send Commands to Socket Server"),
    ("命令類型", "Command Type"),
    ("發送命令", "Send Command"),
    ("刷新玩家狀態", "Refresh Player Status"),
    ("刷新日誌", "Refresh Log"),
    ("刷新狀態", "Refresh Status"),
    ("刷新列表", "Refresh List"),
    ("局部刷新", "Partial Refresh"),
    ("自動刷新", "Auto Refresh"),
    ("序列管理", "Sequence Management"),
    ("章節切換", "Chapter Switch"),
    ("單獨切換", "Individual Switch"),
    ("自動分配序列號", "Auto Assign Sequence"),
    ("指定設備序列號", "Assign Sequence to Device"),
    ("目標設備", "Target Device"),
    ("目標章節 ID", "Target Chapter ID"),
    ("選擇目標設備", "Select Target Device"),
    ("選擇在線設備", "Select Online Device"),
    ("新序列號", "New Sequence"),
    ("分配序列號", "Assign Sequence"),
    ("切換章節", "Switch Chapter"),
    ("執行動作", "Execute Action"),
    ("批量執行動作", "Batch Execute Action"),
    ("執行結果", "Execution Results"),
    ("連接結果", "Connection Results"),
    ("查看詳細結果", "View Detailed Results"),
    ("設備連接狀態", "Device Connection Status"),
    ("重新連接設備", "Reconnect Devices"),
    ("開始重新連接", "Start Reconnect"),
    ("重新連線", "Reconnect"),
    ("中斷連線", "Disconnect"),
    ("加入房間", "Add to Room"),
    ("移出房間", "Remove from Room"),
    ("關閉所有監控", "Close All Monitors"),
    ("監控牆", "Monitor Wall"),
    ("監看設備", "Monitor Device"),
    ("所有設備", "All Devices"),
    ("在線", "Online"),
    ("離線", "Offline"),
    ("未連接", "Not Connected"),
    ("無法連線", "Unreachable"),
    ("清醒", "Awake"),
    ("休眠中", "Sleeping"),
    ("電量", "Battery"),
    ("溫度", "Temperature"),
    ("運行時間", "Uptime"),
    ("開機", "Uptime"),
    ("說明", "Description"),
    ("備註", "Notes"),
    ("備註名稱", "Alias"),
    ("設備唯一標識符", "Unique device identifier"),
    ("當前章節", "Current Chapter"),
    ("當前時間", "Current Time"),
    ("從心跳訊息解析的時間", "Time parsed from heartbeat message"),
    ("章節 5 時由 Client 回傳的 z 座標", "z coordinate reported by the client in chapter 5"),
    ("只會回寫 z 座標", "Only the z coordinate will be written back"),
    ("目前玩家數量", "Current Player Count"),
    ("暫無玩家連接", "No connected players"),
    ("沒有可用的設備", "No available devices"),
    ("沒有在線設備", "No online devices"),
    ("此房間內沒有設備", "There are no devices in this room"),
    ("房間已滿", "Room is full"),
    ("剩餘名額", "Remaining Slots"),
    ("容量限制", "Capacity Limit"),
    ("無限制", "Unlimited"),
    ("最大設備數量", "Maximum Device Count"),
    ("房間名稱", "Room Name"),
    ("房間說明", "Room Description"),
    ("基本資訊", "Basic Information"),
    ("設備代號", "Device Alias"),
    ("設備名稱", "Device Name"),
    ("IP 地址", "IP Address"),
    ("端口", "Port"),
    ("方便識別的代號", "Easy-to-recognize alias"),
    ("方便識別的簡短代號", "Short alias for easy identification"),
    ("設備的完整名稱", "Full device name"),
    ("例如", "Example"),
    ("選填", "Optional"),
    ("創建房間", "Create Room"),
    ("創建動作", "Create Action"),
    ("動作名稱", "Action Name"),
    ("動作說明", "Action Description"),
    ("動作類型", "Action Type"),
    ("參數名稱", "Parameter Name"),
    ("參數類型", "Parameter Type"),
    ("參數值設定", "Parameter Value Settings"),
    ("類型", "Type"),
    ("類型篩選", "Type Filter"),
    ("路徑", "Path"),
    ("下載設定檔", "Download Config"),
    ("匯入設定", "Import Settings"),
    ("匯出設定", "Export Settings"),
    ("匯入/匯出設定", "Import / Export Settings"),
    ("重新載入設定", "Reload Settings"),
    ("重置為預設設定", "Reset to Default"),
    ("儲存設定", "Save Settings"),
    ("保存設定", "Save Settings"),
    ("套用匯入的設定", "Apply Imported Settings"),
    ("查看當前設定", "View Current Settings"),
    ("查看匯入的設定", "View Imported Settings"),
    ("選擇設定檔", "Select Config File"),
    ("選擇先前匯出的 JSON 設定檔", "Select a previously exported JSON config file"),
    ("設定檔讀取成功", "Configuration loaded successfully"),
    ("儲存使用者設定成功", "User settings saved successfully"),
    ("儲存使用者設定失敗", "Failed to save user settings"),
    ("儲存匯入的設定失敗", "Failed to save imported settings"),
    ("匯入設定成功", "Settings imported successfully"),
    ("匯入設定失敗", "Failed to import settings"),
    ("重置設定失敗", "Failed to reset settings"),
    ("設定已保存", "Settings saved"),
    ("設定已儲存", "Settings saved"),
    ("設定已套用並儲存", "Settings applied and saved"),
    ("沒有變更", "No changes"),
    ("設備資訊已保存", "Device information saved"),
    ("保存設備失敗", "Failed to save device"),
    ("保存失敗", "Save failed"),
    ("創建房間成功", "Room created successfully"),
    ("創建房間失敗", "Failed to create room"),
    ("更新房間設備", "Room devices updated"),
    ("房間已刪除", "Room deleted"),
    ("房間已更新", "Room updated"),
    ("創建動作成功", "Action created successfully"),
    ("創建動作失敗", "Failed to create action"),
    ("更新動作成功", "Action updated successfully"),
    ("更新動作失敗", "Failed to update action"),
    ("動作已創建", "Action created"),
    ("動作已更新", "Action updated"),
    ("動作已刪除", "Action deleted"),
    ("已複製", "Copied"),
    ("連接失敗", "Connection failed"),
    ("重新連接失敗", "Reconnect failed"),
    ("中斷連線失敗", "Disconnect failed"),
    ("執行失敗", "Execution failed"),
    ("發送失敗", "Failed to send"),
    ("分配失敗", "Assignment failed"),
    ("切換失敗", "Switch failed"),
    ("成功次數", "Successful Runs"),
    ("總執行次數", "Total Executions"),
    ("成功率", "Success Rate"),
    ("執行次數", "Execution Count"),
    ("最後執行", "Last Executed"),
    ("命令說明", "Command Description"),
    ("所有設備連接正常，無需重新連接", "All device connections are healthy. No reconnect needed."),
    ("當前房間有", "Current room has"),
    ("超過新設定的上限", "which exceeds the new limit"),
    ("此房間未配置 Socket Server", "This room has not been configured with a Socket Server"),
    ("此房間尚未配置或啟動 Socket Server", "This room has not been configured with or started a Socket Server"),
    ("Socket Server 已啟動", "Socket Server started"),
    ("Socket Server 已重啟", "Socket Server restarted"),
    ("Socket Server 未運行", "Socket Server is not running"),
    ("Socket Server 啟動失敗", "Socket Server failed to start"),
    ("Socket Server 重啟失敗", "Socket Server failed to restart"),
    ("Socket Server 管理器未初始化", "Socket Server manager is not initialized"),
    ("要啟用 Socket Server 請輸入 IP", "Enter an IP address to enable the Socket Server"),
    ("留空 IP 地址則不會啟動 Socket Server", "Leave the IP empty to avoid starting the Socket Server"),
    ("將在啟動時監聽", "will listen on startup"),
    ("運行中", "Running"),
    ("未運行", "Stopped"),
    ("讀取設定檔失敗", "Failed to read config file"),
    ("重置設定", "Reset Settings"),
    ("網路監控設定", "Network Monitoring Settings"),
    ("scrcpy 監看設定", "scrcpy Monitor Settings"),
    ("截圖預覽設定", "Screenshot Preview Settings"),
    ("圖片設定", "Image Settings"),
    ("視訊設定", "Video Settings"),
    ("基本設定", "Basic Settings"),
    ("其他選項", "Other Options"),
    ("視窗設定", "Window Settings"),
    ("渲染驅動", "Render Driver"),
    ("視訊位元率", "Video Bitrate"),
    ("最大畫面寬度", "Max Video Width"),
    ("最大幀率", "Max FPS"),
    ("視窗寬度", "Window Width"),
    ("視窗高度", "Window Height"),
    ("關閉設備螢幕", "Turn Screen Off"),
    ("顯示觸控點", "Show Touches"),
    ("全螢幕模式", "Fullscreen"),
    ("視窗置頂", "Always on Top"),
    ("保持設備清醒", "Stay Awake"),
    ("啟用音訊轉發", "Enable Audio Forwarding"),
    ("啟用截圖預覽", "Enable Screenshot Preview"),
    ("啟用快取", "Enable Cache"),
    ("啟用網路監控", "Enable Network Monitoring"),
    ("啟用自動連接", "Enable Auto Connect"),
    ("顯示即時截圖預覽", "show live screenshot previews"),
    ("下載當前設定為 JSON 檔案", "Download the current settings as a JSON file"),
    ("從 JSON 檔案恢復設定", "Restore settings from a JSON file"),
    ("最大重試次數", "Maximum Retry Count"),
    ("失敗後冷卻時間", "Cooldown After Failure"),
    ("Ping 目標", "Ping Targets"),
    ("Ping 所有設備", "Ping All Devices"),
    ("僅 Ping 未連接設備", "Ping Only Disconnected Devices"),
    ("僅 Ping WiFi 設備", "Ping Only Wi-Fi Devices"),
    ("使用說明", "Usage Notes"),
    ("送茶時間設定", "Tea Time Config"),
    ("發送當前參數至 Socket Server", "Send Current Parameters to Socket Server"),
    ("即時同步", "Live Sync"),
    ("設為全域參數", "Use as Global Parameter"),
    ("所有設備使用相同值", "Same value for all devices"),
    ("擇要發送的命令類型", "Select the command type to send"),
    ("選擇要發送的命令類型", "Select the command type to send"),
    ("發送成功", "Sent successfully"),
    ("命令發送成功", "Command sent successfully"),
    ("命令發送失敗", "Command failed to send"),
    ("所有設備", "All Devices"),
    ("目前無在線設備，請確認設備已連接", "There are currently no online devices. Please verify device connectivity."),
    ("等待開始", "Waiting to Start"),
    ("當前環節", "Current Segment"),
    ("選擇要執行的設備", "Select a device to execute on"),
    ("選擇要執行的動作", "Select an action to execute"),
    ("選擇 APK 文件", "Select APK File"),
    ("選擇要安裝的 APK 文件", "Select the APK file to install"),
    ("替換已存在的應用", "Replace Existing App"),
    ("自動授予權限", "Grant Permissions Automatically"),
    ("等待啟動完成", "Wait for launch completion"),
    ("先發送返回鍵", "Send BACK first"),
    ("強制休眠", "Force Sleep"),
    ("驗證喚醒成功", "Verify Wake Success"),
    ("驗證休眠成功", "Verify Sleep Success"),
    ("驗證關閉成功", "Verify Stop Success"),
    ("關閉方式", "Stop Method"),
    ("重啟應用", "Restart App"),
    ("發送按鍵", "Send Key"),
    ("常用按鍵", "Common Keys"),
    ("按鍵碼", "Keycode"),
    ("重複次數", "Repeat Count"),
    ("安裝 APK", "Install APK"),
    ("執行程式", "Launch App"),
    ("回到應用前景", "Resume App to Foreground"),
    ("關閉程式", "Stop App"),
    ("選擇 APK 文件", "Select APK File"),
    ("請將 APK 文件放到以下目錄", "Please place APK files in the following directory"),
    ("語言 / Language", "Language / 語言"),
    ("繁中", "Traditional Chinese"),
    ("主函式", "Main Function"),
    ("主函數", "Main Function"),
]

PHRASE_TRANSLATIONS += [
    ("⚡ 極速掃描 (Async)", "⚡ Fast Scan (Async)"),
    ("請輸入 IP 地址", "Please enter an IP address"),
    ("❌ scrcpy 啟動失敗: {device.display_name} - {message}", "❌ Failed to launch scrcpy: {device.display_name} - {message}"),
    ("✅ scrcpy 視窗已開啟: {device.display_name}", "✅ scrcpy window opened: {device.display_name}"),
    ("✅ 確定刪除", "✅ Confirm Delete"),
    ("✏️ 編輯房間", "✏️ Edit Room"),
    ("🗑️ 刪除房間", "🗑️ Delete Room"),
    ("⚠️ 此房間內有 {room.device_count} 台設備", "⚠️ This room currently has {room.device_count} devices"),
    ("🗑️ 刪除房間: {room.display_name}", "🗑️ Delete room: {room.display_name}"),
    ("✏️ 編輯參數: {current_param.name}", "✏️ Edit Parameter: {current_param.name}"),
    ("Quest 設備的 IP 地址", "Quest device IP address"),
    ("ADB 端口，默認為 5555", "ADB port, default is 5555"),
    ("例如：訓練室 A", "Example: Training Room A"),
    ("訓練室 A - Quest 3", "Training Room A - Quest 3"),
    ("例如：主要用於新手訓練", "Example: Mainly used for beginner training"),
    ("任何額外的說明（選填）", "Any additional notes (optional)"),
    ("沒有設備可掃描", "No devices available to scan"),
    ("正在連接設備...", "Connecting device..."),
    ("執行中...", "Running..."),
    ("掃描完成！", "Scan complete!"),
    ("✅ 設備已移除", "✅ Device removed"),
    ("❌ 移除失敗", "❌ Removal failed"),
    ("✅ 設備 **{alias}** 已更新", "✅ Device **{alias}** updated"),
    ("❌ 保存失敗，請查看日誌", "❌ Save failed, please check the logs"),
    ("⚠️ 設備未連接，請先連接後再執行動作", "⚠️ Device not connected. Please connect it before executing the action."),
    ("⚠️ 設備離線（ADB state: offline），請等待設備恢復後再執行動作", "⚠️ Device offline (ADB state: offline). Please wait for recovery before executing the action."),
    ("⚠️ 設備狀態異常（{device.status}），無法執行動作", "⚠️ Device status is abnormal ({device.status}), action cannot be executed."),
    ("📝 還沒有任何動作，請先前往動作管理頁面創建動作", "📝 No actions yet. Please create one in Action Management first."),
    ("📱 尚無設備，請點擊「新增設備」來連接 Quest 設備", "📱 No devices yet. Click \"Add Device\" to connect a Quest headset."),
    ("❌ 取消移除: {device.display_name}", "❌ Removal canceled: {device.display_name}"),
    ("❌ 取消編輯: {device.display_name}", "❌ Edit canceled: {device.display_name}"),
    ("💾 保存設備編輯: {device.display_name}", "💾 Saving device edits: {device.display_name}"),
    ("舊別名: {device.alias} → 新別名: {alias}", "Old alias: {device.alias} -> New alias: {alias}"),
    ("⬆️ 嘗試向上移動: {device.display_name} (當前位置: {current_index}, sort_order: {device.sort_order})", "⬆️ Attempting to move up: {device.display_name} (current index: {current_index}, sort_order: {device.sort_order})"),
    ("⬇️ 嘗試向下移動: {device.display_name} (當前位置: {current_index}, sort_order: {device.sort_order})", "⬇️ Attempting to move down: {device.display_name} (current index: {current_index}, sort_order: {device.sort_order})"),
    ("交換對象: {prev_device.display_name} (sort_order: {prev_device.sort_order})", "Swap target: {prev_device.display_name} (sort_order: {prev_device.sort_order})"),
    ("交換對象: {next_device.display_name} (sort_order: {next_device.sort_order})", "Swap target: {next_device.display_name} (sort_order: {next_device.sort_order})"),
    ("已在最頂部，無法向上移動", "Already at the top, cannot move up"),
    ("已在最底部，無法向下移動", "Already at the bottom, cannot move down"),
    ("✅ 移動成功: {device.display_name} (新 sort_order: {device.sort_order})", "✅ Move succeeded: {device.display_name} (new sort_order: {device.sort_order})"),
    ("✅ 執行動作成功: {selected_action.display_name} -> {device.display_name}", "✅ Action executed successfully: {selected_action.display_name} -> {device.display_name}"),
    ("❌ 執行動作失敗: {selected_action.display_name} -> {device.display_name}", "❌ Action execution failed: {selected_action.display_name} -> {device.display_name}"),
    ("🟢 剛剛在線", "🟢 Just now"),
    ("✅ 自動標記為在線: {device.display_name} (ADB state: device)", "✅ Auto-marked online: {device.display_name} (ADB state: device)"),
    ("🟠 自動標記為離線: {device.display_name} (ADB state: offline)", "🟠 Auto-marked offline: {device.display_name} (ADB state: offline)"),
    ("⚫ 自動標記為未連接: {device.display_name} (不在 ADB 列表中)", "⚫ Auto-marked not connected: {device.display_name} (not in the ADB list)"),
    ("✅ 設備已連接：{device.display_name}", "✅ Device connected: {device.display_name}"),
    ("📺 啟動監看: {device.display_name}", "📺 Launch monitor: {device.display_name}"),
    ("🔌 嘗試中斷連線: {device.display_name} ({device.connection_string})", "🔌 Attempting disconnect: {device.display_name} ({device.connection_string})"),
    ("🔌 中斷結果: success={success}, output={output}", "🔌 Disconnect result: success={success}, output={output}"),
    ("✅ 已中斷連線：{device.connection_string}", "✅ Disconnected: {device.connection_string}"),
    ("✅ 設備 {device.display_name} 已標記為未連接", "✅ Device {device.display_name} marked as not connected"),
    ("❌ 中斷連線失敗：{output}", "❌ Disconnect failed: {output}"),
    ("❌ 中斷連線失敗: {device.display_name} - {output}", "❌ Disconnect failed: {device.display_name} - {output}"),
    ("🔄 嘗試重新連線: {device.display_name} ({device.ip}:{device.port})", "🔄 Attempting reconnect: {device.display_name} ({device.ip}:{device.port})"),
    ("🔄 連線結果: success={success}, output={output}", "🔄 Connection result: success={success}, output={output}"),
    ("⚠️ 設備沒有 IP 地址，無法重新連線", "⚠️ Device has no IP address and cannot reconnect"),
    ("⚠️ 設備 {device.display_name} 沒有 IP 地址", "⚠️ Device {device.display_name} has no IP address"),
    ("需要手動開啟 WiFi ADB", "Wi-Fi ADB must be enabled manually"),
    ("（無法連線 - WiFi ADB 未開啟）", "(Unreachable - Wi-Fi ADB not enabled)"),
    ("（設備狀態：{device.status}）", "(Device status: {device.status})"),
    ("（設備未連接）", "(Device not connected)"),
    ("（設備離線）", "(Device offline)"),
    ("✅ 已重新連線：{device.ip}:{device.port}", "✅ Reconnected: {device.ip}:{device.port}"),
    ("✅ 設備 {device.display_name} 重新連線成功", "✅ Device {device.display_name} reconnected successfully"),
    ("❌ 連線失敗：{output}", "❌ Connection failed: {output}"),
    ("❌ 重新連線失敗: {device.display_name} - {output}", "❌ Reconnect failed: {device.display_name} - {output}"),
    ("⚠️ 更新設備狀態失敗: {device.display_name} - {e}", "⚠️ Failed to update device status: {device.display_name} - {e}"),
    ("🚀 正在並行掃描所有設備...", "🚀 Scanning all devices in parallel..."),
    ("確定要移除設備 **{device.display_name}** 嗎？", "Are you sure you want to remove device **{device.display_name}**?"),
    ("📋 動作詳情", "📋 Action Details"),
    ("📋 參數詳情", "📋 Parameter Details"),
    ("**操作選單**", "**Action Menu**"),
    ("**參數**:", "**Parameters**:"),
    ("**連接**：", "**Connection**: "),
    ("**連接**:", "**Connection**:"),
    ("連接：", "Connection: "),
    ("▶️ 執行", "▶️ Execute"),
    ("⚙️ 編輯設定", "⚙️ Edit Settings"),
    ("✅ 確定移除", "✅ Confirm Removal"),
    ("❌ 取消", "❌ Cancel"),
    ("❌ 關閉", "❌ Close"),
    ("➕ 前往動作管理", "➕ Go to Action Management"),
    ("向上移動", "Move Up"),
    ("向下移動", "Move Down"),
    ("🔌 連接", "🔌 Connect"),
    ("💾 保存", "💾 Save"),
    ("取消", "Cancel"),
    ("關閉", "Close"),
    ("動作", "Action"),
    ("確定要刪除房間 **{room.display_name}** 嗎？", "Are you sure you want to delete room **{room.display_name}**?"),
    ("為房間取一個容易識別的名稱", "Give the room an easy-to-recognize name"),
    ("房間說明（選填）", "Room description (optional)"),
    ("描述這個房間的用途...", "Describe what this room is used for..."),
    ("0 表示無限制", "0 means unlimited"),
    ("🔌 Socket Server 設定（選填）", "🔌 Socket Server Settings (optional)"),
    ("⚙️ 房間參數設定", "⚙️ Room Parameter Settings"),
    ("房間 ID:", "Room ID:"),
    ("**選擇要加入房間的設備**", "**Select devices to add to the room**"),
    ("💡 已經在其他房間的設備，勾選後會自動轉移到此房間", "💡 Devices already assigned to another room will be moved here automatically when selected"),
    ("⚡ 批量執行動作 - {room.display_name}", "⚡ Batch Execute Action - {room.display_name}"),
    ("📱 房間內設備：共 {len(room_devices)} 台（🟢 在線 {len(online_devices)} 台，🟠 離線 {len(offline_devices)} 台，⚫ 未連接 {len(not_connected_devices)} 台）", "📱 Devices in Room: {len(room_devices)} total (🟢 {len(online_devices)} online, 🟠 {len(offline_devices)} offline, ⚫ {len(not_connected_devices)} not connected)"),
    ("💡 動作將在所有在線設備上執行", "💡 The action will be executed on all online devices"),
    ("💡 檢查房間內設備的連接狀態，並嘗試重新連接不在線的設備", "💡 Check device connection status in this room and try to reconnect the ones that are not online"),
    ("會存成這個房間的預設 z 值", "This will be saved as the room's default z value"),
    ("💡 設為 0 表示此房間可容納無限數量的設備", "💡 Set to 0 to allow unlimited devices in this room"),
    ("💡 此房間最多可容納 {max_devices} 台設備", "💡 This room can contain up to {max_devices} devices"),
    ("0.0.0.0 或 127.0.0.1", "0.0.0.0 or 127.0.0.1"),
    ("若要啟用 Socket Server 請輸入 IP", "Enter an IP address to enable the Socket Server"),
    ("💡 留空 IP 地址則不會啟動 Socket Server", "💡 Leave the IP address blank to keep the Socket Server disabled"),
    ("設定傳遞給 Android 應用的 Intent 參數", "Intent parameters passed to the Android app"),
    ("尚未設定任何參數", "No parameters configured yet"),
    ("💡 刪除房間後，設備將不再屬於任何房間（但不會被刪除）", "💡 After deleting the room, the devices will belong to no room, but the devices themselves will not be deleted"),
    ("📊 房間容量：{room.capacity_text}（剩餘 {room.max_devices - room.device_count} 個名額）", "📊 Room capacity: {room.capacity_text} ({room.max_devices - room.device_count} slots remaining)"),
    ("📊 房間容量：{room.capacity_text}（無限制）", "📊 Room capacity: {room.capacity_text} (Unlimited)"),
    ("⚠️ 房間內沒有設備", "⚠️ There are no devices in this room"),
    ("⚠️ 沒有在線設備，無法執行動作", "⚠️ There are no online devices, so the action cannot be executed"),
    ("📋 發現 {len(devices_to_reconnect)} 台設備需要重新連接", "📋 Found {len(devices_to_reconnect)} devices that need reconnection"),
    ("⚠️ 設備離線，請先連線後再執行動作", "⚠️ Device offline. Please reconnect before executing the action."),
    ("📭 房間內沒有設備，點擊「管理設備」添加設備", "📭 This room has no devices. Click \"Manage Devices\" to add one."),
    ("💡 提示：點擊「新增房間」創建房間，然後在房間中加入設備", "💡 Tip: Click \"Add Room\" to create a room, then add devices to it"),
    ("🏠 還沒有任何房間，點擊「新增房間」開始創建", "🏠 No rooms yet. Click \"Add Room\" to get started"),
    ("請為房間內的設備設定參數值", "Please configure parameter values for the devices in this room"),
    ("將當前參數設定直接發送給 Node.js Server（無需保存）", "Send the current parameters directly to the Node.js server without saving"),
    ("🚀 發送", "🚀 Send"),
    ("確認", "Confirm"),
    ("⚠️ 當前房間有 {room_buffer.device_count} 台設備，超過新設定的上限！", "⚠️ The current room has {room_buffer.device_count} devices, which exceeds the new limit!"),
    ("（無需重新連接的設備）", "(Devices that do not need reconnection)"),
    ("🔔 **當前環節**: {current_evt['content']} (表定 {current_evt['rawTime']})", "🔔 **Current Segment**: {current_evt['content']} (scheduled {current_evt['rawTime']})"),
    ("連接 Server 查詢狀態失敗: {e}", "Failed to connect to the server for status lookup: {e}"),
    ("✅ 房間已創建：{room.display_name}", "✅ Room created: {room.display_name}"),
    ("✅ 創建房間成功: {room.display_name}", "✅ Room created successfully: {room.display_name}"),
    ("❌ 創建房間失敗（可能名稱已存在）", "❌ Failed to create room (the name may already exist)"),
    ("{dev.display_name} 旋轉(rotation) (Euler 列表)", "{dev.display_name} rotation (Euler list)"),
    ("❌ 刪除失敗", "❌ Delete failed"),
    ("❌ 選擇的設備數量（{len(selected_devices)}）超過房間上限（{room.max_devices}）", "❌ Selected device count ({len(selected_devices)}) exceeds the room limit ({room.max_devices})"),
    ("🚀 並發執行中...", "🚀 Running in parallel..."),
    ("✅ 成功：{success_count} 台", "✅ Success: {success_count} devices"),
    ("❌ 失敗：{fail_count} 台", "❌ Failed: {fail_count} devices"),
    ("⚡ 批量執行動作: {selected_action.display_name} -> {room.display_name} (成功: {success_count}, 失敗: {fail_count})", "⚡ Batch action execution: {selected_action.display_name} -> {room.display_name} (success: {success_count}, failed: {fail_count})"),
    ("⏳ **等待開始**: 下一個環節 {events[0]['content']} ({events[0]['rawTime']})", "⏳ **Waiting to Start**: next segment {events[0]['content']} ({events[0]['rawTime']})"),
    ("無法獲取即時狀態: {response.get('message', 'Unknown error')}", "Unable to fetch real-time status: {response.get('message', 'Unknown error')}"),
    ("🔄 重啟", "🔄 Restart"),
    ("🚀 啟動 Server", "🚀 Start Server"),
    ("Socket Server 日誌", "Socket Server Logs"),
    ("📝 日誌文件不存在或為空", "📝 The log file does not exist or is empty"),
    ("選擇目標設備，顯示為：備註 (ID)", "Select target device, displayed as: Notes (ID)"),
    ("🔄 刷新", "🔄 Refresh"),
    ("💡 命令說明", "💡 Command Description"),
    ("共用位置: {bulk_message}", "Shared position: {bulk_message}"),
    ("❌ 更新失敗", "❌ Update failed"),
    ("🛑 已停止 Socket Server: {room.name}", "🛑 Socket Server stopped: {room.name}"),
    ("正在重新連接設備...", "Reconnecting devices..."),
    ("🔌 開始並發重新連接: {room.display_name} ({len(devices_list)} 台設備)", "🔌 Starting parallel reconnects: {room.display_name} ({len(devices_list)} devices)"),
    ("🔌 重新連接完成: {room.display_name} (成功: {success_count}, 失敗: {fail_count})", "🔌 Reconnect completed: {room.display_name} (success: {success_count}, failed: {fail_count})"),
    ("{device_label}: z 值格式無效", "{device_label}: invalid z value format"),
    ("序號:", "Sequence:"),
    ("（房間內無設備）", "(No devices in this room)"),
    ("🔌 重新連接", "🔌 Reconnect"),
    ("🔄 重啟 Socket Server ({status_text})", "🔄 Restart Socket Server ({status_text})"),
    ("已設定 {len(param.device_values)} 台設備", "{len(param.device_values)} devices configured"),
    ("❌ 房間名稱已存在", "❌ Room name already exists"),
    ("將依序開啟 {device_count} 台設備的單眼監看視窗...", "Opening single-eye monitor windows for {device_count} devices in sequence..."),
    ("關閉失敗: {e}", "Close failed: {e}"),
    ("指定目標 App 的 Package Name", "Specify the target app package name"),
    ("選擇目標設備 (Target Device)", "Select target device"),
    ("選擇要切換章節的特定設備", "Select the specific device to switch chapters"),
    ("根據設備別名 (OBx) 自動計算並分配序列號。規則：OBx -> (x-1)%8", "Automatically calculate and assign sequence numbers by device alias (OBx). Rule: OBx -> (x-1)%8"),
    ("🤖 執行自動分配", "🤖 Run Auto Assignment"),
    ("⚠️ 目前無在線設備，請確認設備已連接", "⚠️ No online devices right now. Please verify the devices are connected."),
    ("❌ Socket Server 未運行，無法發送命令", "❌ The Socket Server is not running, so the command cannot be sent"),
    ("正在重啟 Socket Server...", "Restarting Socket Server..."),
    ("✅ 重新連接成功: {device.display_name}，等待狀態掃描更新", "✅ Reconnect succeeded: {device.display_name}, waiting for status scan update"),
    ("❌ 重新連接失敗: {device.display_name} - {output}", "❌ Reconnect failed: {device.display_name} - {output}"),
    ("✅ Server 啟動成功", "✅ Server started successfully"),
    ("❌ Server 啟動失敗: {msg}", "❌ Failed to start server: {msg}"),
    ("✅ 已依序開啟 {success_count} 台設備監看視窗", "✅ Opened monitor windows for {success_count} devices"),
    ("⚠️ 監看視窗已開啟 {success_count} 台，失敗 {failure_count} 台", "⚠️ Opened monitor windows for {success_count} devices, failed on {failure_count} devices"),
    ("錯: {e}", "Error: {e}"),
    ("✅ 重啟 Socket Server 成功: {room.name} ({room.socket_ip}:{room.socket_port})", "✅ Socket Server restarted successfully: {room.name} ({room.socket_ip}:{room.socket_port})"),
    ("❌ 重啟 Socket Server 失敗: {room.name} - {msg}", "❌ Failed to restart Socket Server: {room.name} - {msg}"),
    ("✅ 參數 {live_param.name} 發送成功!", "✅ Parameter {live_param.name} sent successfully!"),
    ("❌ 發送失敗: {response.get('message', '未知錯誤')}", "❌ Failed to send: {response.get('message', 'Unknown error')}"),
    ("✅ 備註已更新", "✅ Notes updated"),
    ("無法獲取玩家狀態", "Unable to fetch player status"),
    ("⚠️ 請選擇目標設備", "⚠️ Please select a target device"),
    ("✅ 命令發送成功", "✅ Command sent successfully"),
    ("❌ 命令發送失敗: {response.get('message', '未知錯誤')}", "❌ Command failed to send: {response.get('message', 'Unknown error')}"),
    ("✅ 章節切換指令已發送 (Ch. {target_chapter})", "✅ Chapter switch command sent (Ch. {target_chapter})"),
    ("✅ 已對 {target_move_device} 切換至 Ch. {target_chapter}", "✅ Switched {target_move_device} to Ch. {target_chapter}"),
    ("❌ 切換失敗: {response.get('message', '未知錯誤')}", "❌ Switch failed: {response.get('message', 'Unknown error')}"),
    ("成功分配 {auto_success_count} 台設備", "Successfully assigned {auto_success_count} devices"),
    ("失敗 {auto_fail_count} 台設備", "Failed to assign {auto_fail_count} devices"),
    ("✅ 已分配序列號 {new_sequence} 給 {target_device_id}", "✅ Assigned sequence {new_sequence} to {target_device_id}"),
    ("❌ 分配失敗: {response.get('message', '未知錯誤')}", "❌ Assignment failed: {response.get('message', 'Unknown error')}"),
    ("⏱️ 時間提醒已重置並開始！", "⏱️ Time reminder reset and started!"),
    ("例如：啟動訓練程式", "Example: Launch training app"),
    ("為動作取一個容易識別的名稱", "Give the action an easy-to-recognize name"),
    ("動作說明（選填）", "Action description (optional)"),
    ("描述這個動作的用途...", "Describe what this action is used for..."),
    ("⚙️ 動作參數", "⚙️ Action Parameters"),
    ("動作 ID:", "Action ID:"),
    ("確定要刪除動作 **{action.display_name}** 嗎？", "Are you sure you want to delete action **{action.display_name}**?"),
    ("創建 APKs 目錄: {apks_dir}", "Created APKs directory: {apks_dir}"),
    ("☀️ 喚醒設備不需要額外參數", "☀️ Waking the device does not require extra parameters"),
    ("📊 此動作已執行 {action.execution_count} 次", "📊 This action has been executed {action.execution_count} times"),
    ("⚠️ 沒有在線設備", "⚠️ No online devices"),
    ("🔍 搜索動作", "🔍 Search actions"),
    ("輸入關鍵字...", "Enter keywords..."),
    ("📊 動作總數", "📊 Total Actions"),
    ("📈 整體成功率", "📈 Overall Success Rate"),
    ("😴 休眠設備", "😴 Put Device to Sleep"),
    ("🔍 沒有找到包含「{search_keyword}」的動作", "🔍 No actions found containing \"{search_keyword}\""),
    ("🔌 保持喚醒（接電源時不進入深度睡眠）", "🔌 Stay awake (do not enter deep sleep while charging)"),
    ("💡 設置設備在接上電源時保持喚醒狀態，避免網路功能被關閉", "💡 Keep the device awake while charging so network features remain available"),
    ("喚醒模式 *", "Wake Mode *"),
    ("選擇設備在接電源時保持喚醒的模式", "Select the wake mode to use while the device is charging"),
    ("- **模式 0**: 禁用此功能，設備會按正常的閒置計時器進入深度睡眠", "- **Mode 0**: Disable this feature and let the device enter deep sleep based on the normal idle timer"),
    ("- **模式 1**: 僅在使用牆上充電器（AC）時保持喚醒", "- **Mode 1**: Stay awake only when using a wall charger (AC)"),
    ("- **模式 2**: 僅在連接電腦 USB 充電時保持喚醒", "- **Mode 2**: Stay awake only when charging through a computer USB connection"),
    ("- **模式 3**: AC 和 USB 充電時都保持喚醒，確保網路功能不被關閉（推薦）", "- **Mode 3**: Stay awake during both AC and USB charging so network features stay available (recommended)"),
    ("✅ 創建動作成功: {action.display_name}", "✅ Action created successfully: {action.display_name}"),
    ("❌ 創建動作失敗", "❌ Failed to create action"),
    ("✏️ 編輯", "✏️ Edit"),
    ("📋 複製", "📋 Duplicate"),
    ("🗑️ 刪除", "🗑️ Delete"),
    ("Package 名稱 *", "Package Name *"),
    ("應用程式的 package 名稱", "The app package name"),
    ("Activity 名稱（選填）", "Activity name (optional)"),
    ("Activity 名稱（以 . 開頭的相對名稱或完整類名）", "Activity name (relative name starting with . or a full class name)"),
    ("啟動前先關閉已運行的實例", "Stop any running instance before launch"),
    ("✅ 執行動作成功: {action.display_name} -> {selected_device.display_name}", "✅ Action executed successfully: {action.display_name} -> {selected_device.display_name}"),
    ("❌ 執行動作失敗: {action.display_name} -> {selected_device.display_name}", "❌ Action execution failed: {action.display_name} -> {selected_device.display_name}"),
    ("要帶回前景的應用程式 package 名稱", "Package name of the app to bring back to the foreground"),
    ("要關閉的應用程式 package 名稱", "Package name of the app to stop"),
    ("force-stop 完全停止應用，kill 僅殺進程", "force-stop fully stops the app, while kill only terminates the process"),
    ("要重啟的應用程式 package 名稱", "Package name of the app to restart"),
    ("重啟延遲（秒）", "Restart delay (seconds)"),
    ("關閉後等待多少秒再啟動", "How many seconds to wait after stopping before launching again"),
    ("使用常用按鍵", "Use common keys"),
    ("選擇按鍵", "Select a key"),
    ("KEYCODE_HOME 或 3", "KEYCODE_HOME or 3"),
    ("輸入按鍵碼名稱或數字", "Enter a keycode name or number"),
    ("如果應用已安裝，是否替換安裝", "Replace the app if it is already installed"),
    ("安裝時自動授予所有權限", "Automatically grant all permissions during installation"),
    ("⚠️ apks 目錄中沒有找到 APK 文件", "⚠️ No APK files were found in the apks directory"),
    ("選擇要安裝的 APK 文件（顯示創建時間以便區分）", "Select the APK file to install (creation time shown for reference)"),
    ("使用 SLEEP 而非 POWER 鍵", "Use SLEEP instead of the POWER key"),
    ("📝 還沒有任何動作，點擊「新增動作」開始創建", "📝 No actions yet. Click \"Add Action\" to get started"),
    ("設備", "Device"),
    ("🔄 重新載入", "🔄 Reload"),
    ("不勾選則由系統自動決定", "Leave unchecked to let the system choose automatically"),
    ("不勾選則自動根據畫面大小調整", "Leave unchecked to auto-adjust based on the display size"),
    ("以全螢幕模式啟動", "Start in fullscreen"),
    ("僅對 WiFi 連接的設備進行 Ping（USB 設備不需要 Ping）", "Ping only Wi-Fi connected devices (USB devices do not need ping)"),
    ("僅對未連接的設備進行 Ping", "Ping only disconnected devices"),
    ("啟用後系統會定期 Ping 設備以監控網路狀況", "When enabled, the system will ping devices periodically to monitor network conditions"),
    ("在畫面上顯示觸控位置", "Show touch positions on screen"),
    ("在設備卡片上顯示即時截圖預覽", "Show live screenshot previews on device cards"),
    ("對所有設備進行 Ping（包括已連接的設備）", "Ping all devices, including connected devices"),
    ("當設備 Ping 通但未連接時，自動嘗試連接", "Automatically try to connect when a device responds to ping but is not connected"),
    ("啟用快取可減少 ADB 命令執行次數", "Enabling cache can reduce the number of ADB command executions"),
    ("監看時保持設備螢幕常亮", "Keep the device screen on while monitoring"),
    ("自訂視窗位置", "Custom window position"),
    ("自訂視窗寬度", "Custom window width"),
    ("自訂視窗高度", "Custom window height"),
    ("視窗永遠在最上層", "Keep the window always on top"),
    ("轉發設備音訊到電腦（⚠️ 可能會關閉 Quest 的內建聲音）", "Forward device audio to the computer (⚠️ this may disable Quest's built-in audio)"),
    ("鏡像時關閉設備螢幕（節省電力）", "Turn off the device screen while mirroring (saves power)"),
    ("❌ 儲存失敗！", "❌ Save failed!"),
    ("❌ 儲存設定失敗！", "❌ Failed to save settings!"),
    ("❌ 重置失敗！", "❌ Reset failed!"),
    ("匯入設定失敗: {e}", "Failed to import settings: {e}"),
    ("ℹ️ 使用說明", "ℹ️ Usage Notes"),
    ("💾 匯入/匯出設定", "💾 Import / Export Settings"),
    ("ℹ️ 截圖預覽將每 **{screenshot_config['update_interval']} 秒**自動更新，最大尺寸為 **{screenshot_config['max_width']}x{screenshot_config['max_height']}** 像素", "ℹ️ Screenshot previews will refresh automatically every **{screenshot_config['update_interval']} seconds**, with a maximum size of **{screenshot_config['max_width']}x{screenshot_config['max_height']} px**"),
    ("匯入設定成功", "Settings imported successfully"),
    ("備份或恢復您的系統設定", "Back up or restore your system settings"),
    ("將所有設定恢復為預設值", "Restore all settings to their defaults"),
    ("將當前設定匯出為 JSON 檔案", "Export the current settings as a JSON file"),
    ("設定網路監控和自動連接功能", "Configure network monitoring and auto-connect"),
    ("設定設備卡片上的截圖預覽功能", "Configure screenshot previews shown on device cards"),
    ("設定點擊「監看設備」時啟動 scrcpy 的參數", "Configure the scrcpy parameters used when clicking \"Monitor Device\""),
    ("X 座標", "X Coordinate"),
    ("Y 座標", "Y Coordinate"),
    ("失敗後冷卻時間（秒）", "Cooldown after failure (seconds)"),
    ("最大畫面寬度（像素）", "Maximum video width (px)"),
    ("自動連接失敗後的最大重試次數", "Maximum retry count after auto-connect failures"),
    ("視窗寬度（像素）", "Window width (px)"),
    ("視窗高度（像素）", "Window height (px)"),
    ("連接失敗後等待多少秒再重試", "How many seconds to wait before retrying after a connection failure"),
    ("限制幀率，0 表示無限制", "Limit the frame rate; 0 means unlimited"),
    ("限制視訊寬度，0 表示無限制", "Limit the video width; 0 means unlimited"),
    ("預覽圖最大寬度（像素）", "Maximum preview width (px)"),
    ("預覽圖最大高度（像素）", "Maximum preview height (px)"),
    ("預覽圖的最大寬度", "Maximum preview width"),
    ("預覽圖的最大高度", "Maximum preview height"),
    ("截圖自動更新的時間間隔（秒）", "Screenshot auto-refresh interval (seconds)"),
    ("更新頻率（秒）", "Update interval (seconds)"),
    ("較高的位元率提供更好的畫質，但需要更多頻寬", "Higher bitrates provide better image quality, but require more bandwidth"),
    ("選擇渲染驅動，一般使用自動即可", "Choose a render driver. Auto is recommended in most cases."),
    ("JPEG 品質", "JPEG Quality"),
    ("Ping 請求的超時時間", "Timeout for ping requests"),
    ("Ping 超時（秒）", "Ping timeout (seconds)"),
    ("Ping 間隔（秒）", "Ping interval (seconds)"),
    ("每隔多少秒 Ping 一次設備", "How often to ping devices (seconds)"),
    ("較高品質提供更清晰的圖片，但檔案較大", "Higher quality produces clearer images, but also larger files"),
    ("🔄 自動連接", "🔄 Auto Connect"),
    ("✅ 已重新載入設定！", "✅ Settings reloaded!"),
    ("✅ 已重置為預設設定！", "✅ Reset to default settings!"),
    ("💾 匯入/匯出", "💾 Import / Export"),
    ("⚠️ 截圖預覽已停用，設備卡片將不會顯示即時截圖", "⚠️ Screenshot preview is disabled, so live screenshots will not appear on device cards"),
    ("選擇要發送的命令類型", "Select the command type to send"),
    ("選擇在線設備", "Select online device"),
    ("設備數量", "Device Count"),
    ("語言 / Language", "Language"),
    ("保存", "Save"),
    ("重新載入", "Reload"),
    ("匯入/匯出", "Import / Export"),
]


PUNCTUATION_TRANSLATIONS = [
    ("（", "("),
    ("）", ")"),
    ("：", ": "),
    ("，", ", "),
    ("。", "."),
    ("！", "!"),
    ("？", "?"),
]


REGEX_TRANSLATIONS = [
    (re.compile(r"(?P<count>\{[^{}]+\}|\d+) 分前"), r"\g<count> min ago"),
    (re.compile(r"(?P<count>\{[^{}]+\}|\d+) 時前"), r"\g<count> hr ago"),
]

_EXACT_TRANSLATIONS_NORMALIZED = {
    source.strip(): target.strip()
    for source, target in EXACT_TRANSLATIONS.items()
}
_PHRASE_TRANSLATIONS_SORTED = sorted(
    PHRASE_TRANSLATIONS,
    key=lambda item: len(item[0]),
    reverse=True,
)
_OPTION_WIDGETS = {"selectbox", "radio", "multiselect", "select_slider"}


_STREAMLIT_PATCHED = False
_ORIGINAL_STREAMLIT_CALLABLES: dict[str, Callable[..., Any]] = {}
_ORIGINAL_COLUMN_CONFIG_CALLABLES: dict[str, Callable[..., Any]] = {}


def get_current_language() -> str:
    """Return the current UI language."""
    language = st.session_state.get(LANGUAGE_SESSION_KEY, DEFAULT_LANGUAGE)
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    st.session_state[LANGUAGE_SESSION_KEY] = language
    return language


def set_current_language(language: str):
    """Persist the current UI language."""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    st.session_state[LANGUAGE_SESSION_KEY] = language


def get_language_display(language_code: str, ui_language: str | None = None) -> str:
    """Return a localized label for a language option."""
    current_ui_language = ui_language or get_current_language()
    display = LANGUAGE_DISPLAY.get(language_code, language_code)
    if isinstance(display, dict):
        return display.get(current_ui_language, display.get(DEFAULT_LANGUAGE, language_code))
    return display


def has_cjk(text: str) -> bool:
    """Return True when the string contains visible CJK characters."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _is_non_ui_markup(text: str) -> bool:
    """Return True when the string is a raw style/script block that should not be translated."""
    stripped = text.lstrip()
    return stripped.startswith("<style") or stripped.startswith("<script")


def translate_text(text: str) -> str:
    """Translate a single UI string according to the active language."""
    if not isinstance(text, str):
        return text

    if get_current_language() != "en":
        return text

    if not text.strip():
        return text

    if _is_non_ui_markup(text):
        return text

    normalized_text = text.strip()
    if normalized_text in _EXACT_TRANSLATIONS_NORMALIZED:
        return _EXACT_TRANSLATIONS_NORMALIZED[normalized_text]

    translated = text

    if has_cjk(translated):
        for source, target in _PHRASE_TRANSLATIONS_SORTED:
            if source in translated:
                translated = translated.replace(source, target)

        for pattern, replacement in REGEX_TRANSLATIONS:
            translated = pattern.sub(replacement, translated)

        for source, target in PUNCTUATION_TRANSLATIONS:
            translated = translated.replace(source, target)

        translated = re.sub(r" +", " ", translated)
        translated = re.sub(r" *\n *", "\n", translated)

    return translated


def translate_value(value: Any) -> Any:
    """Translate common Streamlit argument values."""
    if isinstance(value, str):
        return translate_text(value)
    if isinstance(value, list):
        return [translate_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(translate_value(item) for item in value)
    return value


def _wrap_option_format_func(existing_format_func: Callable[[Any], Any] | None):
    """Wrap a widget format_func so the display text is translated without mutating option values."""

    def wrapped(option: Any) -> Any:
        label = existing_format_func(option) if existing_format_func else option
        return translate_value(label)

    return wrapped


def _wrap_streamlit_callable(name: str, original: Callable[..., Any], positional_indices: tuple[int, ...] = (0,), keyword_names: tuple[str, ...] = ("label", "help", "placeholder", "value", "caption")):
    @wraps(original)
    def wrapped(*args, **kwargs):
        args = list(args)
        for index in positional_indices:
            if index < len(args):
                args[index] = translate_value(args[index])

        for key in keyword_names:
            if key in kwargs:
                kwargs[key] = translate_value(kwargs[key])

        if name in _OPTION_WIDGETS:
            kwargs["format_func"] = _wrap_option_format_func(kwargs.get("format_func"))

        return original(*args, **kwargs)

    wrapped.__name__ = getattr(original, "__name__", name)
    return wrapped


def apply_streamlit_i18n():
    """Patch common Streamlit UI functions so they honor the global language."""
    global _STREAMLIT_PATCHED
    if _STREAMLIT_PATCHED:
        return

    streamlit_targets = {
        "title": (0,),
        "header": (0,),
        "subheader": (0,),
        "caption": (0,),
        "markdown": (0,),
        "info": (0,),
        "warning": (0,),
        "error": (0,),
        "success": (0,),
        "button": (0,),
        "form_submit_button": (0,),
        "metric": (0,),
        "text_input": (0,),
        "text_area": (0,),
        "number_input": (0,),
        "selectbox": (0,),
        "multiselect": (0,),
        "checkbox": (0,),
        "radio": (0,),
        "tabs": (0,),
        "expander": (0,),
        "popover": (0,),
        "spinner": (0,),
        "toast": (0,),
        "file_uploader": (0,),
        "download_button": (0,),
        "dialog": (0,),
        "slider": (0,),
        "select_slider": (0,),
    }

    for name, indices in streamlit_targets.items():
        if hasattr(st, name):
            original_module_callable = getattr(st, name)
            _ORIGINAL_STREAMLIT_CALLABLES[f"module:{name}"] = original_module_callable
            setattr(
                st,
                name,
                _wrap_streamlit_callable(
                    name,
                    original_module_callable,
                    positional_indices=indices,
                ),
            )
            if hasattr(DeltaGenerator, name):
                original_delta_callable = getattr(DeltaGenerator, name)
                _ORIGINAL_STREAMLIT_CALLABLES[f"dg:{name}"] = original_delta_callable
                setattr(
                    DeltaGenerator,
                    name,
                    _wrap_streamlit_callable(
                        name,
                        original_delta_callable,
                        positional_indices=tuple(index + 1 for index in indices),
                    ),
                )

    column_config_targets = [
        "TextColumn",
        "NumberColumn",
        "CheckboxColumn",
        "SelectboxColumn",
        "DateColumn",
        "DatetimeColumn",
        "TimeColumn",
        "LinkColumn",
        "ListColumn",
        "ProgressColumn",
        "ImageColumn",
        "LineChartColumn",
        "BarChartColumn",
        "AreaChartColumn",
    ]

    for name in column_config_targets:
        if hasattr(st_column_config, name):
            original = getattr(st_column_config, name)
            _ORIGINAL_COLUMN_CONFIG_CALLABLES[name] = original
            setattr(
                st_column_config,
                name,
                _wrap_streamlit_callable(name, original, positional_indices=(0,), keyword_names=("label", "help")),
            )

    _STREAMLIT_PATCHED = True
