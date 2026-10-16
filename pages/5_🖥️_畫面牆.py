"""
畫面牆 (Screen Wall)

監控方式可切換：
  • 🖥️ scrcpy：一鍵依「螢幕大小 + 設備數」自動排版開原生視窗（高畫質），
    另有裝置端縮圖牆（省頻寬、可同時看很多台，需 ffmpeg）。
  • ⚡ WebRTC：代管 vrcontrol（Go + Pion WebRTC），瀏覽器硬體解碼，更即時流暢；
    以 iframe 嵌入其房間監控牆頁。
"""
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import time
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(page_title="畫面牆 - QQQuest", page_icon="🖥️", layout="wide")

from utils.init import ensure_initialization
if not ensure_initialization():
    st.stop()

from core.vrcontrol_manager import get_vrcontrol_manager

adb = st.session_state.adb_manager
registry = st.session_state.device_registry
has_ffmpeg = adb.ffmpeg_available()

st.title("🖥️ 畫面牆 (Screen Wall)")

online = [d for d in registry.get_all_devices() if d.is_online]
if not online:
    st.info("目前沒有在線設備。先到「📱 設備管理」連線，再回來。")
    st.stop()

# 選要監看的設備（兩種模式共用）
device_labels = {d.device_id: d.display_name for d in online}
selected_ids = st.multiselect(
    "選擇設備",
    options=[d.device_id for d in online],
    default=[d.device_id for d in online],
    format_func=lambda did: device_labels.get(did, did),
)
selected = [d for d in online if d.device_id in selected_ids]
if not selected:
    st.info("請至少選一台設備。")
    st.stop()

# --- 監控方式切換 ---
SCRCPY_MODE = "🖥️ scrcpy"
WEBRTC_MODE = "⚡ WebRTC"
if "wall_mode" not in st.session_state:
    st.session_state.wall_mode = SCRCPY_MODE
mode = st.segmented_control("監控方式", [SCRCPY_MODE, WEBRTC_MODE], key="wall_mode")
if mode is None:
    mode = SCRCPY_MODE

st.divider()

