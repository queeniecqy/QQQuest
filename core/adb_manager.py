"""
ADB 管理器
"""
import asyncio
import subprocess
import re
import platform
import threading
from typing import List, Optional, Dict, Tuple, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.logger import get_logger
from config.constants import DeviceStatus, ConnectionType
from config.settings import ADB_DEFAULT_PORT, ADB_CONNECTION_TIMEOUT

logger = get_logger(__name__)

QUEST_SINGLE_EYE_CROP = "1600:1440:200:300"
SCRCPY_AUTO_WINDOW_WIDTH = 420
SCRCPY_AUTO_WINDOW_HEIGHT = 380
SCRCPY_WINDOW_GAP_X = 24
SCRCPY_WINDOW_GAP_Y = 36
SCRCPY_WINDOW_MARGIN_X = 40
SCRCPY_WINDOW_MARGIN_Y = 40
SCRCPY_GRID_COLUMNS = 3
SCRCPY_FALLBACK_SCREEN_SIZE = (2560, 1440)
OCULUS_SYSTEM_FOCUS_PACKAGES = (
    "com.oculus.os.clearactivity",
    "com.oculus.vrshell",
    "com.oculus.systemux",
    "com.oculus.panelapp",
    "com.oculus.vrguardianservice",
)
OCULUS_PANEL_OVERLAY_MARKERS = (
    "com.oculus.panelapp.controlbar",
    "com.oculus.panelapp.toasts",
    "com.oculus.panelapp.bloom",
    "controlbaractivity",
    "toastsactivity",
    "bloomactivity",
)


