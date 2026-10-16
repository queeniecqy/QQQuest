"""
vrcontrol 管理器

代管 vrcontrol 的 Go API 伺服器（:8080），供「畫面牆」的 WebRTC 模式使用。
畫面牆自己用原生 RTCPeerConnection 畫純影像格、直接連 Go 端的 signaling
WebSocket（/api/ws/webrtc/:deviceId），所以【不需要】vrcontrol 的 Vite 前端。

沿用 SocketServerManager 的模式（Popen + log 檔 + 啟動驗證 + terminate/kill），
兩個重要差異：
  • 用 start_new_session 起新 process group，停止時 killpg——go run 會再生子行程，
    單殺父行程會留孤兒。
  • pgid 另存 pidfile（logs/vrcontrol/*.pid）：Streamlit 重啟後 Popen 把手沒了，
    但行程還活著；stop() 會退回讀 pidfile 殺整個 group，不會變成殺不掉的孤兒。

另提供 ensure_devices()：把 QQQuest 選到的設備確保存在於 vrcontrol（REST API），
回傳 serial → vrcontrol device_id 的對照，畫面牆用它去開每台的 WebRTC 串流。
"""
import hashlib
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from config.settings import LOGS_DIR, get_user_config
from utils.logger import get_logger

logger = get_logger(__name__)


