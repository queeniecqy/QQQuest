import streamlit.components.v1 as components
import json

def time_reminder_component(events, trigger_ts=0):
    """
    Renders the Time Reminder component.
    
    Args:
        events (list): List of dicts [{'seconds': 123, 'rawTime': '02:03', 'content': 'Event'}]
        trigger_ts (float): Timestamp of the last start trigger. Changing this value restarts the timer.
    """
    
    events_json = json.dumps(events)
    
    html_code = f"""
<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js"></script>
  <style>
    :root {{
      --bg: #262831;
      --surface: #303340;
      --surface-soft: #3a3e4c;
      --border: #4e5261;
      --text: #e3e6ef;
      --muted: #a8afc1;
      --button: #434857;
      --button-hover: #4e5261;
      --idle-bg: #3a3d49;
      --idle-text: #d0d5e2;
      --alert-bg: #454957;
      --alert-text: #e3e6ef;
      --active-bg: #515565;
      --active-text: #f1f3f8;
    }}
    body {{ margin: 0; background: linear-gradient(180deg, #2c2f39 0%, var(--bg) 100%); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji"; overflow: hidden; }}
    .wrap {{ padding: 8px; }}
    canvas {{ display: block; margin: 0 auto; border-radius: 12px; border: 1px solid var(--border); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04); }}
    .panel {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
    .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 12px; height: 300px; overflow-y: auto; box-shadow: 0 12px 24px rgba(16, 18, 24, 0.28); }}
    .btns {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; justify-content: center; }}
    button {{ background: var(--button); color: var(--text); border: 1px solid #5c6172; border-radius: 10px; padding: 8px 12px; cursor: pointer; transition: background 0.2s ease, transform 0.2s ease; }}
    button:hover {{ background: var(--button-hover); transform: translateY(-1px); }}
    .tag {{ display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; margin-left: 8px; }}
    .tag-idle {{ background: var(--idle-bg); color: var(--idle-text); }}
    .tag-alert {{ background: var(--alert-bg); color: var(--alert-text); }}
    .tag-active {{ background: var(--active-bg); color: var(--active-text); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 8px; text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--surface-soft); }}
    tr:hover td {{ background: #353947; }}
    .muted {{ color: var(--muted); font-size: 12px; text-align: center; margin: 4px 0; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }}
    .tea-countdowns {{ margin-top: 10px; display: flex; flex-direction: column; gap: 4px; align-items: center; }}
    .tea-row {{ font-size: 14px; color: var(--text); }}
    .tea-remain {{ color: var(--idle-text); }}
    .tea-row.tea-alert {{ color: #ff4d4d; font-weight: 700; animation: teaFlash 0.7s ease-in-out infinite; }}
    .tea-row.tea-alert .tea-remain {{ color: #ff4d4d; }}
    .tea-remind {{ display: none; margin-left: 12px; color: #ff4d4d; font-weight: 800; }}
    .tea-row.tea-alert .tea-remind {{ display: inline; }}
    @keyframes teaFlash {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.35; }}
    }}
    @keyframes flashRed {{
      0%, 100% {{ color: var(--text); background: transparent; }}
      50% {{ color: #ff5a5a; background: rgba(255, 70, 70, 0.22); }}
    }}
    .flash-red {{ animation: flashRed 0.8s ease-in-out infinite; border-radius: 6px; font-weight: 700; }}

    /* Scrollbar */
    ::-webkit-scrollbar {{ width: 8px; }}
    ::-webkit-scrollbar-track {{ background: #2a2d36; }}
    ::-webkit-scrollbar-thumb {{ background: #4b5060; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #5a6072; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div style="display:flex; justify-content:space-between; align-items:center;">
       <h3 style="margin:0;">時間提醒 <span class="tag tag-idle" id="statusTag">Idle</span></h3>
       <div class="btns" style="margin:0;">
          <button id="btnStart">開始</button>
          <button id="btnPause">暫停</button>
          <button id="btnReset">重置</button>
        </div>
    </div>
    
    <div class="panel">
      <div class="card" style="display:flex; flex-direction:column; justify-content:center;">
        <div id="canvasMount"></div>
        <p class="muted">事件前 5 秒提醒，維持 15 秒。</p>
        <div id="teaCountdowns" class="tea-countdowns"></div>
      </div>
      <div class="card">
        <h4 style="margin:0 0 8px;">事件清單</h4>
        <table>
          <thead>
            <tr>
              <th>Sec</th>
              <th>Time</th>
              <th>Content</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="eventsTable"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    // Data passed from Python
    let events = {events_json};
    let triggerTimestamp = {trigger_ts};
    
    // Global State
    let timer = 0;
    let running = false;
    let lastMillis = 0;
    const ALERT_PRE_SECONDS = 5;
    const ALERT_DURATION = 15;
    const IDLE_COLOR = [38, 40, 49];
    const ALERT_COLOR = [43, 46, 56];
    const ACTIVE_COLOR = [49, 53, 64];

    // Events whose content mentions 奉茶 — shown as countdowns in the left panel.
    const teaEvents = events.filter(ev => (ev.content || '').indexOf('奉茶') !== -1);

    // Red alert: flashes for 10s starting AT the event time, i.e. [ev, ev+10s].
    const RED_WINDOW = 10;
    // 奉茶提醒：每到設定的「分鐘點」就閃紅+文字提醒，維持這麼多秒。
    const TEA_REMIND_DURATION = 10;
    // 沒有特別設定提醒分鐘時的預設（分鐘）。
    const TEA_DEFAULT_REMIND_MIN = 7;
    let redActive = false;   // set each frame in draw()
    let redPulse = 0;        // 0..1 blink, set each frame in draw()

    function fmtMMSS(totalSeconds) {{
      const s = Math.max(0, Math.floor(totalSeconds));
      const mm = String(Math.floor(s / 60)).padStart(2, '0');
      const ss = String(s % 60).padStart(2, '0');
      return mm + ':' + ss;
    }}

    // Check for trigger update
    // We store the last trigger in localStorage to persist across re-renders if needed, 
    // or just check against a purely JS variable if the iframe doesn't reload.
    // Streamlit re-renders might reload the iframe.
    // If triggerTimestamp is different from stored, we auto-start.
    
    // Actually, since iframe creates fresh context, we can just check if triggerTimestamp > 0
    // But we need to know if it's "new".
    // A simple way: If the parent re-renders this HTML with a NEW timestamp, 
    // this script runs from scratch. So if(triggerTimestamp > 0), we can Auto-Start?
    // User wants it to start when command sent.
    
    // Problem: If user refreshes page, triggerTimestamp might still be old value from session state?
    // No, if session state persists, it might auto-start again on refresh.
    // We can assume if triggerTimestamp updates (client side check?), we start.
    
    // Let's rely on the fact that if this variable triggers, we reset.
    // We will use a small persistence to avoid re-starting on simple UI interactions if the timestamp didn't change.
    const LAST_TRIGGER_KEY = 'last_trigger_ts';
    
    function checkAutoStart() {{
        const stored = localStorage.getItem(LAST_TRIGGER_KEY);
        if (triggerTimestamp > 0 && String(triggerTimestamp) !== stored) {{
            // New trigger!
            localStorage.setItem(LAST_TRIGGER_KEY, String(triggerTimestamp));
            resetAndStart();
        }}
    }}

    function resetAndStart() {{
        timer = 0;
        running = true;
        updateStatusTag('Running');
    }}

    // p5.js
    function setup() {{
      // Adjust canvas size to fit card
      const c = createCanvas(400, 180);
      c.parent('canvasMount');
      textFont('system-ui');
      textSize(18);
      lastMillis = millis();

      // UI Bindings
      document.getElementById('btnStart').onclick = () => {{ running = true; updateStatusTag('Running'); }};
      document.getElementById('btnPause').onclick = () => {{ running = false; updateStatusTag('Paused'); }};
      document.getElementById('btnReset').onclick = () => {{ timer = 0; running = false; updateStatusTag('Idle'); }};
      
      renderEventsTable();
      renderTeaCountdowns();
      updateStatusTag('Idle');

      checkAutoStart();
    }}

    function draw() {{
      const now = millis();
      const dt = (now - lastMillis) / 1000;
      lastMillis = now;
      if (running) timer += dt;

      const state = computeState(timer);

      // Red alert window: |timer - event time| <= 5s
      redActive = false;
      for (const ev of events) {{
        if (timer >= ev.seconds && timer - ev.seconds <= RED_WINDOW) {{ redActive = true; break; }}
      }}
      redPulse = (sin(frameCount * 0.25) * 0.5 + 0.5);

      // BG
      let bg = IDLE_COLOR;
      if (state.mode === 'alert') bg = ALERT_COLOR;
      if (state.mode === 'active') bg = ACTIVE_COLOR;
      background(bg[0], bg[1], bg[2]);

      const pulse = (sin(frameCount * 0.08) * 0.5 + 0.5);
      const accent = state.mode === 'alert' ? color(114, 121, 142) :
                     state.mode === 'active' ? color(130, 137, 159) :
                     color(94, 100, 119);
      const textPrimary = color(227, 230, 239);
      const textMuted = color(168, 175, 193);

      // Top Bar
      stroke(78, 82, 97);
      strokeWeight(1.5);
      fill(redActive ? 60 + redPulse * 20 : 48, redActive ? 40 : 51, redActive ? 44 : 64);
      rect(10, 10, width - 20, 50, 8);
      // Flashing red border when within ±5s of an event
      if (redActive) {{
        noFill();
        stroke(255, 70, 70, 120 + redPulse * 135);
        strokeWeight(2 + redPulse * 2.5);
        rect(10, 10, width - 20, 50, 8);
      }}

      // Time
      noStroke();
      if (redActive) {{
        fill(255, 90 + redPulse * 60, 90 + redPulse * 60);
      }} else {{
        fill(214 + pulse * 18, 218 + pulse * 16, 229 + pulse * 12);
      }}
      textSize(24);
      textAlign(LEFT, CENTER);
      text(fmtMMSS(timer), 20, 35);

      textSize(14);
      fill(redActive ? color(255, 90, 90) : textMuted);
      const modeText = redActive ? '即將觸發' : state.mode === 'alert' ? '提醒中' : state.mode === 'active' ? '事件中' : '待機';
      textAlign(RIGHT, CENTER);
      text(modeText, width - 20, 35);

      // Current Event
      textSize(18);
      fill(redActive ? color(255, 90 + redPulse * 50, 90 + redPulse * 50) : accent);
      textAlign(LEFT, TOP);
      const title = state.currentEvent ? (state.currentEvent.content + ' @ ' + state.currentEvent.rawTime) : '無事件';
      text(title, 15, 75);

      if (!state.currentEvent) {{
        fill(textMuted);
        textSize(14);
        text('等待下一個時間點', 15, 103);
      }}

      // Alert Bar
      if (state.mode !== 'idle') {{
        const barX = 15, barY = 110, barW = width - 30, barH = 24;
        if (redActive) {{
          fill(255, 70, 70, 150 + redPulse * 90);
        }} else {{
          fill(red(accent), green(accent), blue(accent), 200);
        }}
        rect(barX, barY, barW, barH, 6);
        
        fill(textPrimary);
        textSize(14);
        textAlign(CENTER, CENTER);
        let msg = '';
        if (state.mode === 'alert') {{
          const remain = Math.max(0, state.alertEnd - timer);
          msg = '提醒: ' + remain.toFixed(1) + 's';
        }} else {{
          msg = '維持: ' + (ALERT_DURATION - (timer - (state.alertEnd - ALERT_DURATION))).toFixed(0) + 's'; 
          // Simplified calc, technically alertEnd is ev.seconds + duration
        }}
        text(msg, barX + barW / 2, barY + barH / 2);
      }}

      // Timeline
      drawTimeline(state, accent);

      // 奉茶 countdowns (left panel)
      updateTeaCountdowns();
    }}

    function computeState(t) {{
      let currentEvent = null;
      let mode = 'idle';
      let alertEnd = null;

      for (const ev of events) {{
        const startAlert = ev.seconds - ALERT_PRE_SECONDS;
        const endAlert = ev.seconds + ALERT_DURATION;
        if (t >= startAlert && t <= endAlert) {{
          currentEvent = ev;
          if (t < ev.seconds) {{
            mode = 'alert';
            alertEnd = ev.seconds + ALERT_DURATION;
          }} else {{
            mode = 'active';
            alertEnd = ev.seconds + ALERT_DURATION;
          }}
          break;
        }}
      }}
      return {{ currentEvent, mode, alertEnd }};
    }}

    function drawTimeline(state, accent) {{
      const margin = 20;
      const y = height - 25;
      const W = width - margin * 2;
      const windowSpan = 120;
      const tMin = Math.max(0, timer - windowSpan / 2);
      const tMax = timer + windowSpan / 2;

      stroke(90, 96, 113);
      strokeWeight(2);
      line(margin, y, width - margin, y);

      for (const ev of events) {{
        if (ev.seconds < tMin || ev.seconds > tMax) continue;
        const x = map(ev.seconds, tMin, tMax, margin, width - margin);
        const isCurrent = state.currentEvent && state.currentEvent.seconds === ev.seconds;
        const isRed = timer >= ev.seconds && timer - ev.seconds <= RED_WINDOW;
        noStroke();
        if (isRed) {{
          // Pulsing red halo + dot for the imminent event
          fill(255, 70, 70, 60 + redPulse * 60);
          circle(x, y, 16 + redPulse * 8);
          fill(255, 70, 70);
          circle(x, y, 9 + redPulse * 3);
        }} else if (isCurrent) {{
          fill(red(accent), green(accent), blue(accent));
          circle(x, y, 8);
        }} else {{
          fill(100, 106, 124);
          circle(x, y, 5);
        }}

        // Label (Simplified for small canvas)
        if (isCurrent || isRed) {{
             fill(isRed ? color(255, 150, 150) : color(227, 230, 239)); textSize(10); textAlign(CENTER, BOTTOM);
             text(ev.rawTime, x, y - 10);
        }}
      }}

      const xNow = map(timer, tMin, tMax, margin, width - margin);
      if (redActive) {{
        stroke(255, 70, 70, 150 + redPulse * 105);
        strokeWeight(3 + redPulse * 2);
      }} else {{
        stroke(206, 211, 223, 220);
        strokeWeight(2);
      }}
      line(xNow, y - 12, xNow, y + 12);
    }}

    function renderEventsTable() {{
      const tbody = document.getElementById('eventsTable');
      tbody.innerHTML = '';
      for (const ev of events) {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td class="mono">${{ev.seconds}}</td><td class="mono">${{ev.rawTime}}</td><td>${{ev.content}}</td><td><span class="tag tag-idle">Idle</span></td>`;
        tbody.appendChild(tr);
      }}
      
      setInterval(() => {{
        const rows = tbody.querySelectorAll('tr');
        rows.forEach((tr, idx) => {{
          const ev = events[idx];
          if (!ev) return;
          const startAlert = ev.seconds - ALERT_PRE_SECONDS;
          const endAlert = ev.seconds + ALERT_DURATION;
          const tag = tr.children[3].querySelector('.tag');
          if (timer >= startAlert && timer < ev.seconds) {{
            tag.className = 'tag tag-alert';
            tag.textContent = 'Alert';
          }} else if (timer >= ev.seconds && timer <= endAlert) {{
            tag.className = 'tag tag-active';
            tag.textContent = 'Active';
          }} else {{
            tag.className = 'tag tag-idle';
            tag.textContent = 'Idle';
          }}

          // Flash the Time cell red for 5s starting at this event's time
          const timeCell = tr.children[1];
          if (timer >= ev.seconds && timer - ev.seconds <= RED_WINDOW) {{
            timeCell.classList.add('flash-red');
          }} else {{
            timeCell.classList.remove('flash-red');
          }}
        }});
      }}, 200);
    }}

    function renderTeaCountdowns() {{
      const box = document.getElementById('teaCountdowns');
      if (!box) return;
      box.innerHTML = '';
      for (const ev of teaEvents) {{
        const m = (ev.content || '').match(/第.泡/);
        const label = (m ? m[0] : '') + '奉茶';
        const marks = (Array.isArray(ev.remindMins) && ev.remindMins.length)
          ? ev.remindMins
          : [TEA_DEFAULT_REMIND_MIN];
        const row = document.createElement('div');
        row.className = 'tea-row mono';
        row.dataset.sec = ev.seconds;
        row.dataset.marks = marks.join(',');   // 這一泡要提醒的分鐘點
        row.innerHTML = '距離' + label + '還有 <span class="tea-remain">--:--</span>' +
                        '<span class="tea-remind">請提醒製茶師時間!!</span>';
        box.appendChild(row);
      }}
    }}

    function updateTeaCountdowns() {{
      const rows = document.querySelectorAll('#teaCountdowns .tea-row');
      rows.forEach(row => {{
        const sec = Number(row.dataset.sec);
        const remain = sec - timer;
        const span = row.querySelector('.tea-remain');
        if (span) span.textContent = remain > 0 ? fmtMMSS(remain) : '--:--';

        // 解析這一泡設定的提醒分鐘點（可多個，逗號分隔）
        const marks = (row.dataset.marks || '')
          .split(',')
          .map(s => parseFloat(s))
          .filter(n => !isNaN(n) && n > 0);

        // 倒數進入任一分鐘點之後的 10 秒視窗 → 閃紅 + 文字提醒
        let active = false;
        for (const mMin of marks) {{
          const mSec = mMin * 60;
          if (remain <= mSec && remain > mSec - TEA_REMIND_DURATION) {{ active = true; break; }}
        }}

        if (active) {{
          row.classList.add('tea-alert');
        }} else {{
          row.classList.remove('tea-alert');
        }}
      }});
    }}

    function updateStatusTag(s) {{
      const el = document.getElementById('statusTag');
      if(el) {{
          el.textContent = s;
          el.className = 'tag ' + (s === 'Running' ? 'tag-active' : s === 'Paused' ? 'tag-alert' : 'tag-idle');
      }}
    }}
  </script>
</body>
</html>
    """
    components.html(html_code, height=400)