class ADBManager:
    """ADB 管理器類別"""
    
    def __init__(self):
        self._check_adb_available()
        # 緩存設備列表（避免頻繁調用）
        self._devices_cache: Optional[List[Dict[str, str]]] = None
        self._devices_cache_time: float = 0
        self._devices_cache_ttl: float = 1.0  # 緩存有效期（秒）
        self._scrcpy_layout_lock = threading.Lock()
        self._scrcpy_window_index: int = 0
        self._passthrough_monitor_lock = threading.Lock()
        self._passthrough_monitors: Dict[str, Dict[str, Any]] = {}
        self._passthrough_alerts: Dict[str, Dict[str, Any]] = {}
        self._passthrough_alert_suppress_until: Dict[str, float] = {}
    
    def _check_adb_available(self) -> bool:
        """檢查 ADB 是否可用"""
        try:
            result = subprocess.run(
                ['adb', 'version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"ADB 可用: {result.stdout.split()[4]}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"ADB 不可用: {e}")
            raise RuntimeError("ADB 未安裝或不在 PATH 中")
        return False
    
    def execute_command(
        self,
        command: str,
        device: Optional[str] = None,
        timeout: int = ADB_CONNECTION_TIMEOUT
    ) -> Tuple[bool, str]:
        """
        執行 ADB 命令
        
        Args:
            command: ADB 命令（不包含 'adb' 前綴）
            device: 設備序列號或 IP:Port
            timeout: 超時時間（秒）
        
        Returns:
            (成功, 輸出)
        """
        try:
            cmd = ['adb']
            if device:
                cmd.extend(['-s', device])
            cmd.extend(command.split())
            
            logger.debug(f"執行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            if success:
                logger.debug(f"命令成功: {output[:100]}")
            else:
                logger.warning(f"命令失敗: {output}")
            
            return success, output.strip()
            
        except subprocess.TimeoutExpired:
            logger.error(f"命令超時: {command}")
            return False, "命令執行超時"
        except Exception as e:
            logger.error(f"命令執行錯誤: {e}")
            return False, str(e)
    
    def execute_shell_command(
        self,
        command: str,
        device: Optional[str] = None,
        timeout: int = ADB_CONNECTION_TIMEOUT
    ) -> Tuple[bool, str]:
        """執行 ADB shell 命令"""
        return self.execute_command(f"shell {command}", device, timeout)

    def start_passthrough_logcat_monitor(
        self,
        device: str,
        package: str,
        clear_logcat: bool = False
    ) -> Tuple[bool, str]:
        """啟動單台設備的 logcat 監控，用於偵測疑似誤觸 Passthrough / 系統 UI。"""
        if not device:
            return False, "缺少 device"

        with self._passthrough_monitor_lock:
            existing = self._passthrough_monitors.get(device)
            if existing and existing.get('thread') and existing['thread'].is_alive():
                return True, "監控已啟動"

            stop_event = threading.Event()

            try:
                if clear_logcat:
                    clear_cmd = ['adb', '-s', device, 'logcat', '-c']
                    subprocess.run(clear_cmd, capture_output=True, text=True, timeout=3)

                cmd = ['adb', '-s', device, 'logcat', '-v', 'time']
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                thread = threading.Thread(
                    target=self._passthrough_logcat_loop,
                    args=(device, package, process, stop_event),
                    daemon=True
                )

                self._passthrough_monitors[device] = {
                    'process': process,
                    'thread': thread,
                    'stop_event': stop_event,
                    'package': package
                }
                thread.start()

                logger.info(f"✅ 已啟動 Passthrough logcat 監控: {device}")
                return True, "監控已啟動"

            except Exception as e:
                logger.warning(f"⚠️ 啟動 Passthrough logcat 監控失敗 ({device}): {e}")
                return False, str(e)

    def stop_passthrough_logcat_monitor(self, device: str) -> Tuple[bool, str]:
        """停止單台設備的 Passthrough logcat 監控。"""
        with self._passthrough_monitor_lock:
            monitor = self._passthrough_monitors.pop(device, None)

        if not monitor:
            return True, "監控未啟動"

        try:
            monitor['stop_event'].set()
            process = monitor.get('process')
            if process and process.poll() is None:
                process.terminate()
            return True, "監控已停止"
        except Exception as e:
            logger.warning(f"⚠️ 停止 Passthrough logcat 監控失敗 ({device}): {e}")
            return False, str(e)

    def get_passthrough_alert(self, device: str) -> Optional[Dict[str, Any]]:
        """取得單台設備最近一次疑似 Passthrough alert。"""
        import time

        with self._passthrough_monitor_lock:
            suppress_until = self._passthrough_alert_suppress_until.get(device, 0)
            if suppress_until and time.time() < suppress_until:
                return None

            alert = self._passthrough_alerts.get(device)
            return dict(alert) if alert else None

    def clear_passthrough_alert(self, device: str, suppress_seconds: float = 5.0):
        """清除單台設備的 Passthrough alert，並短暫忽略切回過程中的舊 log。"""
        import time

        with self._passthrough_monitor_lock:
            self._passthrough_alerts.pop(device, None)
            self._passthrough_alert_suppress_until[device] = time.time() + suppress_seconds

    def _passthrough_logcat_loop(
        self,
        device: str,
        package: str,
        process: subprocess.Popen,
        stop_event: threading.Event
    ):
        try:
            if not process.stdout:
                return

            while not stop_event.is_set():
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    continue

                reason = self._match_passthrough_logcat_line(line, package)
                if reason:
                    self._set_passthrough_alert(device, reason, line)

        except Exception as e:
            logger.warning(f"⚠️ Passthrough logcat 監控中斷 ({device}): {e}")
        finally:
            try:
                if process.poll() is None:
                    process.terminate()
            except Exception:
                pass

            with self._passthrough_monitor_lock:
                monitor = self._passthrough_monitors.get(device)
                if monitor and monitor.get('process') is process:
                    self._passthrough_monitors.pop(device, None)

    def _match_passthrough_logcat_line(self, line: str, package: str) -> Optional[str]:
        text = line.strip()
        lower = text.lower()
        package_lower = package.lower()

        if "foregroundapphandler" in lower and f"from ({package_lower}) to ()" in lower:
            return "遊戲 immersive focus 被系統清空"

        if "com.oculus.os.clearactivity" in lower:
            return "偵測到 Oculus ClearActivity"

        if "focusedapp: com.oculus.os.clearactivity" in lower:
            return "焦點切到 Oculus ClearActivity"

        if "focused window changed" in lower and "com.oculus.vrshell" in lower:
            return "焦點切到 Oculus 系統介面"

        return None

    def _set_passthrough_alert(self, device: str, reason: str, line: str):
        import time

        now = time.time()

        alert = {
            'device': device,
            'reason': reason,
            'line': line.strip()[:500],
            'timestamp': now
        }

        with self._passthrough_monitor_lock:
            suppress_until = self._passthrough_alert_suppress_until.get(device, 0)
            if suppress_until and now < suppress_until:
                return

            previous = self._passthrough_alerts.get(device)
            self._passthrough_alerts[device] = alert

        if not previous or previous.get('reason') != reason:
            logger.warning(f"🥽 偵測到疑似 Passthrough 誤觸 ({device}): {reason}")
    
    async def execute_command_async(
        self,
        command: str,
        device: Optional[str] = None,
        timeout: int = ADB_CONNECTION_TIMEOUT
    ) -> Tuple[bool, str]:
        """
        異步執行 ADB 命令（非阻塞）
        """
        try:
            cmd = ['adb']
            if device:
                cmd.extend(['-s', device])
            cmd.extend(command.split())
            
            logger.debug(f"執行異步命令: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                success = process.returncode == 0
                output = stdout.decode().strip() if success else stderr.decode().strip()
                
                if success:
                    logger.debug(f"異步命令成功: {output[:100]}")
                else:
                    logger.warning(f"異步命令失敗: {output}")
                    
                return success, output
                
            except asyncio.TimeoutError:
                logger.error(f"異步命令超時: {command}")
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                return False, "命令執行超時"
                
        except Exception as e:
            logger.error(f"異步命令執行錯誤: {e}")
            return False, str(e)

    async def execute_shell_command_async(
        self,
        command: str,
        device: Optional[str] = None,
        timeout: int = ADB_CONNECTION_TIMEOUT
    ) -> Tuple[bool, str]:
        """異步執行 ADB shell 命令"""
        return await self.execute_command_async(f"shell {command}", device, timeout)
    
    async def connect_async(self, ip: str, port: int = ADB_DEFAULT_PORT) -> Tuple[bool, str]:
        """異步連接到設備"""
        target = f"{ip}:{port}"
        success, output = await self.execute_command_async(f"connect {target}")
        
        if success or "already connected" in output.lower():
            logger.info(f"已連接到設備 (Async): {target}")
            self.clear_devices_cache()
            return True, output
        
        logger.error(f"連接失敗 (Async): {target} - {output}")
        return False, output

    async def get_device_status_async(self, device: str) -> Dict[str, Any]:
        """異步獲取設備狀態"""
        status = {
            'battery': 0,
            'temperature': 0.0,
            'is_charging': False,
            'is_screen_on': False,
            'is_awake': True,
            'uptime': 0,
        }
        
        try:
            command = """dumpsys battery | grep -E 'level:|temperature:|powered:' && echo '---POWER---' && dumpsys power | grep -E 'Display Power|mWakefulness=' && echo '---UPTIME---' && cat /proc/uptime | cut -d' ' -f1"""
            
            # 使用稍長的超時，因為 dumpsys 很慢
            success, output = await self.execute_shell_command_async(command, device, timeout=15)
            
            if not success:
                logger.warning(f"獲取設備狀態失敗 (Async): {device}")
                return status
            
            lines = output.split('\n')
            for line in lines:
                if 'level:' in line:
                    match = re.search(r'level:\s*(\d+)', line)
                    if match: status['battery'] = int(match.group(1))
                elif 'temperature:' in line:
                    match = re.search(r'temperature:\s*(\d+)', line)
                    if match: status['temperature'] = int(match.group(1)) / 10.0
                elif 'powered:' in line:
                    if 'true' in line.lower(): status['is_charging'] = True
                elif 'Display Power' in line:
                    if 'ON' in line: status['is_screen_on'] = True
                elif 'mWakefulness=' in line:
                    if 'Asleep' in line or 'Dozing' in line: status['is_awake'] = False
                    else: status['is_awake'] = True
                elif line.strip() and not line.startswith('---'):
                    try:
                        uptime = float(line.strip().split()[0])
                        status['uptime'] = int(uptime)
                    except (ValueError, IndexError):
                        pass
            
            return status
            
        except Exception as e:
            logger.error(f"解析設備狀態失敗 (Async): {device} - {e}")
            return status
    
    def get_devices(self, use_cache: bool = True) -> List[Dict[str, str]]:
        """
        取得所有連接的設備（帶緩存機制）
        
        Args:
            use_cache: 是否使用緩存（預設 True）
        
        Returns:
            設備列表，每個設備包含 serial, state, connection_type
        """
        import time
        
        # 檢查緩存
        if use_cache and self._devices_cache is not None:
            current_time = time.time()
            if current_time - self._devices_cache_time < self._devices_cache_ttl:
                logger.debug(f"使用緩存的設備列表（{len(self._devices_cache)} 台設備）")
                return self._devices_cache
        
        # 執行 ADB 命令獲取設備列表
        success, output = self.execute_command("devices -l")
        if not success:
            if use_cache and self._devices_cache is not None:
                # 如果命令失敗但緩存存在，返回緩存
                logger.debug("ADB 命令失敗，使用緩存的設備列表")
                return self._devices_cache
            return []
        
        devices = []
        lines = output.split('\n')[1:]  # 跳過第一行 "List of devices attached"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 解析設備資訊
            parts = line.split()
            if len(parts) < 2:
                continue
            
            serial = parts[0]
            state = parts[1]
            
            # 判斷連線類型
            connection_type = ConnectionType.USB
            if ':' in serial:  # IP:Port 格式
                connection_type = ConnectionType.WIFI
            
            devices.append({
                'serial': serial,
                'state': state,
                'connection_type': connection_type
            })
        
        # 更新緩存
        if use_cache:
            self._devices_cache = devices
            self._devices_cache_time = time.time()
        
        logger.debug(f"發現 {len(devices)} 台設備")
        return devices
    
    def clear_devices_cache(self):
        """清除設備列表緩存（在連接或斷開設備後調用）"""
        self._devices_cache = None
        self._devices_cache_time = 0
        logger.debug("設備列表緩存已清除")
    
    def connect(self, ip: str, port: int = ADB_DEFAULT_PORT) -> Tuple[bool, str]:
        """連接到設備（WiFi ADB）"""
        target = f"{ip}:{port}"
        success, output = self.execute_command(f"connect {target}")
        
        if success or "already connected" in output.lower():
            logger.info(f"已連接到設備: {target}")
            # 清除緩存，強制下次獲取最新列表
            self.clear_devices_cache()
            return True, output
        
        logger.error(f"連接失敗: {target} - {output}")
        return False, output
    
    def disconnect(self, device: str) -> Tuple[bool, str]:
        """斷開設備連接"""
        success, output = self.execute_command(f"disconnect {device}")
        logger.info(f"斷開設備: {device}")
        # 清除緩存，強制下次獲取最新列表
        if success:
            self.clear_devices_cache()
        return success, output
    
    def connect_batch(
        self,
        devices: List[Tuple[str, int]],  # List of (ip, port) tuples
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Tuple[str, bool, str]]:
        """
        並發連接到多個設備（大幅提升批量連接速度）
        
        Args:
            devices: 設備列表 [(ip, port), ...]
            max_workers: 最大並發數（默認 10）
            progress_callback: 進度回調函數 callback(completed, total)
        
        Returns:
            [(connection_string, success, message), ...]
            
        範例：
            devices = [("192.168.1.100", 5555), ("192.168.1.101", 5555)]
            results = adb_manager.connect_batch(devices)
            
            for connection_str, success, msg in results:
                print(f"{connection_str}: {'✅' if success else '❌'} {msg}")
        """
        if not devices:
            return []
        
        results = []
        completed = 0
        total = len(devices)
        
        logger.info(f"🔌 開始並發連接: {total} 台設備（並發數：{max_workers}）")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_device = {
                    executor.submit(self.connect, ip, port): (ip, port)
                    for ip, port in devices
                }
                
                # 收集結果（按完成順序，不保證原始順序）
                for future in as_completed(future_to_device):
                    ip, port = future_to_device[future]
                    connection_str = f"{ip}:{port}"
                    try:
                        success, message = future.result()
                        results.append((connection_str, success, message))
                    except Exception as e:
                        logger.error(f"❌ 連接異常: {connection_str} - {e}")
                        results.append((connection_str, False, f"連接異常: {str(e)}"))
                    
                    completed += 1
                    if progress_callback:
                        try:
                            progress_callback(completed, total)
                        except Exception as e:
                            logger.warning(f"進度回調失敗: {e}")
            
            logger.info(f"✅ 並發連接完成: {completed}/{total}")
            return results
            
        except Exception as e:
            logger.error(f"❌ 並發連接失敗: {e}")
            return results
    
    def enable_tcpip(self, device: str, port: int = ADB_DEFAULT_PORT) -> Tuple[bool, str]:
        """
        啟用 TCP/IP 模式（用於 USB 轉 WiFi）
        
        Args:
            device: 設備序列號
            port: TCP/IP 端口
        """
        success, output = self.execute_command(f"tcpip {port}", device)
        if success:
            logger.info(f"已啟用 TCP/IP 模式: {device}")
        return success, output

    def prevent_sleep(self, device: str) -> Tuple[bool, str]:
        """
        讓 Quest 盡量不要進入休眠。

        為什麼需要：Quest 一旦真正休眠，adbd 會整個停止（實測 5555 與無線偵錯 TLS 埠
        雙雙 Connection refused），而 Quest 不支援 Wake-on-LAN——Android 平台沒有
        WoWLAN API，連 ArborXR 的「睡眠時保持連線」也只支援 PICO 而非 Quest。
        也就是說「睡著後遠端叫醒」做不到，唯一辦法是一開始就別讓它睡。

        必須趁設備醒著（adb 可連）時套用。

        限制（誠實說明）：
        - stay_on_while_plugged_in 只在「插著電」時有效
        - screen_off_timeout 只擋閒置計時器，擋不掉「摘下頭盔」觸發的睡眠
        - prox_close 讓頭盔誤以為一直被戴著，是最有效的一項；但它是計時租約，
          斷開 adb 連線後約 10 分鐘會自動恢復，需要定期重下

        Returns:
            (是否全部成功, 每個步驟的結果說明)
        """
        steps = [
            ("input keyevent KEYCODE_WAKEUP", "喚醒螢幕"),
            ("settings put global stay_on_while_plugged_in 7", "插電時不休眠"),
            ("settings put system screen_off_timeout 2147483647", "螢幕不自動關閉"),
            ("am broadcast -a com.oculus.vrpowermanager.prox_close", "關閉近接感應器"),
        ]
        logs, all_ok = [], True
        for cmd, label in steps:
            ok, out = self.execute_command(f"shell {cmd}", device, timeout=15)
            out = (out or "").strip().replace("\n", " ")[:80]
            if ok:
                logs.append(f"✅ {label}")
            else:
                all_ok = False
                logs.append(f"❌ {label}：{out or '失敗'}")
        return all_ok, "；".join(logs)

    WIRELESS_HELPER_PACKAGE = "tdg.oculuswirelessadb"

    def install_wireless_helper(self, device: str, apk_path: str) -> Tuple[bool, str]:
        """
        安裝「無線 ADB helper」並授予 WRITE_SECURE_SETTINGS。

        這個 App 的角色是保險：當某台重開機後 5555 與無線偵錯都關掉、adb 完全連不上時，
        戴上頭盔開它一次就能把無線偵錯打開（那個「允許」確認框只能在頭盔裡按）。
        平常的自動救援走的是 reconnect_via_mdns，用不到它。

        Returns:
            (是否就緒, 說明)
        """
        pkg = self.WIRELESS_HELPER_PACKAGE

        ok, out = self.execute_command(f"shell pm list packages {pkg}", device, timeout=20)
        already = pkg in (out or "")

        if not already:
            from pathlib import Path as _P
            if not _P(apk_path).exists():
                return False, f"找不到 APK：{apk_path}（先跑 python3 tools/setup_wireless_helper.py 下載）"
            ok, out = self.execute_command(f"install -r {apk_path}", device, timeout=300)
            if "Success" not in (out or ""):
                return False, f"安裝失敗：{(out or '').strip()[:100]}"

        self.execute_command(
            f"shell pm grant {pkg} android.permission.WRITE_SECURE_SETTINGS",
            device, timeout=20)
        ok, out = self.execute_command(f"shell dumpsys package {pkg}", device, timeout=25)
        granted = "WRITE_SECURE_SETTINGS: granted=true" in (out or "")
        if not granted:
            return False, "已安裝但授權失敗"
        return True, ("已安裝並授權" if not already else "已裝過，授權正常")

    def ensure_wireless_debugging(self, device: str) -> Tuple[bool, str]:
        """
        確保該設備的「無線偵錯」已啟用，作為重開機後的救援通道。

        為什麼重要：Quest 重開機會清空 service.adb.tcp.port（5555 因此關閉）。若無線偵錯
        是開的，adbd 會另外在隨機埠提供 TLS 連線並用 mDNS 廣播，我們就能從那裡連進去重下
        tcpip 5555（見 reconnect_via_mdns）——不必接 USB，也不必戴頭盔開 App。
        若無線偵錯是關的，重開機後就只能接線或戴頭盔。

        重要條件（實測）：shell 雖持有 WRITE_SECURE_SETTINGS 寫得進去，但系統會檢查
        「目前這個 Wi-Fi 網路（依 BSSID）是否已被信任」。沒被信任時，framework 會想在
        頭盔裡跳出「允許在這個網路上使用無線偵錯？」的確認框，而頭盔螢幕沒亮時無法確認，
        於是設定會在約 1 秒內被系統寫回 0。
        因此「第一次」仍必須戴上頭盔確認一次（開 Oculus Wireless ADB 並按允許，
        勾「一律允許」），之後同一個網路就能純用 adb 設定。

        Returns:
            (是否已啟用, 說明)
        """
        ok, out = self.execute_command("shell settings get global adb_wifi_enabled",
                                       device, timeout=10)
        current = (out or "").strip()
        if current == "1":
            return True, "無線偵錯已啟用"

        ok, out = self.execute_command("shell settings put global adb_wifi_enabled 1",
                                       device, timeout=10)
        if not ok:
            return False, f"啟用失敗：{(out or '').strip()[:100]}"

        ok, out = self.execute_command("shell settings get global adb_wifi_enabled",
                                       device, timeout=10)
        if (out or "").strip() == "1":
            return True, "已啟用無線偵錯（重開機後可自動救援）"
        return False, ("設定被系統寫回 0：這個 Wi-Fi 網路尚未被該設備信任。"
                       "請戴上頭盔（螢幕要亮）開一次 Oculus Wireless ADB 並按「允許」"
                       "（勾「一律允許」），之後就能純用 adb 設定。")

    def find_mdns_tls_port(self, ip: str) -> Optional[int]:
        """
        從 adb 的 mDNS 探索結果，找出該 IP 的「無線偵錯」TLS 埠。

        背景：Quest 重開機後 `service.adb.tcp.port` 會被清空（非持久屬性），5555 因此關閉。
        但若該機的無線偵錯（adb_wifi_enabled=1）仍啟用，adbd 會另外在一個「隨機埠」上
        提供 TLS 連線並透過 mDNS 廣播。這個埠每次重開機都不一樣，所以只能動態查詢。

        Returns:
            埠號；找不到則 None
        """
        ok, output = self.execute_command("mdns services", timeout=10)
        if not ok:
            return None
        # 格式：adb-XXXX-YYYY\t_adb-tls-connect._tcp\t192.168.68.90:36727
        for line in output.splitlines():
            if "_adb-tls-connect" not in line:
                continue
            m = re.search(rf"{re.escape(ip)}:(\d+)", line)
            if m:
                return int(m.group(1))
        return None

    def reconnect_via_mdns(
        self,
        ip: str,
        port: int = ADB_DEFAULT_PORT,
        settle_seconds: float = 2.5,
    ) -> Tuple[bool, str]:
        """
        重開機後救援：不必接 USB、也不必戴頭盔開 App。

        流程：mDNS 找出無線偵錯的 TLS 埠 → 連進去 → 下 tcpip 5555 → 再用 5555 連回來。

        前提：該設備的無線偵錯必須是開啟的（adb_wifi_enabled=1）且本機金鑰已配對過。
        實測若該機 adb_wifi_enabled=0，TLS 埠會 Connection refused，此時只能戴上頭盔
        開一次 Oculus Wireless ADB（或手動開無線偵錯）。

        Returns:
            (是否成功, 過程說明)
        """
        import time

        logs = []
        tls_port = self.find_mdns_tls_port(ip)
        if not tls_port:
            return False, ("找不到無線偵錯廣播——該設備的無線偵錯可能沒開啟。"
                           "需戴上頭盔開一次 Oculus Wireless ADB（或在開發者選項開啟無線偵錯）。")
        logs.append(f"mDNS 找到無線偵錯埠：{ip}:{tls_port}")

        tls_target = f"{ip}:{tls_port}"
        ok, out = self.execute_command(f"connect {tls_target}", timeout=15)
        out = (out or "").strip()
        logs.append(f"$ adb connect {tls_target} → {out or ('OK' if ok else '失敗')}")
        if "connected" not in out.lower():
            if "refused" in out.lower():
                return False, "\n".join(logs + [
                    "TLS 埠拒絕連線：該設備的無線偵錯已關閉（mDNS 記錄是過期快取）。"
                    "需戴上頭盔開一次 Oculus Wireless ADB。"])
            return False, "\n".join(logs + ["無法連上無線偵錯埠"])

        ok, out = self.enable_tcpip(tls_target, port)
        logs.append(f"$ adb -s {tls_target} tcpip {port} → {(out or '').strip() or ('OK' if ok else '失敗')}")
        time.sleep(settle_seconds)  # adbd 重啟需要一點時間

        ok, out = self.connect(ip, port)
        logs.append(f"$ adb connect {ip}:{port} → {(out or '').strip()}")
        if not ok:
            time.sleep(1.0)
            ok, out = self.connect(ip, port)
            logs.append(f"（重試）$ adb connect {ip}:{port} → {(out or '').strip()}")

        # 以 adb devices 的實際狀態為準（adb connect 會樂觀回報成功）
        target = f"{ip}:{port}"
        live = {d.get('serial'): d.get('state')
                for d in self.get_devices(use_cache=False)}
        if live.get(target) == 'device':
            logs.append(f"✅ {target} 已恢復（狀態 device）")
            return True, "\n".join(logs)
        logs.append(f"❌ {target} 狀態為 {live.get(target) or '不存在'}")
        return False, "\n".join(logs)

    def reconnect_via_tcpip(
        self,
        ip: str,
        port: int = ADB_DEFAULT_PORT,
        prefer_serial: Optional[str] = None,
        settle_seconds: float = 1.5
    ) -> Tuple[bool, str]:
        """
        先把 USB 連線的設備切到 TCP/IP 模式，再用 WiFi 連接。

        流程（等同手動操作）：
            1. adb devices                  取得目前以 USB 連線的設備序號
            2. adb -s <serial> tcpip <port> 把該設備切到 TCP/IP 模式
            3. adb connect <ip>:<port>      再用 WiFi 連接

        Args:
            ip: 目標設備 IP
            port: TCP/IP 端口（預設 5555）
            prefer_serial: 偏好的 USB 序號（通常是 device.serial）；在 adb devices 中對得到就用它
            settle_seconds: 下完 tcpip 後等待 adbd 重啟的秒數

        Returns:
            (success, output)；output 內含每一步的指令與結果，方便在 UI 顯示
        """
        import time

        if not ip:
            return False, "設備沒有 IP，無法以 TCP/IP 連接"

        logs = []

        # 1. adb devices（強制刷新，不用快取）
        devices = self.get_devices(use_cache=False)
        usb_devices = [
            d for d in devices
            if d.get('state') == 'device' and ':' not in str(d.get('serial', ''))
        ]
        listed = ', '.join(f"{d.get('serial')}({d.get('state')})" for d in devices) or '(無)'
        logs.append(f"$ adb devices → {listed}")

        # 2. 決定要對哪個 USB 序號下 tcpip
        target_serial = None
        if prefer_serial and any(d.get('serial') == prefer_serial for d in usb_devices):
            target_serial = prefer_serial
        elif len(usb_devices) == 1:
            target_serial = usb_devices[0]['serial']

        if target_serial:
            ok_tcp, out_tcp = self.enable_tcpip(target_serial, port)
            logs.append(f"$ adb -s {target_serial} tcpip {port} → {(out_tcp or '').strip() or ('OK' if ok_tcp else '失敗')}")
            time.sleep(settle_seconds)   # tcpip 會重啟 adbd，稍等再連
        elif not usb_devices:
            logs.append("ℹ️ 沒有 USB 設備，純 WiFi 重連（略過 tcpip，直接 adb connect）")
        else:
            usb_list = ', '.join(d['serial'] for d in usb_devices)
            logs.append(f"⚠️ 有多台 USB 設備且無法對應目標序號（prefer_serial={prefer_serial}），略過 tcpip：{usb_list}")

        # 3. adb connect <ip>:<port>（剛重啟 adbd，失敗再等一下重試一次）
        ok_conn, out_conn = self.connect(ip, port)
        logs.append(f"$ adb connect {ip}:{port} → {(out_conn or '').strip()}")
        success = ok_conn or 'already connected' in (out_conn or '').lower()
        if not success and target_serial:
            time.sleep(1.0)
            ok_conn, out_conn = self.connect(ip, port)
            logs.append(f"$ adb connect {ip}:{port} (retry) → {(out_conn or '').strip()}")
            success = ok_conn or 'already connected' in (out_conn or '').lower()

        return success, "\n".join(logs)

    def get_device_ip(self, device: str) -> Optional[str]:
        """取得設備 IP 地址"""
        # 嘗試取得 WiFi IP
        success, output = self.execute_shell_command(
            "ip addr show wlan0",
            device
        )
        
        if success:
            # 解析 IP 地址
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', output)
            if match:
                ip = match.group(1)
                logger.info(f"設備 IP: {ip}")
                return ip
        
        return None
    
    def get_device_info(self, device: str) -> Dict[str, str]:
        """取得設備詳細資訊"""
        info = {}
        
        # 型號
        success, output = self.execute_command(f"-s {device} shell getprop ro.product.model")
        if success:
            info['model'] = output
        
        # Android 版本
        success, output = self.execute_command(f"-s {device} shell getprop ro.build.version.release")
        if success:
            info['android_version'] = output
        
        # 序列號
        success, output = self.execute_command(f"-s {device} get-serialno")
        if success:
            info['serial'] = output
        
        return info
    
    def get_battery_level(self, device: str) -> Optional[int]:
        """取得電池電量"""
        success, output = self.execute_shell_command(
            "dumpsys battery | grep level",
            device
        )
        
        if success:
            match = re.search(r'level: (\d+)', output)
            if match:
                return int(match.group(1))
        
        return None
    
    def get_battery_temperature(self, device: str) -> Optional[float]:
        """取得電池溫度"""
        success, output = self.execute_shell_command(
            "dumpsys battery | grep temperature",
            device
        )
        
        if success:
            match = re.search(r'temperature: (\d+)', output)
            if match:
                # 溫度單位是 0.1°C，需要除以 10
                return int(match.group(1)) / 10.0
        
        return None
    
    def is_charging(self, device: str) -> bool:
        """檢查是否正在充電"""
        success, output = self.execute_shell_command(
            "dumpsys battery | grep 'AC powered\\|USB powered'",
            device
        )
        
        if success:
            return 'true' in output.lower()
        
        return False
    
    def get_device_status(self, device: str) -> Dict[str, Any]:
        """
        一次性獲取設備所有狀態（高效批量查詢）
        
        Returns:
            包含以下資訊的字典：
            - battery: 電量百分比 (int)
            - temperature: 溫度 (float, °C)
            - is_charging: 是否充電中 (bool)
            - is_screen_on: 螢幕是否開啟 (bool)
            - is_awake: 是否清醒（非休眠） (bool)
            - uptime: 開機時間（秒） (int)
        """
        status = {
            'battery': 0,
            'temperature': 0.0,
            'is_charging': False,
            'is_screen_on': False,
            'is_awake': True,
            'uptime': 0,
        }
        
        try:
            command = """dumpsys battery | grep -E 'level:|temperature:|powered:' && echo '---POWER---' && dumpsys power | grep -E 'Display Power|mWakefulness=' && echo '---UPTIME---' && cat /proc/uptime | cut -d' ' -f1"""
            
            success, output = self.execute_shell_command(command, device, timeout=15)
            
            if not success:
                logger.warning(f"獲取設備狀態失敗: {device}")
                return status
            
            # 解析輸出
            lines = output.split('\n')
            
            # 解析電池資訊
            for line in lines:
                # 電量
                if 'level:' in line:
                    match = re.search(r'level:\s*(\d+)', line)
                    if match:
                        status['battery'] = int(match.group(1))
                
                # 溫度（單位：0.1°C）
                elif 'temperature:' in line:
                    match = re.search(r'temperature:\s*(\d+)', line)
                    if match:
                        status['temperature'] = int(match.group(1)) / 10.0
                
                # 充電狀態
                elif 'powered:' in line:
                    if 'true' in line.lower():
                        status['is_charging'] = True
                
                # 螢幕狀態
                elif 'Display Power' in line:
                    if 'ON' in line:
                        status['is_screen_on'] = True
                
                # 清醒狀態
                elif 'mWakefulness=' in line:
                    if 'Asleep' in line or 'Dozing' in line:
                        status['is_awake'] = False
                    else:
                        status['is_awake'] = True
                
                # 開機時間
                elif line.strip() and not line.startswith('---'):
                    try:
                        uptime = float(line.strip().split()[0])
                        status['uptime'] = int(uptime)
                    except (ValueError, IndexError):
                        pass
            
            logger.debug(f"設備狀態: {device} -> {status}")
            return status
            
        except Exception as e:
            logger.error(f"解析設備狀態失敗: {device} - {e}")
            return status
    
    def sleep_device(self, device: str) -> Tuple[bool, str]:
        """設備休眠"""
        return self.execute_shell_command(
            "input keyevent KEYCODE_SLEEP",
            device
        )
    
    def wake_device(self, device: str) -> Tuple[bool, str]:
        """喚醒設備"""
        return self.execute_shell_command(
            "input keyevent KEYCODE_WAKEUP",
            device
        )
    
    def check_scrcpy_available(self) -> bool:
        """檢查 scrcpy 是否可用"""
        try:
            result = subprocess.run(
                ['scrcpy', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _parse_crop_size(self, crop: Optional[str]) -> Optional[Tuple[int, int]]:
        """從 scrcpy crop 參數中解析寬高。"""
        if not crop:
            return None

        try:
            width_str, height_str, _, _ = crop.split(":")
            width = int(width_str)
            height = int(height_str)
            if width > 0 and height > 0:
                return width, height
        except (ValueError, AttributeError):
            logger.debug(f"無法解析 scrcpy crop 尺寸: {crop}")

        return None

    def _estimate_scrcpy_window_size(
        self,
        options: Dict[str, Any],
        crop: Optional[str]
    ) -> Tuple[int, int]:
        """估算 scrcpy 視窗尺寸，供自動排版使用。"""
        window_width = options.get('window_width') or SCRCPY_AUTO_WINDOW_WIDTH
        window_height = options.get('window_height')

        if window_height:
            return int(window_width), int(window_height)

        crop_size = self._parse_crop_size(crop)
        if crop_size:
            crop_width, crop_height = crop_size
            estimated_height = max(240, int(window_width * crop_height / crop_width))
            return int(window_width), estimated_height

        return int(window_width), SCRCPY_AUTO_WINDOW_HEIGHT

    def _get_macos_screen_size_from_coregraphics(self) -> Optional[Tuple[int, int]]:
        """使用 CoreGraphics 取得主螢幕尺寸，避免 tkinter 在 macOS 上觸發原生崩潰。"""
        try:
            import ctypes

            core_graphics = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
            display_id = core_graphics.CGMainDisplayID()
            if display_id == 0:
                return None

            core_graphics.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
            core_graphics.CGDisplayPixelsWide.restype = ctypes.c_size_t
            core_graphics.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
            core_graphics.CGDisplayPixelsHigh.restype = ctypes.c_size_t

            screen_width = int(core_graphics.CGDisplayPixelsWide(display_id))
            screen_height = int(core_graphics.CGDisplayPixelsHigh(display_id))

            if screen_width > 0 and screen_height > 0:
                return screen_width, screen_height
        except Exception as e:
            logger.debug(f"CoreGraphics 螢幕尺寸檢測失敗: {e}")

        return None

    def _get_macos_screen_size_from_system_profiler(self) -> Optional[Tuple[int, int]]:
        """從 system_profiler 解析主顯示器解析度。"""
        try:
            result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None

            resolutions: List[Tuple[int, int]] = []
            pending_resolution: Optional[Tuple[int, int]] = None

            for line in result.stdout.splitlines():
                stripped = line.strip()
                match = re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", stripped)
                if match:
                    pending_resolution = (int(match.group(1)), int(match.group(2)))
                    resolutions.append(pending_resolution)
                    continue

                if stripped.startswith("Main Display:") and pending_resolution:
                    return pending_resolution

            if resolutions:
                return resolutions[0]
        except Exception as e:
            logger.debug(f"system_profiler 螢幕尺寸檢測失敗: {e}")

        return None

    def _get_screen_size(self) -> Tuple[int, int]:
        """取得主螢幕尺寸，失敗時回退到預設值。"""
        if platform.system() == "Darwin":
            screen_size = self._get_macos_screen_size_from_coregraphics()
            if screen_size:
                return screen_size

            screen_size = self._get_macos_screen_size_from_system_profiler()
            if screen_size:
                return screen_size

            logger.debug("macOS 螢幕尺寸檢測失敗，改用預設值")
            return SCRCPY_FALLBACK_SCREEN_SIZE

        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.update_idletasks()
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            root.destroy()

            if screen_width > 0 and screen_height > 0:
                return screen_width, screen_height
        except Exception as e:
            logger.debug(f"取得螢幕尺寸失敗，改用預設值: {e}")

        return SCRCPY_FALLBACK_SCREEN_SIZE

    def _has_active_scrcpy_processes(self) -> bool:
        """檢查目前是否已有 scrcpy 視窗在運行。"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq scrcpy.exe'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return 'scrcpy.exe' in result.stdout.lower()

            result = subprocess.run(
                ['pgrep', '-x', 'scrcpy'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except Exception as e:
            logger.debug(f"檢查 scrcpy 進程失敗: {e}")
            return False

    def reset_scrcpy_window_layout(self):
        """重置 scrcpy 視窗自動排版索引。"""
        with self._scrcpy_layout_lock:
            self._scrcpy_window_index = 0

    def _apply_auto_arrange_options(
        self,
        options: Dict[str, Any],
        crop: Optional[str]
    ) -> Dict[str, Any]:
        """依照螢幕尺寸自動安排 scrcpy 視窗位置。"""
        arranged_options = options.copy()
        window_width, window_height = self._estimate_scrcpy_window_size(arranged_options, crop)
        screen_width, screen_height = self._get_screen_size()

        layout_total = arranged_options.get('layout_total')
        try:
            layout_total = int(layout_total) if layout_total else None
        except (TypeError, ValueError):
            layout_total = None

        preferred_columns = arranged_options.get('layout_columns', SCRCPY_GRID_COLUMNS)
        try:
            preferred_columns = max(1, int(preferred_columns))
        except (TypeError, ValueError):
            preferred_columns = SCRCPY_GRID_COLUMNS

        columns = min(preferred_columns, layout_total) if layout_total else preferred_columns
        columns = max(1, columns)
        rows_needed = (
            max(1, (layout_total + columns - 1) // columns)
            if layout_total
            else SCRCPY_GRID_COLUMNS
        )

        available_width = max(window_width, screen_width - 2 * SCRCPY_WINDOW_MARGIN_X)
        available_height = max(window_height, screen_height - 2 * SCRCPY_WINDOW_MARGIN_Y)
        max_window_width = max(
            160,
            (available_width - (columns - 1) * SCRCPY_WINDOW_GAP_X) // columns
        )
        max_window_height = max(
            120,
            (available_height - (rows_needed - 1) * SCRCPY_WINDOW_GAP_Y) // rows_needed
        )

        scale = min(
            1.0,
            max_window_width / window_width if window_width else 1.0,
            max_window_height / window_height if window_height else 1.0,
        )
        if scale < 1.0:
            window_width = max(160, int(window_width * scale))
            window_height = max(120, int(window_height * scale))

        arranged_options['window_width'] = window_width
        arranged_options['window_height'] = window_height

        grid_width = columns * window_width + (columns - 1) * SCRCPY_WINDOW_GAP_X
        grid_height = rows_needed * window_height + (rows_needed - 1) * SCRCPY_WINDOW_GAP_Y

        def choose_grid_origin(preferred_value, screen_size, grid_size, margin):
            try:
                preferred = int(preferred_value) if preferred_value is not None else None
            except (TypeError, ValueError):
                preferred = None

            if (
                preferred is not None
                and preferred >= margin
                and preferred + grid_size <= screen_size - margin
            ):
                return preferred

            return max(0, (screen_size - grid_size) // 2)

        base_x = choose_grid_origin(
            arranged_options.get('window_x'),
            screen_width,
            grid_width,
            SCRCPY_WINDOW_MARGIN_X
        )
        base_y = choose_grid_origin(
            arranged_options.get('window_y'),
            screen_height,
            grid_height,
            SCRCPY_WINDOW_MARGIN_Y
        )

        slot_override = arranged_options.get('layout_slot')
        try:
            slot_override = int(slot_override) if slot_override is not None else None
        except (TypeError, ValueError):
            slot_override = None

        if slot_override is not None:
            slot = max(0, slot_override)
        else:
            with self._scrcpy_layout_lock:
                if not self._has_active_scrcpy_processes():
                    self._scrcpy_window_index = 0

                slot = self._scrcpy_window_index
                self._scrcpy_window_index += 1

        column = slot % columns
        row = slot // columns

        arranged_options['window_x'] = base_x + column * (window_width + SCRCPY_WINDOW_GAP_X)
        arranged_options['window_y'] = base_y + row * (window_height + SCRCPY_WINDOW_GAP_Y)
        return arranged_options

    def start_scrcpy(
        self, 
        device: str, 
        window_title: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        crop: Optional[str] = None,
        auto_arrange: bool = False
    ) -> Tuple[bool, str]:
        """
        啟動 scrcpy 監看設備
        
        Args:
            device: 設備序列號或 IP:Port
            window_title: 視窗標題（選填）
            options: 額外選項（選填）
            crop: 裁切參數 (e.g. "1600:1440:200:300")
            auto_arrange: 是否自動排版視窗位置
        """
        try:
            if not self.check_scrcpy_available():
                return False, "scrcpy 未安裝，請先安裝 scrcpy"
            
            # 載入系統設定（單一設定來源：SCRCPY_CONFIG 當預設底、使用者設定覆蓋、傳入 options 最優先）
            from config.settings import get_user_config, SCRCPY_CONFIG
            user_config = get_user_config()
            final_options = {**SCRCPY_CONFIG, **user_config.get('scrcpy', {})}
            if options:
                final_options.update(options)
            
            # 構建命令
            cmd = ['scrcpy', '-s', device]
            
            # 設定視窗標題
            if window_title:
                cmd.extend(['--window-title', window_title])
            
            # 裁切 (User 指定優先，其次是 options，最後是 config)
            # scrcpy argument format: --crop=width:height:x:y
            final_crop = crop or final_options.get('crop')
            if auto_arrange:
                final_options = self._apply_auto_arrange_options(final_options, final_crop)

            if final_crop:
                cmd.extend(['--crop', final_crop])
            
            # === 頻寬限流：預設值全部來自 SCRCPY_CONFIG（唯一來源），使用者可在系統設定頁調整 ===
            # 位元率：scrcpy 3.x 用 --video-bit-rate
            bitrate = final_options.get('bitrate') or SCRCPY_CONFIG['bitrate']
            cmd.extend(['--video-bit-rate', str(bitrate)])

            # 最大畫面寬度
            max_size = final_options.get('max_size', SCRCPY_CONFIG['max_size'])
            if max_size:
                cmd.extend(['-m', str(max_size)])

            # 最大幀率
            max_fps = final_options.get('max_fps', SCRCPY_CONFIG['max_fps'])
            if max_fps and int(max_fps) > 0:
                cmd.extend(['--max-fps', str(max_fps)])

            # 唯讀監看（--no-control）：省一點頻寬也防誤觸。可在系統設定頁把 no_control 關掉以取得控制權
            control_enabled = not final_options.get('no_control', SCRCPY_CONFIG['no_control'])
            if not control_enabled:
                cmd.append('--no-control')

            # 視窗大小
            if final_options.get('window_width'):
                cmd.extend(['--window-width', str(final_options['window_width'])])
            if final_options.get('window_height'):
                cmd.extend(['--window-height', str(final_options['window_height'])])

            # 視窗位置
            if final_options.get('window_x') is not None:
                cmd.extend(['--window-x', str(final_options['window_x'])])
            if final_options.get('window_y') is not None:
                cmd.extend(['--window-y', str(final_options['window_y'])])

            # 渲染驅動
            if final_options.get('render_driver'):
                cmd.extend(['--render-driver', final_options['render_driver']])

            # 布林選項（以下需要 control 模式；--no-control 時自動略過，避免 scrcpy 報錯而啟動失敗）
            if control_enabled and final_options.get('stay_awake', True):
                cmd.append('--stay-awake')

            if control_enabled and final_options.get('show_touches', False):
                cmd.append('--show-touches')

            if final_options.get('fullscreen', False):
                cmd.append('--fullscreen')

            if final_options.get('always_on_top', False):
                cmd.append('--always-on-top')

            if control_enabled and final_options.get('turn_screen_off', False):
                cmd.append('--turn-screen-off')

            # 音訊設定 - 預設禁用以避免關閉 Quest 的聲音
            if not final_options.get('enable_audio', False):
                cmd.append('--no-audio')
            
            # 啟動 scrcpy（非阻塞）
            logger.info(f"啟動 scrcpy: {' '.join(cmd)}")
            
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # 獨立進程，不受父進程影響
            )
            
            logger.info(f"scrcpy 已啟動監看設備: {device}")
            return True, f"已啟動監看視窗"
            
        except Exception as e:
            logger.error(f"啟動 scrcpy 失敗: {e}")
            return False, f"啟動失敗: {str(e)}"

    def start_quest_single_eye_scrcpy(
        self,
        device: str,
        window_title: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        auto_arrange: bool = False
    ) -> Tuple[bool, str]:
        """啟動 Quest 單眼監看視窗。"""
        return self.start_scrcpy(
            device=device,
            window_title=window_title,
            options=options,
            # crop=QUEST_SINGLE_EYE_CROP,  # 暫時關閉單眼裁切，用於測試黑屏是否與 crop 有關
            auto_arrange=auto_arrange
        )

    def ffmpeg_available(self) -> bool:
        """Mac 端有沒有 ffmpeg（裝置端縮圖法要用它抽幀）。結果快取。"""
        if getattr(self, '_ffmpeg_ok', None) is None:
            import shutil
            self._ffmpeg_ok = shutil.which('ffmpeg') is not None
        return self._ffmpeg_ok

    def capture_screenshot(self, device: str, max_width: int = 320, quality: int = 50,
                           method: str = "ondevice") -> Optional[bytes]:
        """抓一張縮圖（給畫面牆用），回傳 JPEG bytes；失敗回 None。

        method:
          'ondevice'  裝置端用 screenrecord 縮放 → ffmpeg 抽 1 幀 → JPEG。
                      小又快（Quest 實測 ~1.2s / ~20KB），需要 Mac 有 ffmpeg。
                      （這是 minicap 的替代：minicap 在 Android 12+/SDK34 已無法運作。）
          'screencap' adb screencap 全解析度 PNG → Mac 端縮放。相容任何裝置，但很重
                      （Quest 是雙眼 framebuffer，一張 ~10MB、透過 WiFi 要十幾秒）。
        """
        if method in ("ondevice", "minicap", "screenrecord"):
            data = self._capture_ondevice(device, max_width, quality)
            if data is not None:
                return data
            # ondevice 失敗就回 None（不自動退回很重的 screencap，避免拖垮）
            return None
        return self._capture_screencap(device, max_width, quality)

    def _capture_ondevice(self, device: str, max_width: int, quality: int) -> Optional[bytes]:
        """裝置端 screenrecord 縮放 → ffmpeg 抽 1 幀 → JPEG。需 ffmpeg。失敗回 None。"""
        if not self.ffmpeg_available():
            return None

        w = max(2, int(max_width) - (int(max_width) % 2))
        h = int(round(w * 9 / 16))
        h -= h % 2
        # UI quality(20~90, 高=好) 映射到 ffmpeg -q:v(2~31, 低=好)
        qv = max(2, min(31, int(round(2 + (90 - int(quality)) / 70 * 29))))

        p1 = None
        try:
            # 裝置端就把畫面縮到 w×h 再編 h264（傳出來只有幾十 KB），exec-out 為 binary-safe
            p1 = subprocess.Popen(
                ['adb', '-s', device, 'exec-out', 'screenrecord',
                 '--output-format=h264', '--size', f'{w}x{h}',
                 '--bit-rate', '1000000', '--time-limit', '1', '-'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            ff = subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'h264',
                 '-i', 'pipe:0', '-frames:v', '1', '-q:v', str(qv), '-f', 'mjpeg', 'pipe:1'],
                stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20
            )
            try:
                p1.stdout.close()
            except Exception:
                pass
            p1.wait(timeout=5)

            data = ff.stdout
            if data and data[:3] == b'\xff\xd8\xff':
                return data
            return None
        except Exception as e:
            logger.debug(f"裝置端擷取失敗 {device}: {e}")
            return None
        finally:
            if p1 is not None and p1.poll() is None:
                try:
                    p1.kill()
                except Exception:
                    pass

    def _capture_screencap(self, device: str, max_width: int, quality: int) -> Optional[bytes]:
        """adb screencap 全解析度 PNG → Mac 端縮放成 JPEG。相容但重（Quest ~10MB/張）。"""
        try:
            # -p 輸出 PNG；exec-out 為 binary-safe。Quest framebuffer 很大，timeout 放寬到 25s。
            result = subprocess.run(
                ['adb', '-s', device, 'exec-out', 'screencap', '-p'],
                capture_output=True, timeout=25
            )
            if result.returncode != 0 or not result.stdout:
                return None

            from PIL import Image
            import io
            img = Image.open(io.BytesIO(result.stdout))
            w, h = img.size
            if w > max_width:
                img = img.resize((max_width, max(1, int(h * max_width / w))))
            buf = io.BytesIO()
            img.convert('RGB').save(buf, format='JPEG', quality=int(quality))
            return buf.getvalue()
        except Exception as e:
            logger.debug(f"screencap 擷取失敗 {device}: {e}")
            return None

    def start_app(self, device: str, package: str, activity: str) -> Tuple[bool, str]:
        """啟動應用程式"""
        return self.execute_shell_command(
            f"am start -n {package}/{activity}",
            device
        )

    def launch_app_with_extras(
        self, 
        device: str, 
        package: str, 
        activity: str, 
        extras: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        啟動應用程式並帶入 Intent Extras
        
        Args:
            device: 設備序列號
            package: 套件名稱
            activity: Activity 名稱 (e.g., .MainActivity)
            extras: 參數字典 (支援 str, int, bool)
        """
        cmd = f"am start -n {package}/{activity}"
        
        for key, value in extras.items():
            if isinstance(value, int):
                cmd += f" --ei {key} {value}"
            elif isinstance(value, bool):
                cmd += f" --ez {key} {'true' if value else 'false'}"
            else:
                # 預設為字串
                cmd += f" --es {key} \"{str(value)}\""
                
        return self.execute_shell_command(cmd, device)
    
    def stop_app(self, device: str, package: str) -> Tuple[bool, str]:
        """關閉應用程式"""
        return self.execute_shell_command(
            f"am force-stop {package}",
            device
        )
    
    def send_broadcast(
        self,
        device: str,
        package: str,
        action: str,
        extras: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        """發送廣播訊息"""
        cmd = f"am broadcast -a {package}.{action}"
        
        if extras:
            for key, value in extras.items():
                cmd += f" --es {key} \"{value}\""
        
        return self.execute_shell_command(cmd, device)
    
    def install_apk(self, device: str, apk_path: str) -> Tuple[bool, str]:
        """安裝 APK"""
        return self.execute_command(f"-s {device} install -r {apk_path}")
    
    def uninstall_app(self, device: str, package: str) -> Tuple[bool, str]:
        """卸載應用"""
        return self.execute_command(f"-s {device} uninstall {package}")
    
    def reboot_device(self, device: str) -> Tuple[bool, str]:
        """重啟設備"""
        return self.execute_command(f"-s {device} reboot")
    
    def get_screenshot(
        self,
        device: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        quality: int = 80
    ) -> Optional[bytes]:
        """
        獲取設備截圖（PNG 格式）
        
        Args:
            device: 設備序列號或 IP:Port
            max_width: 最大寬度（像素），None 表示原始大小
            max_height: 最大高度（像素），None 表示原始大小
            quality: JPEG 品質（1-100），僅在調整大小時使用
        
        Returns:
            PNG 格式的圖像數據，失敗返回 None
        """
        try:
            # 執行截圖命令
            cmd = ['adb', '-s', device, 'shell', 'screencap', '-p']
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=ADB_CONNECTION_TIMEOUT
            )
            
            if result.returncode != 0:
                logger.error(f"截圖失敗: {device}")
                return None
            
            # 處理 Windows 換行符問題
            img_bytes = result.stdout.replace(b'\r\n', b'\n')
            
            if max_width or max_height:
                try:
                    from PIL import Image
                    import io
                    
                    # 解碼圖像
                    img = Image.open(io.BytesIO(img_bytes))
                    
                    # 計算新尺寸（保持比例）
                    width, height = img.size
                    if max_width and width > max_width:
                        height = int(height * max_width / width)
                        width = max_width
                    if max_height and height > max_height:
                        width = int(width * max_height / height)
                        height = max_height
                    
                    # 調整大小
                    if (width, height) != img.size:
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                        logger.debug(f"截圖已調整大小: {device} -> {width}x{height}")
                    
                    # 轉換回 PNG 格式
                    output = io.BytesIO()
                    img.save(output, format='PNG', optimize=True)
                    return output.getvalue()
                    
                except ImportError:
                    logger.warning("PIL 未安裝，無法調整截圖大小")
                    return img_bytes
                except Exception as e:
                    logger.error(f"調整截圖大小失敗: {e}")
                    return img_bytes
            
            return img_bytes
            
        except subprocess.TimeoutExpired:
            logger.error(f"截圖超時: {device}")
            return None
        except Exception as e:
            logger.error(f"截圖失敗: {device} - {e}")
            return None
    
    def screenshot(self, device: str, save_path: str) -> Tuple[bool, str]:
        """
        截圖並儲存到檔案
        
        Args:
            device: 設備序列號或 IP:Port
            save_path: 儲存路徑
        
        Returns:
            (成功, 訊息)
        """
        try:
            img_bytes = self.get_screenshot(device)
            if img_bytes:
                with open(save_path, 'wb') as f:
                    f.write(img_bytes)
                logger.info(f"截圖已儲存: {save_path}")
                return True, f"截圖已儲存到 {save_path}"
            else:
                return False, "截圖失敗"
        except Exception as e:
            logger.error(f"儲存截圖失敗: {e}")
            return False, f"儲存失敗: {str(e)}"
    
    # ==================== 動作執行方法 ====================
    
    def execute_wake_up(self, device: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        執行喚醒動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數（可選）
                - verify: 是否驗證喚醒成功（預設 True）
        
        Returns:
            (成功, 訊息)
        """
        try:
            params = params or {}
            verify = params.get('verify', True)
            
            # 發送喚醒按鍵
            success, output = self.execute_shell_command(
                "input keyevent KEYCODE_WAKEUP",
                device
            )
            
            if not success:
                return False, f"喚醒命令執行失敗: {output}"
            
            # 驗證是否成功喚醒
            if verify:
                import time
                time.sleep(0.5)  # 等待設備響應
                
                # 檢查設備狀態
                success, power_state = self.execute_shell_command(
                    "dumpsys power | grep 'Display Power: state='",
                    device
                )
                
                if success and 'ON' in power_state:
                    logger.info(f"✅ 設備喚醒成功: {device}")
                    return True, "設備已喚醒"
                else:
                    logger.warning(f"⚠️ 無法驗證喚醒狀態: {device}")
                    return True, "喚醒命令已發送（無法驗證狀態）"
            
            logger.info(f"✅ 喚醒命令已發送: {device}")
            return True, "喚醒命令已發送"
        
        except Exception as e:
            logger.error(f"❌ 喚醒失敗: {device} - {e}")
            return False, f"喚醒失敗: {str(e)}"
    
    def execute_sleep(self, device: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        執行休眠動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數（可選）
                - force: 是否強制休眠（預設 False）
                - verify: 是否驗證休眠成功（預設 True）
        
        Returns:
            (成功, 訊息)
        """
        try:
            params = params or {}
            force = params.get('force', False)
            verify = params.get('verify', True)
            
            # 發送休眠按鍵
            keycode = "KEYCODE_SLEEP" if force else "KEYCODE_POWER"
            success, output = self.execute_shell_command(
                f"input keyevent {keycode}",
                device
            )
            
            if not success:
                return False, f"休眠命令執行失敗: {output}"
            
            # 驗證是否成功休眠
            if verify:
                import time
                time.sleep(0.5)  # 等待設備響應
                
                # 檢查設備狀態
                success, power_state = self.execute_shell_command(
                    "dumpsys power | grep 'Display Power: state='",
                    device
                )
                
                if success and 'OFF' in power_state:
                    logger.info(f"✅ 設備休眠成功: {device}")
                    return True, "設備已休眠"
                else:
                    logger.warning(f"⚠️ 無法驗證休眠狀態: {device}")
                    return True, "休眠命令已發送（無法驗證狀態）"
            
            logger.info(f"✅ 休眠命令已發送: {device}")
            return True, "休眠命令已發送"
        
        except Exception as e:
            logger.error(f"❌ 休眠失敗: {device} - {e}")
            return False, f"休眠失敗: {str(e)}"
    
    def execute_keep_awake(self, device: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        執行保持喚醒動作（設置設備在接電源時不進入深度睡眠）
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數（可選）
                - mode: 喚醒模式（預設 3）
                    - 0: 禁用此功能（預設值）
                    - 1: 僅 AC 充電時保持喚醒
                    - 2: 僅 USB 充電時保持喚醒
                    - 3: AC 和 USB 充電時保持喚醒（推薦）
        
        Returns:
            (成功, 訊息)
        """
        try:
            params = params or {}
            mode = params.get('mode', 3)
            
            # 驗證 mode 參數
            if mode not in [0, 1, 2, 3]:
                return False, f"無效的 mode 參數: {mode}（必須為 0、1、2 或 3）"
            
            # 執行 ADB 命令設置 stay_on_while_plugged_in
            success, output = self.execute_shell_command(
                f"settings put global stay_on_while_plugged_in {mode}",
                device
            )
            
            if not success:
                return False, f"設置保持喚醒失敗: {output}"
            
            # 驗證設置是否成功
            verify_success, verify_output = self.execute_shell_command(
                "settings get global stay_on_while_plugged_in",
                device
            )
            
            if verify_success:
                current_mode = verify_output.strip()
                if current_mode == str(mode):
                    mode_names = {
                        0: "禁用（預設值）",
                        1: "僅 AC 充電時保持喚醒",
                        2: "僅 USB 充電時保持喚醒",
                        3: "AC 和 USB 充電時保持喚醒"
                    }
                    mode_name = mode_names.get(mode, f"模式 {mode}")
                    logger.info(f"✅ 保持喚醒設置成功: {device} - {mode_name}")
                    return True, f"保持喚醒已設置為: {mode_name}"
                else:
                    logger.warning(f"⚠️ 設置可能未生效: {device} (期望: {mode}, 實際: {current_mode})")
                    return True, f"保持喚醒命令已發送（當前值: {current_mode}）"
            else:
                logger.warning(f"⚠️ 無法驗證設置: {device}")
                return True, "保持喚醒命令已發送（無法驗證）"
        
        except Exception as e:
            logger.error(f"❌ 保持喚醒設置失敗: {device} - {e}")
            return False, f"保持喚醒設置失敗: {str(e)}"

    def _is_package_installed(self, device: str, package: str) -> bool:
        """檢查 package 是否安裝在此設備。"""
        ok, out = self.execute_shell_command(f"pm path {package}", device)
        return ok and bool(out) and "package:" in out

    def _resolve_launch_activity(self, device: str, package: str) -> Optional[str]:
        """從 dumpsys 找出 package 處理 MAIN 的啟動 activity，回傳 'pkg/activity'；找不到/未安裝回 None。

        activity 名稱會隨 Unity 版本/Player Settings 不同，直接讀 dumpsys 最可靠，
        不必猜 LAUNCHER / VR 類別或固定的 Unity activity 名稱。
        """
        ok, out = self.execute_shell_command(f"dumpsys package {package}", device)
        if not ok or not out or "Unable to find package" in out:
            return None

        import re
        pattern = re.compile(rf"{re.escape(package)}/[A-Za-z0-9_.$]+")
        lines = out.splitlines()
        # 優先：android.intent.action.MAIN 區段下方第一個 pkg/activity（真正的啟動點）
        for i, line in enumerate(lines):
            if "android.intent.action.MAIN:" in line:
                for nxt in lines[i + 1:i + 12]:
                    m = pattern.search(nxt)
                    if m:
                        return m.group(0)
        # 退而求其次：整段任何 pkg/activity 候選
        m = pattern.search(out)
        return m.group(0) if m else None

    def execute_launch_app(self, device: str, params: Dict[str, Any], room_info: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        執行啟動應用動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數
                - package: 應用 package 名稱（必填）
                - activity: Activity 名稱（選填）
                - stop_existing: 是否先關閉已運行的實例（預設 False）
                - wait: 是否等待啟動完成（預設 True）
            room_info: 房間信息（可選）
                - socket_ip: Socket Server IP 地址
                - socket_port: Socket Server 端口
        
        Returns:
            (成功, 訊息)
        """
        try:
            package = params.get('package')
            if not package:
                return False, "缺少 package 參數"
            
            activity = params.get('activity', '')
            stop_existing = params.get('stop_existing', False)
            wait = params.get('wait', True)
            
            if stop_existing:
                self.execute_shell_command(f"am force-stop {package}", device)
                logger.info(f"已關閉已運行的實例: {package}")

            # Socket Server 參數（給 am start 用）
            socket_extras = ""
            if room_info and room_info.get('socket_ip') and room_info.get('socket_port'):
                socket_extras = (
                    f" --es qqquest_server_ip \"{room_info['socket_ip']}\""
                    f" --ei qqquest_server_port {room_info['socket_port']}"
                )
                logger.info(f"📡 添加 Socket Server 參數: {room_info['socket_ip']}:{room_info['socket_port']}")

            wait_flag = " -W" if wait else ""

            # 構建啟動命令（依序嘗試，第一個成功就停）
            if activity:
                launch_cmds = [f"am start -n {package}/{activity}{socket_extras}{wait_flag}"]
            else:
                # 沒指定 activity：一般 app 用 LAUNCHER；Quest/VR app 多半沒有 LAUNCHER，
                # 再試常見的 Unity activity（名稱依 Unity 版本/Player Settings 而不同）與 VR 類別。
                launch_cmds = [
                    f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
                    f"am start -n {package}/com.unity3d.player.UnityPlayerActivity{socket_extras}{wait_flag}",
                    f"am start -n {package}/com.unity3d.player.UnityPlayerGameActivity{socket_extras}{wait_flag}",
                    f"monkey -p {package} -c com.oculus.intent.category.VR 1",
                ]

            last_output = ""
            for cmd in launch_cmds:
                success, output = self.execute_shell_command(cmd, device)
                last_output = output
                method = cmd.split()[0]  # monkey / am
                if success and "Error" not in output and "error" not in output.lower():
                    logger.info(f"✅ 啟動應用成功: {package}（{method}）")
                    return True, f"應用 {package} 已啟動"
                logger.warning(f"啟動嘗試失敗（{method}）: {package} - {output.strip()[:200]}")

            # 以上都失敗且沒指定 activity → 動態解析（dumpsys）真正的啟動 activity 再試一次（最可靠）
            if not activity:
                resolved = self._resolve_launch_activity(device, package)
                if resolved:
                    cmd = f"am start -n {resolved}{socket_extras}{wait_flag}"
                    success, output = self.execute_shell_command(cmd, device)
                    last_output = output
                    if success and "Error" not in output and "error" not in output.lower():
                        logger.info(f"✅ 啟動應用成功: {package}（解析到 {resolved}）")
                        return True, f"應用 {package} 已啟動"
                    logger.warning(f"啟動嘗試失敗（解析 {resolved}）: {package} - {output.strip()[:200]}")
                elif not self._is_package_installed(device, package):
                    msg = f"應用未安裝於此設備：{package}"
                    logger.error(f"❌ {msg}")
                    return False, msg

            logger.error(f"❌ 啟動應用失敗: {package} - {last_output}")
            return False, f"啟動失敗: {last_output}"
        
        except Exception as e:
            logger.error(f"❌ 啟動應用失敗: {e}")
            return False, f"啟動失敗: {str(e)}"

    def execute_resume_app(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        將背景中的應用帶回前景，不先關閉或重啟。

        這適合 Quest 使用者誤觸穿透模式時，把仍在背景運行的遊戲喚回前景。
        """
        try:
            package = params.get('package')
            if not package:
                return False, "缺少 package 參數"

            import time

            activity = params.get('activity') or ""
            if not activity and params.get('resolve_activity', True):
                activity = self._resolve_launcher_activity(device, package) or ""

            def send_back_events(count: int, delay: float = 0.15):
                for _ in range(max(0, count)):
                    self.execute_shell_command("input keyevent 4", device)
                    time.sleep(delay)

            def send_overlay_clear_events(back_events: int = 1, escape_events: int = 1):
                for _ in range(max(0, escape_events)):
                    self.execute_shell_command("input keyevent KEYCODE_ESCAPE", device)
                    time.sleep(0.2)
                send_back_events(back_events, delay=0.2)

            def has_vrshell_panel_overlay(status: Dict[str, str]) -> bool:
                summary = status.get('summary', '').lower()
                return (
                    "com.oculus.vrshell" in summary
                    and any(marker in summary for marker in OCULUS_PANEL_OVERLAY_MARKERS)
                )

            def reset_vrshell_panel_overlay(label: str, status: Dict[str, str]) -> bool:
                if not params.get('force_stop_vrshell_if_panel_overlay', False):
                    return False

                if not has_vrshell_panel_overlay(status):
                    return False

                logger.warning(
                    f"⚠️ resume_app 偵測到 vrshell panel overlay，重置 Quest 系統覆蓋層 ({label}): "
                    f"{status.get('summary', '')}"
                )

                if params.get('send_escape_before_vrshell_reset', True):
                    send_overlay_clear_events(back_events=1, escape_events=1)

                success, output = self.execute_shell_command("am force-stop com.oculus.vrshell", device)
                logger.info(f"resume_app force-stop vrshell output ({device}): {output}")
                time.sleep(float(params.get('vrshell_reset_wait_seconds', 1.0)))

                if params.get('send_wakeup_after_vrshell_reset', True):
                    self.execute_shell_command("input keyevent KEYCODE_WAKEUP", device)
                    time.sleep(0.15)

                return success

            back_count = int(params.get('back_count', 1 if params.get('send_back_first', False) else 0))
            send_back_events(back_count)

            if params.get('send_wakeup_first', True):
                self.execute_shell_command("input keyevent KEYCODE_WAKEUP", device)
                time.sleep(0.1)

            focus_status = self._get_resume_focus_status(device, package)
            if focus_status['state'] in ('system_overlay', 'app_with_overlay') and params.get('send_escape_if_overlay', True):
                send_overlay_clear_events(
                    back_events=int(params.get('overlay_clear_back_count', 0)),
                    escape_events=int(params.get('overlay_clear_escape_count', 1))
                )
                reset_vrshell_panel_overlay("initial", focus_status)

            if (
                params.get('clear_oculus_clearactivity', True)
                and focus_status['state'] in ('system_overlay', 'app_with_overlay')
                and "com.oculus.os.clearactivity" in focus_status['summary'].lower()
            ):
                self.execute_shell_command("am force-stop com.oculus.os.clearactivity", device)
                time.sleep(0.2)

            successes = []
            failures = []

            def run_resume_command(label: str, cmd: str):
                success, output = self.execute_shell_command(cmd, device)
                logger.info(f"resume_app {label} output ({device}): {output}")
                if success and "error" not in output.lower() and "exception" not in output.lower():
                    successes.append(label)
                else:
                    failures.append(f"{label}: {output}")
                    logger.warning(f"⚠️ resume_app {label} 失敗: {package} - {output}")

            def build_explicit_cmd():
                return (
                    "am start --activity-reorder-to-front --activity-single-top --activity-no-animation "
                    f"-a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
                    f"-c com.oculus.intent.category.VR -n {package}/{activity}"
                )

            def run_resume_sequence(sequence_label: str):
                if activity and params.get('explicit_activity_first', True):
                    run_resume_command(f"{sequence_label} explicit activity", build_explicit_cmd())
                    time.sleep(0.25)

                if params.get('use_monkey', True):
                    monkey_cmd = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
                    run_resume_command(f"{sequence_label} monkey", monkey_cmd)
                    time.sleep(0.2)

                if params.get('am_start_after', False):
                    if activity and params.get('explicit_activity_after', True):
                        am_cmd = build_explicit_cmd()
                    else:
                        am_cmd = f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {package}"
                    run_resume_command(f"{sequence_label} am start", am_cmd)

            def verify_stable_focus(label: str, first_status: Dict[str, str]) -> Tuple[bool, Dict[str, str]]:
                stable_checks = max(1, int(params.get('stable_focus_checks', 3)))
                stable_interval = float(params.get('stable_focus_interval_seconds', 0.35))
                current_status = first_status

                for check_index in range(stable_checks):
                    if check_index > 0:
                        time.sleep(stable_interval)
                        current_status = self._get_resume_focus_status(device, package)

                    logger.info(
                        f"resume_app stable focus {label} {check_index + 1}/{stable_checks} ({device}): "
                        f"state={current_status['state']} {current_status['summary']}"
                    )

                    if current_status['state'] != 'app':
                        return False, current_status

                return True, current_status

            run_resume_sequence("primary")

            verify_focus = params.get('verify_focus', True)
            if verify_focus:
                time.sleep(float(params.get('focus_wait_seconds', 0.6)))
                focus_status = self._get_resume_focus_status(device, package)
                logger.info(f"resume_app focus after primary ({device}): {focus_status['summary']}")
                focus_stable, focus_status = verify_stable_focus("primary", focus_status)

                fallback_rounds = int(params.get('focus_fallback_rounds', 2))
                fallback_back_count = int(params.get('focus_fallback_back_count', 1))
                fallback_escape_count = int(params.get('focus_fallback_escape_count', 1))
                for round_index in range(fallback_rounds):
                    if focus_stable:
                        break

                    if focus_status['state'] in ('system_overlay', 'app_with_overlay'):
                        logger.warning(
                            f"⚠️ resume_app 畫面仍有 Quest 系統層，嘗試補救 {round_index + 1}/{fallback_rounds}: "
                            f"{focus_status['summary']}"
                        )
                        if (
                            params.get('clear_oculus_clearactivity', True)
                            and "com.oculus.os.clearactivity" in focus_status['summary'].lower()
                        ):
                            self.execute_shell_command("am force-stop com.oculus.os.clearactivity", device)
                            time.sleep(0.2)

                        panel_reset = reset_vrshell_panel_overlay(f"fallback {round_index + 1}", focus_status)
                        if not panel_reset:
                            send_overlay_clear_events(
                                back_events=fallback_back_count,
                                escape_events=fallback_escape_count
                            )
                    else:
                        send_back_events(fallback_back_count)

                    if activity:
                        run_resume_command(f"fallback {round_index + 1} explicit activity", build_explicit_cmd())
                    else:
                        run_resume_command(
                            f"fallback {round_index + 1} monkey",
                            f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
                        )
                    time.sleep(float(params.get('focus_fallback_wait_seconds', 0.7)))
                    focus_status = self._get_resume_focus_status(device, package)
                    logger.info(
                        f"resume_app focus after fallback {round_index + 1} ({device}): "
                        f"{focus_status['summary']}"
                    )
                    focus_stable, focus_status = verify_stable_focus(f"fallback {round_index + 1}", focus_status)

                if focus_stable:
                    logger.info(f"✅ 已確認回到應用前景: {package}")
                    return True, f"已回到應用前景: {package}"

                if focus_status['state'] == 'app':
                    return False, f"遊戲焦點短暫回來，但沒有穩定停在前景: {focus_status['summary']}"

                if focus_status['state'] == 'app_with_overlay':
                    return False, f"遊戲已恢復，但 Quest 系統面板仍覆蓋畫面: {focus_status['summary']}"

                if focus_status['state'] == 'system_overlay':
                    return False, f"命令已送出，但畫面焦點仍在 Quest 系統層: {focus_status['summary']}"

                if focus_status['state'] == 'unknown' and successes:
                    logger.info(f"✅ 已送出回到應用前景命令（焦點無法驗證）: {package}")
                    return True, f"已送出回到應用前景命令: {package}"

                if focus_status['state'] == 'other':
                    failures.append(f"焦點未回到遊戲: {focus_status['summary']}")

            if not successes:
                error_text = "; ".join(failures) if failures else "沒有成功的切回命令"
                return False, f"回到應用失敗: {error_text}"

            logger.info(f"✅ 已回到應用前景: {package}")
            return True, f"已回到應用前景: {package}"

        except Exception as e:
            logger.error(f"❌ 回到應用前景失敗: {e}")
            return False, f"回到應用失敗: {str(e)}"

    def _get_resume_focus_status(self, device: str, package: str) -> Dict[str, str]:
        """讀取目前焦點，判斷畫面是否真的回到目標 App。"""
        focus_lines = []
        resumed_lines = []
        focus_keywords = (
            "mCurrentFocus",
            "mFocusedApp",
            "mFocusedWindow",
        )
        resumed_keywords = (
            "topResumedActivity",
            "ResumedActivity",
            "mResumedActivity",
            "mFocusedRootTask",
            "Resumed:",
        )

        success, output = self.execute_shell_command("dumpsys window windows", device, timeout=8)
        if success:
            for line in output.splitlines():
                stripped = line.strip()
                if any(keyword in stripped for keyword in focus_keywords):
                    focus_lines.append(stripped)

        success, output = self.execute_shell_command("dumpsys activity activities", device, timeout=8)
        if success:
            for line in output.splitlines():
                stripped = line.strip()
                if any(keyword in stripped for keyword in focus_keywords):
                    focus_lines.append(stripped)
                elif any(keyword in stripped for keyword in resumed_keywords):
                    resumed_lines.append(stripped)

        important_overlay_lines = [
            line for line in resumed_lines
            if "focusplaceholderactivity" in line.lower()
            or any(system_package in line.lower() for system_package in OCULUS_SYSTEM_FOCUS_PACKAGES)
        ]
        summary_lines = focus_lines[:6] + resumed_lines[:8]
        for line in important_overlay_lines:
            if line not in summary_lines:
                summary_lines.append(line)

        summary = " | ".join(summary_lines[:10]).strip()
        if not summary:
            return {"state": "unknown", "summary": "無法讀取目前焦點"}

        focus_summary = " | ".join(focus_lines).lower()
        lower_summary = " | ".join(focus_lines + resumed_lines).lower()
        top_resumed_summary = " | ".join(
            line for line in resumed_lines if "topresumedactivity" in line.lower()
        ).lower()
        package_lower = package.lower()

        has_app_focus = package_lower in focus_summary
        has_oculus_focus = any(system_package in focus_summary for system_package in OCULUS_SYSTEM_FOCUS_PACKAGES)
        has_app = package_lower in lower_summary
        has_oculus_top_resumed = (
            any(system_package in top_resumed_summary for system_package in OCULUS_SYSTEM_FOCUS_PACKAGES)
            or "focusplaceholderactivity" in top_resumed_summary
        )
        has_focus_placeholder = "focusplaceholderactivity" in lower_summary
        has_oculus_overlay = (
            has_oculus_focus
            or has_oculus_top_resumed
            or has_focus_placeholder
        )

        if has_app and has_oculus_overlay:
            return {"state": "app_with_overlay", "summary": summary}

        if has_oculus_focus or has_oculus_top_resumed:
            return {"state": "system_overlay", "summary": summary}

        if has_app_focus:
            return {"state": "app", "summary": summary}

        if has_app:
            return {"state": "app", "summary": summary}

        if has_oculus_overlay:
            return {"state": "system_overlay", "summary": summary}

        return {"state": "other", "summary": summary}

    def _resolve_launcher_activity(self, device: str, package: str) -> Optional[str]:
        """解析 package 的 launcher activity，回傳相對或完整 activity 名稱。"""
        success, output = self.execute_shell_command(
            f"cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER {package}",
            device
        )
        if not success:
            return None

        for line in reversed(output.splitlines()):
            line = line.strip()
            if line.startswith(f"{package}/"):
                return line.split("/", 1)[1]

        return None

    def execute_stop_app(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        執行關閉應用動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數
                - package: 應用 package 名稱（必填）
                - method: 關閉方式（force-stop 或 kill，預設 force-stop）
                - verify: 是否驗證關閉成功（預設 True）
        
        Returns:
            (成功, 訊息)
        """
        try:
            package = params.get('package')
            if not package:
                return False, "缺少 package 參數"
            
            method = params.get('method', 'force-stop')
            verify = params.get('verify', True)
            
            # 執行關閉命令
            if method == 'kill':
                cmd = f"am kill {package}"
            else:
                cmd = f"am force-stop {package}"
            
            success, output = self.execute_shell_command(cmd, device)
            
            if not success:
                return False, f"關閉失敗: {output}"
            
            # 驗證是否成功關閉
            if verify:
                import time
                time.sleep(0.3)  # 等待進程終止
                
                # 檢查進程是否還在運行
                success, pid_output = self.execute_shell_command(
                    f"pidof {package}",
                    device
                )
                
                if success and pid_output.strip():
                    logger.warning(f"⚠️ 應用可能仍在運行: {package}")
                    return True, "關閉命令已發送（應用可能仍在運行）"
                else:
                    logger.info(f"✅ 關閉應用成功: {package}")
                    return True, f"應用 {package} 已關閉"
            
            logger.info(f"✅ 關閉命令已發送: {package}")
            return True, f"關閉命令已發送"
        
        except Exception as e:
            logger.error(f"❌ 關閉應用失敗: {e}")
            return False, f"關閉失敗: {str(e)}"
    
    def execute_restart_app(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        執行重啟應用動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數
                - package: 應用 package 名稱（必填）
                - activity: Activity 名稱（選填）
                - delay: 關閉後等待秒數（預設 1）
        
        Returns:
            (成功, 訊息)
        """
        try:
            package = params.get('package')
            if not package:
                return False, "缺少 package 參數"
            
            delay = params.get('delay', 1)
            
            # 先關閉應用
            logger.info(f"正在關閉應用: {package}")
            success, msg = self.execute_stop_app(device, {'package': package, 'verify': True})
            
            if not success:
                return False, f"關閉失敗: {msg}"
            
            # 等待
            import time
            logger.info(f"等待 {delay} 秒後重啟...")
            time.sleep(delay)
            
            # 重新啟動
            logger.info(f"正在啟動應用: {package}")
            success, msg = self.execute_launch_app(device, params)
            
            if not success:
                return False, f"啟動失敗: {msg}"
            
            logger.info(f"✅ 重啟應用成功: {package}")
            return True, f"應用 {package} 已重啟"
        
        except Exception as e:
            logger.error(f"❌ 重啟應用失敗: {e}")
            return False, f"重啟失敗: {str(e)}"
    
    def execute_send_key(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        執行發送按鍵動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數
                - keycode: 按鍵碼（必填，可以是名稱如 "KEYCODE_HOME" 或數字如 3）
                - repeat: 重複次數（預設 1）
        
        Returns:
            (成功, 訊息)
        """
        try:
            keycode = params.get('keycode')
            if not keycode:
                return False, "缺少 keycode 參數"
            
            repeat = params.get('repeat', 1)
            
            # 如果是數字，直接使用；否則作為 keycode 名稱
            try:
                keycode_value = int(keycode)
                keycode_str = str(keycode_value)
            except (ValueError, TypeError):
                keycode_str = str(keycode)
            
            # 重複發送按鍵
            for i in range(repeat):
                success, output = self.execute_shell_command(
                    f"input keyevent {keycode_str}",
                    device
                )
                
                if not success:
                    return False, f"發送按鍵失敗: {output}"
                
                if repeat > 1 and i < repeat - 1:
                    import time
                    time.sleep(0.1)  # 按鍵間隔
            
            logger.info(f"✅ 發送按鍵成功: {keycode_str} x{repeat}")
            return True, f"已發送按鍵: {keycode_str} ({repeat} 次)"
        
        except Exception as e:
            logger.error(f"❌ 發送按鍵失敗: {e}")
            return False, f"發送失敗: {str(e)}"
    
    def execute_install_apk(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        執行安裝 APK 動作
        
        Args:
            device: 設備序列號或 IP:Port
            params: 參數
                - apk_path: APK 文件路徑（必填）
                - replace: 是否替換已存在的應用（預設 True）
                - grant_permissions: 是否自動授予權限（預設 False）
        
        Returns:
            (成功, 訊息)
        """
        try:
            from pathlib import Path
            
            apk_path = params.get('apk_path')
            if not apk_path:
                return False, "缺少 apk_path 參數"
            
            # 驗證文件存在
            apk_file = Path(apk_path)
            if not apk_file.exists():
                return False, f"APK 文件不存在: {apk_path}"
            
            if not apk_file.is_file():
                return False, f"路徑不是文件: {apk_path}"
            
            replace = params.get('replace', True)
            grant_permissions = params.get('grant_permissions', False)
            
            # 構建安裝命令
            cmd = ['adb', '-s', device, 'install']
            
            if replace:
                cmd.append('-r')  # 替換已存在的應用
            
            if grant_permissions:
                cmd.append('-g')  # 自動授予權限
            
            cmd.append(str(apk_file.absolute()))
            
            logger.info(f"正在安裝 APK: {apk_file.name} -> {device}")
            logger.debug(f"執行命令: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 安裝可能需要較長時間
            )
            
            if result.returncode == 0:
                logger.info(f"✅ 安裝 APK 成功: {apk_file.name} -> {device}")
                return True, f"APK 安裝成功: {apk_file.name}"
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"❌ 安裝 APK 失敗: {apk_file.name} -> {device}: {error_msg}")
                return False, f"安裝失敗: {error_msg}"
        
        except subprocess.TimeoutExpired:
            logger.error(f"❌ 安裝 APK 超時: {apk_path}")
            return False, "安裝超時（超過 120 秒）"
        except Exception as e:
            logger.error(f"❌ 安裝 APK 失敗: {e}")
            return False, f"安裝失敗: {str(e)}"
    
    async def execute_wake_up_async(self, device: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """異步執行喚醒"""
        params = params or {}
        verify = params.get('verify', True)
        
        success, output = await self.execute_shell_command_async("input keyevent KEYCODE_WAKEUP", device)
        if not success: return False, f"喚醒命令執行失敗: {output}"
        
        if verify:
            await asyncio.sleep(0.5)
            success, power_state = await self.execute_shell_command_async("dumpsys power | grep 'Display Power: state='", device)
            if success and 'ON' in power_state: return True, "設備已喚醒"
            return True, "喚醒命令已發送（無法驗證狀態）"
            
        return True, "喚醒命令已發送"

    async def execute_sleep_async(self, device: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """異步執行休眠"""
        params = params or {}
        force = params.get('force', False)
        verify = params.get('verify', True)
        keycode = "KEYCODE_SLEEP" if force else "KEYCODE_POWER"
        
        success, output = await self.execute_shell_command_async(f"input keyevent {keycode}", device)
        if not success: return False, f"休眠命令執行失敗: {output}"
        
        if verify:
            await asyncio.sleep(0.5)
            success, power_state = await self.execute_shell_command_async("dumpsys power | grep 'Display Power: state='", device)
            if success and 'OFF' in power_state: return True, "設備已休眠"
            return True, "休眠命令已發送（無法驗證狀態）"
        
        return True, "休眠命令已發送"

    async def execute_launch_app_async(self, device: str, params: Dict[str, Any], room_info: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """異步執行啟動應用"""
        package = params.get('package')
        if not package: return False, "缺少 package 參數"
        
        activity = params.get('activity', '')
        stop_existing = params.get('stop_existing', False)
        wait = params.get('wait', True)
        
        if stop_existing:
            await self.execute_shell_command_async(f"am force-stop {package}", device)
        
        if activity:
            cmd = f"am start -n {package}/{activity}"
            
            # 加入 Socket Server 參數
            if room_info and room_info.get('socket_ip') and room_info.get('socket_port'):
                cmd += f" --es qqquest_server_ip \"{room_info['socket_ip']}\""
                cmd += f" --ei qqquest_server_port {room_info['socket_port']}"
            
            # 加入自定義房間參數
            if room_info and room_info.get('parameters'):
                from core.room import RoomParameter
                # 假設傳進來的是 RoomParameter 對象列表
                parameters = room_info['parameters']
                
                # 獲取設備 ID (可能只是 IP:Port，需要解析或從 registry 查找?)
                # 這裡 device 參數通常是序列號或 IP:Port
                # 簡單起見，我們嘗試用 device ID 直接匹配
                # 在 ADBManager 中我們只有 device string (serial/ip)
                # 從 room.parameters.device_values 是用 device_id 存的
                # 我們需要將 ADB device serial 映射到 device_id
                # 這可能比較麻煩，因為 ADBManager 不依賴 DeviceRegistry
                # 解決方案：在調用 execute_action_batch 時，已經是 iteration over devices
                # 我們可以在那裡把 context 準備好。
                # 但 execute_action_async 只接收 device string.
                
                # 這裡是一個潛在的問題：ADBManager 不知道 device_id。
                # 權宜之計：我們依賴調用方 (ActionRegistry / UI) 把解析好的值傳進來？
                # 不行，因為 execute_action 是通用的。
                
                # 改進方案：room_info 包含 'device_map' (serial -> device_id) ?
                # 或者我們簡單點，假設 device string 就是 key (如果是 IP 連接的話通常也是唯一標識)
                # 但 DeviceRegistry 的 device_id 是 UUID。
                
                # 讓我們看看 DeviceRegistry。device.device_id 是 UUID。
                # 當我們在 UI 中調用 execute_action_batch 時，我們傳入的是 device.serial (connection_string)。
                
                # 所以我們需要在 room_info 中傳遞一個查找表 serial -> device_id。
                # 或者，我們在此處傳遞的是 "resolved parameters"？
                # 不，因為 global parameters 是通用的。
                
                # 讓我們在 UI 層組裝 room_info 時，把 `device_id_map` 放進去。
                device_id = None
                if room_info.get('device_id_map'):
                     device_id = room_info['device_id_map'].get(device)
                
                # 自動注入設備識別參數 (device_id, device_ip)
                if device_id:
                    cmd += f" --es device_id \"{device_id}\""
                
                # 嘗試獲取 device_ip
                device_ip = None
                if room_info.get('device_params_map'): # 使用更通用的映射?
                     d_info = room_info['device_params_map'].get(device)
                     if d_info: device_ip = d_info.get('ip')
                
                if not device_ip:
                    # 嘗試從 device serial 解析 IP (如果是網絡設備)
                    if ':' in device and device.replace('.','').replace(':','').isdigit():
                         device_ip = device.split(':')[0]
                
                if device_ip:
                    cmd += f" --es device_ip \"{device_ip}\""
                
                for param in parameters:
                    # 確保 param 是 RoomParameter 對象 (如果是 dict 則轉換)
                    if isinstance(param, dict):
                         # 簡單的反序列化，如果需要
                         pass 
                    
                    flag = param.adb_flag
                    value = None
                    
                    if param.is_global:
                        value = param.global_value
                    elif device_id and device_id in param.device_values:
                        value = param.device_values[device_id]
                        # 若值是 dict，取出主要 value 欄位，忽略 rotation_value
                        if isinstance(value, dict):
                            value = value.get('value')
                    
                    if value is not None:
                        # 處理值格式
                        if param.value_type == "string":
                            cmd += f" {flag} {param.name} \"{value}\""
                        else:
                            # 對於 array 類型，需要逗號分隔
                            if "array" in param.value_type and isinstance(value, list):
                                value_str = ",".join(map(str, value))
                                cmd += f" {flag} {param.name} {value_str}"
                            else:
                                cmd += f" {flag} {param.name} {value}"

        else:
            cmd = None  # 改用下方 launch_cmds 組裝

        # 組裝要嘗試的啟動命令（依序嘗試，第一個成功就停）
        if activity:
            launch_cmds = [cmd + (" -W" if wait else "")]
        else:
            # 沒指定 activity：一般 app 用 LAUNCHER；Quest/VR app 多半沒有 LAUNCHER，
            # 再試常見 Unity activity（名稱依 Unity 版本而不同）與 Oculus VR 類別。
            launch_cmds = [
                f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
                f"am start -n {package}/com.unity3d.player.UnityPlayerActivity" + (" -W" if wait else ""),
                f"am start -n {package}/com.unity3d.player.UnityPlayerGameActivity" + (" -W" if wait else ""),
                f"monkey -p {package} -c com.oculus.intent.category.VR 1",
            ]

        last_output = ""
        for c in launch_cmds:
            success, output = await self.execute_shell_command_async(c, device)
            last_output = output
            if success and "Error" not in output and "error" not in output.lower():
                return True, f"應用 {package} 已啟動"
        return False, f"啟動失敗: {last_output}"

    async def execute_resume_app_async(self, device: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """異步將背景中的應用帶回前景，不先關閉或重啟。"""
        package = params.get('package')
        if not package:
            return False, "缺少 package 參數"

        activity = params.get('activity') or ""
        if not activity and params.get('resolve_activity', True):
            activity = self._resolve_launcher_activity(device, package) or ""

        back_count = int(params.get('back_count', 1 if params.get('send_back_first', False) else 0))
        for _ in range(max(0, back_count)):
            await self.execute_shell_command_async("input keyevent 4", device)
            await asyncio.sleep(0.15)

        successes = []
        failures = []

        async def run_resume_command(label: str, cmd: str):
            success, output = await self.execute_shell_command_async(cmd, device)
            logger.info(f"resume_app {label} output ({device}): {output}")
            if success and "error" not in output.lower() and "exception" not in output.lower():
                successes.append(label)
            else:
                failures.append(f"{label}: {output}")
                logger.warning(f"⚠️ resume_app {label} 失敗: {package} - {output}")

        if activity and params.get('explicit_activity_first', True):
            explicit_cmd = (
                "am start --activity-reorder-to-front --activity-single-top --activity-no-animation "
                f"-a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
                f"-c com.oculus.intent.category.VR -n {package}/{activity}"
            )
            await run_resume_command("explicit activity", explicit_cmd)
            await asyncio.sleep(0.2)

        if params.get('use_monkey', True):
            monkey_cmd = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
            await run_resume_command("monkey", monkey_cmd)
            await asyncio.sleep(0.2)

        if params.get('am_start_after', False):
            if activity and params.get('explicit_activity_after', True):
                am_cmd = (
                    "am start --activity-reorder-to-front --activity-single-top --activity-no-animation "
                    f"-a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
                    f"-c com.oculus.intent.category.VR -n {package}/{activity}"
                )
            else:
                am_cmd = f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {package}"
            await run_resume_command("am start", am_cmd)

        if not successes:
            error_text = "; ".join(failures) if failures else "沒有成功的切回命令"
            return False, f"回到應用失敗: {error_text}"

        return True, f"已回到應用前景: {package}"

    async def execute_action_async(self, device: str, action, room_info: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """異步執行動作（通用方法）"""
        from core.action import ActionType
        try:
            logger.info(f"⚡ 執行異步動作: {action.display_name} -> {device}")
            
            if action.action_type == ActionType.WAKE_UP:
                return await self.execute_wake_up_async(device, action.params)
            elif action.action_type == ActionType.SLEEP:
                return await self.execute_sleep_async(device, action.params)
            elif action.action_type == ActionType.LAUNCH_APP:
                return await self.execute_launch_app_async(device, action.params, room_info)
            elif action.action_type == ActionType.RESUME_APP:
                return await self.execute_resume_app_async(device, action.params)
            elif action.action_type == ActionType.STOP_APP:
                package = action.params.get('package')
                method = action.params.get('method', 'force-stop')
                cmd = f"am {'kill' if method == 'kill' else 'force-stop'} {package}"
                success, output = await self.execute_shell_command_async(cmd, device)
                return success, f"應用 {package} 已關閉" if success else f"關閉失敗: {output}"
            elif action.action_type == ActionType.SEND_KEY:
                keycode = action.params.get('keycode')
                repeat = action.params.get('repeat', 1)
                for _ in range(repeat):
                    await self.execute_shell_command_async(f"input keyevent {keycode}", device)
                    if repeat > 1: await asyncio.sleep(0.1)
                return True, f"已發送按鍵: {keycode}"
            
            # 對於其他尚未實現 async 版本的動作，退回到同步執行（在 executor 中）
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.execute_action, device, action, room_info)
            
        except Exception as e:
            logger.error(f"❌ 執行異步動作失敗: {e}")
            return False, f"執行失敗: {str(e)}"
            
    def execute_action(self, device: str, action, room_info: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        執行動作（通用方法）
        
        Args:
            device: 設備序列號或 IP:Port
            action: Action 對象
            room_info: 房間信息（可選），包含 socket_ip 和 socket_port
        
        Returns:
            (成功, 訊息)
        """
        from core.action import ActionType
        
        try:
            logger.info(f"⚡ 執行動作: {action.display_name} -> {device}")
            
            # 根據動作類型調用對應的執行方法
            if action.action_type == ActionType.WAKE_UP:
                return self.execute_wake_up(device, action.params)
            elif action.action_type == ActionType.SLEEP:
                return self.execute_sleep(device, action.params)
            elif action.action_type == ActionType.KEEP_AWAKE:
                return self.execute_keep_awake(device, action.params)
            elif action.action_type == ActionType.LAUNCH_APP:
                return self.execute_launch_app(device, action.params, room_info)
            elif action.action_type == ActionType.RESUME_APP:
                return self.execute_resume_app(device, action.params)
            elif action.action_type == ActionType.STOP_APP:
                return self.execute_stop_app(device, action.params)
            elif action.action_type == ActionType.RESTART_APP:
                return self.execute_restart_app(device, action.params)
            elif action.action_type == ActionType.SEND_KEY:
                return self.execute_send_key(device, action.params)
            elif action.action_type == ActionType.INSTALL_APK:
                return self.execute_install_apk(device, action.params)
            else:
                return False, f"不支援的動作類型: {action.action_type}"
        
        except Exception as e:
            logger.error(f"❌ 執行動作失敗: {action.display_name} - {e}")
            return False, f"執行失敗: {str(e)}"
    
    # ==================== 並發處理方法 ====================
    
    def execute_action_batch(
        self,
        devices: List[str],
        action,
        max_workers: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        room_info: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, bool, str]]:
        """
        並發執行動作到多個設備（大幅提升批量操作速度）
        
        Args:
            devices: 設備列表 (connection_string)
            action: Action 對象
            max_workers: 最大並發數（默認 10）
            progress_callback: 進度回調函數 callback(completed, total)
        
        Returns:
            [(device, success, message), ...]
        
        範例：
            devices = ["192.168.1.100:5555", "192.168.1.101:5555"]
            results = adb_manager.execute_action_batch(devices, wake_action)
            
            for device, success, msg in results:
                print(f"{device}: {'✅' if success else '❌'} {msg}")
        """
        if not devices:
            return []
        
        results = []
        completed = 0
        total = len(devices)
        
        logger.info(f"🚀 開始並發執行: {action.display_name} -> {total} 台設備（並發數：{max_workers}）")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_device = {
                    executor.submit(self.execute_action, device, action, room_info): device
                    for device in devices
                }
                
                # 收集結果（按完成順序，不保證原始順序）
                for future in as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        success, message = future.result()
                        results.append((device, success, message))
                    except Exception as e:
                        logger.error(f"❌ 設備執行異常: {device} - {e}")
                        results.append((device, False, f"執行異常: {e}"))
                    
                    # 進度回調
                    completed += 1
                    if progress_callback:
                        try:
                            progress_callback(completed, total)
                        except Exception as e:
                            logger.warning(f"進度回調失敗: {e}")
            
            logger.info(f"✅ 並發執行完成: {action.display_name} ({completed}/{total})")
            return results
            
        except Exception as e:
            logger.error(f"❌ 並發執行失敗: {e}")
            return results
    
    def get_status_batch(
        self,
        devices: List[str],
        max_workers: int = 10
    ) -> Dict[str, Dict[str, Any]]:
        """
        並發獲取多個設備的狀態（大幅提升狀態查詢速度）
        
        Args:
            devices: 設備列表 (connection_string)
            max_workers: 最大並發數（默認 10）
        
        Returns:
            {device: status_dict, ...}
            
            status_dict 包含:
            - battery: 電量百分比
            - temperature: 溫度（°C）
            - is_charging: 是否充電中
            - is_screen_on: 螢幕是否開啟
            - is_awake: 是否清醒
            - uptime: 開機時間（秒）
        
        範例：
            devices = ["192.168.1.100:5555", "192.168.1.101:5555"]
            status_dict = adb_manager.get_status_batch(devices)
            
            for device, status in status_dict.items():
                print(f"{device}: 電量 {status['battery']}%")
        """
        if not devices:
            return {}
        
        status_dict = {}
        
        logger.info(f"🚀 開始並發查詢狀態: {len(devices)} 台設備（並發數：{max_workers}）")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_device = {
                    executor.submit(self.get_device_status, device): device
                    for device in devices
                }
                
                # 收集結果
                for future in as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        status = future.result()
                        status_dict[device] = status
                    except Exception as e:
                        logger.error(f"❌ 獲取狀態失敗: {device} - {e}")
                        # 返回默認狀態
                        status_dict[device] = {
                            'battery': 0,
                            'temperature': 0.0,
                            'is_charging': False,
                            'is_screen_on': False,
                            'is_awake': True,
                            'uptime': 0,
                        }
            
            logger.info(f"✅ 並發查詢完成: {len(status_dict)}/{len(devices)} 台設備")
            return status_dict
            
        except Exception as e:
            logger.error(f"❌ 並發查詢失敗: {e}")
            return status_dict
    
    def start_scrcpy_batch(
        self,
        devices: List[Tuple[str, str]],
        options: Optional[Dict[str, Any]] = None,
        max_workers: int = 10
    ) -> List[Tuple[str, bool, str]]:
        """
        並發啟動多個 scrcpy 監看視窗
        
        Args:
            devices: [(device, window_title), ...] 
            options: scrcpy 選項（選填）
            max_workers: 最大並發數（默認 10）
        
        Returns:
            [(device, success, message), ...]
        
        範例：
            devices = [
                ("192.168.1.100:5555", "Quest 01"),
                ("192.168.1.101:5555", "Quest 02")
            ]
            results = adb_manager.start_scrcpy_batch(devices)
        """
        if not devices:
            return []
        
        results = []
        
        logger.info(f"🚀 開始並發啟動 scrcpy: {len(devices)} 台設備（並發數：{max_workers}）")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                future_to_device = {
                    executor.submit(self.start_scrcpy, device, title, options): (device, title)
                    for device, title in devices
                }
                
                # 收集結果
                for future in as_completed(future_to_device):
                    device, title = future_to_device[future]
                    try:
                        success, message = future.result()
                        results.append((device, success, message))
                    except Exception as e:
                        logger.error(f"❌ 啟動 scrcpy 失敗: {device} - {e}")
                        results.append((device, False, f"啟動失敗: {e}"))
            
            success_count = sum(1 for _, success, _ in results if success)
            logger.info(f"✅ 並發啟動完成: {success_count}/{len(devices)} 台設備")
            return results
            
        except Exception as e:
            logger.error(f"❌ 並發啟動失敗: {e}")
            return results
    
    # ==================== 網路監控方法 ====================
    
    def ping_device(self, ip: str, timeout: int = 2) -> Optional[float]:
        """
        Ping 設備並返回響應時間（毫秒）
        
        Args:
            ip: 設備 IP 地址
            timeout: 超時時間（秒）
        
        Returns:
            None: Ping 失敗或超時
            float: Ping 響應時間（毫秒）
        """
        try:
            is_windows = platform.system() == "Windows"
            
            if is_windows:
                cmd = ['ping', '-n', '1', '-w', str(timeout * 1000), ip]
            else:
                cmd = ['ping', '-c', '1', '-W', str(timeout), ip]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            if result.returncode == 0:
                output = result.stdout
                if is_windows:
                    match = re.search(r'時間[<=](\d+)ms', output)
                else:
                    match = re.search(r'time[<=]([\d.]+)\s*ms', output)
                
                if match:
                    ping_time = float(match.group(1))
                    logger.debug(f"Ping {ip}: {ping_time:.1f}ms")
                    return ping_time
            
            return None
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Ping 失敗: {ip} - {e}")
            return None
    
    def ping_devices_batch(
        self,
        devices: List[Any],
        max_workers: int = 10
    ) -> Dict[str, Optional[float]]:
        """
        並發 Ping 多個設備
        
        Args:
            devices: 設備列表（Device 對象）
            max_workers: 最大並發數
        
        Returns:
            {device_id: ping_time_ms or None}
        """
        results = {}
        
        if not devices:
            return results
        
        def ping_device_wrapper(device):
            if not device.ip:
                return device.device_id, None
            ping_time = self.ping_device(device.ip)
            return device.device_id, ping_time
        
        logger.debug(f"開始並發 Ping {len(devices)} 台設備")
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(ping_device_wrapper, device): device
                    for device in devices
                }
                
                for future in as_completed(futures):
                    try:
                        device_id, ping_time = future.result()
                        results[device_id] = ping_time
                    except Exception as e:
                        device = futures[future]
                        logger.error(f"Ping 設備異常: {device.device_id} - {e}")
                        results[device.device_id] = None
            
            logger.debug(f"並發 Ping 完成: {len(results)} 台設備")
            return results
            
        except Exception as e:
            logger.error(f"並發 Ping 失敗: {e}")
            return results
    
    def check_and_auto_connect_device(
        self,
        device: Any,
        config: Dict[str, Any],
        retry_manager: Optional[Any] = None
    ) -> Tuple[DeviceStatus, Optional[str], Optional[float]]:
        """
        檢查設備狀態並自動連接（如果需要）
        
        Args:
            device: Device 對象
            config: 網路監控配置
            retry_manager: 重試管理器（可選）
        
        Returns:
            (new_status, message, ping_time)
        """
        if not device.ip:
            return device.status, None, None
        
        # 1. Ping 設備
        ping_timeout = config.get('ping_timeout', 2)
        ping_time = self.ping_device(device.ip, timeout=ping_timeout)
        
        if ping_time is None:
            return DeviceStatus.NOT_CONNECTED, "設備無響應", None
        
        # 2. Ping 通，檢查 ADB 連接狀態
        adb_devices = self.get_devices()
        connection_str = device.connection_string
        
        for adb_device in adb_devices:
            if adb_device['serial'] == connection_str:
                if adb_device['state'] == 'device':
                    # 設備已連接，重置重試次數
                    if retry_manager:
                        retry_manager.reset_retry_count(device.device_id)
                    return DeviceStatus.ONLINE, "設備已連接", ping_time
                elif adb_device['state'] == 'offline':
                    return DeviceStatus.OFFLINE, "設備離線", ping_time
        
        # 3. 不在 ADB 列表中，但 Ping 通：嘗試自動連接
        auto_connect = config.get('auto_connect', False)
        
        if not auto_connect:
            return DeviceStatus.NOT_CONNECTED, f"設備在線（Ping: {ping_time:.1f}ms），但未連接", ping_time
        
        # 4. 檢查重試次數
        if retry_manager:
            retries = retry_manager.get_retry_count(device.device_id)
            max_retries = config.get('auto_connect_max_retries', 3)
            cooldown = config.get('auto_connect_cooldown', 30)
            
            if retries >= max_retries:
                if retry_manager.is_in_cooldown(device.device_id, cooldown):
                    return DeviceStatus.ADB_NOT_ENABLED, f"自動連接失敗（已重試 {retries} 次），冷卻中", ping_time
                else:
                    retry_manager.reset_retry_count(device.device_id)
                    retries = 0
        
        # 5. 執行連接
        success, output = self.connect(device.ip, device.port)
        
        if success or "already connected" in output.lower():
            if retry_manager:
                retry_manager.reset_retry_count(device.device_id)
            return DeviceStatus.ONLINE, "自動連接成功", ping_time
        
        # 6. 連接失敗
        if retry_manager:
            retry_manager.increment_retry_count(device.device_id)
            retry_manager.set_cooldown(device.device_id)
        
        error_msg = output.lower()
        if "cannot connect" in error_msg or "connection refused" in error_msg or "unable to connect" in error_msg:
            return DeviceStatus.ADB_NOT_ENABLED, f"無法連接：WiFi ADB 未開啟（Ping: {ping_time:.1f}ms）", ping_time
        else:
            return DeviceStatus.NOT_CONNECTED, f"連接失敗：{output}", ping_time
