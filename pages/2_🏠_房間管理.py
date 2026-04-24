"""
房間管理頁面
"""
import streamlit as st
from typing import Optional
import time
import json
import re
from datetime import datetime
from components.control_panel_cards import (
    inject_control_panel_card_styles,
    themed_card_key,
)
from core.room import Room
from core.room_registry import RoomRegistry
from config.constants import DeviceStatus, STATUS_ICONS
from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GAME_PACKAGE = "com.Awespire.OrientalBeauty"
STATUS_TABLE_ROW_HEIGHT = 42
USER_POSITION_SYNC_CHAPTER = 5

# 頁面配置
st.set_page_config(
    page_title="房間管理 - QQQuest",
    page_icon="🏠",
    layout="wide"
)

# 自定義 CSS 樣式
st.markdown("""
    <style>
    /* 強調灰色背景區塊 */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.highlight-gray-bg) {
        background-color: #33363d !important;
        border-color: #666 !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.highlight-gray-bg) * {
        color: #f8f9fa !important;
    }


    /* 隱藏標題旁的錨點鏈接圖標 */
    a.st-emotion-cache-yinll1,
    a[class*="st-emotion-cache"][href^="#"] {
        display: none !important;
    }
    
    /* 統一房間卡片和設備卡片高度和對齊 */
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
        height: 100%;
        min-height: 320px;
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
    
    /* 房間卡片中的按鈕允許換行，避免長名稱被截斷 */
    [data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stBaseButton-secondary"] {
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        height: auto !important;
        min-height: 2.5rem !important;
        line-height: 1.4 !important;
    }
    
    [data-testid="stVerticalBlockBorderWrapper"] button[data-testid="stBaseButton-secondary"] > div {
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""
    <style>
    div[data-testid="column"]:has(.resume-game-action-column) div[data-testid="stVerticalBlock"] {{
        gap: 0 !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stVerticalBlock"] {{
        gap: 0 !important;
    }}

    div[data-testid="column"]:has(.resume-game-action-column) div[data-testid="stButton"] {{
        min-height: {STATUS_TABLE_ROW_HEIGHT}px !important;
        height: {STATUS_TABLE_ROW_HEIGHT}px !important;
        display: flex !important;
        align-items: center !important;
        margin: 0 !important;
    }}

    div[data-testid="column"]:has(.resume-game-action-column) div[data-testid="stButton"] button {{
        width: 100% !important;
        max-width: 96px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        min-height: 28px !important;
        height: 28px !important;
        padding: 0 0.45rem !important;
        line-height: 1 !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stForm"] {{
        border: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: {STATUS_TABLE_ROW_HEIGHT}px !important;
        height: {STATUS_TABLE_ROW_HEIGHT}px !important;
        display: flex !important;
        align-items: center !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stForm"] form {{
        border: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
        background: transparent !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stNumberInput"] {{
        margin: 0 !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stNumberInput"] input {{
        text-align: right !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stFormSubmitButton"] {{
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stFormSubmitButton"] button {{
        width: 100% !important;
        min-height: 28px !important;
        height: 28px !important;
        padding: 0 0.45rem !important;
        line-height: 1 !important;
        background-color: var(--primary-color, #1f77ff) !important;
        border-color: var(--primary-color, #1f77ff) !important;
        color: #ffffff !important;
    }}

    div[data-testid="column"]:has(.position-adjust-column) div[data-testid="stFormSubmitButton"] button:hover {{
        filter: brightness(0.96);
    }}

    .resume-game-action-header {{
        min-height: 35px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        box-sizing: border-box;
    }}

    .position-adjust-header {{
        min-height: 35px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        box-sizing: border-box;
    }}

    .position-bulk-controls {{
        margin-bottom: 0.5rem;
    }}

    .position-bulk-aligner {{
        height: 1.9rem;
    }}

    .resume-alert-marker-header {{
        min-height: 35px;
        height: 35px;
    }}

    .resume-alert-marker-wrap {{
        min-height: {STATUS_TABLE_ROW_HEIGHT}px;
        height: {STATUS_TABLE_ROW_HEIGHT}px;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .resume-alert-marker {{
        width: 8px;
        height: 28px;
        border-radius: 4px;
        background-color: transparent;
        display: inline-block;
    }}

    .resume-alert-marker.is-active {{
        background-color: #d92d20;
    }}
    </style>
""", unsafe_allow_html=True)

inject_control_panel_card_styles()

# 初始化系統
from utils.init import init_all, ensure_room_registry, ensure_socket_server_manager

if not init_all():
    st.stop()

# 確保房間註冊管理器已初始化（雙重檢查）
ensure_room_registry()

# 確保 Socket Server 管理器已初始化
ensure_socket_server_manager()

# Session state 初始化
if 'show_add_room_dialog' not in st.session_state:
    st.session_state.show_add_room_dialog = False


def reopen_room_view(room_id: Optional[str]):
    """重新打開指定房間視圖，讓操作完成後停留在該房間。"""
    if room_id:
        st.session_state[f'show_room_view_{room_id}'] = True


def close_room_execute_action_dialog(room_id: str, reopen_view: bool = True):
    """關閉房間批量執行動作對話框，可選擇回到房間視圖。"""
    st.session_state[f'show_execute_action_room_{room_id}'] = False
    if reopen_view:
        reopen_room_view(room_id)


def close_device_execute_action_dialog(device_id: str, room: Optional[Room] = None):
    """關閉設備執行動作對話框，若有房間上下文則回到該房間。"""
    st.session_state[f'execute_action_on_{device_id}'] = False
    st.session_state.pop(f'execute_action_room_{device_id}', None)
    if room:
        reopen_room_view(room.room_id)


def start_room_device_monitor(
    device,
    room: Optional[Room] = None,
    layout_slot: Optional[int] = None,
    layout_total: Optional[int] = None
):
    """啟動房間設備監看，統一使用 Quest 單眼畫面與自動排版。"""
    room_name = room.name if room else "QQQuest"
    scrcpy_options = {}
    if layout_slot is not None:
        scrcpy_options['layout_slot'] = layout_slot
    if layout_total is not None:
        scrcpy_options['layout_total'] = layout_total

    return st.session_state.adb_manager.start_quest_single_eye_scrcpy(
        device.connection_string,
        window_title=f"{device.display_name} - {room_name}",
        options=scrcpy_options or None,
        auto_arrange=True
    )


def extract_current_time_from_message(message: str) -> str:
    """從 heartbeat 訊息中提取 `MM:SS` 格式的當前時間。"""
    if not isinstance(message, str):
        return ""

    cleaned_message = message.strip()
    if not cleaned_message:
        return ""

    # 支援一般格式 `03:19|15:53`，也支援 debug JSON 內嵌的 `"message":"03:19|15:53"`.
    match = re.search(r"\b(\d{1,2}:\d{2})(?:\|\d{1,2}:\d{2})?\b", cleaned_message)
    if match:
        return match.group(1)

    # 若是 debug heartbeat 字串但沒有完整時間，避免把整段 JSON 顯示到表格。
    if cleaned_message.startswith("[TCP] Send HB:"):
        return ""

    return cleaned_message


def coerce_optional_float(value) -> Optional[float]:
    """將任意值轉成 float，失敗則回傳 None。"""
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def sync_user_position_input_state(room_id: str, device_id: str, current_z: Optional[float]) -> str:
    """同步每台設備的位置輸入框，避免表格刷新時覆蓋掉使用者剛輸入的值。"""
    input_key = f"user_position_input_{room_id}_{device_id}"
    source_key = f"user_position_source_{room_id}_{device_id}"

    if input_key not in st.session_state:
        st.session_state[input_key] = current_z if current_z is not None else 0.0
        st.session_state[source_key] = current_z
        return input_key

    previous_source = coerce_optional_float(st.session_state.get(source_key))
    current_input = coerce_optional_float(st.session_state.get(input_key))

    if current_z is not None:
        is_synced_with_source = (
            current_input is None or
            previous_source is None or
            abs(current_input - previous_source) < 1e-6
        )
        if is_synced_with_source:
            st.session_state[input_key] = current_z

    st.session_state[source_key] = current_z
    return input_key


def send_user_position_adjust_command(room: Room, device_id: str, new_z: float):
    """發送單台設備的使用者位置 z 值調整指令。"""
    from core.socket_client import SocketClient

    save_success, save_message = save_room_user_position_and_sync(room, new_z, apply_now=False)
    if not save_success:
        return False, save_message

    payload = {
        "message_type": "user_position_adjust",
        "user_position_adjust": {
            "device_id": device_id,
            "z": float(new_z),
            "timestamp": int(time.time() * 1000)
        }
    }

    try:
        with SocketClient(room.socket_ip, room.socket_port) as client:
            success, response = client.send_command(
                "admin_unicast",
                {
                    "target_device_id": device_id,
                    "data": payload
                }
            )
    except Exception as exc:
        return False, str(exc)

    if not success:
        return False, response.get("message", "送出位置調整失敗")

    if response.get("success") is False:
        return False, response.get("message", "目標設備未連線")

    return True, f"{save_message}，{response.get('message', '已送出位置調整指令')}"


def sync_room_user_position_input_state(room: Room) -> str:
    """同步房間層級的共用 z 值輸入框。"""
    input_key = f"room_user_position_input_{room.room_id}"
    source_key = f"room_user_position_source_{room.room_id}"

    saved_z = coerce_optional_float(getattr(room, "saved_user_position_z", None))
    status_data = st.session_state.get(f"realtime_status_data_{room.room_id}", [])

    if saved_z is None:
        for row_data in status_data:
            current_z = coerce_optional_float(row_data.get("user_position_z"))
            if current_z is not None:
                saved_z = current_z
                break

    if input_key not in st.session_state:
        st.session_state[input_key] = saved_z if saved_z is not None else 0.0
        st.session_state[source_key] = saved_z
        return input_key

    previous_source = coerce_optional_float(st.session_state.get(source_key))
    current_input = coerce_optional_float(st.session_state.get(input_key))

    if saved_z is not None:
        is_synced_with_source = (
            current_input is None or
            previous_source is None or
            abs(current_input - previous_source) < 1e-6
        )
        if is_synced_with_source:
            st.session_state[input_key] = saved_z

    st.session_state[source_key] = saved_z
    return input_key


def persist_room_user_position_z(room: Room, new_z: float):
    """把房間的共用 z 值記錄到本地資料庫。"""
    normalized_z = float(new_z)
    room.saved_user_position_z = normalized_z
    if not st.session_state.room_registry.update_room(room):
        return False, "儲存房間位置設定失敗"
    return True, "已儲存房間位置設定"


def sync_room_user_position_target(room: Room, new_z: float, apply_now: bool):
    """同步房間記憶的 z 值到正在運行的 room socket server。"""
    from core.socket_client import SocketClient

    if not room.socket_ip or not room.socket_port:
        return False, "房間未設定 Socket Server"

    try:
        with SocketClient(room.socket_ip, room.socket_port) as client:
            success, response = client.send_command(
                "set_user_position_target",
                {
                    "z": float(new_z),
                    "apply_now": apply_now
                }
            )
    except Exception as exc:
        return False, str(exc)

    if not success:
        return False, response.get("message", "同步房間位置設定失敗")

    if response.get("success") is False:
        return False, response.get("message", "同步房間位置設定失敗")

    return True, response.get("message", "已同步房間位置設定")


def save_room_user_position_and_sync(room: Room, new_z: float, apply_now: bool):
    """先儲存本地 z 值，再同步到 server。"""
    persist_success, persist_message = persist_room_user_position_z(room, new_z)
    if not persist_success:
        return False, persist_message

    if not room.socket_ip or not room.socket_port:
        return True, f"{persist_message}，房間尚未啟動 Socket Server"

    sync_success, sync_message = sync_room_user_position_target(room, new_z, apply_now=apply_now)
    if sync_success:
        return True, sync_message

    return False, f"{persist_message}，但同步到 Socket Server 失敗: {sync_message}"


def render_room_user_position_bulk_controls(room: Room):
    """渲染房間層級的共用 z 值與批量調整按鈕。"""
    input_key = sync_room_user_position_input_state(room)
    saved_z = coerce_optional_float(getattr(room, "saved_user_position_z", None))

    st.markdown('<div class="position-bulk-controls"></div>', unsafe_allow_html=True)
    value_col, action_col, info_col = st.columns([1.1, 1.05, 2.85])

    with value_col:
        st.number_input(
            "使用者位置",
            key=input_key,
            step=0.1,
            format="%.3f",
            help="會存成這個房間的預設 z 值"
        )

    with action_col:
        st.markdown('<div class="position-bulk-aligner"></div>', unsafe_allow_html=True)
        if st.button(
            "批量修改位置",
            key=f"bulk_adjust_user_position_{room.room_id}",
            type="primary",
            width="stretch"
        ):
            target_z = coerce_optional_float(st.session_state.get(input_key))
            if target_z is None:
                st.error("共用 z 值格式無效")
            else:
                success_bulk, bulk_message = save_room_user_position_and_sync(room, target_z, apply_now=True)
                if success_bulk:
                    st.success(f"共用位置: {bulk_message}")
                else:
                    st.error(f"共用位置: {bulk_message}")

    with info_col:
        st.markdown('<div class="position-bulk-aligner"></div>', unsafe_allow_html=True)
        saved_label = f"{saved_z:.3f}" if saved_z is not None else "尚未儲存"
        st.caption(
            f"目前記憶位置 z：{saved_label}。批量修改會送到目前連線中的設備，之後 client 重新連線並回到 chapter 0，或再次進入 chapter 5 時，也會自動套用這個值。"
        )