# ======================================================================
# ⚡ WebRTC 模式（vrcontrol 後端 + QQQuest 自建畫面格）
# ======================================================================
if mode == WEBRTC_MODE:
    st.caption("WebRTC 串流：瀏覽器硬體解碼，比 scrcpy 視窗更即時流暢。畫面格由 QQQuest 直接繪製，只用 vrcontrol 的串流後端。")
    manager = get_vrcontrol_manager()
    running = manager.is_running()

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if running:
            if st.button("🛑 停止串流服務", use_container_width=True):
                ok, msg = manager.stop()
                st.session_state.pop("vrc_synced", None)
                st.session_state.pop("vrc_devmap", None)
                (st.success if ok else st.error)(msg)
                time.sleep(0.5)
                st.rerun()
        else:
            if st.button("🚀 啟動串流服務", type="primary", use_container_width=True):
                with st.spinner("啟動 vrcontrol 串流服務中…"):
                    ok, msg = manager.start()
                (st.success if ok else st.error)(msg)
                if ok:
                    time.sleep(0.5)
                    st.rerun()
    with c2:
        if running and st.button("🔄 重新同步設備", use_container_width=True):
            st.session_state.pop("vrc_synced", None)
            st.session_state.pop("vrc_devmap", None)
    with c3:
        st.caption(("🟢 執行中" if running else "⚪ 未啟動") + f" · 串流後端 :{manager.api_port}")

    if not running:
        st.info("按「🚀 啟動串流服務」後即可看到 WebRTC 監控牆。")
        st.stop()

    # 選取的設備先確保存在於 vrcontrol（選取變了才重打 API；
    # 失敗也記下 sel_key，避免每次 rerun 都重試——重試靠「🔄 重新同步設備」）
    sel_key = tuple(sorted(d.connection_string for d in selected))
    if st.session_state.get("vrc_synced") != sel_key:
        with st.spinner("同步設備…"):
            ok, msg, mapping = manager.ensure_devices(selected)
        st.session_state.vrc_synced = sel_key
        st.session_state.vrc_devmap = mapping
        if not ok:
            st.warning(msg)

    devmap = st.session_state.get("vrc_devmap") or {}
    tiles = [{"id": devmap[d.connection_string], "label": d.display_name}
             for d in selected if d.connection_string in devmap]
    if not tiles:
        st.error("沒有可串流的設備。請按「🔄 重新同步設備」重試。")
        st.stop()

    # 畫面更新頻率（FPS）：寫進 vrcontrol 串流設定；重啟串流才會立即生效
    FPS_OPTIONS = [1, 2, 5, 10, 15, 20, 30, 60]
    current_cfg = manager.get_stream_config() or {}
    current_fps = int(current_cfg.get('max_fps') or 0)  # 0 = 未設定（無上限）
    snapped_fps = min(FPS_OPTIONS, key=lambda o: abs(o - (current_fps or 60)))
    f1, f2 = st.columns([3, 1])
    with f1:
        webrtc_fps = st.select_slider(
            "畫面更新頻率（FPS，每秒傳幾張）",
            options=FPS_OPTIONS, value=snapped_fps,
            help="數字越小越省頻寬/CPU，但畫面越不流暢。套用時會重啟串流（約 2 秒黑一下）。",
        )
    with f2:
        st.write("")  # 對齊
        if st.button("✅ 套用 FPS", use_container_width=True, disabled=(webrtc_fps == current_fps)):
            ok, msg = manager.set_stream_fps(webrtc_fps)
            if ok:
                ok2, msg2 = manager.restart_server()
                (st.success if ok2 else st.warning)(msg2)
                if ok2:
                    time.sleep(0.5)
                    st.rerun()
            else:
                st.error(msg)

    g1, g2 = st.columns(2)
    with g1:
        wall_cols = st.slider("每列格數", min_value=1, max_value=6, value=min(3, max(1, len(tiles))))
    with g2:
        wall_height = st.slider("牆面高度 (px)", min_value=400, max_value=1600, value=820, step=20)

    # 自建的純畫面格：每台一條 signaling WS + RTCPeerConnection（協定同 vrcontrol 前端），
    # 用瀏覽器自己的 hostname 連後端——從別台電腦開 Streamlit 也通。斷線自動重連。
    import json as _json
    wall_html = """
<style>
  #wall { display: grid; grid-template-columns: repeat(__COLS__, 1fr); gap: 8px;
          font-family: -apple-system, "PingFang TC", sans-serif; }
  .tile { position: relative; background: #000; border-radius: 8px; overflow: hidden;
          aspect-ratio: 16/9; }
  .tile video { width: 100%; height: 100%; object-fit: contain; display: block; }
  .lbl { position: absolute; left: 6px; top: 6px; padding: 2px 8px; font-size: 12px;
         color: #fff; background: rgba(0,0,0,.55); border-radius: 6px; }
  .st  { position: absolute; right: 6px; top: 6px; padding: 2px 8px; font-size: 11px;
         color: #fff; background: rgba(0,0,0,.55); border-radius: 6px; }
  .st.live { background: rgba(22,163,74,.8); }
  .st.err  { background: rgba(220,38,38,.8); }
  .msg { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
         color: rgba(255,255,255,.75); font-size: 12px; text-align: center; padding: 8px; }
</style>
<div id="wall"></div>
<script>
(function () {
  const DEVICES = __DEVICES__;
  const API_PORT = __API_PORT__;
  // components.html 是 srcdoc iframe（location = about:srcdoc，hostname 為空），
  // 必須取「父頁面」的主機名，手機等其他裝置開啟時才會連到 Mac 而不是自己。
  function resolveHost() {
    try { if (window.parent.location.hostname) return window.parent.location.hostname; } catch (e) {}
    try { if (document.referrer) return new URL(document.referrer).hostname; } catch (e) {}
    return window.location.hostname || "localhost";
  }
  const host = resolveHost();
  const wall = document.getElementById("wall");

  DEVICES.forEach(function (dev) {
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML = '<video autoplay muted playsinline></video>' +
      '<div class="lbl"></div><div class="st">連線中…</div><div class="msg">正在建立串流…</div>';
    tile.querySelector(".lbl").textContent = dev.label;
    wall.appendChild(tile);
    connect(tile, dev.id);
  });

  function connect(tile, deviceId) {
    const video = tile.querySelector("video");
    const stEl = tile.querySelector(".st");
    const msgEl = tile.querySelector(".msg");
    let pc = null, ws = null, dead = false;
    const pendingOut = [], pendingCand = [];

    function setStatus(cls, text, msg) {
      stEl.className = "st" + (cls ? " " + cls : "");
      stEl.textContent = text;
      msgEl.style.display = msg ? "flex" : "none";
      msgEl.textContent = msg || "";
    }

    function send(m) {
      if (dead) return;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(m));
      else pendingOut.push(m);
    }

    function retry(reason) {
      if (dead) return;
      dead = true;
      try { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "close" })); } catch (e) {}
      try { if (ws) ws.close(); } catch (e) {}
      try { if (pc) pc.close(); } catch (e) {}
      setStatus("err", "重連中", reason + "，5 秒後自動重連…");
      setTimeout(function () { connect(tile, deviceId); }, 5000);
    }

    pc = new RTCPeerConnection();
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = function (e) {
      video.srcObject = (e.streams && e.streams[0]) || new MediaStream([e.track]);
      video.play().catch(function () {});
      setStatus("live", "LIVE", "");
    };
    pc.onicecandidate = function (e) {
      send({ type: "ice", candidate: e.candidate ? e.candidate.toJSON() : undefined });
    };
    pc.onconnectionstatechange = function () {
      if (dead) return;
      if (pc.connectionState === "failed") retry("連線失敗");
      else if (pc.connectionState === "disconnected") setStatus("", "斷線", "訊號中斷，等待恢復…");
      else if (pc.connectionState === "connected" && video.srcObject) setStatus("live", "LIVE", "");
    };

    ws = new WebSocket("ws://" + host + ":" + API_PORT + "/api/ws/webrtc/" + encodeURIComponent(deviceId));
    ws.onopen = function () {
      pc.createOffer().then(function (offer) {
        return pc.setLocalDescription(offer);
      }).then(function () {
        while (pendingOut.length) ws.send(JSON.stringify(pendingOut.shift()));
        send({ type: "offer", sdp: pc.localDescription.sdp });
      }).catch(function () { retry("無法建立串流請求"); });
    };
    ws.onmessage = function (ev) {
      if (dead) return;
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.type === "answer" && m.sdp) {
        pc.setRemoteDescription({ type: "answer", sdp: m.sdp }).then(function () {
          const flush = pendingCand.splice(0);
          flush.forEach(function (c) { pc.addIceCandidate(c).catch(function () {}); });
        }).catch(function () { retry("協商失敗"); });
      } else if (m.type === "ice") {
        if (!m.candidate) { if (pc.remoteDescription) pc.addIceCandidate(null).catch(function () {}); }
        else if (pc.remoteDescription) pc.addIceCandidate(m.candidate).catch(function () {});
        else pendingCand.push(m.candidate);
      } else if (m.type === "error") {
        retry("串流錯誤：" + (m.error || "unknown"));
      }
    };
    ws.onerror = function () { retry("WebSocket 連線失敗"); };
    ws.onclose = function () { if (!dead) retry("連線中斷"); };
  }
})();
</script>
"""
    wall_html = (wall_html
                 .replace("__DEVICES__", _json.dumps(tiles, ensure_ascii=False))
                 .replace("__COLS__", str(wall_cols))
                 .replace("__API_PORT__", str(manager.api_port)))
    components.html(wall_html, height=wall_height, scrolling=True)
    st.caption(f"共 {len(tiles)} 台 · WebRTC 串流（後端 vrcontrol :{manager.api_port}）")
    st.stop()

