"""
QQQuest - Quest device management entrypoint.
"""
import streamlit as st

from config.settings import STREAMLIT_CONFIG
from utils.i18n import (
    SUPPORTED_LANGUAGES,
    apply_streamlit_i18n,
    get_current_language,
    get_language_display,
    set_current_language,
)
from utils.init import init_all
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(**STREAMLIT_CONFIG)

if not init_all():
    st.stop()

apply_streamlit_i18n()


NAV_TITLES = {
    "zh-TW": {
        "home": "首頁",
        "devices": "設備管理",
        "rooms": "房間管理",
        "actions": "動作管理",
        "screen_wall": "畫面牆",
        "settings": "系統設定",
    },
    "en": {
        "home": "Home",
        "devices": "Device Management",
        "rooms": "Room Management",
        "actions": "Action Management",
        "screen_wall": "Screen Wall",
        "settings": "System Settings",
    },
}


def render_language_selector():
    """Render the global language switcher in the sidebar."""
    current_language = get_current_language()
    selected_language = st.sidebar.selectbox(
        "Language / 語言",
        options=list(SUPPORTED_LANGUAGES),
        index=list(SUPPORTED_LANGUAGES).index(current_language),
        format_func=lambda code: get_language_display(code, current_language),
        key="global_language_selector",
    )
    if selected_language != current_language:
        set_current_language(selected_language)
        st.rerun()


def render_home_page():
    """Render the home dashboard."""
    language = get_current_language()
    is_en = language == "en"

    if is_en:
        st.title("🎮 QQQuest - Quest Device Sync Management")
        st.markdown(
            """
## Welcome to QQQuest!

This is a Quest device group management system built on ADB and scrcpy, supporting multi-device synchronized control, timeline sync, and operation scheduling.

### Key Features

- 📱 **Device Management**: Wi-Fi ADB connection and device status monitoring
- 🏠 **Room Management**: Create rooms, assign devices, and batch control
- ⚡ **Action Management**: Reusable actions for sleep, app launch/stop, and messaging
- ⏱️ **Timeline Sync**: Room-level timing and high-precision device synchronization
- 📅 **CUE Scheduling**: Timeline editing and automated operation sequences
- 🖥️ **scrcpy Integration**: Multi-device screen mirroring

### Quick Start

1. Go to **📱 Device Management** to connect your Quest devices
2. Create a room and assign devices in **🏠 Room Management**
3. Use **⚡ Action Management** to configure and run operations

---

### System Status
"""
        )
    else:
        st.title("🎮 QQQuest - Quest 設備同步管理系統")
        st.markdown(
            """
## 歡迎使用 QQQuest！

這是一個基於 ADB 和 scrcpy 的 Quest 設備群組管理系統，支援多設備同步控制、時間碼同步和操作排程。

### 功能特色

- 📱 **設備管理**：WiFi ADB 連接、設備狀態監控
- 🏠 **房間管理**：創建房間、設備分配、批量控制
- ⚡ **動作管理**：預設動作（休眠、開啟/關閉程式、傳送訊息）
- ⏱️ **時間碼同步**：房間時間碼、高精度設備同步
- 📅 **CUE 排程**：時間軸編輯、自動執行操作序列
- 📺 **scrcpy 監看**：單台/少量設備螢幕鏡像（已限流）
- 🖥️ **畫面牆**：多台設備縮圖同時監看（裝置端縮圖，最省頻寬）

### 快速開始

1. 前往 **📱 設備管理** 頁面連接你的 Quest 設備
2. 在 **🏠 房間管理** 頁面建立房間並分配設備
3. 使用 **⚡ 動作管理** 頁面設定和執行操作

---

### 系統狀態
"""
        )

    devices = st.session_state.device_registry.get_all_devices()
    online_devices = len([device for device in devices if device.is_online])
    rooms = st.session_state.room_registry.get_all_rooms()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("設備總數" if not is_en else "Total Devices", len(devices))
    with col2:
        st.metric("在線設備" if not is_en else "Online Devices", online_devices)
    with col3:
        st.metric("房間數量" if not is_en else "Room Count", len(rooms))

    st.markdown("### 快速操作" if not is_en else "### Quick Actions")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📱 管理設備" if not is_en else "📱 Manage Devices", width="stretch"):
            st.switch_page("pages/1_📱_設備管理.py")

    with col2:
        if st.button("🏠 管理房間" if not is_en else "🏠 Manage Rooms", width="stretch"):
            st.switch_page("pages/2_🏠_房間管理.py")

    with col3:
        if st.button("⚡ 管理動作" if not is_en else "⚡ Manage Actions", width="stretch"):
            st.switch_page("pages/3_⚡_動作管理.py")

    st.markdown("### 最近活動" if not is_en else "### Recent Activity")
    st.info("暫無活動記錄" if not is_en else "No recent activity")

    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>QQQuest v1.0.0 | Made with ❤️ by QQQuest Team</div>",
        unsafe_allow_html=True,
    )


def build_navigation():
    """Build the sidebar navigation structure."""
    titles = NAV_TITLES[get_current_language()]
    return st.navigation(
        [
            st.Page(render_home_page, title=titles["home"], icon="🏠", default=True),
            st.Page("pages/1_📱_設備管理.py", title=titles["devices"], icon="📱"),
            st.Page("pages/2_🏠_房間管理.py", title=titles["rooms"], icon="🏠"),
            st.Page("pages/3_⚡_動作管理.py", title=titles["actions"], icon="⚡"),
            st.Page("pages/5_🖥️_畫面牆.py", title=titles["screen_wall"], icon="🖥️", url_path="screenwall"),
            st.Page("pages/4_⚙️_系統設定.py", title=titles["settings"], icon="⚙️"),
        ],
        position="sidebar",
    )


def main():
    """Application router."""
    render_language_selector()
    page = build_navigation()
    page.run()


if __name__ == "__main__":
    main()
