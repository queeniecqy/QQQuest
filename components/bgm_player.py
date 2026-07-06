"""背景音樂 (BGM) 播放元件。

在「控制端瀏覽器」播放 bgm 資料夾裡的 mp3：
  - 開始：音量從 0 漸入到目標音量，並循環播放（單曲 loop／多曲輪播後回頭）。
  - 暫停：音量漸淡出後停住（保留播放位置，下次開始再淡入續播）。

元件是自包含的（開始／暫停按鈕與所有音訊控制都在 iframe 內的 JS），
所以 Streamlit 重新執行(rerun)時只要傳入內容不變，iframe 會被保留、音樂不中斷。
"""

import os
import json
import base64

import streamlit as st
import streamlit.components.v1 as components


def default_bgm_dir():
    """專案根目錄下的 bgm 資料夾（相對於本檔位置解析，最穩定）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bgm")


def list_bgm_tracks(bgm_dir=None):
    """回傳 bgm_dir 內的 mp3 清單 [{name, path}]，依檔名排序；資料夾不存在會自動建立。"""
    if bgm_dir is None:
        bgm_dir = default_bgm_dir()
    os.makedirs(bgm_dir, exist_ok=True)
    names = sorted(
        f for f in os.listdir(bgm_dir)
        if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(bgm_dir, f))
    )
    return [{"name": f, "path": os.path.join(bgm_dir, f)} for f in names]


@st.cache_data(show_spinner=False)
def _encode_track(path, size, mtime):
    """把 mp3 讀檔並 base64 編成 data URI。用 (path, size, mtime) 當快取鍵，
    檔案沒變就不重複讀檔／編碼，避免每次 rerun 都重算幾 MB 的 base64。"""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return "data:audio/mpeg;base64," + b64


def bgm_player_component(tracks, fade_in=4.0, fade_out=4.0, volume=0.8, height=250):
    """渲染 BGM 播放器。

    tracks: [{name, path}]（通常用 list_bgm_tracks() 取得）。
    fade_in / fade_out: 淡入／淡出秒數。
    volume: 目標音量 0~1（可在元件內用滑桿即時調整，不會中斷播放）。
    """
    track_data = []
    for t in tracks:
        try:
            src = _encode_track(t["path"], os.path.getsize(t["path"]), os.path.getmtime(t["path"]))
            track_data.append({"name": t["name"], "src": src})
        except Exception:
            # 單一檔案讀取失敗就略過，不影響其他曲目
            continue

    payload = json.dumps({
        "tracks": track_data,
        "fadeIn": float(fade_in),
        "fadeOut": float(fade_out),
        "volume": max(0.0, min(1.0, float(volume))),
    })

    components.html(_TEMPLATE.replace("__PAYLOAD__", payload), height=height)


_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {
    --bg: #262831; --surface: #303340; --border: #4e5261; --text: #e3e6ef;
    --muted: #a8afc1; --btn: #434857; --btn-hover: #4e5261;
    --play: #2f9e6b; --play-hover: #37b67c; --pause: #b06a3a; --pause-hover: #c77c46;
    --accent: #6f8bd6;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Helvetica Neue", Arial, "Apple Color Emoji"; }
  .bgm { padding: 12px; }
  .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .btn { border: 1px solid var(--border); border-radius: 10px; padding: 9px 16px;
    color: var(--text); cursor: pointer; font-size: 15px; transition: background .15s ease, transform .1s ease; }
  .btn:hover { transform: translateY(-1px); }
  .btn.play { background: var(--play); border-color: var(--play); }
  .btn.play:hover { background: var(--play-hover); }
  .btn.pause { background: var(--pause); border-color: var(--pause); }
  .btn.pause:hover { background: var(--pause-hover); }
  .btn:disabled { opacity: .5; cursor: default; transform: none; }
  .status { color: var(--muted); font-size: 13px; margin-left: 4px; }
  .now { margin: 12px 0 6px; font-size: 15px; color: var(--text); }
  .volwrap { display: flex; align-items: center; gap: 10px; margin: 6px 0 10px; }
  .volwrap label { font-size: 12px; color: var(--muted); white-space: nowrap; }
  input[type=range] { flex: 1; accent-color: var(--accent); }
  .bar { height: 6px; background: #3a3e4c; border-radius: 999px; overflow: hidden; }
  .bar .fill { height: 100%; width: 0%; background: linear-gradient(90deg, var(--play), var(--accent)); transition: width .08s linear; }
  .list { list-style: none; margin: 12px 0 0; padding: 0; max-height: 90px; overflow-y: auto; }
  .list li { font-size: 13px; color: var(--muted); padding: 4px 6px; border-radius: 6px; }
  .list li.active { color: var(--text); background: #353947; }
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-thumb { background: #4b5060; border-radius: 4px; }
</style>
</head>
<body>
  <div class="bgm">
    <div class="row">
      <button id="btnStart" class="btn play">▶ 開始</button>
      <button id="btnPause" class="btn pause">⏸ 暫停</button>
      <span id="status" class="status">待機</span>
    </div>

    <div id="now" class="now">—</div>

    <div class="volwrap">
      <label>音量</label>
      <input id="volSlider" type="range" min="0" max="100" value="80" />
      <span id="volPct" class="status" style="margin:0; min-width:36px; text-align:right;">80%</span>
    </div>
    <div class="bar"><div id="fill" class="fill"></div></div>

    <ul id="list" class="list"></ul>
  </div>

<script>
  const CONFIG = __PAYLOAD__;
  const tracks = CONFIG.tracks || [];
  const fadeInMs = (CONFIG.fadeIn || 0) * 1000;
  const fadeOutMs = (CONFIG.fadeOut || 0) * 1000;
  let targetVol = clamp01(CONFIG.volume != null ? CONFIG.volume : 0.8);

  const audio = new Audio();
  audio.preload = "auto";
  audio.loop = tracks.length <= 1;          // 單曲用原生 loop（無縫）；多曲用 ended 事件輪播

  let idx = 0;
  let state = "stopped";                      // stopped | playing | paused
  let fadeTimer = null;

  const elStatus = document.getElementById("status");
  const elNow = document.getElementById("now");
  const elFill = document.getElementById("fill");
  const elList = document.getElementById("list");
  const elVol = document.getElementById("volSlider");
  const elVolPct = document.getElementById("volPct");
  const btnStart = document.getElementById("btnStart");
  const btnPause = document.getElementById("btnPause");

  function clamp01(x) { return Math.max(0, Math.min(1, x)); }
  function setStatus(s) { elStatus.textContent = s; }
  function setFill() { elFill.style.width = Math.round(audio.volume * 100) + "%"; }

  function renderNow() {
    elNow.textContent = tracks.length ? ("♪ " + tracks[idx].name) : "bgm 資料夾沒有 mp3";
    elList.innerHTML = "";
    tracks.forEach((t, i) => {
      const li = document.createElement("li");
      li.textContent = (i === idx && state === "playing" ? "▶ " : "") + t.name;
      if (i === idx && state === "playing") li.className = "active";
      elList.appendChild(li);
    });
  }

  function loadTrack(i) {
    if (!tracks.length) return;
    idx = ((i % tracks.length) + tracks.length) % tracks.length;
    audio.src = tracks[idx].src;
    renderNow();
  }

  audio.addEventListener("ended", () => {
    if (tracks.length > 1) { loadTrack(idx + 1); audio.play().catch(() => {}); }
  });

  function clearFade() { if (fadeTimer) { clearInterval(fadeTimer); fadeTimer = null; } }

  function fadeTo(target, durMs, onDone) {
    clearFade();
    target = clamp01(target);
    const startVol = audio.volume;
    const startT = performance.now();
    if (durMs <= 0) { audio.volume = target; setFill(); if (onDone) onDone(); return; }
    fadeTimer = setInterval(() => {
      const p = Math.min(1, (performance.now() - startT) / durMs);
      audio.volume = clamp01(startVol + (target - startVol) * p);
      setFill();
      if (p >= 1) { clearFade(); if (onDone) onDone(); }
    }, 50);
  }

  function start() {
    if (!tracks.length) { setStatus("bgm 資料夾沒有 mp3"); return; }
    clearFade();
    if (state === "stopped" || !audio.src) { loadTrack(idx); audio.volume = 0; setFill(); }
    audio.play().then(() => {
      state = "playing";
      renderNow();
      setStatus("淡入中…");
      fadeTo(targetVol, fadeInMs, () => setStatus("播放中 🔊"));
    }).catch((e) => setStatus("無法播放：" + e.message));
  }

  function pause() {
    if (state !== "playing") return;
    clearFade();
    setStatus("淡出中…");
    fadeTo(0, fadeOutMs, () => {
      audio.pause();
      state = "paused";
      renderNow();
      setStatus("已暫停");
    });
  }

  btnStart.onclick = start;
  btnPause.onclick = pause;

  elVol.oninput = () => {
    targetVol = clamp01(elVol.value / 100);
    elVolPct.textContent = elVol.value + "%";
    // 播放中即時套用音量（不經淡入淡出），暫停／待機只記住目標值
    if (state === "playing") { clearFade(); audio.volume = targetVol; setFill(); setStatus("播放中 🔊"); }
  };

  // 初始化
  elVol.value = Math.round(targetVol * 100);
  elVolPct.textContent = elVol.value + "%";
  loadTrack(0);
  audio.volume = 0; setFill();
  setStatus(tracks.length ? "待機（按開始淡入播放）" : "bgm 資料夾沒有 mp3");
  if (!tracks.length) { btnStart.disabled = true; btnPause.disabled = true; }
</script>
</body>
</html>
"""