# ======================================================================
# 🖥️ scrcpy 模式（原生視窗牆 + 縮圖牆）
# ======================================================================
st.caption("一鍵開 scrcpy 原生監控牆（高畫質），或看省頻寬的縮圖牆（可同時看很多台）。")

# 畫面更新頻率（FPS）：本次開視窗用的 --max-fps；預設值來自「系統設定 → scrcpy 監看設定」
from config.settings import get_user_config
SCRCPY_FPS_OPTIONS = [5, 10, 15, 20, 30, 60]
_cfg_fps = int(get_user_config().get('scrcpy', {}).get('max_fps') or 15)
scrcpy_fps = st.select_slider(
    "畫面更新頻率（FPS，每秒傳幾張）",
    options=SCRCPY_FPS_OPTIONS,
    value=min(SCRCPY_FPS_OPTIONS, key=lambda o: abs(o - _cfg_fps)),
    help="數字越小越省頻寬/CPU。只對「接下來開啟」的視窗生效；已開的視窗要關掉重開。",
)

bcol1, bcol2 = st.columns(2)
with bcol1:
    open_scrcpy = st.button(
        f"🖥️ 開啟 scrcpy 監控牆（{len(selected)} 台，自動排版）",
        use_container_width=True, type="primary",
    )
with bcol2:
    stop_scrcpy = st.button("🛑 關閉所有 scrcpy 視窗", use_container_width=True)