@st.dialog("➕ 新增房間", width="large")
def add_room_dialog():
    """新增房間對話框"""
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
    
    st.subheader("📝 基本資訊")
    
    # 房間名稱
    name = st.text_input(
        "房間名稱 *",
        placeholder="例如：訓練室 A",
        help="為房間取一個容易識別的名稱",
        key="new_room_name"
    )
    
    # 房間描述
    description = st.text_area(
        "房間說明（選填）",
        placeholder="描述這個房間的用途...",
        height=80,
        key="new_room_description"
    )
    
    # 最大設備數量
    max_devices = st.number_input(
        "最大設備數量",
        min_value=0,
        max_value=100,
        value=0,
        help="0 表示無限制",
        key="new_room_max_devices"
    )
    
    if max_devices == 0:
        st.caption("💡 設為 0 表示此房間可容納無限數量的設備")
    else:
        st.caption(f"💡 此房間最多可容納 {max_devices} 台設備")
    
    st.markdown("---")
    st.subheader("🔌 Socket Server 設定（選填）")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        socket_ip = st.text_input(
            "Socket Server IP",
            placeholder="0.0.0.0 或 127.0.0.1",
            help="若要啟用 Socket Server 請輸入 IP",
            key="new_room_socket_ip"
        )
    with col_s2:
        socket_port = st.number_input(
            "Socket Server Port",
            min_value=1,
            max_value=65535,
            value=3000,
            key="new_room_socket_port"
        )
    
    if socket_ip:
        st.info(f"📡 Socket Server 將在啟動時監聽 {socket_ip}:{socket_port}")
    else:
        st.caption("💡 留空 IP 地址則不會啟動 Socket Server")

    st.markdown("---")
    
    # 按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 保存", type="primary", use_container_width=True, key="add_room_save"):
            # 驗證必填欄位
            if not name:
                st.error("❌ 請輸入房間名稱")
                return
            
            # 創建房間
            room = st.session_state.room_registry.create_room(
                name=name,
                description=description if description else None,
                max_devices=max_devices,
                socket_ip=socket_ip if socket_ip else None,
                socket_port=socket_port if socket_ip else None
            )
            
            if room:
                st.success(f"✅ 房間已創建：{room.display_name}")
                logger.info(f"✅ 創建房間成功: {room.display_name}")
                
                # 如果配置了 Socket Server，自動啟動
                if room.socket_ip and room.socket_port:
                    if 'socket_server_manager' in st.session_state:
                        socket_manager = st.session_state.socket_server_manager
                        success, msg = socket_manager.start_server(
                            room.room_id,
                            room.name,
                            room.socket_ip,
                            room.socket_port,
                            room.saved_user_position_z
                        )
                        if success:
                            st.info(f"📡 Socket Server 已啟動: {room.socket_ip}:{room.socket_port}")
                        else:
                            st.warning(f"⚠️ Socket Server 啟動失敗: {msg}")
                
                st.session_state.show_add_room_dialog = False
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 創建房間失敗（可能名稱已存在）")
    
    with col2:
        if st.button("❌ 取消", use_container_width=True, key="add_room_cancel"):
            st.session_state.show_add_room_dialog = False
            st.rerun()