class VRControlManager:
    """管理 vrcontrol Go 伺服器行程、串流參數與設備同步"""

    def __init__(self):
        self._lock = threading.Lock()  # 多個 Streamlit 分頁共用單例，避免同時 start/stop
        self.server_process: Optional[subprocess.Popen] = None
        # 8080 上已有別人先開好的 vrcontrol（例如手動跑 npm run dev）→ 借用、不代管
        self.adopted_external = False
        self._load_config()

    def _load_config(self):
        """讀 user_config（start 時重讀，讓使用者改了 root 不用重開 Streamlit）"""
        cfg = get_user_config().get('vrcontrol', {})
        self.root = Path(cfg.get('root', str(Path.home() / "Downloads" / "vrcontrol")))
        self.api_port: int = int(cfg.get('api_port', 8080))
        self.api_base = f"http://127.0.0.1:{self.api_port}/api"
        self.log_dir = LOGS_DIR / "vrcontrol"

    # ------------------------------------------------------------------
    # 狀態偵測
    # ------------------------------------------------------------------

    def _port_open(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def _api_alive(self) -> bool:
        """8080 上回應的是不是 vrcontrol API"""
        try:
            r = requests.get(f"{self.api_base}/devices", timeout=2)
            return r.ok and isinstance(r.json(), dict) and 'data' in r.json()
        except Exception:
            return False

    def is_running(self) -> bool:
        return self._api_alive()

    # ------------------------------------------------------------------
    # 啟動 / 停止
    # ------------------------------------------------------------------

    def start(self) -> Tuple[bool, str]:
        with self._lock:
            return self._start_locked()

    def _start_locked(self) -> Tuple[bool, str]:
        self._load_config()

        if self._api_alive():
            if self.server_process is None:
                self.adopted_external = not self._reclaim_pidfiles()
            return True, "vrcontrol 已在執行中"

        # 前置檢查
        if not self.root.exists():
            return False, f"找不到 vrcontrol 專案：{self.root}（可在 data/user_config.json 的 vrcontrol.root 修改路徑）"
        server_binary = self.root / "vrcontrol-server"
        if not server_binary.exists() and not self._go_available():
            return False, ("找不到 vrcontrol-server 執行檔，且系統沒有 go。"
                           f"請先在 {self.root} 執行：npm run server:build")

        # 8080 被占用但不是 vrcontrol → 不硬搶
        if self._port_open(self.api_port):
            return False, (f"埠 {self.api_port} 被其他程式占用（且不是 vrcontrol）。"
                           f"請先釋放：lsof -nP -iTCP:{self.api_port} -sTCP:LISTEN")

        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self._start_managed_process('server'):
            return False, self._startup_failure_message('server')

        # 啟動驗證：輪詢到 API 活著
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._api_alive():
                logger.info("vrcontrol 啟動完成")
                return True, f"vrcontrol 已啟動（API :{self.api_port}）"
            if self.server_process is not None and self.server_process.poll() is not None:
                msg = self._startup_failure_message('server')
                self._stop_locked()
                return False, msg
            time.sleep(0.5)

        msg = "vrcontrol 啟動逾時（15 秒內服務未就緒），請查看 logs/vrcontrol/server.log"
        self._stop_locked()
        return False, msg

    def _start_managed_process(self, name: str) -> bool:
        """啟動 Go 伺服器行程；回傳是否成功送出（不代表服務已就緒）"""
        env = os.environ.copy()
        # launchd/打包啟動時 PATH 可能缺 homebrew（adb 在那裡）
        env['PATH'] = f"/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
        # gin router.Run() 會吃 $PORT 改綁別的埠——絕不能讓它換
        env.pop('PORT', None)

        server_binary = self.root / "vrcontrol-server"
        if server_binary.exists():
            cmd = [str(server_binary)]
        else:
            cmd = ['go', 'run', 'main.go']
        # cwd 必須是 server/：Go 端以 CWD 解析 data/*.json 與 ../vendor/scrcpy
        cwd = self.root / "server"

        log_path = self.log_dir / f"{name}.log"
        try:
            log_file = open(log_path, "w", encoding="utf-8")  # 每次啟動清空，避免無限成長
            process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=True,  # 自成 process group，stop 時 killpg 才殺得乾淨
            )
            log_file.close()  # 子行程已繼承 fd，父行程不留
        except Exception as e:
            logger.error(f"啟動 vrcontrol {name} 失敗: {e}")
            return False

        self.server_process = process
        # pgid 存 pidfile：Streamlit 重啟後沒有 Popen 把手，stop() 靠這個殺孤兒
        try:
            self._pidfile(name).write_text(str(os.getpgid(process.pid)))
        except Exception:
            pass
        logger.info(f"vrcontrol {name} 已啟動 (PID {process.pid})，log: {log_path}")
        return True

    def _startup_failure_message(self, name: str) -> str:
        tail = ""
        log_path = self.log_dir / f"{name}.log"
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                tail = "".join(f.readlines()[-10:])
        except Exception:
            pass
        return f"vrcontrol {name} 啟動失敗。log 末段：\n{tail or '(無 log)'}"

    def stop(self) -> Tuple[bool, str]:
        with self._lock:
            return self._stop_locked()

    def _stop_locked(self) -> Tuple[bool, str]:
        stopped = []
        attempted = False
        # 'client' 只為了清掉舊版（曾代管 Vite 前端）留下的 pidfile/孤兒
        for name in ('client', 'server'):
            process = self.server_process if name == 'server' else None
            pgid: Optional[int] = None
            if process is not None:
                try:
                    pgid = os.getpgid(process.pid)
                except ProcessLookupError:
                    # leader 已死也要 killpg：group 裡可能還有活著的子行程
                    pgid = process.pid
            else:
                # Streamlit 重啟過：從 pidfile 找回之前代管的 process group
                pgid = self._read_pidfile(name)

            if pgid is not None:
                attempted = True
                if self._kill_group(pgid, process):
                    stopped.append(name)
            if name == 'server':
                self.server_process = None
            self._remove_pidfile(name)

        # 保險：killpg 後埠上還有殘留 listener（pgid 追不到的漏網子行程）→ 按埠補刀
        if attempted:
            self._kill_port_listeners(self.api_port)

        if self._api_alive():
            self.adopted_external = False
            return False, ("vrcontrol 仍在執行，但不是本程式代管的（外部手動啟動）。"
                           f"請在原終端機關閉，或手動：lsof -nP -iTCP:{self.api_port} -sTCP:LISTEN")
        self.adopted_external = False
        return True, f"已停止 vrcontrol（{', '.join(stopped) or '無代管行程'}）"

    def _kill_group(self, pgid: int, process: Optional[subprocess.Popen]) -> bool:
        """SIGTERM 整個 process group，5 秒沒死補 SIGKILL。回傳是否有殺到東西。"""
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            if process is not None:
                process.wait()  # 收屍，避免 zombie
            return False
        except Exception as e:
            logger.warning(f"停止 vrcontrol group {pgid} 出錯: {e}")
            return False

        deadline = time.time() + 5
        while time.time() < deadline:
            if process is not None:
                if process.poll() is not None and not self._group_alive(pgid):
                    return True
            elif not self._group_alive(pgid):
                return True
            time.sleep(0.2)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            # macOS：group 裡只剩殭屍（或無法 signal 的成員）時 killpg 回 EPERM。
            # 沒東西可殺了，交給後面的按埠補刀 + _api_alive 最終驗證。
            logger.warning(f"killpg({pgid}, SIGKILL) EPERM——group 應已無可殺成員")
        if process is not None:
            try:
                process.wait(timeout=3)
            except Exception:
                pass
        return True

    def _group_alive(self, pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # macOS：只剩殭屍的 group 也會 EPERM——對我們而言等同已死
            return False

    def _kill_port_listeners(self, port: int):
        """殺掉還掛在指定埠上的 listener（stop 的最後保險）"""
        try:
            r = subprocess.run(['lsof', '-ti', f'tcp:{port}', '-sTCP:LISTEN'],
                               capture_output=True, text=True, timeout=5)
            for pid_str in r.stdout.split():
                try:
                    os.kill(int(pid_str), signal.SIGKILL)
                    logger.info(f"補刀：埠 {port} 上殘留的 PID {pid_str}")
                except Exception:
                    pass
        except Exception:
            pass

    def _pidfile(self, name: str) -> Path:
        return self.log_dir / f"{name}.pid"

    def _read_pidfile(self, name: str) -> Optional[int]:
        try:
            pgid = int(self._pidfile(name).read_text().strip())
            return pgid if self._group_alive(pgid) else None
        except Exception:
            return None

    def _remove_pidfile(self, name: str):
        try:
            self._pidfile(name).unlink()
        except Exception:
            pass

    def _reclaim_pidfiles(self) -> bool:
        """重啟後檢查是否有本程式之前留下的 pidfile（有 → 是我們的孤兒，可停）"""
        return self._read_pidfile('server') is not None

    def _go_available(self) -> bool:
        env = os.environ.copy()
        env['PATH'] = f"/opt/homebrew/bin:/usr/local/bin:{env.get('PATH', '')}"
        try:
            return subprocess.run(['go', 'version'], capture_output=True, timeout=5, env=env).returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 串流參數（FPS）
    # ------------------------------------------------------------------

    def get_stream_config(self) -> Optional[dict]:
        """讀 vrcontrol 的串流編碼設定（bitrate/max_size/max_fps/video_codec_options）"""
        try:
            r = requests.get(f"{self.api_base}/scrcpy/config", timeout=3)
            if r.ok and r.json().get('success'):
                return r.json().get('data') or {}
        except Exception:
            pass
        return None

    def set_stream_fps(self, fps: int) -> Tuple[bool, str]:
        """改 WebRTC 串流的 FPS。只影響之後新開的串流——要立即生效需 restart_server()。"""
        cfg = self.get_stream_config() or {}
        # 現場的 scrcpy_config.json 可能是空值（bitrate=''、max_size=0），PUT 會被驗證擋，
        # 補成 vrcontrol 的預設值再寫回。
        if not cfg.get('bitrate'):
            cfg['bitrate'] = "8M"
        if not cfg.get('max_size'):
            cfg['max_size'] = 1024
        cfg.setdefault('video_codec_options', "")
        cfg['max_fps'] = int(fps)
        try:
            r = requests.put(f"{self.api_base}/scrcpy/config", json=cfg, timeout=5)
            if r.ok and r.json().get('success'):
                return True, f"FPS 已設為 {fps}"
            return False, f"設定失敗: {r.status_code} {r.text[:150]}"
        except Exception as e:
            return False, f"設定失敗: {e}"

    def restart_server(self) -> Tuple[bool, str]:
        """重啟 Go 伺服器（會砍掉進行中的串流，讓新的編碼設定立即生效）"""
        with self._lock:
            process = self.server_process
            pgid: Optional[int] = None
            if process is not None:
                try:
                    pgid = os.getpgid(process.pid)
                except ProcessLookupError:
                    pgid = process.pid
            else:
                pgid = self._read_pidfile('server')

            if pgid is None:
                # 外部手動啟動的 server 我們殺不得也重啟不了
                return False, ("vrcontrol 伺服器不是本程式代管的，無法自動重啟。"
                               "新 FPS 會在下次串流重新建立時生效，或請手動重啟 vrcontrol。")

            self._kill_group(pgid, process)
            self.server_process = None
            self._remove_pidfile('server')
            self._kill_port_listeners(self.api_port)

            if not self._start_managed_process('server'):
                return False, self._startup_failure_message('server')
            deadline = time.time() + 10
            while time.time() < deadline:
                if self._api_alive():
                    return True, "串流已重啟，新設定生效"
                if self.server_process is not None and self.server_process.poll() is not None:
                    return False, self._startup_failure_message('server')
                time.sleep(0.5)
            return False, "vrcontrol 伺服器重啟逾時，請查看 logs/vrcontrol/server.log"

    # ------------------------------------------------------------------
    # 設備同步（QQQuest → vrcontrol）
    # ------------------------------------------------------------------

    @staticmethod
    def _vr_device_id(serial: str) -> str:
        """由 serial 決定性導出 vrcontrol 要求的 device_id（8 碼 [0-9A-Z]；同台永遠同 ID）"""
        return hashlib.md5(serial.encode()).hexdigest()[:8].upper()

    def ensure_devices(self, devices) -> Tuple[bool, str, Dict[str, str]]:
        """
        確保 QQQuest 設備存在於 vrcontrol（不存在就建立），供 WebRTC 串流指名。

        Args:
            devices: QQQuest 的 Device 列表（用 connection_string 當 vrcontrol serial）
        Returns:
            (成功, 訊息, {serial: vrcontrol device_id})
        """
        if not self._api_alive():
            return False, "vrcontrol API 未執行，請先啟動", {}

        try:
            existing = self._get_devices_by_serial()
            mapping: Dict[str, str] = {}
            created, failed = 0, []
            need_connect = []  # vrcontrol 認定非 online 的（它只肯串流 online 設備）
            for d in devices:
                serial = d.connection_string
                vr_dev = existing.get(serial)
                if vr_dev is None:
                    r = requests.post(f"{self.api_base}/devices", json={
                        "device_id": self._vr_device_id(serial),  # vrcontrol 必填（8 碼英數）
                        "serial": serial,
                        "ip": d.ip or serial.split(":")[0],
                        "port": d.port or 5555,
                        "alias": d.display_name,
                        "name": d.name or "",
                        "model": d.model or "",
                        "status": "offline",
                    }, timeout=5)
                    if r.ok and r.json().get('success'):
                        vr_dev = r.json().get('data') or {}
                        created += 1
                    else:
                        failed.append(serial)
                        logger.warning(f"vrcontrol 建立設備失敗 {serial}: {r.status_code} {r.text[:200]}")
                        continue
                vr_id = vr_dev.get('device_id')
                if not vr_id:
                    failed.append(serial)
                    continue
                mapping[serial] = vr_id
                if (vr_dev.get('status') or '').lower() != 'online':
                    need_connect.append((serial, vr_id))

            # vrcontrol 只串流「它認定 online」的設備，且只在它啟動時對一次 adb。
            # 對非 online 的補打它的 connect API（= adb connect + 標記 online；
            # 設備其實已被 QQQuest 連上，同一個 adb daemon，瞬間完成）。
            not_online = []
            if need_connect:
                from concurrent.futures import ThreadPoolExecutor

                def _connect(item):
                    serial, vid = item
                    try:
                        r = requests.post(f"{self.api_base}/devices/{vid}/connect", timeout=20)
                        return serial, r.ok and r.json().get('success', False)
                    except Exception:
                        return serial, False

                with ThreadPoolExecutor(max_workers=min(6, len(need_connect))) as ex:
                    for serial, okc in ex.map(_connect, need_connect):
                        if not okc:
                            not_online.append(serial)

            msg = f"設備就緒：{len(mapping)}/{len(devices)} 台（新增 {created}、標記上線 {len(need_connect) - len(not_online)}）"
            if not_online:
                # 不當致命錯：留在牆上顯示連線失敗並自動重試
                msg += f"；未上線: {', '.join(not_online)}"
            if failed:
                msg += f"，失敗: {', '.join(failed)}"
            return not failed, msg, mapping
        except Exception as e:
            logger.error(f"同步設備到 vrcontrol 失敗: {e}")
            return False, f"同步失敗: {e}", {}

    def _get_devices_by_serial(self) -> Dict[str, dict]:
        r = requests.get(f"{self.api_base}/devices", timeout=5)
        r.raise_for_status()
        return {dev.get('serial'): dev for dev in (r.json().get('data') or [])}


# 模組級單例（跨 Streamlit rerun 存活）
_vrcontrol_manager: Optional[VRControlManager] = None
_singleton_lock = threading.Lock()


def get_vrcontrol_manager() -> VRControlManager:
    global _vrcontrol_manager
    with _singleton_lock:
        if _vrcontrol_manager is None:
            _vrcontrol_manager = VRControlManager()
        return _vrcontrol_manager