if open_scrcpy:
    total = len(selected)
    st.toast(f"將依序開啟 {total} 台的 scrcpy 監看視窗…", icon="🖥️")
    ptext = st.empty()
    prog = st.progress(0)
    adb.reset_scrcpy_window_layout()
    ok = 0
    fails = []
    for idx, d in enumerate(selected):
        ptext.text(f"正在開啟 {idx + 1}/{total}: {d.display_name}")
        success, msg = adb.start_quest_single_eye_scrcpy(
            d.connection_string,
            window_title=d.display_name,
            options={'layout_slot': idx, 'layout_total': total, 'max_fps': scrcpy_fps},
            auto_arrange=True,
        )
        if success:
            ok += 1
        else:
            fails.append(f"{d.display_name}: {msg}")
        prog.progress((idx + 1) / total)
        time.sleep(1.2)  # 逐一開，讓自動排版就位
    ptext.empty()
    prog.empty()
    if not fails:
        st.success(f"✅ 已依螢幕自動排版開啟 {ok} 台 scrcpy 視窗")
    else:
        st.warning(f"⚠️ 開啟 {ok} 台，失敗 {len(fails)} 台：\n" + "\n".join(fails))

if stop_scrcpy:
    import subprocess
    try:
        subprocess.run(["pkill", "scrcpy"])
        adb.reset_scrcpy_window_layout()
        st.success("已關閉所有 scrcpy 視窗")
    except Exception as e:
        st.error(f"關閉失敗: {e}")

st.divider()

# --- 縮圖牆（裝置端縮圖，需 ffmpeg）---
st.subheader("🖼️ 縮圖牆（省頻寬 · 自動更新）")
if not has_ffmpeg:
    st.error("❌ 找不到 ffmpeg，縮圖牆無法使用（請 `brew install ffmpeg`）。可改用上方的 scrcpy 監控牆。")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
with c1:
    interval = st.slider("更新間隔（秒）", min_value=3, max_value=120, value=8)
with c2:
    thumb_w = st.select_slider("縮圖寬度 (px)", options=[240, 320, 400, 480], value=320)
with c3:
    cols_per_row = st.slider("每列張數", min_value=2, max_value=6, value=4)
with c4:
    quality = st.slider("JPEG 品質", min_value=20, max_value=90, value=50)

# 自動刷新（只刷新縮圖牆）
st_autorefresh(interval=interval * 1000, key="screenwall_refresh")
st.caption(f"縮圖牆 {len(selected)} 台 · 每 {interval}s · 寬 {thumb_w}px · {datetime.now().strftime('%H:%M:%S')}")


def grab(device):
    return device, adb.capture_screenshot(
        device.connection_string, max_width=thumb_w, quality=quality, method="ondevice"
    )


with st.spinner(f"擷取 {len(selected)} 台畫面中…"):
    with ThreadPoolExecutor(max_workers=min(10, len(selected))) as ex:
        results = list(ex.map(grab, selected))

ok_count = sum(1 for _, img in results if img)
if ok_count < len(results):
    st.caption(f"✅ 成功 {ok_count}/{len(results)} 台（失敗多半是設備睡著或剛掉線）")

cols = st.columns(cols_per_row)
for i, (device, img) in enumerate(results):
    with cols[i % cols_per_row]:
        if img:
            st.image(img, caption=device.display_name, use_container_width=True)
        else:
            st.markdown(f"**{device.display_name}**")
            st.warning("擷取失敗")