@st.dialog("✏️ 編輯房間", width="large")
def edit_room_dialog(room: Room):
    """編輯房間對話框"""
    from core.room import Room, RoomParameter, RoomParameterType
    
    # 初始化緩衝區（如果尚未存在）
    buffer_key = f'room_buffer_{room.room_id}'
    if buffer_key not in st.session_state:
        # 使用 model_copy 創建副本，確保不直接修改原始對象（直到保存）
        st.session_state[buffer_key] = room.model_copy(deep=True)
    
    # 使用緩衝區對象進行所有操作
    room_buffer = st.session_state[buffer_key]
    
    # 隱藏對話框右上角的關閉按鈕
    st.markdown("""
        <style>


        button[kind="header"] { display: none !important; }
        button[aria-label="Close"] { display: none !important; }
        div[data-testid="stDialog"] button[kind="header"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------
    # 參數編輯子視圖
    # ---------------------------
    if f'editing_param_{room.room_id}' in st.session_state:
        param_idx = st.session_state[f'editing_param_{room.room_id}']
        
        # 標題
        if param_idx == -1:
            st.subheader("➕ 新增參數")
            # 初始化新參數（如果是第一次進入此狀態）
            if f'temp_param_{room.room_id}' not in st.session_state:
                st.session_state[f'temp_param_{room.room_id}'] = RoomParameter(
                    name="new_param",
                    value_type=RoomParameterType.STRING,
                    is_global=True,
                    global_value=""
                )
            current_param = st.session_state[f'temp_param_{room.room_id}']
        else:
            # 編輯現有參數 - 從 buffer 取值
            # 注意：這裡我們操作的是 room 對象中的引用，或者我們應該 clone 一份？
            # 為了避免未保存的修改影響原對象，我們應該 clone。
            # 但 Pydantic model copy 比較簡單。
            if f'temp_param_{room.room_id}' not in st.session_state:
                st.session_state[f'temp_param_{room.room_id}'] = room_buffer.parameters[param_idx].model_copy(deep=True)
            
            current_param = st.session_state[f'temp_param_{room.room_id}']
            st.subheader(f"✏️ 編輯參數: {current_param.name}")

        st.caption("設定傳遞給 Android 應用的 Intent 參數")
        st.markdown("---")

        # 編輯表單
        p_name = st.text_input("參數名稱", value=current_param.name, key=f"p_name_{room.room_id}")
        
        # 類型選擇
        type_options = [t.value for t in RoomParameterType]
        try:
            type_index = type_options.index(current_param.value_type)
        except ValueError:
            type_index = 0
            
        p_type_str = st.selectbox(
            "參數類型", 
            type_options, 
            index=type_index,
            key=f"p_type_{room.room_id}"
        )
        p_type = RoomParameterType(p_type_str)
        
        is_global = st.checkbox("設為全域參數 (所有設備使用相同值)", value=current_param.is_global, key=f"p_global_{room.room_id}")
        
        st.markdown("---")
        st.caption("參數值設定")
        
        # 輔助函數：根據類型渲染輸入框
        def render_input(label, current_value, key_suffix):
            k = f"val_{key_suffix}_{room.room_id}"
            
            if p_type == RoomParameterType.BOOLEAN:
                return st.checkbox(label, value=bool(current_value) if current_value is not None else False, key=k)
            elif p_type in [RoomParameterType.INTEGER, RoomParameterType.LONG]:
                return st.number_input(label, value=int(current_value) if current_value is not None else 0, key=k, step=1)
            elif p_type == RoomParameterType.FLOAT:
                return st.number_input(label, value=float(current_value) if current_value is not None else 0.0, key=k, format="%f")
            else:
                return st.text_input(label, value=str(current_value) if current_value is not None else "", key=k)

        new_global_value = current_param.global_value
        import copy
        new_device_values = copy.deepcopy(current_param.device_values)
        device_meta_map = {}

        if is_global:
            new_global_value = render_input("全域值", current_param.global_value, "global")
        else:
            st.info("請為房間內的設備設定參數值")
            # 獲取房間內設備
            registry_devices = st.session_state.device_registry.get_all_devices()
            room_devices = [d for d in registry_devices if d.device_id in room_buffer.device_ids]
            device_meta_map = {}
            for d in room_devices:
                device_num = d.alias or d.name
                if device_num:
                    device_meta_map[d.device_id] = {
                        "num": device_num,
                    }
            
            if not room_devices:
                st.warning("此房間內沒有設備")
            
            for dev in room_devices:
                dev_val = current_param.device_values.get(dev.device_id)
                # 若先前已存為 dict，拆出 value 與 rotation_value
                if isinstance(dev_val, dict):
                    existing_val = dev_val.get("value")
                    existing_rot = dev_val.get("rotation_value")
                else:
                    existing_val = dev_val
                    existing_rot = None
                
                new_val = render_input(f"{dev.display_name} ({dev.ip})", existing_val, f"dev_{dev.device_id}")
                # rotation 以文字輸入，讓用戶自由填 float 列表等格式
                rot_key = f"rot_{dev.device_id}_{room.room_id}"
                new_rot = st.text_input(
                    f"{dev.display_name} 旋轉(rotation) (Euler 列表)",
                    value=str(existing_rot) if existing_rot is not None else "",
                    key=rot_key,
                    placeholder="[0,30,0]"
                )
                
                # 保存成 dict，to_transport 會識別
                new_device_values[dev.device_id] = {
                    "value": new_val,
                    "rotation_value": new_rot if new_rot != "" else None
                }

        st.markdown("---")
        
        # 同步功能區塊
        st.markdown("##### 📤 即時同步")
        sync_col1, sync_col2 = st.columns([3, 1])
        with sync_col1:
            st.caption("將當前參數設定直接發送給 Node.js Server（無需保存）")
        with sync_col2:
            if st.button("🚀 發送", key=f"sync_param_{room.room_id}", help="發送當前參數至 Socket Server"):
                # 構建臨時參數對象用於發送
                live_param = current_param.model_copy(deep=True)
                live_param.name = p_name
                live_param.value_type = p_type
                live_param.is_global = is_global
                if is_global:
                    live_param.global_value = new_global_value
                    live_param.device_values = {}
                else:
                    live_param.global_value = None
                    live_param.device_values = new_device_values
                
                # 檢查 Socket Server 狀態 (使用原始 room 配置或 buffer? 通常是用已啟動的配置)
                # 我們應該檢查 room.socket_ip (已保存的) 是否有運行的服務器
                # 如果用戶改了 IP 但沒保存重啟，這裡發送會失敗，這是預期的。
                if room.socket_ip and room.socket_port:
                    from core.socket_client import SocketClient

                    try:
                        with SocketClient(room.socket_ip, room.socket_port) as client:
                            # 構建 payload
                            command_type = "send_params" # 重用協議，或者單獨定義 "update_param"?
                            # 用戶請求是 "send parameters"，可以是一個 list 包含單個 param
                            data = [live_param.to_transport(device_meta_map=device_meta_map)]
                            
                            success, response = client.send_command(command_type, data)
                            if success:
                                st.toast(f"✅ 參數 {live_param.name} 發送成功!", icon="🚀")
                            else:
                                st.error(f"❌ 發送失敗: {response.get('message', '未知錯誤')}")
                    except Exception as e:
                        st.error(f"❌ 連接失敗: {str(e)}")
                else:
                    st.warning("⚠️ 此房間尚未配置或啟動 Socket Server")

        st.markdown("---")
        col_a, col_b = st.columns(2)
        
        with col_a:
            if st.button("確認", type="primary", use_container_width=True, key=f"save_param_{room.room_id}"):
                # 更新 temp param
                current_param.name = p_name
                current_param.value_type = p_type
                current_param.is_global = is_global
                if is_global:
                    current_param.global_value = new_global_value
                    current_param.device_values = {}
                else:
                    current_param.global_value = None
                    current_param.device_values = new_device_values
                
                # 寫回 room_buffer 對象
                if param_idx == -1:
                    room_buffer.parameters.append(current_param)
                else:
                    room_buffer.parameters[param_idx] = current_param
                
                # 清理 state 並返回
                del st.session_state[f'editing_param_{room.room_id}']
                del st.session_state[f'temp_param_{room.room_id}']
                st.rerun()
        
        with col_b:
            if st.button("取消", use_container_width=True, key=f"cancel_param_{room.room_id}"):
                del st.session_state[f'editing_param_{room.room_id}']
                del st.session_state[f'temp_param_{room.room_id}']
                st.rerun()
        
        # 結束子視圖渲染
        return

    # ---------------------------
    # 主視圖：房間編輯
    # ---------------------------
    
    st.caption(f"房間 ID: {room_buffer.room_id}")
    st.markdown("---")
    
    st.subheader("📝 基本資訊")
    
    # 房間名稱
    name_key = f"edit_room_name_{room.room_id}"
    name = st.text_input(
        "房間名稱 *",
        value=room_buffer.name,
        help="為房間取一個容易識別的名稱",
        key=name_key
    )
    
    # 房間描述
    desc_key = f"edit_room_description_{room.room_id}"
    description = st.text_area(
        "房間說明（選填）",
        value=room_buffer.description if room_buffer.description else "",
        height=80,
        key=desc_key
    )
    
    # 最大設備數量
    max_dev_key = f"edit_room_max_devices_{room.room_id}"
    max_devices = st.number_input(
        "最大設備數量",
        min_value=0,
        max_value=100,
        value=room_buffer.max_devices,
        help="0 表示無限制",
        key=max_dev_key
    )
    
    # ... 容量提示 ...
    if max_devices == 0:
        st.caption("💡 設為 0 表示此房間可容納無限數量的設備")
    else:
        st.caption(f"💡 此房間最多可容納 {max_devices} 台設備")
        if room_buffer.device_count > max_devices:
            st.warning(f"⚠️ 當前房間有 {room_buffer.device_count} 台設備，超過新設定的上限！")
    
    st.markdown("---")
    st.subheader("🔌 Socket Server 設定（選填）")
    
    col1, col2 = st.columns(2)
    with col1:
        ip_key = f"edit_room_socket_ip_{room.room_id}"
        socket_ip = st.text_input(
            "Socket Server IP",
            value=room_buffer.socket_ip if room_buffer.socket_ip else "",
            placeholder="0.0.0.0 或 127.0.0.1",
            key=ip_key
        )
    with col2:
        port_key = f"edit_room_socket_port_{room.room_id}"
        socket_port = st.number_input(
            "Socket Server Port",
            min_value=1,
            max_value=65535,
            value=room_buffer.socket_port if room_buffer.socket_port else 3000,
            key=port_key
        )
    
    if socket_ip:
        st.info(f"📡 Socket Server 將在啟動時監聽 {socket_ip}:{socket_port}")
    else:
        st.caption("💡 留空 IP 地址則不會啟動 Socket Server")
    
    st.markdown("---")
    
    # --- 房間參數設定 ---
    st.subheader("⚙️ 房間參數設定")
    
    if not room_buffer.parameters:
        st.info("尚未設定任何參數")
    else:
        for i, param in enumerate(room_buffer.parameters):
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 2, 3, 2])
                with c1:
                    st.markdown(f"**{param.name}**")
                    st.caption(f"`{param.value_type}`")
                with c2:
                    st.markdown("🌐 全域" if param.is_global else "📱 個別設備")
                with c3:
                    if param.is_global:
                        st.code(str(param.global_value), language="text")
                    else:
                        st.caption(f"已設定 {len(param.device_values)} 台設備")
                with c4:
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        def on_edit_click(idx=i):
                            # 保存當前場景狀態到 buffer
                            room_buffer.name = st.session_state[name_key]
                            room_buffer.description = st.session_state[desc_key]
                            room_buffer.max_devices = st.session_state[max_dev_key]
                            room_buffer.socket_ip = st.session_state[ip_key]
                            room_buffer.socket_port = st.session_state[port_key]
                            st.session_state[f'editing_param_{room.room_id}'] = idx
                            
                        st.button("✏️", key=f"edit_param_{room.room_id}_{i}", on_click=on_edit_click)
                    with col_del:
                        if st.button("🗑️", key=f"del_param_{room.room_id}_{i}"):
                            room_buffer.parameters.pop(i)
                            st.rerun()
            st.markdown("---")

    # 新增參數按鈕
    def on_add_click():
        # 保存當前場景狀態
        room_buffer.name = st.session_state[name_key]
        room_buffer.description = st.session_state[desc_key]
        room_buffer.max_devices = st.session_state[max_dev_key]
        room_buffer.socket_ip = st.session_state[ip_key]
        room_buffer.socket_port = st.session_state[port_key]
        st.session_state[f'editing_param_{room.room_id}'] = -1
        
    st.button("➕ 新增參數", key=f"add_param_btn_{room.room_id}", on_click=on_add_click)
    
    st.markdown("---")
    
    # 底部按鈕
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 保存", type="primary", use_container_width=True, key=f"edit_room_save_{room.room_id}"):
            if not name:
                st.error("❌ 請輸入房間名稱")
            else:
                # 檢查名稱重複
                if name != room_buffer.name:
                    existing = st.session_state.room_registry.get_room_by_name(name)
                    # 確保不與他人重複（排除自己）
                    if existing and existing.room_id != room.room_id:
                        st.error("❌ 房間名稱已存在")
                        return 
                
                # 這裡的賦值其實已經在 widget binding 中完成了嗎？
                # 不，st.text_input(value=room.name) 只是初始值。
                # 我們需要手動獲取最新值，或者信賴 session_state 綁定
                # 這裡直接用 name 變數即可 (它包含最新輸入)
                
                old_socket_ip = room_buffer.socket_ip
                old_socket_port = room_buffer.socket_port
                
                room_buffer.name = name
                room_buffer.description = description if description else None
                room_buffer.max_devices = max_devices
                room_buffer.socket_ip = socket_ip if socket_ip else None
                room_buffer.socket_port = socket_port if socket_ip else None
                
                if st.session_state.room_registry.update_room(room_buffer):
                    st.success(f"✅ 房間已更新")
                    # Socket Server 重啟邏輯 (與之前相同)
                    # ... 略 ...
                    if (old_socket_ip != room_buffer.socket_ip or old_socket_port != room_buffer.socket_port):
                         if 'socket_server_manager' in st.session_state:
                            sm = st.session_state.socket_server_manager
                            if old_socket_ip: sm.stop_server(room.room_id)
                            if room_buffer.socket_ip: 
                                sm.start_server(
                                    room.room_id,
                                    room_buffer.name,
                                    room_buffer.socket_ip,
                                    room_buffer.socket_port,
                                    room_buffer.saved_user_position_z
                                )

                    st.session_state[f'edit_room_{room.room_id}'] = False
                    # 清除 buffer
                    if buffer_key in st.session_state:
                        del st.session_state[buffer_key]
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ 更新失敗")

    with col2:
        if st.button("❌ 取消", use_container_width=True, key=f"edit_room_cancel_{room.room_id}"):
            st.session_state[f'edit_room_{room.room_id}'] = False
            # 清除 buffer
            if buffer_key in st.session_state:
                del st.session_state[buffer_key]
            st.rerun()


@st.dialog("🗑️ 確認刪除房間", width="small")
def delete_room_dialog(room: Room):
    """刪除房間確認對話框"""
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
    
    st.warning(f"確定要刪除房間 **{room.display_name}** 嗎？")
    
    if room.device_count > 0:
        st.error(f"⚠️ 此房間內有 {room.device_count} 台設備")
        st.info("💡 刪除房間後，設備將不再屬於任何房間（但不會被刪除）")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("✅ 確定刪除", type="primary", use_container_width=True):
            # 停止 Socket Server（如果存在）
            if room.socket_ip and room.socket_port:
                if 'socket_server_manager' in st.session_state:
                    socket_manager = st.session_state.socket_server_manager
                    socket_manager.stop_server(room.room_id)
                    logger.info(f"🛑 已停止 Socket Server: {room.name}")
            
            # 刪除房間
            if st.session_state.room_registry.delete_room(room.room_id):
                st.success("✅ 房間已刪除")
                logger.info(f"🗑️ 刪除房間: {room.display_name}")
                st.session_state[f'delete_room_{room.room_id}'] = False
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 刪除失敗")
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state[f'delete_room_{room.room_id}'] = False
            st.rerun()


@st.dialog("➕ 管理設備", width="large")
def manage_devices_dialog(room: Room):
    """管理房間設備對話框"""
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
    
    st.subheader(f"📱 管理設備 - {room.display_name}")
    
    # 顯示房間容量
    if room.max_devices > 0:
        st.info(f"📊 房間容量：{room.capacity_text}（剩餘 {room.max_devices - room.device_count} 個名額）")
    else:
        st.info(f"📊 房間容量：{room.capacity_text}（無限制）")
    
    st.markdown("---")
    
    # 獲取所有設備並按排序順序排列
    all_devices = st.session_state.device_registry.get_all_devices()
    all_devices.sort(key=lambda d: d.sort_order)  # 按設備管理頁面的排序方式排序
    
    if not all_devices:
        st.warning("⚠️ 沒有可用的設備")
        if st.button("關閉"):
            st.session_state[f'show_manage_devices_{room.room_id}'] = False
            st.rerun()
        return
    
    st.markdown("**選擇要加入房間的設備**")
    st.caption("💡 已經在其他房間的設備，勾選後會自動轉移到此房間")
    
    # 創建設備選擇列表
    selected_devices = []
    
    for device in all_devices:
        # 檢查設備當前所在房間
        current_room = st.session_state.room_registry.get_device_room(device.device_id)
        
        # 預設勾選狀態（如果設備已在此房間）
        default_checked = (current_room and current_room.room_id == room.room_id)
        
        # 顯示設備信息
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # 構建標籤
            label = device.display_name
            if current_room:
                if current_room.room_id == room.room_id:
                    label += f" ✅ **（目前在此房間）**"
                else:
                    label += f" 📍 **（目前在：{current_room.name}）**"
            
            # 設備選擇框
            checked = st.checkbox(
                label,
                value=default_checked,
                key=f"device_select_{device.device_id}_{room.room_id}"
            )
            
            if checked:
                selected_devices.append((device, current_room))
        
        with col2:
            # 顯示設備狀態
            if device.is_online:
                st.caption("🟢 在線")
            else:
                st.caption("🔴 離線")
    
    st.markdown("---")
    
    # 按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 保存", type="primary", use_container_width=True):
            # 檢查容量
            if room.max_devices > 0 and len(selected_devices) > room.max_devices:
                st.error(f"❌ 選擇的設備數量（{len(selected_devices)}）超過房間上限（{room.max_devices}）")
                return
            
            # 處理設備變更
            success_count = 0
            transfer_count = 0
            
            # 移除未勾選的設備
            for device_id in room.device_ids.copy():
                if not any(d.device_id == device_id for d, _ in selected_devices):
                    success, msg = st.session_state.room_registry.remove_device_from_room(
                        room.room_id,
                        device_id
                    )
                    if success:
                        success_count += 1
            
            # 添加勾選的設備
            for device, current_room in selected_devices:
                if not room.has_device(device.device_id):
                    success, msg = st.session_state.room_registry.add_device_to_room(
                        room.room_id,
                        device.device_id
                    )
                    if success:
                        success_count += 1
                        if current_room and current_room.room_id != room.room_id:
                            transfer_count += 1
            
            if success_count > 0:
                msg_parts = [f"✅ 成功更新 {success_count} 台設備"]
                if transfer_count > 0:
                    msg_parts.append(f"（其中 {transfer_count} 台從其他房間轉移）")
                st.success(" ".join(msg_parts))
                logger.info(f"✅ 更新房間設備: {room.display_name}")
                time.sleep(1)
                st.session_state[f'show_manage_devices_{room.room_id}'] = False
                st.rerun()
            else:
                st.info("💡 沒有變更")
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state[f'show_manage_devices_{room.room_id}'] = False
            st.rerun()


@st.dialog("⚡ 執行動作", width="large")
def execute_action_on_room_dialog(room: Room):
    """在房間所有設備上執行動作對話框"""
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
    
    st.subheader(f"⚡ 批量執行動作 - {room.display_name}")
    
    # 獲取房間內設備
    room_devices = st.session_state.room_registry.get_room_devices(
        room.room_id,
        st.session_state.device_registry
    )
    
    # 按設備管理頁面的排序方式排序
    room_devices.sort(key=lambda d: d.sort_order)
    
    if not room_devices:
        st.warning("⚠️ 房間內沒有設備")
        if st.button("關閉"):
            close_room_execute_action_dialog(room.room_id)
            st.rerun()
        return
    
    # 顯示設備信息
    online_devices = [d for d in room_devices if d.status == DeviceStatus.ONLINE]
    offline_devices = [d for d in room_devices if d.status == DeviceStatus.OFFLINE]
    not_connected_devices = [d for d in room_devices if d.status == DeviceStatus.NOT_CONNECTED]
    
    st.info(f"📱 房間內設備：共 {len(room_devices)} 台（🟢 在線 {len(online_devices)} 台，🟠 離線 {len(offline_devices)} 台，⚫ 未連接 {len(not_connected_devices)} 台）")
    
    if not online_devices:
        st.warning("⚠️ 沒有在線設備，無法執行動作")
        if st.button("關閉"):
            close_room_execute_action_dialog(room.room_id)
            st.rerun()
        return
    
    st.caption("💡 動作將在所有在線設備上執行")
    
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
                close_room_execute_action_dialog(room.room_id)
                st.rerun()
        return
    
    # 動作選擇
    st.markdown("**選擇要執行的動作**")
    
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
    with st.expander("📋 動作詳情", expanded=False):
        st.markdown(f"**類型**: {selected_action.type_name}")
        if selected_action.params:
            st.markdown("**參數**:")
            for key, value in selected_action.params.items():
                if value:
                    st.text(f"  {key}: {value}")
    
    st.markdown("---")
    
    # 執行按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ 執行", type="primary", use_container_width=True):
            # 準備設備列表
            device_list = [device.connection_string for device in online_devices]
            
            # 創建進度顯示
            progress_placeholder = st.empty()
            progress_bar = st.progress(0)
            progress_text = st.empty()
            
            # 定義進度回調
            def update_progress(completed, total):
                progress = completed / total
                progress_bar.progress(progress)
                progress_text.text(f"🚀 執行進度：{completed}/{total} 台設備")
            
            with st.spinner("🚀 並發執行中..."):
                # 準備房間信息（如果房間配置了 Socket Server）
                # 準備房間信息
                room_info = {}
                
                # Socket Server 參數
                if room.socket_ip and room.socket_port:
                    room_info['socket_ip'] = room.socket_ip
                    room_info['socket_port'] = room.socket_port
                
                # 房間參數
                if room.parameters:
                    room_info['parameters'] = room.parameters
                    
                    # 建立 device connection_string -> device_id 的映射
                    # 這樣 ADB Manager 就能找到正確的設備 ID 來查詢參數
                    device_id_map = {d.connection_string: d.device_id for d in online_devices}
                    room_info['device_id_map'] = device_id_map
                
                # 準備設備參數映射
                # 即使沒有房間參數，我們也想發送 device_id/ip 給應用
                if 'device_id_map' not in room_info:
                     room_info['device_id_map'] = {d.connection_string: d.device_id for d in online_devices}
                
                # 構建 device_params_map (目前主要用於 IP)
                device_params_map = {}
                for d in online_devices:
                    device_params_map[d.connection_string] = {
                        'ip': d.ip,
                        'port': d.port
                    }
                room_info['device_params_map'] = device_params_map
                
                # 使用並發方法執行
                batch_results = st.session_state.adb_manager.execute_action_batch(
                    device_list,
                    selected_action,
                    progress_callback=update_progress,
                    room_info=room_info
                )
                
                # 處理結果
                success_count = 0
                fail_count = 0
                results = []
                
                for device_str, success, message in batch_results:
                    # 找到對應的設備對象
                    device = next((d for d in online_devices if d.connection_string == device_str), None)
                    device_name = device.display_name if device else device_str
                    
                    if success:
                        success_count += 1
                        results.append(f"✅ {device_name}: {message}")
                    else:
                        fail_count += 1
                        results.append(f"❌ {device_name}: {message}")
                
                # 清除進度顯示
                progress_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()
                
                # 更新動作統計
                selected_action.execution_count += len(online_devices)
                selected_action.success_count += success_count
                selected_action.failure_count += fail_count
                from datetime import datetime
                selected_action.last_executed_at = datetime.now()
                selected_action.last_execution_status = f"批量執行：成功 {success_count}/{len(online_devices)}"
                st.session_state.action_registry.update_action(selected_action)
                
                # 顯示結果
                st.markdown("### 執行結果")
                st.success(f"✅ 成功：{success_count} 台")
                if fail_count > 0:
                    st.error(f"❌ 失敗：{fail_count} 台")
                
                # 顯示詳細結果
                with st.expander("查看詳細結果"):
                    for result in results:
                        st.text(result)
                
                logger.info(f"⚡ 批量執行動作: {selected_action.display_name} -> {room.display_name} (成功: {success_count}, 失敗: {fail_count})")
                
                time.sleep(2)
                close_room_execute_action_dialog(room.room_id)
                st.rerun()
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            close_room_execute_action_dialog(room.room_id)
            st.rerun()


@st.dialog("🔌 重新連接設備", width="large")
def reconnect_room_devices_dialog(room: Room):
    """重新連接房間內設備對話框"""
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
    
    st.subheader(f"🔌 重新連接設備 - {room.display_name}")
    st.caption("💡 檢查房間內設備的連接狀態，並嘗試重新連接不在線的設備")
    
    st.markdown("---")
    
    # 獲取房間內設備
    room_devices = st.session_state.room_registry.get_room_devices(
        room.room_id,
        st.session_state.device_registry
    )
    
    # 按設備管理頁面的排序方式排序
    room_devices.sort(key=lambda d: d.sort_order)
    
    if not room_devices:
        st.warning("⚠️ 房間內沒有設備")
        if st.button("關閉"):
            st.session_state[f'show_reconnect_room_{room.room_id}'] = False
            st.rerun()
        return
    
    # 獲取當前 ADB 連接的設備列表
    adb_devices = st.session_state.adb_manager.get_devices()
    # 創建 serial -> state 的映射
    adb_device_map = {d['serial']: d['state'] for d in adb_devices}
    
    # 檢查每個設備的連接狀態
    devices_to_reconnect = []
    devices_status = []
    
    for device in room_devices:
        # 構建可能的連接字串
        possible_serials = [device.serial]
        if device.ip:
            possible_serials.append(f"{device.ip}:{device.port}")
        
        # 查找設備在 adb devices 中的狀態
        adb_state = None
        for serial in possible_serials:
            if serial in adb_device_map:
                adb_state = adb_device_map[serial]
                break
        
        # 根據設備狀態和 ADB 狀態判斷
        if device.status == DeviceStatus.NOT_CONNECTED and device.ip:
            # 未連接狀態且有 IP → 需要重新連接
            devices_to_reconnect.append(device)
            devices_status.append({
                'device': device,
                'status': '需要重新連接',
                'reason': '設備未連接（不在 ADB 列表中）'
            })
        elif device.status == DeviceStatus.ONLINE:
            if adb_state == "device":
                devices_status.append({
                    'device': device,
                    'status': '已連接',
                    'reason': '設備在線（ADB state: device）'
                })
            elif adb_state == "offline":
                devices_status.append({
                    'device': device,
                    'status': '離線',
                    'reason': '設備在 ADB 列表中但狀態為 offline'
                })
            else:
                # 狀態不一致，可能需要重新連接
                if device.ip:
                    devices_to_reconnect.append(device)
                    devices_status.append({
                        'device': device,
                        'status': '需要重新連接',
                        'reason': '設備標記為在線但不在 ADB 列表中'
                    })
                else:
                    devices_status.append({
                        'device': device,
                        'status': '無法連接',
                        'reason': '設備沒有 IP 地址'
                    })
        elif device.status == DeviceStatus.OFFLINE:
            devices_status.append({
                'device': device,
                'status': '跳過',
                'reason': '設備狀態為離線（ADB state: offline），不需要重新連接'
            })
        else:
            # 其他狀態
            if device.ip:
                devices_status.append({
                    'device': device,
                    'status': '無法連接',
                    'reason': f'設備狀態：{device.status}'
                })
            else:
                devices_status.append({
                    'device': device,
                    'status': '無法連接',
                    'reason': '設備沒有 IP 地址'
                })
    
    # 顯示設備狀態
    st.markdown("### 📊 設備連接狀態")
    
    for status_info in devices_status:
        device = status_info['device']
        status = status_info['status']
        reason = status_info['reason']
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if status == '需要重新連接':
                st.markdown(f"**{device.display_name}** - ⚠️ {status}")
            elif status == '已連接':
                st.markdown(f"**{device.display_name}** - ✅ {status}")
            elif status == '跳過':
                st.markdown(f"**{device.display_name}** - ⏭️ {status}")
            else:
                st.markdown(f"**{device.display_name}** - ❌ {status}")
            st.caption(f"  {reason}")
        
        with col2:
            # 顯示設備狀態圖示
            status_icon = STATUS_ICONS.get(device.status, "❓")
            status_text = {
                DeviceStatus.ONLINE: "🟢 在線",
                DeviceStatus.OFFLINE: "🟠 離線",
                DeviceStatus.NOT_CONNECTED: "⚫ 未連接",
            }.get(device.status, f"{status_icon} {device.status}")
            st.caption(status_text)
    
    st.markdown("---")
    
    # 顯示需要重新連接的設備數量
    if devices_to_reconnect:
        st.info(f"📋 發現 {len(devices_to_reconnect)} 台設備需要重新連接")
    else:
        st.success("✅ 所有設備連接正常，無需重新連接")
    
    # 按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if devices_to_reconnect:
            if st.button("🔌 開始重新連接", type="primary", use_container_width=True):
                with st.spinner("正在重新連接設備..."):
                    # 準備設備列表（IP 和 Port）
                    devices_list = [(device.ip, device.port) for device in devices_to_reconnect if device.ip]
                    
                    # 創建設備映射（用於查找結果對應的設備）
                    device_map = {f"{device.ip}:{device.port}": device for device in devices_to_reconnect if device.ip}
                    
                    # 進度顯示
                    progress_text = st.empty()
                    
                    def progress_callback(completed, total):
                        progress_text.text(f"🔌 連接進度：{completed}/{total} 台設備")
                    
                    # 使用並發連接（與 execute_action_batch 相同的模式）
                    logger.info(f"🔌 開始並發重新連接: {room.display_name} ({len(devices_list)} 台設備)")
                    batch_results = st.session_state.adb_manager.connect_batch(
                        devices_list,
                        max_workers=10,
                        progress_callback=progress_callback
                    )
                    
                    # 處理結果
                    success_count = 0
                    fail_count = 0
                    results = []
                    
                    for connection_str, success, output in batch_results:
                        device = device_map.get(connection_str)
                        if not device:
                            continue
                        
                        if success or "already connected" in output.lower():
                            # 連接成功，更新 last_seen
                            # 狀態會在下次自動掃描時根據 ADB 實際狀態更新（ONLINE 或 OFFLINE）
                            device.last_seen = datetime.now()
                            st.session_state.device_registry.save_device(device)
                            success_count += 1
                            results.append(f"✅ {device.display_name}: 連接命令已發送，狀態將在下次掃描時更新")
                            logger.info(f"✅ 重新連接成功: {device.display_name}，等待狀態掃描更新")
                        else:
                            fail_count += 1
                            results.append(f"❌ {device.display_name}: {output}")
                            logger.error(f"❌ 重新連接失敗: {device.display_name} - {output}")
                    
                    # 清除進度顯示
                    progress_text.empty()
                    
                    # 顯示結果
                    st.markdown("### 連接結果")
                    st.success(f"✅ 成功：{success_count} 台")
                    if fail_count > 0:
                        st.error(f"❌ 失敗：{fail_count} 台")
                    
                    # 顯示詳細結果
                    with st.expander("查看詳細結果"):
                        for result in results:
                            st.text(result)
                    
                    logger.info(f"🔌 重新連接完成: {room.display_name} (成功: {success_count}, 失敗: {fail_count})")
                    
                    time.sleep(2)
                    st.session_state[f'show_reconnect_room_{room.room_id}'] = False
                    st.rerun()
        else:
            st.button("🔌 開始重新連接", use_container_width=True, disabled=True)
            st.caption("（無需重新連接的設備）")
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state[f'show_reconnect_room_{room.room_id}'] = False
            st.rerun()


@st.dialog("⚡ 執行動作", width="large")
def execute_device_action_dialog(device, room: Optional[Room] = None):
    """在設備上執行動作對話框（房間視圖使用）"""
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
    
    st.subheader(f"📱 目標設備：{device.display_name}")
    
    if not device.is_online:
        st.warning("⚠️ 設備離線，請先連線後再執行動作")
        if st.button("關閉"):
            close_device_execute_action_dialog(device.device_id, room)
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
                close_device_execute_action_dialog(device.device_id, room)
                st.rerun()
        return
    
    # 動作選擇
    st.markdown("**選擇要執行的動作**")
    
    # 顯示動作列表
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
                from datetime import datetime
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
                if value:
                    st.text(f"  {key}: {value}")
    
    st.markdown("---")
    
    # 執行按鈕
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ 執行", type="primary", use_container_width=True):
            with st.spinner("執行中..."):
                # 準備房間信息（如果提供了房間且房間配置了 Socket Server）
                room_info = None
                if room and room.socket_ip and room.socket_port:
                    room_info = {
                        'socket_ip': room.socket_ip,
                        'socket_port': room.socket_port
                    }
                
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
                close_device_execute_action_dialog(device.device_id, room)
                st.rerun()
    
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            close_device_execute_action_dialog(device.device_id, room)
            st.rerun()


def render_realtime_status_content(room: Room, events, editable: bool = True, editor_key_suffix: str = "manual"):
    """渲染房間即時狀態內容，可被 fragment 局部刷新。"""
    # --- Current Event Banner ---
    trigger_key = f"timer_trigger_{room.room_id}"
    trigger_ts = st.session_state.get(trigger_key, 0)

    if trigger_ts > 0 and events:
        elapsed = time.time() - trigger_ts
        current_evt = None

        for e in events:
            if elapsed >= e['seconds']:
                current_evt = e
            else:
                break

        if current_evt:
            st.info(f"🔔 **當前環節**: {current_evt['content']} (表定 {current_evt['rawTime']})")
        elif elapsed < events[0]['seconds']:
            st.info(f"⏳ **等待開始**: 下一個環節 {events[0]['content']} ({events[0]['rawTime']})")

    from core.socket_client import SocketClient
    import pandas as pd

    try:
        with SocketClient(room.socket_ip, room.socket_port) as client:
            success, response = client.send_command('who')

            if success and 'players' in response:
                players = response['players']
                if players:
                    status_data = []

                    all_registry_devices = st.session_state.device_registry.get_all_devices()
                    registry_map = {d.device_id: d for d in all_registry_devices}
                    registry_ip_map = {d.ip: d for d in all_registry_devices if d.ip}

                    for p in players:
                        p_id = p.get('device_id', 'Unknown')
                        chapter = p.get('chapter', -1)
                        try:
                            chapter = int(float(chapter))
                        except (TypeError, ValueError):
                            chapter = -1
                        message = p.get('message', '')
                        address = p.get('address', '')
                        user_position_z = coerce_optional_float(p.get('user_position_z'))

                        current_time_str = extract_current_time_from_message(message)

                        device_obj = registry_map.get(p_id) or registry_ip_map.get(address)
                        current_alias = device_obj.alias or "" if device_obj else ""

                        adb_target = ""
                        if device_obj:
                            adb_target = device_obj.connection_string
                        elif address:
                            adb_target = address if ":" in address else f"{address}:5555"

                        if "ebb89c" in p_id:
                            current_alias = "OB6"
                        elif "a5aaf9" in p_id:
                            current_alias = "OB7"
                        elif "f14b0e" in p_id:
                            current_alias = "OB5"
                        elif "640596" in p_id:
                            current_alias = "OB4"
                        elif "4b5c31" in p_id:
                            current_alias = "OB8"
                        elif "2ed155" in p_id:
                            current_alias = "OB9"
                        elif "af5776" in p_id:
                            current_alias = "OB2"
                        elif "03022c" in p_id:
                            current_alias = "OB3"
                        elif "d18452" in p_id:
                            current_alias = "OB10"

                        status_data.append({
                            "device_id": p_id,
                            "registry_device_id": device_obj.device_id if device_obj else "",
                            "alias": current_alias,
                            "chapter": chapter if chapter != -1 else 0,
                            "current_time": current_time_str,
                            "user_position_z": user_position_z,
                            "adb_target": adb_target
                        })

                    if status_data:
                        import statistics

                        def parse_time_seconds(t_str):
                            try:
                                if not t_str:
                                    return -1
                                parts = t_str.strip().split(':')
                                if len(parts) == 2:
                                    return int(parts[0]) * 60 + int(parts[1])
                            except Exception:
                                pass
                            return -1

                        param_chapters = [d['chapter'] for d in status_data if d['chapter'] > 0]
                        param_times = [
                            parse_time_seconds(d['current_time'])
                            for d in status_data
                            if parse_time_seconds(d['current_time']) >= 0
                        ]

                        consensus_chapter = -1
                        if param_chapters:
                            try:
                                consensus_chapter = statistics.mode(param_chapters)
                            except Exception:
                                consensus_chapter = max(set(param_chapters), key=param_chapters.count)

                        median_time = statistics.median(param_times) if param_times else 0

                        for d in status_data:
                            is_error = False
                            if consensus_chapter != -1 and d['chapter'] > 0 and d['chapter'] != consensus_chapter:
                                is_error = True

                            t_val = parse_time_seconds(d['current_time'])
                            if median_time > 0 and t_val >= 0 and abs(t_val - median_time) > 4:
                                is_error = True

                            d['is_error'] = is_error

                        df = pd.DataFrame(status_data)

                        def highlight_warning(row):
                            if row.get('is_error'):
                                return ['background-color: rgba(255, 75, 75, 0.5)'] * len(row)
                            return [''] * len(row)

                        styled_df = df.style.apply(highlight_warning, axis=1)
                        st.session_state[f"realtime_status_data_{room.room_id}"] = status_data

                        table_kwargs = {
                            "column_config": {
                                "device_id": st.column_config.TextColumn("設備 ID", help="設備唯一標識符", disabled=True),
                                "alias": st.column_config.TextColumn("備註名稱 (可編輯)", help="點擊編輯設備備註"),
                                "chapter": st.column_config.NumberColumn("當前章節", format="%d", disabled=True),
                                "current_time": st.column_config.TextColumn("當前時間", help="從心跳訊息解析的時間", disabled=True),
                                "user_position_z": st.column_config.NumberColumn("使用者位置", format="%.3f", help="章節 5 時由 Client 回傳的 z 座標", disabled=True),
                            },
                            "column_order": ["device_id", "alias", "chapter", "current_time", "user_position_z"],
                            "width": "stretch",
                            "row_height": STATUS_TABLE_ROW_HEIGHT,
                            "hide_index": True,
                        }

                        if editable:
                            edited_df = st.data_editor(
                                styled_df,
                                key=f"status_editor_{room.room_id}_{editor_key_suffix}",
                                **table_kwargs
                            )

                            changed = False
                            for index, row in edited_df.iterrows():
                                new_alias = row['alias']
                                registry_device_id = ""
                                if 'registry_device_id' in row:
                                    registry_device_id = row.get('registry_device_id') or ""
                                if not registry_device_id and index < len(status_data):
                                    registry_device_id = status_data[index].get('registry_device_id', '')

                                if registry_device_id in registry_map:
                                    original_alias = registry_map[registry_device_id].alias or ""
                                    if new_alias != original_alias:
                                        registry_map[registry_device_id].alias = new_alias
                                        device_to_update = registry_map[registry_device_id]
                                        st.session_state.device_registry.update_device(
                                            device_to_update.serial,
                                            device_to_update.to_dict()
                                        )
                                        changed = True

                            if changed:
                                st.success("✅ 備註已更新")
                        else:
                            st.dataframe(styled_df, **table_kwargs)
                    else:
                        st.session_state[f"realtime_status_data_{room.room_id}"] = []
                        st.info("目前沒有設備報告狀態")
                else:
                    st.session_state[f"realtime_status_data_{room.room_id}"] = []
                    st.info("目前沒有活躍玩家連接")
            else:
                st.session_state[f"realtime_status_data_{room.room_id}"] = []
                st.warning(f"無法獲取即時狀態: {response.get('message', 'Unknown error')}")

    except Exception as e:
        st.session_state[f"realtime_status_data_{room.room_id}"] = []
        st.error(f"連接 Server 查詢狀態失敗: {e}")


def render_realtime_status_markers(room: Room):
    """渲染每列旁邊的 Passthrough 紅色標記，可局部刷新。"""
    status_data = st.session_state.get(f"realtime_status_data_{room.room_id}", [])
    st.markdown('<div class="resume-alert-marker-header"></div>', unsafe_allow_html=True)

    for row_data in status_data:
        adb_target = row_data.get('adb_target', '')
        passthrough_alert = None

        if adb_target and hasattr(st.session_state.adb_manager, 'start_passthrough_logcat_monitor'):
            st.session_state.adb_manager.start_passthrough_logcat_monitor(
                adb_target,
                DEFAULT_GAME_PACKAGE,
                clear_logcat=True
            )
            passthrough_alert = st.session_state.adb_manager.get_passthrough_alert(adb_target)

        marker_class = "is-active" if passthrough_alert else ""
        marker_title = passthrough_alert.get('reason', '系統 UI 接管') if passthrough_alert else ""
        st.markdown(
            f'''
            <div class="resume-alert-marker-wrap" title="{marker_title}">
                <span class="resume-alert-marker {marker_class}"></span>
            </div>
            ''',
            unsafe_allow_html=True
        )


def render_realtime_status_actions(room: Room):
    """渲染固定的切回遊戲按鈕，不放進自動刷新 fragment。"""
    status_data = st.session_state.get(f"realtime_status_data_{room.room_id}", [])
    st.markdown(
        '<div class="resume-game-action-column resume-game-action-header">操作</div>',
        unsafe_allow_html=True
    )

    for row_index, row_data in enumerate(status_data):
        device_label = row_data.get('alias') or row_data.get('device_id', '設備')
        adb_target = row_data.get('adb_target', '')

        if st.button(
            "切回遊戲",
            key=f"resume_game_{room.room_id}_{row_index}_{row_data.get('device_id', '')}",
            width="stretch",
            type="primary",
            disabled=not bool(adb_target),
            help=f"先送 BACK，再用 explicit VR activity/monkey 將 {DEFAULT_GAME_PACKAGE} 帶回前景，並檢查 Quest 畫面焦點",
            on_click=st.session_state.adb_manager.clear_passthrough_alert,
            args=(adb_target,)
        ):
            success_resume, resume_message = st.session_state.adb_manager.execute_resume_app(
                adb_target,
                {
                    'package': DEFAULT_GAME_PACKAGE,
                    'activity': 'com.unity3d.player.UnityPlayerGameActivity',
                    'send_back_first': True,
                    'back_count': 2,
                    'explicit_activity_first': True,
                    'am_start_after': True,
                    'verify_focus': True,
                    'send_escape_if_overlay': True,
                    'overlay_clear_escape_count': 1,
                    'overlay_clear_back_count': 0,
                    'focus_fallback_rounds': 2,
                    'focus_fallback_back_count': 1,
                    'focus_fallback_escape_count': 1
                }
            )
            if success_resume:
                st.success(f"{device_label}: {resume_message}")
            else:
                st.error(f"{device_label}: {resume_message}")


def render_realtime_status_position_adjustments(room: Room):
    """渲染固定的 z 值調整欄，不跟隨表格 fragment 重建。"""
    status_data = st.session_state.get(f"realtime_status_data_{room.room_id}", [])
    st.markdown(
        '<div class="position-adjust-column position-adjust-header">位置調整</div>',
        unsafe_allow_html=True
    )

    for row_data in status_data:
        device_id = row_data.get("device_id", "")
        if not device_id:
            continue

        device_label = row_data.get("alias") or device_id
        chapter = row_data.get("chapter", 0)
        current_z = coerce_optional_float(row_data.get("user_position_z"))
        can_adjust = chapter == USER_POSITION_SYNC_CHAPTER and current_z is not None
        input_key = sync_user_position_input_state(room.room_id, device_id, current_z)
        form_key = f"user_position_adjust_form_{room.room_id}_{device_id}"
        submit_key = f"user_position_adjust_submit_{room.room_id}_{device_id}"

        with st.form(form_key, border=False):
            value_col, action_col = st.columns([0.95, 1.25], gap="small")

            with value_col:
                st.number_input(
                    f"{device_label} z",
                    key=input_key,
                    step=0.1,
                    format="%.3f",
                    label_visibility="collapsed",
                    disabled=not can_adjust,
                    help="只會回寫 z 座標"
                )

            with action_col:
                submitted = st.form_submit_button(
                    "重新調整位置",
                    key=submit_key,
                    type="primary",
                    width="stretch",
                    disabled=not can_adjust
                )

            if submitted:
                target_z = coerce_optional_float(st.session_state.get(input_key))
                if target_z is None:
                    st.error(f"{device_label}: z 值格式無效")
                else:
                    success_adjust, adjust_message = send_user_position_adjust_command(room, device_id, target_z)
                    if success_adjust:
                        st.success(f"{device_label}: {adjust_message}")
                    else:
                        st.error(f"{device_label}: {adjust_message}")


@st.fragment(run_every="1s")
def render_realtime_status_fragment(room: Room, events):
    """局部自動刷新即時狀態，不重跑整個房間頁。"""
    render_realtime_status_content(room, events, editable=False, editor_key_suffix="fragment")


@st.fragment(run_every="1s")
def render_realtime_status_markers_fragment(room: Room):
    """局部自動刷新 Passthrough 紅色標記，不重建按鈕。"""
    render_realtime_status_markers(room)


@st.dialog("🏠 房間視圖", width="large")
def room_view_dialog(room: Room):
    """房間視圖對話框 - 顯示房間內所有設備"""
    # 確保必要的組件已初始化
    from utils.init import ensure_room_registry, ensure_initialization
    ensure_initialization()
    ensure_room_registry()
    
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
    
    # 房間信息
    st.markdown(f"## {room.display_name}")
    
    if room.description:
        st.caption(room.description)
    
    # 房間統計
    room_devices = st.session_state.room_registry.get_room_devices(
        room.room_id,
        st.session_state.device_registry
    )
    
    # 按設備管理頁面的排序方式排序
    room_devices.sort(key=lambda d: d.sort_order)
    
    online_devices = [d for d in room_devices if d.status == DeviceStatus.ONLINE]
    offline_devices = [d for d in room_devices if d.status == DeviceStatus.OFFLINE]
    not_connected_devices = [d for d in room_devices if d.status == DeviceStatus.NOT_CONNECTED]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("設備總數", room.capacity_text)
    
    with col2:
        st.metric("🟢 在線", len(online_devices))
    
    with col3:
        st.metric("🟠 離線", len(offline_devices))
    
    with col4:
        st.metric("⚫ 未連接", len(not_connected_devices))
    
    with col4:
        if room.max_devices > 0:
            remaining = room.max_devices - room.device_count
            st.metric("剩餘名額", remaining)
        else:
            st.metric("容量限制", "無限制")
    
    st.markdown("---")
    
    # 快速操作按鈕
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("⚡ 執行動作", use_container_width=True, type="primary"):
            st.session_state[f'show_room_view_{room.room_id}'] = False
            st.session_state[f'show_execute_action_room_{room.room_id}'] = True
            st.rerun()
    
    with col2:
        if st.button("➕ 管理設備", use_container_width=True):
            st.session_state[f'show_room_view_{room.room_id}'] = False
            st.session_state[f'show_manage_devices_{room.room_id}'] = True
            st.rerun()
    
    with col3:
        if st.button("❌ 關閉", use_container_width=True):
            st.session_state[f'show_room_view_{room.room_id}'] = False
            st.rerun()
    
    st.markdown("---")
    
    # Socket Server 監控（如果房間配置了 Socket Server）
    if room.socket_ip and room.socket_port:
        st.markdown("### 📡 Socket Server 監控")
        
        # 檢查 Socket Server 狀態
        socket_running = False
        if 'socket_server_manager' in st.session_state:
            socket_manager = st.session_state.socket_server_manager
            socket_running = socket_manager.is_server_running(room.room_id)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if socket_running:
                st.success(f"🟢 Socket Server 運行中 - {room.socket_ip}:{room.socket_port}")
            else:
                st.warning(f"🔴 Socket Server 未運行 - {room.socket_ip}:{room.socket_port}")
        
        with col2:
            if socket_running:
                if st.button("🔄 重啟", key=f"restart_socket_in_view_{room.room_id}", use_container_width=True):
                    if 'socket_server_manager' in st.session_state:
                        socket_manager = st.session_state.socket_server_manager
                        success, msg = socket_manager.restart_server(
                            room.room_id,
                            room.name,
                            room.socket_ip,
                            room.socket_port,
                            room.saved_user_position_z
                        )
                        if success:
                            st.success("✅ Socket Server 已重啟")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                if st.button("🚀 啟動 Server", key=f"start_socket_in_view_{room.room_id}", use_container_width=True):
                     if 'socket_server_manager' in st.session_state:
                         success, msg = st.session_state.socket_server_manager.start_server(
                            room.room_id,
                            room.name,
                            room.socket_ip,
                            room.socket_port,
                            room.saved_user_position_z
                        )
                         if success:
                             st.success("✅ Server 啟動成功")
                             time.sleep(1)
                             st.rerun()
                         else:
                             st.error(f"❌ Server 啟動失敗: {msg}")


        # --- Time Reminder Section ---
        # Display the Time Reminder Component
        # We need to persist the trigger timestamp in session state
        
        # Initialize trigger state if not exists
        trigger_key = f"timer_trigger_{room.room_id}"
        if trigger_key not in st.session_state:
            st.session_state[trigger_key] = 0.0

        with st.container(border=True):
            st.markdown('<div class="highlight-gray-bg"></div>', unsafe_allow_html=True)
            st.markdown("### ⏱️ 時間提醒 (Time Reminder)")
            # Add Config UI
            render_time_config()
            
            events = load_time_events()
            if events:
                time_reminder_component(events, trigger_ts=st.session_state[trigger_key])
            else:
                st.info("尚未載入提醒事件，請展開上方設定進行新增")

        st.divider()

        # --- Real-time Status Section ---
        if socket_running:
            col_h, col_ref = st.columns([3, 1])
            with col_h:
                st.markdown("### 📊 即時狀態 (Real-time Status)")
            with col_ref:
                auto_refresh = st.checkbox("🔄 局部刷新 (1s)", value=True, key=f"local_auto_refresh_{room.room_id}")

            render_room_user_position_bulk_controls(room)

            status_table_col, status_marker_col, status_action_col, status_position_col = st.columns([5.15, 0.18, 0.72, 1.65])

            with status_table_col:
                if auto_refresh:
                    render_realtime_status_fragment(room, events)
                else:
                    render_realtime_status_content(room, events)

            with status_marker_col:
                if auto_refresh:
                    render_realtime_status_markers_fragment(room)
                else:
                    render_realtime_status_markers(room)

            with status_action_col:
                render_realtime_status_actions(room)

            with status_position_col:
                render_realtime_status_position_adjustments(room)

        # Legacy full-page realtime block kept disabled; fragment path above renders the live UI.
        if False and socket_running:
            col_h, col_ref = st.columns([3, 1])
            with col_h:
                st.markdown("### 📊 即時狀態 (Real-time Status)")
            with col_ref:
                auto_refresh = st.checkbox("🔄 自動刷新 (1s)", value=False, key=f"auto_refresh_legacy_{room.room_id}")

            # --- Current Event Banner ---
            # Calculate current event based on elapsed time since trigger
            import time
            trigger_key = f"timer_trigger_{room.room_id}"
            trigger_ts = st.session_state.get(trigger_key, 0)
            
            if trigger_ts > 0 and events:
                elapsed = time.time() - trigger_ts
            
            if trigger_ts > 0 and events:
                elapsed = time.time() - trigger_ts
                current_evt = None
                
                # events should be sorted by seconds (load_time_events does this)
                for e in events:
                    if elapsed >= e['seconds']:
                        current_evt = e
                    else:
                        break
                
                if current_evt:
                    st.info(f"🔔 **當前環節**: {current_evt['content']} (表定 {current_evt['rawTime']})")
                elif elapsed < events[0]['seconds']:
                     # Before first event
                     st.info(f"⏳ **等待開始**: 下一個環節 {events[0]['content']} ({events[0]['rawTime']})")
            # ---------------------------
            from core.socket_client import SocketClient
            import pandas as pd
            import math

            try:
                # Use a short timeout for responsiveness
                with SocketClient(room.socket_ip, room.socket_port) as client:
                    success, response = client.send_command('who')
                    
                    if success and 'players' in response:
                        players = response['players']
                        if players:
                            status_data = []
                            
                            # Pre-fetch all devices registry for quick lookup
                            all_registry_devices = st.session_state.device_registry.get_all_devices()
                            registry_map = {d.device_id: d for d in all_registry_devices}
                            registry_ip_map = {d.ip: d for d in all_registry_devices if d.ip}
                            
                            for p in players:
                                p_id = p.get('device_id', 'Unknown')
                                chapter = p.get('chapter', -1)
                                try:
                                    chapter = int(float(chapter))
                                except (TypeError, ValueError):
                                    chapter = -1
                                message = p.get('message', '')
                                address = p.get('address', '')
                                
                                # Parse Current Time from message/debug payload and only keep `MM:SS`
                                current_time_str = extract_current_time_from_message(message)
                                
                                # Resolve Device/Alias
                                device_obj = registry_map.get(p_id) or registry_ip_map.get(address)
                                current_alias = ""
                                if device_obj:
                                    current_alias = device_obj.alias or ""
                                
                                adb_target = ""
                                if device_obj:
                                    adb_target = device_obj.connection_string
                                elif address:
                                    adb_target = address if ":" in address else f"{address}:5555"
                                
                                # Hardcode alias for specific device
                                if "ebb89c" in p_id:
                                    current_alias = "OB6"
                                elif "a5aaf9" in p_id:
                                    current_alias = "OB7"
                                elif "f14b0e" in p_id:
                                    current_alias = "OB5"
                                elif "640596" in p_id:
                                    current_alias = "OB4"
                                elif "4b5c31" in p_id:
                                    current_alias = "OB8"
                                elif "2ed155" in p_id:
                                    current_alias = "OB9"
                                elif "af5776" in p_id:
                                    current_alias = "OB2"
                                elif "03022c" in p_id:
                                    current_alias = "OB3"
                                elif "d18452" in p_id:
                                    current_alias = "OB10"
                                    # Ensure it's saved in registry execution flow if needed? 
                                    # But here we just display it. The edit flow might override it if we don't handle it there.
                                
                                status_data.append({
                                    "device_id": p_id,
                                    "registry_device_id": device_obj.device_id if device_obj else "",
                                    "alias": current_alias,
                                    "chapter": chapter if chapter != -1 else 0, # Use 0 or -1? User said "e.g. 6"
                                    "current_time": current_time_str,
                                    "adb_target": adb_target
                                })
                            
                            
                            if status_data:
                                import statistics
                                
                                # Helper to parse "MM:SS" to seconds
                                def parse_time_seconds(t_str):
                                    try:
                                        if not t_str: return -1
                                        parts = t_str.strip().split(':')
                                        if len(parts) == 2:
                                            return int(parts[0]) * 60 + int(parts[1])
                                    except:
                                        pass
                                    return -1

                                # 1. Calculate Consensus (Mode Chapter, Median Time)
                                param_chapters = [d['chapter'] for d in status_data if d['chapter'] > 0]
                                param_times = [parse_time_seconds(d['current_time']) for d in status_data if parse_time_seconds(d['current_time']) >= 0]
                                
                                consensus_chapter = -1
                                if param_chapters:
                                    try:
                                        consensus_chapter = statistics.mode(param_chapters)
                                    except:
                                        # If multiple modes, statistics.mode might fail in older python or return one.
                                        # Just pick the first popular one or max.
                                        consensus_chapter = max(set(param_chapters), key=param_chapters.count)
                                
                                median_time = 0
                                if param_times:
                                    median_time = statistics.median(param_times)
                                
                                # 2. Mark Errors
                                for d in status_data:
                                    is_error = False
                                    # Check Chapter
                                    if consensus_chapter != -1 and d['chapter'] > 0:
                                        if d['chapter'] != consensus_chapter:
                                            is_error = True
                                    
                                    # Check Time (Diff > 4s)
                                    t_val = parse_time_seconds(d['current_time'])
                                    if median_time > 0 and t_val >= 0:
                                        if abs(t_val - median_time) > 4:
                                            is_error = True
                                    
                                    d['is_error'] = is_error

                                df = pd.DataFrame(status_data)
                                
                                # 3. Apply Styling
                                # Function to highlight user rows
                                def highlight_warning(row):
                                    # Red background if error
                                    if row.get('is_error'):
                                        return ['background-color: rgba(255, 75, 75, 0.5)'] * len(row)
                                    return [''] * len(row)

                                styled_df = df.style.apply(highlight_warning, axis=1)

                                # Display editable table
                                # Note: 'is_error' is in the dataframe but we hide it.
                                status_table_col, status_action_col = st.columns([5, 1])
                                with status_table_col:
                                    edited_df = st.data_editor(
                                        styled_df,  # Pass Styler object
                                        column_config={
                                            "device_id": st.column_config.TextColumn("設備 ID", help="設備唯一標識符", disabled=True),
                                            "alias": st.column_config.TextColumn("備註名稱 (可編輯)", help="點擊編輯設備備註"),
                                            "chapter": st.column_config.NumberColumn("當前章節", format="%d", disabled=True),
                                            "current_time": st.column_config.TextColumn("當前時間", help="從心跳訊息解析的時間", disabled=True),
                                        },
                                        column_order=["device_id", "alias", "chapter", "current_time"], # Hide is_error
                                        width="stretch",
                                        row_height=STATUS_TABLE_ROW_HEIGHT,
                                        hide_index=True,
                                        key=f"status_editor_{room.room_id}"
                                    )
                                
                                with status_action_col:
                                    st.markdown(
                                        '<div class="resume-game-action-column resume-game-action-header">操作</div>',
                                        unsafe_allow_html=True
                                    )
                                    for row_index, row_data in enumerate(status_data):
                                        device_label = row_data.get('alias') or row_data.get('device_id', '設備')
                                        adb_target = row_data.get('adb_target', '')
                                        passthrough_alert = None
                                        if adb_target and hasattr(st.session_state.adb_manager, 'start_passthrough_logcat_monitor'):
                                            st.session_state.adb_manager.start_passthrough_logcat_monitor(
                                                adb_target,
                                                DEFAULT_GAME_PACKAGE,
                                                clear_logcat=True
                                            )
                                            passthrough_alert = st.session_state.adb_manager.get_passthrough_alert(adb_target)

                                        button_help = f"先送 BACK，再用 monkey 將 {DEFAULT_GAME_PACKAGE} 帶回前景"
                                        if passthrough_alert:
                                            button_help = f"偵測到可能誤觸 Passthrough：{passthrough_alert.get('reason', '系統 UI 接管')}"

                                        if st.button(
                                            "切回遊戲",
                                            key=f"resume_game_{room.room_id}_{row_index}_{row_data.get('device_id', '')}",
                                            width="stretch",
                                            type="primary" if passthrough_alert else "secondary",
                                            disabled=not bool(adb_target),
                                            help=button_help,
                                            on_click=st.session_state.adb_manager.clear_passthrough_alert,
                                            args=(adb_target,)
                                        ):
                                            success_resume, resume_message = st.session_state.adb_manager.execute_resume_app(
                                                adb_target,
                                                {
                                                    'package': DEFAULT_GAME_PACKAGE,
                                                    'activity': 'com.unity3d.player.UnityPlayerGameActivity',
                                                    'send_back_first': True,
                                                    'back_count': 2,
                                                    'explicit_activity_first': True,
                                                    'am_start_after': True
                                                }
                                            )
                                            if success_resume:
                                                st.success(f"{device_label}: {resume_message}")
                                            else:
                                                st.error(f"{device_label}: {resume_message}")
                                
                                # Check for changes in Alias and update registry
                                # This logic runs on every interaction/rerun
                                changed = False
                                for index, row in edited_df.iterrows():
                                    d_id = row['device_id']
                                    new_alias = row['alias']
                                    registry_device_id = ""
                                    if 'registry_device_id' in row:
                                        registry_device_id = row.get('registry_device_id') or ""
                                    if not registry_device_id and index < len(status_data):
                                        registry_device_id = status_data[index].get('registry_device_id', '')
                                    
                                    # Find original to compare (optimization)
                                    # But since we built the df from registry, comparing with 'current_alias' from the loop above isn't easy here
                                    # directly unless we iterate the ORIGINAL df again or look up registry.
                                    # Simplest is look up registry again.
                                    if registry_device_id in registry_map:
                                        original_alias = registry_map[registry_device_id].alias or ""
                                        if new_alias != original_alias:
                                            # Update Registry
                                            registry_map[registry_device_id].alias = new_alias
                                            device_to_update = registry_map[registry_device_id]
                                            st.session_state.device_registry.update_device(
                                                device_to_update.serial,
                                                device_to_update.to_dict()
                                            )
                                            changed = True
                                
                                if changed:
                                    st.success("✅ 備註已更新")
                                    # No st.rerun() needed immediately, the data_editor state persists, 
                                    # and next auto-refresh will pick it up, or user can manually refresh.
                                    # But to sync with other views, maybe good to notify.
                            else:
                                st.info("目前沒有設備報告狀態")
                        else:
                             st.info("目前沒有活躍玩家連接")
                    else:
                        st.warning(f"無法獲取即時狀態: {response.get('message', 'Unknown error')}")

            except Exception as e:
                st.error(f"連接 Server 查詢狀態失敗: {e}")
            
            if auto_refresh:
                time.sleep(1)
                st.rerun()
        col = st.columns(2)
        with col[0]:
            if st.button("📺 CCTV 監控牆 (所有設備)", key=f"cctv_{room.room_id}", use_container_width=True, type="primary"):
                monitor_devices = [device for device in room_devices if device.is_online]

                if not room_devices:
                    st.warning("⚠️ 此房間內沒有設備")
                elif not monitor_devices:
                    st.warning("⚠️ 此房間內沒有在線設備可供監看")
                else:
                    import time

                    device_count = len(monitor_devices)
                    st.toast(f"將依序開啟 {device_count} 台設備的單眼監看視窗...", icon="📺")

                    progress_text = st.empty()
                    progress_bar = st.progress(0)
                    success_count = 0
                    failure_count = 0
                    st.session_state.adb_manager.reset_scrcpy_window_layout()

                    for index, device in enumerate(monitor_devices, start=1):
                        progress_text.text(f"正在開啟 {index}/{device_count}: {device.display_name}")
                        success, message = start_room_device_monitor(
                            device,
                            room,
                            layout_slot=index - 1,
                            layout_total=device_count
                        )
                        if success:
                            success_count += 1
                        else:
                            failure_count += 1
                            st.warning(f"⚠️ {device.display_name}: {message}")

                        progress_bar.progress(index / device_count)
                        time.sleep(1.2)

                    progress_text.empty()
                    progress_bar.empty()

                    if failure_count == 0:
                        st.success(f"✅ 已依序開啟 {success_count} 台設備監看視窗")
                    else:
                        st.warning(f"⚠️ 監看視窗已開啟 {success_count} 台，失敗 {failure_count} 台")
        
        with col[1]:
            if st.button("🛑 關閉所有監控 (Stop All)", key=f"stop_cctv_{room.room_id}", use_container_width=True):
                 try:
                     import subprocess
                     if subprocess.run(["pkill", "scrcpy"]).returncode == 0:
                         st.session_state.adb_manager.reset_scrcpy_window_layout()
                         st.success("已關閉所有監控視窗")
                     else:
                         st.session_state.adb_manager.reset_scrcpy_window_layout()
                         st.info("沒有發現運行的監控視窗")
                 except Exception as e:
                     st.error(f"關閉失敗: {e}")

        
        # 日誌視窗、命令輸入和群控管理
        tab1, tab2, tab3 = st.tabs(["🎮 群控管理", "📋 日誌監看", "⌨️ 命令發送"])
        
        with tab1:
            st.markdown("### 🎮 群控面板")
            
            # 分兩列佈局：左側切換章節，右側序列管理
            col_main_left, col_main_right = st.columns(2)
            
            with col_main_left:
                with st.container(height=380, border=True, key=f"qqquest-control-card-move-command-{room.room_id}"):
                    # --- Move Command ---
                    st.markdown("#### 🚀 章節切換 (Move Command)")
            
                    # 使用 3 列佈局來容納 Package Name
                    col_chn, col_pkg, col_btn = st.columns([1, 2, 2])
            
                    with col_chn:
                        target_chapter = st.number_input(
                            "目標章節 ID",
                            value=0,
                            step=1,
                            format="%d",
                            key=f"move_chapter_{room.room_id}"
                        )
            
                    with col_pkg:
                        target_package = st.text_input(
                            "Package Name (選填)",
                            value="com.Awespire.OrientalBeauty",
                            help="指定目標 App 的 Package Name",
                            key=f"move_package_{room.room_id}"
                        )
            
                    with col_btn:
                        # Add spacing to align button perfectly with the input box
                        st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
                        if st.button("切換章節", use_container_width=True, type="primary", key=f"btn_move_{room.room_id}"):
                            if socket_running:
                                from core.socket_client import SocketClient
                                try:
                                    with SocketClient(room.socket_ip, room.socket_port) as client:
                                        # Payload structure for MoveCommand:
                                        # { "type": "admin_broadcast", "data": { "message_type": "move_command", "move_command": { "chapter": N, "package_name": "..." } } }
                                        payload = {
                                            "message_type": "move_command",
                                            "move_command": {
                                                "chapter": int(target_chapter),
                                                "package_name": target_package
                                            }
                                        }
                                
                                        success, response = client.send_command("admin_broadcast", payload)
                                
                                        if success:
                                            st.success(f"✅ 章節切換指令已發送 (Ch. {target_chapter})")
                                    
                                            # Trigger Time Reminder RESET if Chapter is 2
                                            if int(target_chapter) == 2:
                                                import time
                                                trigger_key = f"timer_trigger_{room.room_id}"
                                                st.session_state[trigger_key] = time.time()
                                                st.toast("⏱️ 時間提醒已重置並開始！")
                                                # Force rerun to update component
                                                st.rerun()
                                        else:
                                            st.error(f"❌ 發送失敗: {response.get('message', '未知錯誤')}")
                                except Exception as e:
                                    st.error(f"❌ 連接失敗: {str(e)}")
                            else:
                                st.error("❌ Socket Server 未運行")
            
                    # --- Individual Move Command ---
                    st.markdown("##### 🎯 單獨切換 (Individual Switch)")
            
                    # Prepare device options for individual switch
                    move_online_players = []
                    if socket_running:
                        from core.socket_client import SocketClient
                        try:
                            with SocketClient(room.socket_ip, room.socket_port) as client:
                                    success, response = client.send_command("who")
                                    if success and "players" in response:
                                        move_online_players = response["players"]
                        except:
                            pass

                    move_device_options = [p["device_id"] for p in move_online_players] if move_online_players else []
            
                    # Helper to display device name
                    def get_move_device_display(device_id):
                        # Reuse logic or simplified version
                        # Ideally we reuse the get_device_display from below but scope is different
                        # Let's duplicate simple lookup for now or rely on registry
                         # Hardcode alias for specific device (reuse same logic as sequence)
                        p_id = device_id
                        current_alias = ""
                        if "ebb89c" in p_id: current_alias = "OB6"
                        elif "a5aaf9" in p_id: current_alias = "OB7"
                        elif "f14b0e" in p_id: current_alias = "OB5"
                        elif "640596" in p_id: current_alias = "OB4"
                        elif "4b5c31" in p_id: current_alias = "OB8"
                        elif "2ed155" in p_id: current_alias = "OB9"
                        elif "af5776" in p_id: current_alias = "OB2"
                        elif "03022c" in p_id: current_alias = "OB3"
                        elif "d18452" in p_id: current_alias = "OB10"
                
                        if current_alias:
                            return f"{current_alias} ({device_id})"

                        if 'device_registry' in st.session_state:
                            device = st.session_state.device_registry.get_device(device_id)
                            if device:
                                if device.alias: return f"{device.alias} ({device.device_id})"
                                if device.notes: return f"{device.notes} ({device.device_id})"
                        return device_id

                    col_m_dev, col_m_btn = st.columns([3, 1])
                    with col_m_dev:
                        target_move_device = st.selectbox(
                            "選擇目標設備 (Target Device)", 
                            options=move_device_options,
                            index=0 if move_device_options else None,
                            format_func=get_move_device_display,
                            key=f"move_target_select_{room.room_id}",
                            help="選擇要切換章節的特定設備"
                        )
            
                    with col_m_btn:
                        st.write("")
                        st.write("")
                        if st.button("單獨切換", key=f"btn_move_individual_{room.room_id}"):
                            if socket_running and target_move_device:
                                from core.socket_client import SocketClient
                                try:
                                    with SocketClient(room.socket_ip, room.socket_port) as client:
                                        # Payload
                                        move_payload = {
                                            "message_type": "move_command",
                                            "move_command": {
                                                "chapter": int(target_chapter),
                                                "package_name": target_package
                                            }
                                        }
                                
                                        unicast_payload = {
                                            "target_device_id": target_move_device,
                                            "data": move_payload
                                        }
                                
                                        success, response = client.send_command("admin_unicast", unicast_payload)
                                
                                        if success and response.get("success"):
                                            st.success(f"✅ 已對 {target_move_device} 切換至 Ch. {target_chapter}")
                                            if int(target_chapter) == 2:
                                                import time
                                                trigger_key = f"timer_trigger_{room.room_id}"
                                                st.session_state[trigger_key] = time.time()
                                                st.toast("⏱️ 時間提醒已重置並開始！")
                                                st.rerun()
                                        else:
                                            st.error(f"❌ 切換失敗: {response.get('message', '未知錯誤')}")
                                except Exception as e:
                                    st.error(f"❌ 連接失敗: {str(e)}")
                            elif not target_move_device:
                                st.warning("⚠️ 請選擇目標設備")
                            else:
                                st.error("❌ Socket Server 未運行")

            with col_main_right:
                with st.container(height=380, border=True, key=f"qqquest-control-card-sequence-{room.room_id}"):
                    # --- Reset Sequences ---
                    st.markdown("#### 🔢 序列管理 (Sequence)")
            
                    # --- Unicast: Assign Sequence ---
                    st.markdown("##### 指定設備序列號")
            
                    # --- Auto Assign Sequence ---
                    with st.expander("🤖 自動分配序列號 (Auto Assign)", expanded=False):
                        st.caption("根據設備別名 (OBx) 自動計算並分配序列號。規則：OBx -> (x-1)%8")
                
                        if st.button("🤖 執行自動分配", key=f"btn_auto_assign_{room.room_id}"):
                            if socket_running:
                                from core.socket_client import SocketClient
                                try:
                                    with SocketClient(room.socket_ip, room.socket_port) as client:
                                        # Get online players first to confirm connection
                                        success_who, response_who = client.send_command("who")
                                        connected_ids = []
                                        if success_who and "players" in response_who:
                                            connected_ids = [p["device_id"] for p in response_who["players"]]
                                
                                        # Logic to determine alias and sequence
                                        auto_success_count = 0
                                        auto_fail_count = 0
                                        results = []
                                
                                        # Process all connected devices
                                        for dev_id in connected_ids:
                                            # 1. Determine Alias
                                            # Check hardcoded mapping first (legacy support)
                                            alias = None
                                            p_id_lower = dev_id.lower()
                                    
                                            # Hardcoded mapping from user request
                                            if "ebb89c" in p_id_lower: alias = "OB6"
                                            elif "a5aaf9" in p_id_lower: alias = "OB7"
                                            elif "f14b0e" in p_id_lower: alias = "OB5"
                                            elif "640596" in p_id_lower: alias = "OB4"
                                            elif "4b5c31" in p_id_lower: alias = "OB8"
                                            elif "2ed155" in p_id_lower: alias = "OB9"
                                            elif "af5776" in p_id_lower: alias = "OB2"
                                            elif "03022c" in p_id_lower: alias = "OB3"
                                    
                                            # Fallback to Registry Alias if not found in hardcoded
                                            if not alias and 'device_registry' in st.session_state:
                                                d_obj = st.session_state.device_registry.get_device(dev_id)
                                                if d_obj and d_obj.alias:
                                                    alias = d_obj.alias
                                    
                                            # 2. Calculate Sequence
                                            seq_num = None
                                            if alias and alias.upper().startswith("OB"):
                                                try:
                                                    # Extract number part "OB6" -> 6
                                                    num_str = "".join(filter(str.isdigit, alias))
                                                    if num_str:
                                                        num = int(num_str)
                                                        # Formula: (num - 1) % 8
                                                        # User rule: OB6 -> 5, OB9 -> 0
                                                        # 6-1 = 5 % 8 = 5.
                                                        # 9-1 = 8 % 8 = 0.
                                                        seq_num = (num - 1) % 8
                                                except:
                                                    pass
                                    
                                            # 3. Send Command
                                            if seq_num is not None:
                                                unicast_data = {
                                                    "message_type": "assign_sequence",
                                                    "sequence": seq_num,
                                                    "device_id": dev_id
                                                }
                                                payload = {
                                                    "target_device_id": dev_id,
                                                    "data": unicast_data
                                                }
                                        
                                                # Send command
                                                # Note: We are ignoring the parallel execution for now as it's just a few socket calls
                                                s_ok, s_resp = client.send_command("admin_unicast", payload)
                                                if s_ok and s_resp.get("success"):
                                                    auto_success_count += 1
                                                    results.append(f"✅ {alias}({dev_id}) -> Seq {seq_num}")
                                                else:
                                                    auto_fail_count += 1
                                                    results.append(f"❌ {alias}({dev_id}) -> Failed: {s_resp.get('message')}")
                                            else:
                                                results.append(f"⚠️ {dev_id}: 無法識別 Alias 或 OB 編號")
                                
                                        # Show results
                                        if auto_success_count > 0:
                                            st.success(f"成功分配 {auto_success_count} 台設備")
                                        if auto_fail_count > 0:
                                            st.error(f"失敗 {auto_fail_count} 台設備")
                                
                                        with st.expander("查看詳細結果", expanded=True):
                                            for r in results:
                                                st.text(r)
                                        
                                except Exception as e:
                                    st.error(f"❌ 執行失敗: {str(e)}")
                            else:
                                st.error("❌ Socket Server 未運行")
            

            
                    # Helper: Fetch players
                    online_players = []
                    if socket_running:
                        from core.socket_client import SocketClient
                        try:
                            with SocketClient(room.socket_ip, room.socket_port) as client:
                                    success, response = client.send_command("who")
                                    if success and "players" in response:
                                        online_players = response["players"]
                        except:
                            pass

                    # Prepare options
                    device_options = [p["device_id"] for p in online_players] if online_players else []
            
                    # If nothing found, maybe allow manual input or just show empty
            
                    # Format function for device display
                    def get_device_display(device_id):
                        # Hardcode alias for specific device
                        p_id = device_id
                        current_alias = ""
                        if "ebb89c" in p_id:
                            current_alias = "OB6"
                        elif "a5aaf9" in p_id:
                            current_alias = "OB7"
                        elif "f14b0e" in p_id:
                            current_alias = "OB5"
                        elif "640596" in p_id:
                            current_alias = "OB4"
                        elif "4b5c31" in p_id:
                            current_alias = "OB8"
                        elif "2ed155" in p_id:
                            current_alias = "OB9"
                        elif "af5776" in p_id:
                            current_alias = "OB2"
                        elif "03022c" in p_id:
                            current_alias = "OB3"
                
                        if current_alias:
                            return f"{current_alias} ({device_id})"

                        # Try to find device in registry
                        if 'device_registry' in st.session_state:
                            device = st.session_state.device_registry.get_device(device_id)
                            if device:
                                if device.notes:
                                    return f"{device.notes} ({device.device_id})"
                                if device.display_name and device.display_name != device.device_id:
                                    return f"{device.display_name} ({device.device_id})"
                        return device_id

                    col_sel, col_btn_ref = st.columns([3, 1])
                    with col_sel:
                        target_device_id = st.selectbox(
                            "選擇目標設備", 
                            options=device_options,
                            index=0 if device_options else None,
                            format_func=get_device_display,
                            key=f"seq_target_select_{room.room_id}",
                            help="選擇在線設備"
                        )
                    with col_btn_ref:
                        st.write("")
                        st.write("")
                        if st.button("🔄 刷新列表", key=f"btn_refresh_devs_{room.room_id}"):
                            st.rerun()

                    if not device_options:
                        st.caption("⚠️ 目前無在線設備，請確認設備已連接")

                    col_u_seq, col_u_btn = st.columns([2, 1])
                    with col_u_seq:
                        # Default to current sequence if possible? No, just 1 or whatever
                        new_sequence = st.number_input("新序列號", min_value=0, step=1, value=1, key=f"new_seq_{room.room_id}")
            
                    with col_u_btn:
                        st.write("")
                        st.write("")
                        if st.button("分配序列號 (Assign)", use_container_width=True, key=f"btn_assign_seq_{room.room_id}"):
                             if socket_running and target_device_id:
                                from core.socket_client import SocketClient
                                try:
                                    with SocketClient(room.socket_ip, room.socket_port) as client:
                                        unicast_data = {
                                            "message_type": "assign_sequence",
                                            "sequence": int(new_sequence),
                                            "device_id": target_device_id
                                        }
                                
                                        payload = {
                                            "target_device_id": target_device_id,
                                            "data": unicast_data
                                        }
                                
                                        success, response = client.send_command("admin_unicast", payload)
                                        if success and response.get("success"):
                                            st.success(f"✅ 已分配序列號 {new_sequence} 給 {target_device_id}")
                                        else:
                                            st.error(f"❌ 分配失敗: {response.get('message', '未知錯誤')}")
                                except Exception as e:
                                    st.error(f"❌ 連接失敗: {str(e)}")
                             elif not target_device_id:
                                 st.warning("⚠️ 請選擇目標設備")
                             else:
                                st.error("❌ Socket Server 未運行")

            # --- Status ---
            if st.button("📊 刷新玩家狀態", key=f"btn_refresh_status_{room.room_id}"):
                 if socket_running:
                    from core.socket_client import SocketClient
                    try:
                        with SocketClient(room.socket_ip, room.socket_port) as client:
                             success, response = client.send_command("who")
                             if success and "players" in response:
                                 players_data = response["players"]
                                 count = response.get("players_count", len(players_data))
                                 st.info(f"目前玩家數量 (Player Count): {count}")
                                 
                                 if players_data:
                                     # Convert to DataFrame for nice table
                                     import pandas as pd
                                     df = pd.DataFrame(players_data)
                                     
                                     # Reorder/Rename columns if they exist
                                     # Expected keys: device_id, chapter, sequence, message, timestamp, last_heartbeat, address
                                     cols_map = {
                                         "sequence": "Sequence",
                                         "device_id": "Device ID",
                                         "chapter": "Chapter",
                                         "message": "Message",
                                         "address": "IP Address",
                                         "last_heartbeat": "Last Heartbeat"
                                     }
                                     
                                     # Filter columns that actually exist
                                     cols_to_show = [c for c in ["sequence", "device_id", "chapter", "message", "address", "last_heartbeat"] if c in df.columns]
                                     
                                     df_display = df[cols_to_show].rename(columns=cols_map)
                                     
                                     # Format timestamp if needed? 
                                     # timestamp is often epoch ms.
                                     if "Last Heartbeat" in df_display.columns:
                                         df_display["Last Heartbeat"] = pd.to_datetime(df_display["Last Heartbeat"], unit='ms').dt.strftime('%H:%M:%S')

                                     st.dataframe(df_display, use_container_width=True, hide_index=True)
                                 else:
                                     st.info("暫無玩家連接")
                             else:
                                 st.warning("無法獲取玩家狀態")
                    except Exception as e:
                        st.error(f"錯: {e}")

        with tab2:
            # 日誌視窗
            from core.socket_client import read_socket_server_log
            
            # 讀取日誌
            log_lines = read_socket_server_log(room.room_id, room.socket_port, lines=200)
            
            if log_lines:
                # 顯示日誌（只讀文本框）
                log_text = ''.join(log_lines)
                # 使用動態 key 強制刷新 UI
                import time
                st.text_area(
                    "Socket Server 日誌",
                    value=log_text,
                    height=300,
                    disabled=True,
                    key=f"socket_log_{room.room_id}_{int(time.time())}"
                )
                
                # 自動滾動到底部
                import streamlit.components.v1 as components
                # 使用當前時間戳確保 JS 每次都會重新執行
                current_time = int(time.time() * 1000)
                js = f"""
                <script>
                    // Timestamp: {current_time}
                    function scrollBottom() {{
                        var textAreas = window.parent.document.querySelectorAll('textarea');
                        for (var i = 0; i < textAreas.length; i++) {{
                            if (textAreas[i].getAttribute('aria-label') === 'Socket Server 日誌') {{
                                textAreas[i].scrollTop = textAreas[i].scrollHeight;
                                break;
                            }}
                        }}
                    }}
                    // 嘗試多次滾動以確保渲染完成
                    setTimeout(scrollBottom, 100);
                    setTimeout(scrollBottom, 300);
                    setTimeout(scrollBottom, 500);
                </script>
                """
                components.html(js, height=0)
                
                # 刷新按鈕
                if st.button("🔄 刷新日誌", key=f"refresh_log_{room.room_id}"):
                    st.rerun()
            else:
                st.info("📝 日誌文件不存在或為空")
                if st.button("🔄 刷新日誌", key=f"refresh_log_{room.room_id}"):
                    st.rerun()
        
        with tab3:
            # 命令輸入欄
            st.markdown("**發送命令到 Socket Server**")
            
            # 命令類型選擇
            command_type = st.selectbox(
                "命令類型",
                options=["height_calibration"],
                index=0,
                help="選擇要發送的命令類型",
                key=f"command_type_{room.room_id}"
            )

            if command_type == "height_calibration":
                # Height Calibration Inputs
                col_h1, col_h2, col_h3 = st.columns(3)
                with col_h1:
                    h_chenyuhui = st.number_input("chenyuhui_height", value=0, step=1, key=f"h_cyh_{room.room_id}")
                with col_h2:
                    h_3in1 = st.number_input("3in1_height", value=0, step=1, key=f"h_3in1_{room.room_id}")
                with col_h3:
                    h_hollow = st.number_input("hollow_height", value=0, step=1, key=f"h_hollow_{room.room_id}")
                
                 # Target Device Selector (Optional: Broadcast if not selected?)
                 # User said: "send to A certain quest client"
                 # Target Device Selector
                all_devices = st.session_state.device_registry.get_all_devices()
                
                def format_device_option(option):
                    if option == "ALL":
                        return "📢 所有設備 (Broadcast)"
                    # Assume option is a Device object
                    display = f"{option.alias} ({option.device_id})" if option.alias else f"{option.device_id}"
                    return f"📱 {display}"

                target_device_selection = st.selectbox(
                    "目標設備 (Target Device)",
                    options=["ALL"] + all_devices,
                    index=0,
                    format_func=format_device_option,
                    help="選擇目標設備，顯示為：備註 (ID)",
                    key=f"h_target_{room.room_id}"
                )
                

            # 發送按鈕
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("📤 發送命令", type="primary", use_container_width=True, key=f"send_command_{room.room_id}"):
                    if socket_running:
                        from core.socket_client import SocketClient
                        
                        try:
                            with SocketClient(room.socket_ip, room.socket_port) as client:
                                # 準備數據
                                data = None
                                msg_type = "admin_broadcast" # Default wrapper
                                
                                if command_type == "height_calibration":
                                    # Inner message
                                    inner = {
                                        "message_type": "height_calibration",
                                        "chenyuhui_height": int(h_chenyuhui),
                                        "3in1_height": int(h_3in1),
                                        "hollow_height": int(h_hollow)
                                    }
                                    if target_device_selection != "ALL":
                                        inner["target_device_id"] = target_device_selection.device_id
                                    
                                    data = inner
                                
                                # 發送命令
                                success, response = client.send_command(msg_type, data)
                                
                                if success:
                                    st.success("✅ 命令發送成功")
                                    st.json(response)
                                else:
                                    st.error(f"❌ 命令發送失敗: {response.get('message', '未知錯誤')}")
                        except Exception as e:
                            st.error(f"❌ 連接失敗: {str(e)}")
                    else:
                        st.error("❌ Socket Server 未運行，無法發送命令")
            
            with col2:
                if st.button("🔄 刷新", use_container_width=True, key=f"refresh_command_{room.room_id}"):
                    st.rerun()
            
            # 顯示幫助信息
            # 顯示幫助信息
            with st.expander("💡 命令說明"):
                st.markdown("""
                **height_calibration**: 
                輸入三個高度參數 (int) 並發送給指定的 Quest 客戶端 (或廣播)。
                """)
        
        st.markdown("---")
    
    st.markdown("---")
    
    # 顯示設備列表
    if not room_devices:
        st.info("📭 房間內沒有設備，點擊「管理設備」添加設備")
        return
    
    st.markdown("### 📱 房間內設備")
    
    # 獲取設備詳細狀態
    from config.settings import DEVICE_UPDATE_INTERVAL
    import time as time_module
    
    # 使用標籤頁分隔不同狀態的設備
    tabs_data = []
    if online_devices:
        tabs_data.append(("🟢 在線", online_devices))
    if offline_devices:
        tabs_data.append(("🟠 離線", offline_devices))
    if not_connected_devices:
        tabs_data.append(("⚫ 未連接", not_connected_devices))
    
    if len(tabs_data) > 1:
        # 多個狀態，使用標籤頁
        tab_names = [f"{name} ({len(devs)})" for name, devs in tabs_data]
        tabs = st.tabs(tab_names)
        for tab, (name, devs) in zip(tabs, tabs_data):
            with tab:
                render_devices_in_room(devs, room)
    elif len(tabs_data) == 1:
        # 只有一種狀態，直接顯示
        _, devs = tabs_data[0]
        render_devices_in_room(devs, room)


def render_devices_in_room(devices, room):
    """在房間視圖中渲染設備卡片"""
    from config.constants import STATUS_ICONS
    from datetime import datetime
    import time as time_module
    
    # 使用網格佈局（每行 2 個卡片）
    cols_per_row = 2
    for i in range(0, len(devices), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, device in enumerate(devices[i:i+cols_per_row]):
            with cols[j]:
                # 狀態圖示
                status_icon = STATUS_ICONS.get(device.status, "❓")
                
                # 卡片容器
                with st.container(
                    border=True,
                    key=themed_card_key("device", room.room_id, device.device_id),
                ):
                    # 頂部：標題和選單按鈕
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"#### {status_icon} {device.display_name}")
                    with col2:
                        # 使用 popover 讓選單在按鈕正下方展開
                        with st.popover("⋮", use_container_width=False):
                            st.markdown("**操作選單**")
                            
                            # 執行動作
                            if device.is_online:
                                if st.button("⚡ 執行動作", key=f"room_dev_action_{device.device_id}", use_container_width=True):
                                    # 關閉房間視圖，打開執行動作對話框
                                    # 保存房間信息到 session state，以便在對話框中使用
                                    st.session_state[f'execute_action_room_{device.device_id}'] = room.room_id
                                    st.session_state[f'show_room_view_{room.room_id}'] = False
                                    st.session_state[f'execute_action_on_{device.device_id}'] = True
                                    st.rerun()
                            else:
                                st.button("⚡ 執行動作", key=f"room_dev_action_{device.device_id}", use_container_width=True, disabled=True)
                                st.caption("（設備離線）")
                            
                            # 監看設備
                            if device.is_online:
                                if st.button("📺 監看設備", key=f"room_dev_monitor_{device.device_id}", use_container_width=True):
                                    success, message = start_room_device_monitor(device, room)
                                    if success:
                                        st.success(f"✅ {message}")
                                    else:
                                        st.error(f"❌ {message}")
                                    time_module.sleep(0.5)
                            
                            st.divider()
                            
                            # 移出房間
                            if st.button("🚪 移出房間", key=f"room_dev_remove_{device.device_id}", use_container_width=True, type="secondary"):
                                success, msg = st.session_state.room_registry.remove_device_from_room(
                                    room.room_id,
                                    device.device_id
                                )
                                if success:
                                    st.success(f"✅ {msg}")
                                    time_module.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")
                    
                    # 設備信息
                    st.caption(f"序號: {device.serial}")
                    
                    if device.notes:
                        st.caption(f"備註: {device.notes}")
                    
                    # 連線信息
                    if device.is_online:
                        st.success(f"🟢 在線 - {device.connection_string}")
                        
                        # 獲取詳細狀態
                        device_status = st.session_state.adb_manager.get_device_status(device.connection_string)
                        
                        if device_status:
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                if device_status.get('battery_level') is not None:
                                    battery = device_status['battery_level']
                                    st.metric("電量", f"{battery}%")
                                
                                if device_status.get('temperature') is not None:
                                    temp = device_status['temperature']
                                    st.metric("溫度", f"{temp}°C")
                            
                            with col2:
                                if device_status.get('is_awake') is not None:
                                    awake_status = "👁️ 清醒" if device_status['is_awake'] else "😴 休眠"
                                    st.caption(awake_status)
                                
                                if device_status.get('uptime_seconds') is not None:
                                    uptime = device_status['uptime_seconds']
                                    hours = uptime // 3600
                                    minutes = (uptime % 3600) // 60
                                    st.caption(f"⏱️ 運行時間: {hours}h {minutes}m")
                    else:
                        st.error("🔴 離線")


from components.time_reminder import time_reminder_component
import pandas as pd
import math


from components.time_reminder import time_reminder_component
import pandas as pd
import math
import json
import os

TIME_EVENTS_FILE = "/Users/imlab/Downloads/QQQuest/time_events.json"

def load_time_events(file_path=TIME_EVENTS_FILE):
    """讀取 time_events.json 並解析為事件列表"""
    try:
        if not os.path.exists(file_path):
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            events_raw = json.load(f)
            
        # Parse seconds
        events = []
        for ev in events_raw:
            raw_time = ev.get('time', '')
            content = ev.get('content', '')
            if not raw_time: continue
            
            seconds = -1
            try:
                parts = raw_time.split(':')
                if len(parts) == 2:
                    seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                     seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif raw_time.isdigit():
                    seconds = int(raw_time)
            except:
                pass
            
            if seconds >= 0:
                events.append({
                    "seconds": seconds,
                    "rawTime": raw_time,
                    "content": content
                })
        
        events.sort(key=lambda x: x['seconds'])
        return events
    except Exception as e:
        import logging
        logging.error(f"Failed to load time_events.json: {e}")
        return []

def save_time_events(df_data):
    """將 DataFrame 資料保存回 JSON"""
    try:
        # Convert df to list of dicts {time, content}
        events = []
        for _, row in df_data.iterrows():
            t = str(row.get('time', '')).strip()
            c = str(row.get('content', '')).strip()
            if t:
                events.append({'time': t, 'content': c})
        
        with open(TIME_EVENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        import logging
        logging.error(f"Failed to save time_events.json: {e}")
        return False

def render_time_config():
    """渲染送茶時間設定 UI"""
    with st.expander("⏱️ 送茶時間設定 (Tea Time Config)", expanded=False):
        # Load existing data (raw)
        data = []
        if os.path.exists(TIME_EVENTS_FILE):
             with open(TIME_EVENTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # Create DataFrame for editor
        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(columns=["time", "content"])
            
        edited_df = st.data_editor(
            df,
            column_config={
                "time": st.column_config.TextColumn("時間 (MM:SS)", help="例如 05:30 或 120", required=True),
                "content": st.column_config.TextColumn("內容", help="提示文字", required=True)
            },
            num_rows="dynamic",
            use_container_width=True,
            key="time_config_editor"
        )
        
        if st.button("💾 保存設定 (Save Config)"):
            if save_time_events(edited_df):
                st.success("✅ 設定已保存")
                st.rerun()
            else:
                st.error("❌ 保存失敗")



def render_room_card(room: Room):
    """渲染房間卡片"""
    # 獲取房間內設備
    room_devices = st.session_state.room_registry.get_room_devices(
        room.room_id,
        st.session_state.device_registry
    )
    
    online_count = len([d for d in room_devices if d.status == DeviceStatus.ONLINE])
    offline_count = len([d for d in room_devices if d.status == DeviceStatus.OFFLINE])
    not_connected_count = len([d for d in room_devices if d.status == DeviceStatus.NOT_CONNECTED])
    
    # 卡片容器
    with st.container(border=True, key=themed_card_key("room", room.room_id)):
        # 頂部：標題和選單按鈕
        col1, col2 = st.columns([5, 1])
        with col1:
            # 可點擊的房間名稱（通過增加列寬度和減少每行卡片數量來顯示更多內容）
            if st.button(
                f"{room.display_name}",
                key=f"btn_room_name_{room.room_id}",
                use_container_width=True,
                type="secondary"
            ):
                st.session_state[f'show_room_view_{room.room_id}'] = True
                st.rerun()
        with col2:
            # 使用 popover 讓選單在按鈕正下方展開
            with st.popover("⋮", use_container_width=False):
                st.markdown("**操作選單**")
                
                # 執行動作
                if room.device_count > 0:
                    if st.button("⚡ 執行動作", key=f"btn_execute_action_room_{room.room_id}", use_container_width=True):
                        st.session_state[f'show_execute_action_room_{room.room_id}'] = True
                        st.rerun()
                else:
                    st.button("⚡ 執行動作", key=f"btn_execute_action_room_{room.room_id}", use_container_width=True, disabled=True)
                    st.caption("（房間內無設備）")
                
                # 管理設備
                if st.button("➕ 管理設備", key=f"btn_manage_devices_{room.room_id}", use_container_width=True):
                    st.session_state[f'show_manage_devices_{room.room_id}'] = True
                    st.rerun()
                
                # 重新連接設備
                if room.device_count > 0:
                    if st.button("🔌 重新連接", key=f"btn_reconnect_room_{room.room_id}", use_container_width=True):
                        st.session_state[f'show_reconnect_room_{room.room_id}'] = True
                        st.rerun()
                else:
                    st.button("🔌 重新連接", key=f"btn_reconnect_room_{room.room_id}", use_container_width=True, disabled=True)
                    st.caption("（房間內無設備）")
                
                # 重新啟動 Socket Server
                if room.socket_ip and room.socket_port:
                    # 檢查 Socket Server 狀態
                    is_running = False
                    if 'socket_server_manager' in st.session_state:
                        socket_manager = st.session_state.socket_server_manager
                        is_running = socket_manager.is_server_running(room.room_id)
                    
                    status_text = "🟢 運行中" if is_running else "🔴 未運行"
                    if st.button(f"🔄 重啟 Socket Server ({status_text})", key=f"btn_restart_socket_{room.room_id}", use_container_width=True):
                        st.session_state[f'restart_socket_{room.room_id}'] = True
                        st.rerun()
                    st.caption(f"📡 {room.socket_ip}:{room.socket_port}")
                
                st.divider()
                
                # 編輯房間
                if st.button("✏️ 編輯房間", key=f"edit_{room.room_id}", use_container_width=True):
                    st.session_state[f'edit_room_{room.room_id}'] = True
                    st.rerun()
                
                # 刪除房間
                if st.button("🗑️ 刪除房間", key=f"delete_{room.room_id}", use_container_width=True, type="secondary"):
                    st.session_state[f'delete_room_{room.room_id}'] = True
                    st.rerun()
        
        # 房間描述
        if room.description:
            st.caption(room.description)
        
        # 房間統計
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("設備數量", room.capacity_text)
        
        with col2:
            st.metric("🟢 在線", online_count)
        
        with col3:
            st.metric("🟠 離線", offline_count)
        
        with col4:
            st.metric("⚫ 未連接", not_connected_count)
        
        # 容量警告
        if room.max_devices > 0 and room.device_count >= room.max_devices:
            st.warning("⚠️ 房間已滿")


def main():
    """主函式"""
    st.title("🏠 房間管理")
    st.caption("建立和管理房間，批量控制多台設備")
    
    # 頂部操作列
    col1, col2 = st.columns([5, 1])
    
    with col1:
        st.caption("💡 提示：點擊「新增房間」創建房間，然後在房間中加入設備")
    
    with col2:
        if st.button("➕ 新增房間", use_container_width=True, type="primary"):
            st.session_state.show_add_room_dialog = True
            st.rerun()
    
    st.markdown("---")
    
    # 獲取所有房間
    rooms = st.session_state.room_registry.get_all_rooms()
    
    # 顯示統計
    if rooms:
        stats = st.session_state.room_registry.get_statistics()
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("📊 房間總數", stats.get('total_rooms', 0))
        col2.metric("📱 總設備數", stats.get('total_devices', 0))
        col3.metric("🏠 有設備的房間", stats.get('rooms_with_devices', 0))
        col4.metric("📭 空房間", stats.get('empty_rooms', 0))
        
        st.markdown("---")
    
    # 顯示房間列表
    if not rooms:
        st.info("🏠 還沒有任何房間，點擊「新增房間」開始創建")
    else:
        # 使用網格佈局（每行 2 個卡片，增加卡片寬度以顯示更多內容）
        cols_per_row = 2
        for i in range(0, len(rooms), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, room in enumerate(rooms[i:i+cols_per_row]):
                with cols[j]:
                    render_room_card(room)
    
    # 處理對話框
    if st.session_state.get('show_add_room_dialog'):
        add_room_dialog()
    
    # 處理設備執行動作對話框（房間視圖中觸發）
    all_devices = st.session_state.device_registry.get_all_devices()
    for device in all_devices:
        if st.session_state.get(f'execute_action_on_{device.device_id}'):
            # 獲取房間信息（如果從房間視圖觸發）
            device_room = None
            room_id = st.session_state.get(f'execute_action_room_{device.device_id}')
            if room_id:
                device_room = st.session_state.room_registry.get_room(room_id)
            else:
                # 如果沒有保存的房間 ID，嘗試查找設備所屬的房間
                device_room = st.session_state.room_registry.get_device_room(device.device_id)
            execute_device_action_dialog(device, device_room)
    
    # 處理房間對話框
    for room in rooms:
        if st.session_state.get(f'show_room_view_{room.room_id}'):
            room_view_dialog(room)
        
        if st.session_state.get(f'edit_room_{room.room_id}'):
            edit_room_dialog(room)
        
        if st.session_state.get(f'delete_room_{room.room_id}'):
            delete_room_dialog(room)
        
        if st.session_state.get(f'show_manage_devices_{room.room_id}'):
            manage_devices_dialog(room)
        
        if st.session_state.get(f'show_execute_action_room_{room.room_id}'):
            execute_action_on_room_dialog(room)
        
        if st.session_state.get(f'show_reconnect_room_{room.room_id}'):
            reconnect_room_devices_dialog(room)
        
        # 處理重新啟動 Socket Server
        if st.session_state.get(f'restart_socket_{room.room_id}'):
            if room.socket_ip and room.socket_port:
                if 'socket_server_manager' in st.session_state:
                    socket_manager = st.session_state.socket_server_manager
                    with st.spinner("正在重啟 Socket Server..."):
                        success, msg = socket_manager.restart_server(
                            room.room_id,
                            room.name,
                            room.socket_ip,
                            room.socket_port,
                            room.saved_user_position_z
                        )
                        if success:
                            st.success(f"✅ Socket Server 已重啟: {room.socket_ip}:{room.socket_port}")
                            logger.info(f"✅ 重啟 Socket Server 成功: {room.name} ({room.socket_ip}:{room.socket_port})")
                        else:
                            st.error(f"❌ Socket Server 重啟失敗: {msg}")
                            logger.error(f"❌ 重啟 Socket Server 失敗: {room.name} - {msg}")
                        time.sleep(1)
                else:
                    st.error("❌ Socket Server 管理器未初始化")
                    time.sleep(1)
            else:
                st.warning("⚠️ 此房間未配置 Socket Server")
                time.sleep(1)
            
            st.session_state[f'restart_socket_{room.room_id}'] = False
            st.rerun()


if __name__ == "__main__":
    main()
