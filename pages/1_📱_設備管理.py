"""
設備管理頁面（簡化版 - 僅手動添加）
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from typing import Optional
import time
import uuid
from components.control_panel_cards import (
    inject_control_panel_card_styles,
    themed_card_key,
)
from core.device import Device
from core.action_registry import ActionRegistry
from core.auto_connect_manager import AutoConnectManager
from core.ping_service import PingService
from config.constants import DeviceStatus, STATUS_ICONS, CONNECTION_ICONS, ConnectionType
from config.settings import UI_REFRESH_INTERVAL, ADB_DEFAULT_PORT, get_user_config
from utils.logger import get_logger

logger = get_logger(__name__)

# 頁面配置
st.set_page_config(
    page_title="設備管理 - QQQuest",
    page_icon="📱",
    layout="wide"
)

# 自定義 CSS 樣式
st.markdown("""
    <style>
    /* 隱藏標題旁的錨點鏈接圖標 */
    a.st-emotion-cache-yinll1,
    a[class*="st-emotion-cache"][href^="#"] {
        display: none !important;
    }
    
    /* 統一設備卡片高度和對齊 */
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
        height: 100%;
        min-height: 380px;
    }
    
    /* 確保卡片內容填充整個容器 */
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] > div {
        height: 100%;
        display: flex;
        flex-direction: column;
    }
    
    /* 讓卡片在 grid 中均勻分布 */
    [data-testid="column"] {
        display: flex;
        flex-direction: column;
    }
    
    /* 排序按鈕容器 - 讓兩個按鈕並排顯示 */
    /* 讓包含排序按鈕的元素容器水平排列 */
    div[class*="st-key-up_"],
    div[class*="st-key-down_"] {
        display: inline-block !important;
        vertical-align: middle !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    div[class*="st-key-up_"] {
        margin-right: 0.05rem !important;
    }
    
    /* 減少排序按鈕容器之間的間距 */
    div[class*="st-key-up_"] + div[class*="st-key-down_"],
    div[class*="st-key-down_"] + div[class*="st-key-up_"] {
        margin-left: 0 !important;
    }
    
    /* 減少包含排序按鈕的垂直塊容器的間距 */
    div[data-testid="stVerticalBlock"]:has(div[class*="st-key-up_"]):has(div[class*="st-key-down_"]) {
        gap: 0.05rem !important;
    }
    
    /* 減少排序按鈕元素容器之間的間距 */
    div[class*="st-key-up_"][data-testid="stElementContainer"],
    div[class*="st-key-down_"][data-testid="stElementContainer"] {
        margin: 0 !important;
        padding: 0 !important;
    }
    
    div[class*="st-key-up_"][data-testid="stElementContainer"] + div[class*="st-key-down_"][data-testid="stElementContainer"],
    div[class*="st-key-down_"][data-testid="stElementContainer"] + div[class*="st-key-up_"][data-testid="stElementContainer"] {
        margin-left: 0 !important;
    }
    
    /* 排序按鈕樣式優化 - 尺寸縮小為1/2 */
    div[class*="st-key-up_"] button,
    div[class*="st-key-down_"] button {
        padding: 0.15rem 0.3rem !important;
        min-height: 1.2rem !important;
        font-size: 0.7rem !important;
        width: auto !important;
        margin: 0 !important;
        line-height: 1.2 !important;
    }
    
    /* 排序按鈕居中對齊 */
    [data-testid="stTooltipHoverTarget"] {
        justify-content: center !important;
    }

    /* ---------- 頂部工具列 ---------- */
    /* 工具列與下方內容拉開距離，按鈕本身也長高一點，不要擠成一團 */
    div[class*="st-key-btn_add_device"] button,
    div[class*="st-key-btn_refresh"] button,
    div[class*="st-key-btn_batch_connect"] button,
    div[class*="st-key-btn_no_sleep"] button,
    div[class*="st-key-btn_install_helper"] button {
        min-height: 2.6rem !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
    }

    /* 工具列整排與下方內容拉開距離 */
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-btn_batch_connect"]) {
        margin-bottom: 1.1rem !important;
    }
    /* 標題與工具列之間留白 */
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-btn_batch_connect"]) {
        margin-top: 0.5rem !important;
    }

    /* ---------- 一鍵連接：高亮 ---------- */
    div[class*="st-key-btn_batch_connect"] button {
        background: linear-gradient(135deg, #16a34a 0%, #12833f 100%) !important;
        color: #ffffff !important;
        border: 1px solid #12833f !important;
        font-weight: 700 !important;
        letter-spacing: .3px !important;
        box-shadow: 0 2px 10px rgba(22, 163, 74, .38) !important;
        transition: transform .08s ease, box-shadow .18s ease, background .18s ease !important;
    }
    div[class*="st-key-btn_batch_connect"] button:hover {
        background: linear-gradient(135deg, #1cb856 0%, #16a34a 100%) !important;
        box-shadow: 0 5px 16px rgba(22, 163, 74, .5) !important;
        transform: translateY(-1px) !important;
        border-color: #16a34a !important;
    }
    div[class*="st-key-btn_batch_connect"] button:active {
        transform: translateY(0) !important;
        box-shadow: 0 2px 8px rgba(22, 163, 74, .4) !important;
    }
    /* 按鈕內文字也要跟著變白（Streamlit 有時把顏色掛在內層 p） */
    div[class*="st-key-btn_batch_connect"] button p,
    div[class*="st-key-btn_batch_connect"] button div {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    </style>
""", unsafe_allow_html=True)

inject_control_panel_card_styles()

# 使用 JavaScript 動態讓排序按鈕容器水平排列
st.markdown("""
    <script>
    (function() {
        // 查找所有包含排序按鈕的列
        const columns = document.querySelectorAll('[data-testid="stColumn"]');
        columns.forEach(col => {
            const upBtn = col.querySelector('[class*="st-key-up_"]');
            const downBtn = col.querySelector('[class*="st-key-down_"]');
            if (upBtn && downBtn) {
                // 找到包含這兩個按鈕的垂直塊容器
                const verticalBlock = col.querySelector('[data-testid="stVerticalBlock"]');
                if (verticalBlock) {
                    verticalBlock.style.display = 'flex';
                    verticalBlock.style.flexDirection = 'row';
                    verticalBlock.style.gap = '0.05rem';
                    verticalBlock.style.alignItems = 'center';
                    verticalBlock.style.justifyContent = 'center';
                }
            }
        });
    })();
    </script>
""", unsafe_allow_html=True)

# 自動刷新（每 3 秒）- 但在有對話框時暫停
dialog_keys = [key for key in st.session_state.keys() if key.startswith(('confirm_remove_', 'edit_device_', 'execute_action_on_', 'show_add_device_dialog'))]
dialog_states = {key: st.session_state.get(key, False) for key in dialog_keys}
has_dialog_open = any(dialog_states.values())

# 只在沒有對話框時自動刷新
if not has_dialog_open:
    try:
        st_autorefresh(interval=UI_REFRESH_INTERVAL * 1000, key="device_refresh", debounce=False)
    except Exception:
        pass

# 初始化系統
from utils.init import ensure_initialization, ensure_action_registry, ensure_room_registry

if not ensure_initialization():
    st.stop()

ensure_action_registry()
ensure_room_registry()  # 需要 room_registry 來查找設備所屬的房間

# Session state 初始化
if 'show_add_device_dialog' not in st.session_state:
    st.session_state.show_add_device_dialog = False


def show_add_device_dialog():
    """顯示手動新增設備對話框"""
    with st.form("add_device_form"):
        st.subheader("➕ 新增設備")
        
        ip = st.text_input(
            "IP 地址 *",
            placeholder="192.168.1.100",
            help="Quest 設備的 IP 地址"
        )
        
        port = st.number_input(
            "端口",
            min_value=1,
            max_value=65535,
            value=ADB_DEFAULT_PORT,
            help="ADB 端口，默認為 5555"
        )
        
        alias = st.text_input(
            "設備代號（選填）",
            placeholder="Q01",
            help="方便識別的代號"
        )
        
        notes = st.text_area(
            "備註（選填）",
            placeholder="例如：訓練室 A"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("🔌 連接", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("取消", use_container_width=True)
        
        if cancel:
            st.session_state.show_add_device_dialog = False
            st.rerun()
        
        if submitted:
            if not ip:
                st.error("請輸入 IP 地址")
                return
            
            # 連接設備
            with st.spinner("正在連接設備..."):
                success, output = st.session_state.adb_manager.connect(ip, port)
                
                if success or "already connected" in output.lower():
                    # 取得設備資訊
                    connection_str = f"{ip}:{port}"
                    info = st.session_state.adb_manager.get_device_info(connection_str)
                    serial = info.get('serial', connection_str)
                    
                    # 建立設備
                    device = Device(
                        device_id=f"device_{uuid.uuid4().hex[:12]}",
                        serial=serial,
                        alias=alias or f"Device-{serial[:4]}",
                        name=alias or f"Device-{serial[:4]}",
                        model=info.get('model', ''),
                        android_version=info.get('android_version', ''),
                        ip=ip,
                        port=port,
                        connection_type="wifi",
                        status=DeviceStatus.ONLINE,
                        notes=notes,
                        first_connected=datetime.now(),
                        last_seen=datetime.now()
                    )
                    
                    # 更新設備狀態
                    battery = st.session_state.adb_manager.get_battery_level(connection_str)
                    if battery:
                        device.battery = battery
                    
                    # 保存到資料庫
                    if st.session_state.device_registry.save_device(device):
                        st.success(f"✅ 設備已連接：{device.display_name}")
                        st.session_state.show_add_device_dialog = False
                        st.rerun()
                    else:
                        st.error("❌ 保存設備失敗")
                else:
                    st.error(f"❌ 連接失敗：{output}")


@st.dialog("🗑️ 確認移除設備", width="small")
def confirm_remove_device(device: Device):
    """確認移除設備對話框（使用 st.dialog 裝飾器）"""
    # 隱藏對話框右上角的關閉按鈕
    st.markdown("""
        <style>
        /* 隱藏對話框的關閉按鈕 - 使用多種選擇器確保覆蓋 */
        button[kind="header"] {
            display: none !important;
        }
        
        button[aria-label="Close"] {
            display: none !important;
        }
        
        div[data-testid="stDialog"] button[kind="header"] {
            display: none !important;
        }
        
        /* 針對可能的內部類名 */
        button.st-emotion-cache-ue6h4q,
        button.st-emotion-cache-7oyrr6 {
            display: none !important;
        }
        
        /* 通過屬性選擇器 */
        button[data-baseweb="button"][kind="header"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.warning(f"確定要移除設備 **{device.display_name}** 嗎？")
    if device.ip:
        st.caption(f"連接：{device.ip}:{device.port}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ 確定移除", key=f"confirm_yes_{device.device_id}", use_container_width=True, type="primary"):
            logger.info(f"🗑️ 移除設備: {device.display_name}")
            if st.session_state.device_registry.remove_device(device.serial):
                st.success("✅ 設備已移除")
                # 清除標記
                st.session_state[f'confirm_remove_{device.device_id}'] = False
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 移除失敗")
    
    with col2:
        if st.button("❌ 取消", key=f"confirm_no_{device.device_id}", use_container_width=True):
            logger.info(f"❌ 取消移除: {device.display_name}")
            st.session_state[f'confirm_remove_{device.device_id}'] = False
            st.rerun()


@st.dialog("⚙️ 編輯設備", width="large")
def edit_device_dialog(device: Device):
    """編輯設備對話框"""
    # 隱藏對話框右上角的關閉按鈕
    st.markdown("""
        <style>
        /* 隱藏對話框的關閉按鈕 - 使用多種選擇器確保覆蓋 */
        button[kind="header"] {
            display: none !important;
        }
        
        button[aria-label="Close"] {
            display: none !important;
        }
        
        div[data-testid="stDialog"] button[kind="header"] {
            display: none !important;
        }
        
        /* 針對可能的內部類名 */
        button.st-emotion-cache-ue6h4q,
        button.st-emotion-cache-7oyrr6 {
            display: none !important;
        }
        
        /* 通過屬性選擇器 */
        button[data-baseweb="button"][kind="header"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if device.ip:
        st.markdown(f"**連接**: `{device.ip}:{device.port}`")
    st.markdown("---")
    
    with st.form("edit_device_form"):
        st.subheader("📝 基本資訊")
        
        # 別名（代號）
        alias = st.text_input(
            "設備代號 *",
            value=device.alias,
            placeholder="Q01",
            help="方便識別的簡短代號",
            key=f"edit_alias_{device.device_id}"
        )
        
        # 名稱
        name = st.text_input(
            "設備名稱",
            value=device.name,
            placeholder="訓練室 A - Quest 3",
            help="設備的完整名稱（選填）",
            key=f"edit_name_{device.device_id}"
        )
        
        # 備註
        notes = st.text_area(
            "備註",
            value=device.notes,
            placeholder="例如：主要用於新手訓練",
            help="任何額外的說明（選填）",
            key=f"edit_notes_{device.device_id}",
            height=100
        )
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            submitted = st.form_submit_button("💾 保存", use_container_width=True, type="primary")
        
        with col2:
            cancel = st.form_submit_button("❌ 取消", use_container_width=True)
        
        if cancel:
            logger.info(f"❌ 取消編輯: {device.display_name}")
            st.session_state[f'edit_device_{device.device_id}'] = False
            st.rerun()
        
        if submitted:
            if not alias:
                st.error("⚠️ 請輸入設備代號")
                return
            
            # 更新設備資訊
            logger.info(f"💾 保存設備編輯: {device.display_name}")
            logger.info(f"   舊別名: {device.alias} → 新別名: {alias}")
            
            device.alias = alias
            device.name = name or alias
            device.notes = notes
            
            # 保存到資料庫
            if st.session_state.device_registry.save_device(device):
                st.success(f"✅ 設備 **{alias}** 已更新")
                logger.info(f"✅ 設備資訊已保存: {alias}")
                st.session_state[f'edit_device_{device.device_id}'] = False
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 保存失敗，請查看日誌")
                logger.error(f"❌ 保存設備失敗: {device.serial}")


@st.dialog("⚡ 執行動作", width="large")
def execute_action_dialog(device: Device):
    """在設備上執行動作對話框"""
    # 隱藏對話框右上角的關閉按鈕
    st.markdown("""
        <style>
        button[kind="header"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.subheader(f"📱 目標設備：{device.display_name}")
    
    if not device.is_online:
        if device.status == DeviceStatus.NOT_CONNECTED:
            st.warning("⚠️ 設備未連接，請先連接後再執行動作")
        elif device.status == DeviceStatus.OFFLINE:
            st.warning("⚠️ 設備離線（ADB state: offline），請等待設備恢復後再執行動作")
        else:
            st.warning(f"⚠️ 設備狀態異常（{device.status}），無法執行動作")
        if st.button("關閉"):
            st.session_state[f'execute_action_on_{device.device_id}'] = False
            st.rerun()
        return
    
    st.markdown("---")
    
    # 獲取所有動作
    all_actions = st.session_state.action_registry.get_all_actions()
    
    if not all_actions:
        st.info("📝 還沒有任何動作，請先前往動作管理頁面創建動作")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ 前往動作管理", use_container_width=True, type="primary"):
                st.switch_page("pages/3_⚡_動作管理.py")
        with col2:
            if st.button("❌ 關閉", use_container_width=True):
                st.session_state[f'execute_action_on_{device.device_id}'] = False
                st.rerun()
        return
    
    # 動作選擇
    st.markdown("**選擇要執行的動作**")
    
    # 顯示動作列表（帶圖標和說明）
    action_options = {action.action_id: action for action in all_actions}
    action_labels = {
        action.action_id: f"{action.display_name}" + (f" - {action.description[:30]}..." if action.description and len(action.description) > 30 else f" - {action.description}" if action.description else "")
        for action in all_actions
    }
    
    selected_action_id = st.selectbox(
        "動作",
        options=list(action_options.keys()),
        format_func=lambda aid: action_labels[aid],
        label_visibility="collapsed"
    )
    
    selected_action = action_options[selected_action_id]
    
    # 顯示動作詳情
    with st.expander("📋 動作詳情", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**類型**: {selected_action.type_name}")
            if selected_action.execution_count > 0:
                st.markdown(f"**執行次數**: {selected_action.execution_count}")
        with col2:
            if selected_action.execution_count > 0:
                st.markdown(f"**成功率**: {selected_action.success_rate:.0f}%")
            if selected_action.last_executed_at:
                time_diff = datetime.now() - selected_action.last_executed_at
                if time_diff.days > 0:
                    last_exec = f"{time_diff.days} 天前"
                elif time_diff.seconds >= 3600:
                    last_exec = f"{time_diff.seconds // 3600} 小時前"
                elif time_diff.seconds >= 60:
                    last_exec = f"{time_diff.seconds // 60} 分鐘前"
                else:
                    last_exec = "剛剛"
                st.markdown(f"**最後執行**: {last_exec}")
        
        # 顯示參數
        if selected_action.params:
            st.markdown("**參數**:")
            for key, value in selected_action.params.items():
                if value:  # 只顯示非空值
                    st.text(f"  {key}: {value}")
    
    st.markdown("---")
    
    # 執行按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ 執行", type="primary", use_container_width=True):
            with st.spinner("執行中..."):
                # 自動查找設備所屬的房間並獲取 Socket Server 信息
                room_info = None
                if 'room_registry' in st.session_state:
                    device_room = st.session_state.room_registry.get_device_room(device.device_id)
                    if device_room and device_room.socket_ip and device_room.socket_port:
                        room_info = {
                            'socket_ip': device_room.socket_ip,
                            'socket_port': device_room.socket_port
                        }
                        logger.debug(f"📡 自動添加 Socket Server 參數: {device.display_name} -> {device_room.name} ({device_room.socket_ip}:{device_room.socket_port})")
                
                # 執行動作
                success, message = st.session_state.adb_manager.execute_action(
                    device.connection_string,
                    selected_action,
                    room_info=room_info
                )
                
                # 更新執行統計
                selected_action.increment_execution(success=success, status=message)
                st.session_state.action_registry.update_action(selected_action)
                
                if success:
                    st.success(f"✅ {message}")
                    logger.info(f"✅ 執行動作成功: {selected_action.display_name} -> {device.display_name}")
                else:
                    st.error(f"❌ {message}")
                    logger.error(f"❌ 執行動作失敗: {selected_action.display_name} -> {device.display_name}")
                
                time.sleep(1.5)
                st.session_state[f'execute_action_on_{device.device_id}'] = False
                st.rerun()
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state[f'execute_action_on_{device.device_id}'] = False
            st.rerun()


def render_device_card(device: Device):
    """渲染設備卡片"""
    import time
    
    # 狀態圖示
    status_icon = STATUS_ICONS.get(device.status, "❓")
    
    # 卡片容器
    with st.container(border=True, key=themed_card_key("device-management", device.device_id)):
        # 頂部：排序按鈕、標題和選單按鈕
        col_sort, col_title, col_menu = st.columns([0.5, 3.5, 1])
        
        # 排序按鈕（合併在一個容器中）
        with col_sort:
            # 兩個按鈕直接放在同一個列中，使用 CSS 讓它們並排顯示
            if st.button("⬆️", key=f"up_{device.device_id}", help="向上移動", use_container_width=False):
                st.session_state[f'move_up_{device.device_id}'] = True
                st.rerun()
            
            if st.button("⬇️", key=f"down_{device.device_id}", help="向下移動", use_container_width=False):
                st.session_state[f'move_down_{device.device_id}'] = True
                st.rerun()
        
        with col_title:
            st.markdown(f"### {status_icon} {device.display_name}")
        with col_menu:
            # 使用 popover 讓選單在按鈕正下方展開
            with st.popover("⋮", use_container_width=False):
                st.markdown("**操作選單**")
                
                # 執行動作
                if device.is_online:
                    if st.button("⚡ 執行動作", key=f"action_{device.device_id}", use_container_width=True):
                        st.session_state[f'execute_action_on_{device.device_id}'] = True
                        st.rerun()
                else:
                    st.button("⚡ 執行動作", key=f"action_{device.device_id}", use_container_width=True, disabled=True)
                    if device.status == DeviceStatus.OFFLINE:
                        st.caption("（設備離線）")
                    elif device.status == DeviceStatus.NOT_CONNECTED:
                        st.caption("（設備未連接）")
                    elif device.status == DeviceStatus.ADB_NOT_ENABLED:
                        st.caption("（無法連線 - WiFi ADB 未開啟）")
                    else:
                        st.caption(f"（設備狀態：{device.status}）")
                
                if st.button("🏠 加入房間", key=f"room_{device.device_id}", use_container_width=True):
                    st.info("房間管理功能開發中...")
                
                # 監看設備（scrcpy）
                if device.is_online:
                    if st.button("📺 監看設備", key=f"monitor_{device.device_id}", use_container_width=True):
                        logger.info(f"📺 啟動監看: {device.display_name}")
                        success, message = st.session_state.adb_manager.start_quest_single_eye_scrcpy(
                            device.connection_string,
                            window_title=f"{device.display_name} - QQQuest",
                            auto_arrange=True
                        )
                        if success:
                            st.success(f"✅ {message}")
                            logger.info(f"✅ scrcpy 視窗已開啟: {device.display_name}")
                        else:
                            st.error(f"❌ {message}")
                            logger.error(f"❌ scrcpy 啟動失敗: {device.display_name} - {message}")
                
                # 中斷連線（僅在線設備）
                if device.is_online:
                    if st.button("🔌 中斷連線", key=f"disconnect_{device.device_id}", use_container_width=True):
                        logger.info(f"🔌 嘗試中斷連線: {device.display_name} ({device.connection_string})")
                        success, output = st.session_state.adb_manager.disconnect(device.connection_string)
                        logger.info(f"🔌 中斷結果: success={success}, output={output}")
                        
                        if success:
                            st.success(f"✅ 已中斷連線：{device.connection_string}")
                            device.status = DeviceStatus.NOT_CONNECTED  # 中斷後變為未連接
                            st.session_state.device_registry.save_device(device)
                            logger.info(f"✅ 設備 {device.display_name} 已標記為未連接")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"❌ 中斷連線失敗：{output}")
                            logger.error(f"❌ 中斷連線失敗: {device.display_name} - {output}")
                
                # 重新連線（僅未連接設備或無法連線設備）
                if device.status == DeviceStatus.NOT_CONNECTED or device.status == DeviceStatus.ADB_NOT_ENABLED:
                    button_text = "🔌 重新連線" if device.status == DeviceStatus.NOT_CONNECTED else "🔧 嘗試連接"
                    if st.button(button_text, key=f"reconnect_{device.device_id}", use_container_width=True):
                        if device.ip:
                            logger.info(f"🔄 嘗試重新連線: {device.display_name} ({device.ip}:{device.port})")
                            # 先 adb devices → adb -s <serial> tcpip 5555 → 再 adb connect
                            success, output = st.session_state.adb_manager.reconnect_via_tcpip(
                                device.ip, device.port, prefer_serial=device.serial
                            )
                            logger.info(f"🔄 連線結果: success={success}, output={output}")
                            with st.expander("🔍 查看 adb 步驟", expanded=not success):
                                st.code(output)

                            if success or "already connected" in output.lower():
                                st.success(f"✅ 已重新連線：{device.ip}:{device.port}")
                                # 連接成功後，狀態會在下次掃描時自動更新為 ONLINE 或 OFFLINE
                                device.last_seen = datetime.now()
                                
                                # 重置自動連接重試次數
                                if 'auto_connect_manager' in st.session_state:
                                    st.session_state.auto_connect_manager.reset_retry_count(device.device_id)
                                    logger.debug(f"重置設備 {device.display_name} 的自動連接重試次數（手動連接成功）")
                                
                                st.session_state.device_registry.save_device(device)
                                logger.info(f"✅ 設備 {device.display_name} 重新連線成功")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"❌ 連線失敗：{output}")
                                logger.error(f"❌ 重新連線失敗: {device.display_name} - {output}")
                        else:
                            st.warning("⚠️ 設備沒有 IP 地址，無法重新連線")
                            logger.warning(f"⚠️ 設備 {device.display_name} 沒有 IP 地址")
                
                if st.button("⚙️ 編輯設定", key=f"edit_{device.device_id}", use_container_width=True):
                    st.session_state[f'edit_device_{device.device_id}'] = True
                    st.rerun()
                
                if st.button("🗑️ 移除設備", key=f"remove_{device.device_id}", use_container_width=True, type="secondary"):
                    st.session_state[f'confirm_remove_{device.device_id}'] = True
                    st.rerun()
        
        # 設備資訊
        if device.ip:
            st.markdown(f"**連接**：`{device.ip}:{device.port}`")
        
        # 取得額外狀態資訊（從 session_state 緩存）
        extra_status = st.session_state.get('device_extra_status', {}).get(device.device_id, {})
        is_awake = extra_status.get('is_awake', True)
        is_screen_on = extra_status.get('is_screen_on', False)
        uptime = extra_status.get('uptime', 0)
        
        # 狀態列 1：電量和溫度
        col1, col2 = st.columns(2)
        with col1:
            if device.battery > 0:
                battery_color = "🟢" if device.battery > 50 else "🟡" if device.battery > 20 else "🔴"
                charging_icon = " ⚡" if device.is_charging else ""
                st.markdown(f"{battery_color} 電量：{device.battery}%{charging_icon}")
        
        with col2:
            if device.temperature > 0:
                temp_color = "🟢" if device.temperature < 35 else "🟡" if device.temperature < 40 else "🔴"
                st.markdown(f"{temp_color} 溫度：{device.temperature:.1f}°C")
            elif device.ping_ms is not None:
                # 顯示 Ping 時間
                ping_color = "🟢" if device.ping_ms < 50 else "🟡" if device.ping_ms < 100 else "🔴"
                st.markdown(f"{ping_color} Ping：{device.ping_ms:.0f}ms")
        
        # 狀態列 2：運作狀態和最後在線
        col1, col2 = st.columns(2)
        with col1:
            if device.status == DeviceStatus.ONLINE:
                # 在線狀態：顯示運作狀態
                if is_awake:
                    screen_status = "📺" if is_screen_on else "📴"
                    st.markdown(f"👁️ 清醒 {screen_status}")
                else:
                    st.markdown("😴 休眠中")
            elif device.status == DeviceStatus.OFFLINE:
                # 離線狀態：在 ADB 列表中但狀態為 offline
                st.markdown("🟠 離線")
            elif device.status == DeviceStatus.NOT_CONNECTED:
                # 未連接狀態：不在 ADB 列表中
                st.markdown("⚫ 未連接")
            elif device.status == DeviceStatus.ADB_NOT_ENABLED:
                # WiFi ADB 未開啟
                st.markdown("🟡 無法連線")
                st.caption("需要手動開啟 WiFi ADB")
            else:
                # 其他狀態
                st.markdown(f"❓ {device.status}")
        
        with col2:
            if device.last_seen:
                time_diff = datetime.now() - device.last_seen
                if time_diff.seconds < 60:
                    st.markdown("🟢 剛剛在線")
                elif time_diff.seconds < 3600:
                    st.markdown(f"🟡 {time_diff.seconds // 60} 分前")
                else:
                    st.markdown(f"🔴 {time_diff.seconds // 3600} 時前")
        
        if uptime > 0 and device.is_online:
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            if hours > 0:
                st.caption(f"⏱️ 開機：{hours}h {minutes}m")
            else:
                st.caption(f"⏱️ 開機：{minutes}m")
        
        # 備註
        if device.notes:
            with st.expander("📝 備註"):
                st.write(device.notes)



def main():
    """主函數"""
    
    st.title("📱 設備管理")
    
    # 頂部操作欄
    col1, col2, col3, col4, col5 = st.columns([1, 1, 1.5, 1.15, 1.25], gap="medium")

    with col1:
        if st.button("➕ 新增設備", key="btn_add_device", use_container_width=True):
            st.session_state.show_add_device_dialog = True

    with col2:
        if st.button("🔄 刷新狀態", key="btn_refresh", use_container_width=True):
            st.rerun()

    with col3:
        if st.button("🔗 一鍵連接所有設備", key="btn_batch_connect", use_container_width=True,
                     help="對清單中所有設定了 IP 的設備並發執行 adb connect"):
            st.session_state.batch_connect_requested = True

    # 一鍵連接的結果：執行後會 rerun 讓設備卡片狀態更新，訊息會被沖掉，
    # 所以先存進 session_state，rerun 後再顯示。
    _bc = st.session_state.pop('batch_connect_result', None)
    if _bc:
        _rescued = _bc.get('rescued', 0)
        _total_ok = _bc['ok'] + _rescued
        _extra = f"（其中 {_rescued} 台是重開機後自動喚醒的）" if _rescued else ""
        if _bc['fail']:
            st.warning(f"⚠️ 一鍵連接完成：成功 {_total_ok}/{_bc['total']} 台{_extra}，失敗 {len(_bc['fail'])} 台")
            with st.expander(f"查看失敗的 {len(_bc['fail'])} 台", expanded=False):
                for _name, _msg in _bc['fail']:
                    st.text(f"• {_name}：{_msg}")
                st.caption("提示：若顯示「無線偵錯已關閉」，該台需戴上頭盔開一次 "
                           "Oculus Wireless ADB；其餘多半是設備睡著或關機。")
        else:
            st.success(f"✅ 一鍵連接完成：{_total_ok}/{_bc['total']} 台全部連上{_extra}")
        if _bc.get('skipped'):
            st.caption(f"（略過 {_bc['skipped']} 台沒有設定 IP 的設備）")

    # 執行一鍵連接：對所有有 IP 的設備並發 adb connect
    if st.session_state.pop('batch_connect_requested', False):
        _all = st.session_state.device_registry.get_all_devices()
        _targets = [d for d in _all if d.ip]
        _skipped = len(_all) - len(_targets)

        if not _targets:
            st.warning("⚠️ 沒有可連接的設備（清單中沒有設定 IP 的設備）")
        else:
            _prog = st.progress(0.0, text=f"正在連接 {len(_targets)} 台設備…")

            def _bc_progress(done, total):
                # connect_batch 是在主執行緒回呼的，可安全更新 Streamlit UI
                try:
                    _prog.progress(done / total, text=f"已完成 {done}/{total} 台")
                except Exception:
                    pass

            logger.info(f"🔗 一鍵連接：開始並發連接 {len(_targets)} 台")
            _results = st.session_state.adb_manager.connect_batch(
                [(d.ip, d.port) for d in _targets],
                max_workers=10,
                progress_callback=_bc_progress,
            )
            _prog.empty()

            # 重要：adb connect 會樂觀回報 "connected"，即使設備根本沒上線。
            # 真正的依據是 adb devices 裡的狀態，所以連完再查一次實際狀態。
            _live = {}
            try:
                for _d in st.session_state.adb_manager.get_devices(use_cache=False):
                    _live[_d.get('serial')] = _d.get('state')
            except Exception as _e:
                logger.warning(f"一鍵連接：查詢實際設備狀態失敗 {_e}")

            _adb_mgr = st.session_state.adb_manager

            def _mark_connected(dev):
                if not dev:
                    return
                dev.last_seen = datetime.now()
                st.session_state.device_registry.save_device(dev)
                # 趁連上時順手確保無線偵錯已開，作為「下次重開機」的救援通道。
                # 沒有它，重開機後 5555 消失就只能接 USB 或戴頭盔。
                try:
                    _adb_mgr.ensure_wireless_debugging(dev.connection_string)
                except Exception:
                    pass
                # 手動連上就重置自動連接重試計數（與單台「重新連線」行為一致）
                if 'auto_connect_manager' in st.session_state:
                    try:
                        st.session_state.auto_connect_manager.reset_retry_count(dev.device_id)
                    except Exception:
                        pass

            _by_conn = {f"{d.ip}:{d.port}": d for d in _targets}
            _ok, _pending = 0, []
            for _conn, _success, _msg in _results:
                _dev = _by_conn.get(_conn)
                _state = _live.get(_conn)
                if _state == 'device':
                    _ok += 1
                    _mark_connected(_dev)
                else:
                    _pending.append((_dev, _conn, _state, _msg))

            # 第二輪：對連不上的設備做 mDNS 救援。
            # Quest 重開機後 5555 會被清空（service.adb.tcp.port 非持久屬性），但只要該機
            # 無線偵錯還開著，就能從 mDNS 廣播的 TLS 埠連進去、重下 tcpip 5555 救回來，
            # 全程不必接 USB 也不必戴頭盔。
            _rescued, _fail = 0, []
            if _pending:
                from concurrent.futures import ThreadPoolExecutor

                _rp = st.progress(0.0, text=f"嘗試喚醒 {len(_pending)} 台連不上的設備…")

                # 必須在主執行緒先取出：worker thread 沒有 ScriptRunContext，
                # 在裡面碰 st.session_state 會直接拋例外（救援會全部靜默失敗）。
                _adb = _adb_mgr

                def _rescue(item):
                    dev, conn, state, msg = item
                    if not dev or not dev.ip:
                        return item, False, "沒有 IP，無法救援"
                    try:
                        _rok, _rmsg = _adb.reconnect_via_mdns(dev.ip, dev.port)
                        return item, _rok, _rmsg
                    except Exception as e:
                        return item, False, f"救援發生例外：{e}"

                with ThreadPoolExecutor(max_workers=6) as _ex:
                    for _i, (_item, _rok, _rmsg) in enumerate(_ex.map(_rescue, _pending)):
                        _dev, _conn, _state, _msg = _item
                        _name = _dev.display_name if _dev else _conn
                        if _rok:
                            _rescued += 1
                            _mark_connected(_dev)
                            logger.info(f"🔗 mDNS 救援成功：{_name}")
                        else:
                            if _state == 'offline':
                                _base = "狀態 offline"
                            elif _state:
                                _base = f"狀態 {_state}"
                            else:
                                _base = (_msg or '').strip()[:60] or "無回應"
                            # 救援訊息的最後一行通常最能說明卡在哪
                            _tail = (_rmsg or '').strip().splitlines()
                            _hint = _tail[-1] if _tail else ""
                            _fail.append((_name, f"{_base}；{_hint}"))
                        try:
                            _rp.progress((_i + 1) / len(_pending))
                        except Exception:
                            pass
                _rp.empty()

            st.session_state.batch_connect_result = {
                'ok': _ok, 'rescued': _rescued, 'total': len(_targets),
                'fail': _fail, 'skipped': _skipped,
            }
            logger.info(f"🔗 一鍵連接完成：直接連上 {_ok}、救援成功 {_rescued}、失敗 {len(_fail)}（共 {len(_targets)}）")
            time.sleep(0.3)
            st.rerun()

    with col4:
        if st.button("☀️ 防止休眠", key="btn_no_sleep", use_container_width=True,
                     help="對目前連得上的設備套用防休眠設定。Quest 一旦真正休眠，adbd 會停止且"
                          "無法遠端喚醒（不支援 Wake-on-LAN），所以只能事先預防。需趁設備醒著時執行。"):
            st.session_state.no_sleep_requested = True

    # 防休眠結果（執行後 rerun，訊息先存 session_state）
    _ns = st.session_state.pop('no_sleep_result', None)
    if _ns:
        if _ns['total'] == 0:
            st.warning("⚠️ 目前沒有連得上的設備，無法套用防休眠設定。\n\n"
                       "Quest 一旦休眠，adbd 會整個停止且不支援 Wake-on-LAN，遠端無法喚醒——"
                       "所以防休眠只能趁設備醒著（戴上頭盔或剛開機）時先設定好。")
        elif _ns['fail']:
            st.warning(f"⚠️ 防休眠設定：成功 {_ns['ok']}/{_ns['total']} 台，失敗 {len(_ns['fail'])} 台")
            with st.expander(f"查看失敗的 {len(_ns['fail'])} 台", expanded=False):
                for _n, _m in _ns['fail']:
                    st.text(f"• {_n}：{_m}")
        elif _ns['ok']:
            st.success(f"✅ 已對 {_ns['ok']} 台套用防休眠設定")
        if _ns.get('offline'):
            st.caption(f"（略過 {_ns['offline']} 台目前連不上的設備——防休眠只能趁設備醒著時設定）")

    with col5:
        if st.button("📦 安裝 helper", key="btn_install_helper", use_container_width=True,
                     help="對 USB 接著或無線連得上的設備安裝無線 ADB helper 並授權。"
                          "USB 接著的會一併開啟 5555 與無線偵錯。"):
            st.session_state.install_helper_requested = True

    # 安裝 helper 的結果
    _ih = st.session_state.pop('install_helper_result', None)
    if _ih:
        if _ih['total'] == 0:
            st.warning("⚠️ 沒有可設定的設備。請用 USB 接上一台（頭盔裡要按過「允許 USB 偵錯」），"
                       "或先讓設備無線連上。")
        elif _ih['fail']:
            st.warning(f"⚠️ 安裝 helper：成功 {_ih['ok']}/{_ih['total']} 台，失敗 {len(_ih['fail'])} 台")
            with st.expander(f"查看失敗的 {len(_ih['fail'])} 台", expanded=False):
                for _n, _m in _ih['fail']:
                    st.text(f"• {_n}：{_m}")
        else:
            st.success(f"✅ 已對 {_ih['ok']} 台安裝 helper 並授權")
        if _ih.get('detail'):
            with st.expander("查看每台詳細結果", expanded=False):
                for _line in _ih['detail']:
                    st.text(_line)
        if _ih.get('need_headset'):
            st.info("💡 有 " + str(len(_ih['need_headset'])) + " 台的「無線偵錯」被系統擋下（"
                    + "、".join(_ih['need_headset']) + "）。\n\n"
                    "這代表該台還沒信任目前這個 Wi-Fi。請戴上頭盔（螢幕要亮）→ 應用程式庫 → "
                    "篩選「未知來源」→ 開啟 Oculus Wireless ADB → 按「允許」並勾「一律允許」。\n\n"
                    "做完之後，該台重開機才能靠「一鍵連接」自動恢復，否則仍需接 USB。")

    # 執行安裝 helper
    if st.session_state.pop('install_helper_requested', False):
        from pathlib import Path as _Path
        _adb_h = st.session_state.adb_manager
        _apk = str(_Path(__file__).resolve().parent.parent / "data" / "helper"
                   / "tdg.oculuswirelessadb-1.3.apk")

        # USB 接著的（serial 不含冒號）+ 無線連得上的，都納入
        _devs = _adb_h.get_devices(use_cache=False)
        _usb = [d['serial'] for d in _devs if d.get('state') == 'device' and ':' not in d.get('serial', '')]
        _wifi = [d['serial'] for d in _devs if d.get('state') == 'device' and ':' in d.get('serial', '')]
        _unauth = [d['serial'] for d in _devs if d.get('state') == 'unauthorized']
        _all_t = _usb + _wifi

        if not _all_t:
            _msg = []
            if _unauth:
                _msg.append(f"有 {len(_unauth)} 台 USB 設備未授權，請戴上頭盔按「允許 USB 偵錯」")
            st.session_state.install_helper_result = {
                'ok': 0, 'total': 0, 'fail': [], 'detail': _msg, 'need_headset': []}
        else:
            _ihp = st.progress(0.0, text=f"對 {len(_all_t)} 台安裝 helper…")
            _ih_ok, _ih_fail, _detail, _need_hs = 0, [], [], []
            for _i, _t in enumerate(_all_t):
                _is_usb = ':' not in _t
                _label = _t
                try:
                    _r_ok, _r_msg = _adb_h.install_wireless_helper(_t, _apk)
                    if _r_ok:
                        _ih_ok += 1
                        _line = f"{_label}：{_r_msg}"
                        # 順便開無線偵錯（USB 的再開 5555）
                        _w_ok, _w_msg = _adb_h.ensure_wireless_debugging(_t)
                        _line += f"｜無線偵錯：{'✅' if _w_ok else '❌'}"
                        if not _w_ok:
                            _need_hs.append(_label)
                        if _is_usb:
                            _adb_h.enable_tcpip(_t, ADB_DEFAULT_PORT)
                            _line += "｜已開 5555"
                        _detail.append(_line)
                    else:
                        _ih_fail.append((_label, _r_msg))
                except Exception as _e:
                    _ih_fail.append((_label, f"例外：{_e}"))
                try:
                    _ihp.progress((_i + 1) / len(_all_t))
                except Exception:
                    pass
            _ihp.empty()
            if _unauth:
                _detail.append(f"⚠️ 另有 {len(_unauth)} 台 USB 未授權（{', '.join(_unauth)}），"
                               "請戴上頭盔按「允許 USB 偵錯」")
            st.session_state.install_helper_result = {
                'ok': _ih_ok, 'total': len(_all_t), 'fail': _ih_fail,
                'detail': _detail, 'need_headset': _need_hs}
            logger.info(f"📦 安裝 helper：成功 {_ih_ok}/{len(_all_t)}")
        time.sleep(0.3)
        st.rerun()

    # 執行防休眠：只對 adb 狀態為 device 的設備套用
    if st.session_state.pop('no_sleep_requested', False):
        _adb_m = st.session_state.adb_manager
        _all_ns = st.session_state.device_registry.get_all_devices()
        _live_ns = {d.get('serial') for d in _adb_m.get_devices(use_cache=False)
                    if d.get('state') == 'device'}
        _reachable = [d for d in _all_ns if d.connection_string in _live_ns]
        _unreachable = len(_all_ns) - len(_reachable)

        if not _reachable:
            st.session_state.no_sleep_result = {
                'ok': 0, 'total': 0, 'fail': [], 'offline': _unreachable}
            st.warning("⚠️ 目前沒有連得上的設備。防休眠設定必須趁設備醒著時套用——"
                       "Quest 休眠後 adbd 會停止，無法遠端操作。")
        else:
            _nsp = st.progress(0.0, text=f"對 {len(_reachable)} 台套用防休眠設定…")
            _ns_ok, _ns_fail = 0, []
            for _i, _d in enumerate(_reachable):
                try:
                    _r_ok, _r_msg = _adb_m.prevent_sleep(_d.connection_string)
                except Exception as _e:
                    _r_ok, _r_msg = False, f"例外：{_e}"
                if _r_ok:
                    _ns_ok += 1
                else:
                    _ns_fail.append((_d.display_name, _r_msg[:150]))
                try:
                    _nsp.progress((_i + 1) / len(_reachable))
                except Exception:
                    pass
            _nsp.empty()
            st.session_state.no_sleep_result = {
                'ok': _ns_ok, 'total': len(_reachable),
                'fail': _ns_fail, 'offline': _unreachable}
            logger.info(f"☀️ 防休眠：成功 {_ns_ok}/{len(_reachable)}")
        time.sleep(0.3)
        st.rerun()





    
    # 對話框：手動新增設備
    if st.session_state.get('show_add_device_dialog', False):
        show_add_device_dialog()
        st.stop()
    
    # 取得所有設備
    devices = st.session_state.device_registry.get_all_devices()
    
    # 先按排序順序排列設備
    devices.sort(key=lambda d: d.sort_order)
    
    # 處理設備移動操作
    moved = False
    for device in devices:
        # 向上移動
        if st.session_state.get(f'move_up_{device.device_id}', False):
            current_index = devices.index(device)
            logger.info(f"⬆️ 嘗試向上移動: {device.display_name} (當前位置: {current_index}, sort_order: {device.sort_order})")
            
            if current_index > 0:
                # 交換排序順序
                prev_device = devices[current_index - 1]
                logger.info(f"   交換對象: {prev_device.display_name} (sort_order: {prev_device.sort_order})")
                
                device.sort_order, prev_device.sort_order = prev_device.sort_order, device.sort_order
                
                st.session_state.device_registry.save_device(device)
                st.session_state.device_registry.save_device(prev_device)
                
                st.session_state.device_registry.reorder_devices()
                
                logger.info(f"✅ 移動成功: {device.display_name} (新 sort_order: {device.sort_order})")
                moved = True
            else:
                logger.info(f"   已在最頂部，無法向上移動")
            
            st.session_state[f'move_up_{device.device_id}'] = False
            if moved:
                st.rerun()
        
        # 向下移動
        if st.session_state.get(f'move_down_{device.device_id}', False):
            current_index = devices.index(device)
            logger.info(f"⬇️ 嘗試向下移動: {device.display_name} (當前位置: {current_index}, sort_order: {device.sort_order})")
            
            if current_index < len(devices) - 1:
                # 交換排序順序
                next_device = devices[current_index + 1]
                logger.info(f"   交換對象: {next_device.display_name} (sort_order: {next_device.sort_order})")
                
                device.sort_order, next_device.sort_order = next_device.sort_order, device.sort_order
                
                st.session_state.device_registry.save_device(device)
                st.session_state.device_registry.save_device(next_device)
                
                st.session_state.device_registry.reorder_devices()
                
                logger.info(f"✅ 移動成功: {device.display_name} (新 sort_order: {device.sort_order})")
                moved = True
            else:
                logger.info(f"   已在最底部，無法向下移動")
            
            st.session_state[f'move_down_{device.device_id}'] = False
            if moved:
                st.rerun()
    
        # 自動同步設備在線狀態
        if devices:
            adb_devices = st.session_state.adb_manager.get_devices()
            adb_device_map = {d['serial']: d['state'] for d in adb_devices}
            logger.debug(f"🔍 ADB 設備列表: {list(adb_device_map.keys())}")
            
            # 同步狀態並批量獲取設備詳細資訊
            devices_to_update = []  # 收集需要更新狀態的設備
            devices_to_save = set()  # 收集需要保存的設備（使用 set 去重）
            st.session_state.devices_for_network_check = []  # 收集需要網路監控檢查的設備
            
            # 首先檢查並應用之前已完成的 Ping 結果（不阻塞）
            if 'ping_service' in st.session_state:
                ping_service = st.session_state.ping_service
                if 'auto_connect_manager' in st.session_state:
                    retry_manager = st.session_state.auto_connect_manager
                else:
                    retry_manager = None
                
                # 非阻塞檢查並應用結果
                ping_updated_devices = ping_service.check_and_apply_results(devices, retry_manager)
                if ping_updated_devices:
                    logger.debug(f"📡 應用 {len(ping_updated_devices)} 台設備的 Ping 結果")
                    for device in ping_updated_devices:
                        devices_to_save.add(device.device_id)
        
        for device in devices:
            # 構建可能的連接字串
            possible_serials = [device.serial]
            if device.ip:
                possible_serials.append(f"{device.ip}:{device.port}")
            
            # 查找設備在 adb devices 中的狀態
            adb_state = None
            matched_serial = None
            for serial in possible_serials:
                if serial in adb_device_map:
                    adb_state = adb_device_map[serial]
                    matched_serial = serial
                    break
            
            # 根據 ADB 狀態更新設備狀態
            new_status = None
            if adb_state == "device":
                # 在列表中且狀態為 device → ONLINE
                new_status = DeviceStatus.ONLINE
                if device.status != DeviceStatus.ONLINE:
                    logger.info(f"✅ 自動標記為在線: {device.display_name} (ADB state: device)")
                    device.status = DeviceStatus.ONLINE
                    device.last_seen = datetime.now()
                    devices_to_save.add(device.device_id)
                    
                    # 設備重新上線，重置自動連接重試次數
                    if 'auto_connect_manager' in st.session_state:
                        st.session_state.auto_connect_manager.reset_retry_count(device.device_id)
                        logger.debug(f"重置設備 {device.display_name} 的自動連接重試次數")
            elif adb_state == "offline":
                # 在列表中但狀態為 offline → OFFLINE
                new_status = DeviceStatus.OFFLINE
                if device.status != DeviceStatus.OFFLINE:
                    logger.info(f"🟠 自動標記為離線: {device.display_name} (ADB state: offline)")
                    device.status = DeviceStatus.OFFLINE
                    devices_to_save.add(device.device_id)
            else:
                # 不在列表中 → 需要檢查網路監控
                new_status = DeviceStatus.NOT_CONNECTED
                if device.status != DeviceStatus.NOT_CONNECTED:
                    logger.info(f"⚫ 自動標記為未連接: {device.display_name} (不在 ADB 列表中)")
                    device.status = DeviceStatus.NOT_CONNECTED
                    devices_to_save.add(device.device_id)
            
            # 收集需要網路監控檢查的設備
            if device.status == DeviceStatus.NOT_CONNECTED or device.status == DeviceStatus.ADB_NOT_ENABLED:
                devices_for_network_check = getattr(st.session_state, 'devices_for_network_check', [])
                devices_for_network_check.append(device)
                st.session_state.devices_for_network_check = devices_for_network_check
            
            if device.status == DeviceStatus.ONLINE:
                should_update = True
                if 'device_status_last_fetch' not in st.session_state:
                    st.session_state.device_status_last_fetch = {}
                
                last_fetch = st.session_state.device_status_last_fetch.get(device.device_id)
                if last_fetch:
                    time_since_fetch = (datetime.now() - last_fetch).total_seconds()
                    should_update = time_since_fetch > 10
                
                if should_update:
                    devices_to_update.append(device)
        
        if devices_to_update:
            device_list = [device.connection_string for device in devices_to_update]
            status_dict = st.session_state.adb_manager.get_status_batch(device_list)
            
            # 更新每個設備的狀態
            for device in devices_to_update:
                connection_str = device.connection_string
                device_status = status_dict.get(connection_str)
                
                if device_status:
                    try:
                        # 記錄這次查詢時間
                        st.session_state.device_status_last_fetch[device.device_id] = datetime.now()
                        
                        # 更新設備資訊
                        if device_status['battery'] > 0:
                            device.battery = device_status['battery']
                            device.temperature = device_status['temperature']
                            device.is_charging = device_status['is_charging']
                            devices_to_save.add(device.device_id)  # 記錄需要保存的設備
                            
                            if 'device_extra_status' not in st.session_state:
                                st.session_state.device_extra_status = {}
                            
                            st.session_state.device_extra_status[device.device_id] = {
                                'is_awake': device_status['is_awake'],
                                'is_screen_on': device_status['is_screen_on'],
                                'uptime': device_status['uptime'],
                                'last_update': datetime.now()
                            }
                            
                            if st.session_state.get(f'device_status_error_{device.device_id}'):
                                st.session_state[f'device_status_error_{device.device_id}'] = False
                    except Exception as e:
                        if not st.session_state.get(f'device_status_error_{device.device_id}'):
                            logger.warning(f"⚠️ 更新設備狀態失敗: {device.display_name} - {e}")
                            st.session_state[f'device_status_error_{device.device_id}'] = True
        
        # 網路監控和自動連接檢查
        devices_for_network_check = getattr(st.session_state, 'devices_for_network_check', [])
        if devices_for_network_check:
            user_config = get_user_config()
            network_config = user_config.get('network_monitoring', {})
            
            if network_config.get('enabled', True):
                # 過濾需要 Ping 的設備
                ping_targets = network_config.get('ping_targets', {})
                devices_to_ping = []
                
                for device in devices_for_network_check:
                    should_ping = False
                    
                    if device.status == DeviceStatus.NOT_CONNECTED or device.status == DeviceStatus.ADB_NOT_ENABLED:
                        should_ping = ping_targets.get('only_not_connected', True)
                    elif ping_targets.get('all_devices', False):
                        should_ping = True
                    
                    if should_ping and device.connection_type == ConnectionType.WIFI and device.ip:
                        # 檢查上次 Ping 時間
                        ping_last_check_key = f'ping_last_check_{device.device_id}'
                        ping_interval = network_config.get('ping_interval', 10)
                        
                        last_check = st.session_state.get(ping_last_check_key)
                        if last_check:
                            time_since = (datetime.now() - last_check).total_seconds()
                            if time_since < ping_interval:
                                continue
                        
                        devices_to_ping.append(device)
                
                if devices_to_ping:
                    # 初始化重試管理器和 Ping 服務
                    if 'auto_connect_manager' not in st.session_state:
                        st.session_state.auto_connect_manager = AutoConnectManager(st.session_state)
                    
                    if 'ping_service' not in st.session_state:
                        st.session_state.ping_service = PingService(
                            st.session_state,
                            st.session_state.adb_manager
                        )
                    
                    retry_manager = st.session_state.auto_connect_manager
                    ping_service = st.session_state.ping_service
                    
                    # 提交 Ping 任務到後台執行（非阻塞）
                    ping_service.submit_ping_tasks(devices_to_ping, network_config, retry_manager)
                    logger.debug(f"📡 已提交 {len(devices_to_ping)} 台設備的 Ping 任務（後台執行）")
                    
                    # 檢查並應用已完成的 Ping 結果（非阻塞檢查）
                    updated_devices = ping_service.check_and_apply_results(devices_to_ping, retry_manager)
                    for device in updated_devices:
                        devices_to_save.add(device.device_id)
                    
                    # 清理過期的結果
                    ping_service.cleanup_old_results(max_age_seconds=60)
                
                # 清除收集的設備列表
                st.session_state.devices_for_network_check = []
        
        if devices_to_save:
            device_map = {d.device_id: d for d in devices}
            for device_id in devices_to_save:
                device = device_map.get(device_id)
                if device:
                    st.session_state.device_registry.save_device(device)
            
            devices = st.session_state.device_registry.get_all_devices()
    
    # 處理編輯設備對話框
    for device in devices:
        if st.session_state.get(f'edit_device_{device.device_id}', False):
            edit_device_dialog(device)
            st.stop()
    
    # 處理執行動作對話框
    for device in devices:
        if st.session_state.get(f'execute_action_on_{device.device_id}', False):
            execute_action_dialog(device)
            st.stop()
    
    # 處理移除設備對話框
    for device in devices:
        if st.session_state.get(f'confirm_remove_{device.device_id}', False):
            confirm_remove_device(device)
            st.stop()
    
    if not devices:
        st.info("📱 尚無設備，請點擊「新增設備」來連接 Quest 設備")
        return
    
    # 統計資訊
    online_count = len([d for d in devices if d.is_online])
    st.markdown(f"**設備總數：{len(devices)} | 在線：{online_count} | 離線：{len(devices) - online_count}**")
    
    st.markdown("---")
    
    # 響應式網格佈局（每行 3 個卡片）
    cols_per_row = 3
    for i in range(0, len(devices), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, device in enumerate(devices[i:i+cols_per_row]):
            with cols[j]:
                render_device_card(device)
                st.markdown("---")


if __name__ == "__main__":
    main()
