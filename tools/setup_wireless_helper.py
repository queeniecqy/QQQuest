#!/usr/bin/env python3
"""
把 Quest 設定成「重開機後不必接線」

問題：Quest 重開機會清空 service.adb.tcp.port（非持久屬性），5555 因此關閉。

解法：只要「無線偵錯」是開的，adbd 會另外在隨機埠提供 TLS 連線並用 mDNS 廣播，
之後就能從那裡連進去重下 tcpip 5555（tools/wake_devices.py 或 UI 的「一鍵連接」）
——不必接 USB，也不必戴頭盔。

這支腳本對每台連得上的設備做三件事：
  1. 安裝 helper APK（本地沒有會自動從 GitHub 官方 release 下載並校驗 SHA256）
  2. 授予 WRITE_SECURE_SETTINGS
  3. 【關鍵】直接開啟無線偵錯 —— 實測 shell 自己就持有 WRITE_SECURE_SETTINGS，
     可以直接寫 adb_wifi_enabled，不需要戴頭盔開 App

helper APK 的角色是保險：萬一某台重開機後 5555 和無線偵錯都關了、adb 完全連不上，
那時才需要戴頭盔開它一次。正常情況用不到。

睡著的 Quest 連不上會自動略過，之後醒著時再跑一次即可。

用法：
    python3 tools/setup_wireless_helper.py            # 對所有已登記設備
    python3 tools/setup_wireless_helper.py --ip 192.168.68.110   # 只針對某台
    python3 tools/setup_wireless_helper.py --status   # 只檢查狀態，不安裝
"""
import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.dhcp_reservations import load_known_devices  # noqa: E402

PACKAGE = "tdg.oculuswirelessadb"
APK_VERSION = "1.3"
APK_URL = ("https://github.com/thedroidgeek/oculus-wireless-adb/releases/download/"
           f"{APK_VERSION}/{PACKAGE}-{APK_VERSION}.apk")
APK_SHA256 = "e022415989d36e425d57f3a0a38912322135730f0ce96870b177b6be041d4ca1"
APK_DIR = PROJECT_ROOT / "data" / "helper"
APK_PATH = APK_DIR / f"{PACKAGE}-{APK_VERSION}.apk"


def sh(args, timeout=120):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def ensure_apk() -> bool:
    """本地沒有 APK 就從官方 release 下載，並比對 SHA256"""
    import hashlib

    if APK_PATH.exists():
        digest = hashlib.sha256(APK_PATH.read_bytes()).hexdigest()
        if digest == APK_SHA256:
            return True
        print(f"⚠️  既有 APK 校驗碼不符，重新下載")
        APK_PATH.unlink()

    APK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"⬇️  下載 helper APK v{APK_VERSION}（約 14MB）…")
    code, out = sh(["curl", "-sL", "--max-time", "180", "-o", str(APK_PATH), APK_URL], timeout=200)
    if code != 0 or not APK_PATH.exists():
        print(f"❌ 下載失敗: {out[:200]}")
        return False

    digest = hashlib.sha256(APK_PATH.read_bytes()).hexdigest()
    if digest != APK_SHA256:
        print(f"❌ 校驗碼不符！預期 {APK_SHA256[:16]}… 實得 {digest[:16]}…")
        APK_PATH.unlink()
        return False
    print(f"✅ APK 已下載並校驗通過")
    return True


def device_state(ip: str) -> dict:
    """回傳單台設備的連線與 helper 狀態"""
    target = f"{ip}:5555"
    st = {"ip": ip, "online": False, "installed": False, "granted": False, "note": ""}

    code, out = sh(["adb", "connect", target], timeout=15)
    if "connected" not in out:
        st["note"] = "連不上（睡著或關機）"
        return st

    code, out = sh(["adb", "-s", target, "shell", "echo ok"], timeout=15)
    if "ok" not in out:
        st["note"] = "adb 無回應"
        return st
    st["online"] = True

    code, out = sh(["adb", "-s", target, "shell", "pm", "list", "packages", PACKAGE], timeout=20)
    st["installed"] = PACKAGE in out

    if st["installed"]:
        code, out = sh(["adb", "-s", target, "shell", "dumpsys", "package", PACKAGE], timeout=25)
        st["granted"] = "WRITE_SECURE_SETTINGS: granted=true" in out
    return st


def setup_device(ip: str) -> dict:
    """對單台設備安裝 helper 並授權"""
    target = f"{ip}:5555"
    st = device_state(ip)
    if not st["online"]:
        return st

    if not st["installed"]:
        code, out = sh(["adb", "-s", target, "install", "-r", str(APK_PATH)], timeout=300)
        if "Success" not in out:
            st["note"] = f"安裝失敗: {out.strip()[:80]}"
            return st
        st["installed"] = True
        st["note"] = "已安裝"
    else:
        st["note"] = "已裝過"

    if not st["granted"]:
        sh(["adb", "-s", target, "shell", "pm", "grant", PACKAGE,
            "android.permission.WRITE_SECURE_SETTINGS"], timeout=20)
        code, out = sh(["adb", "-s", target, "shell", "dumpsys", "package", PACKAGE], timeout=25)
        st["granted"] = "WRITE_SECURE_SETTINGS: granted=true" in out
        if st["granted"] and st["note"] == "已裝過":
            st["note"] = "補上授權"

    # 關鍵：直接開啟無線偵錯，作為重開機後的救援通道。
    # shell 持有 WRITE_SECURE_SETTINGS，可直接寫，不必戴頭盔開 App（實測可行）。
    code, out = sh(["adb", "-s", target, "shell",
                    "settings", "get", "global", "adb_wifi_enabled"], timeout=15)
    if out.strip() != "1":
        sh(["adb", "-s", target, "shell",
            "settings", "put", "global", "adb_wifi_enabled", "1"], timeout=15)
        code, out = sh(["adb", "-s", target, "shell",
                        "settings", "get", "global", "adb_wifi_enabled"], timeout=15)
        if out.strip() == "1":
            st["note"] = (st["note"] + "＋開啟無線偵錯").lstrip("＋")
    st["wifi_debug"] = out.strip() == "1"
    return st


def setup_over_usb() -> int:
    """對目前用 USB 連著的設備做完整設定（新機或 5555 已關的機器適用）"""
    code, out = sh(["adb", "devices"], timeout=20)
    usb = [l.split()[0] for l in out.splitlines()[1:]
           if l.strip() and ":" not in l.split()[0] and l.split()[-1] == "device"]
    unauth = [l.split()[0] for l in out.splitlines()[1:]
              if l.strip() and l.split()[-1] == "unauthorized"]

    if unauth:
        print(f"⚠️  有 {len(unauth)} 台 USB 設備未授權：{', '.join(unauth)}")
        print("   請戴上頭盔（螢幕要亮）按「允許 USB 偵錯」，並勾「一律允許」\n")
    if not usb:
        print("❌ 沒有已授權的 USB 設備。請確認：")
        print("   1. 線有接好，且是「可傳資料」的線（純充電線不行）")
        print("   2. 頭盔裡已按過「允許 USB 偵錯」")
        return 1

    if not ensure_apk():
        return 1

    for serial in usb:
        print(f"\n{'='*58}\n設定 USB 設備 {serial}\n{'='*58}")
        code, out = sh(["adb", "-s", serial, "shell",
                        "ip -4 addr show wlan0 | grep -o 'inet [0-9.]*'"], timeout=15)
        ip = out.strip().replace("inet ", "").strip()
        print(f"  Wi-Fi IP: {ip or '（未連上 Wi-Fi！先在頭盔裡連好 Wi-Fi）'}")
        if not ip:
            continue

        code, out = sh(["adb", "-s", serial, "shell", "pm", "list", "packages", PACKAGE], timeout=20)
        if PACKAGE not in out:
            code, out = sh(["adb", "-s", serial, "install", "-r", str(APK_PATH)], timeout=300)
            print(f"  安裝 helper: {'✅' if 'Success' in out else '❌ ' + out.strip()[:60]}")
        else:
            print("  安裝 helper: ✅ 已裝過")

        sh(["adb", "-s", serial, "shell", "pm", "grant", PACKAGE,
            "android.permission.WRITE_SECURE_SETTINGS"], timeout=20)
        code, out = sh(["adb", "-s", serial, "shell", "dumpsys", "package", PACKAGE], timeout=25)
        print(f"  授權: {'✅' if 'WRITE_SECURE_SETTINGS: granted=true' in out else '❌'}")

        sh(["adb", "-s", serial, "shell", "settings", "put", "global",
            "adb_wifi_enabled", "1"], timeout=15)
        import time as _t; _t.sleep(3)
        code, out = sh(["adb", "-s", serial, "shell", "settings", "get", "global",
                        "adb_wifi_enabled"], timeout=15)
        if out.strip() == "1":
            print("  無線偵錯: ✅ 已開啟（重開機後可自動救援）")
        else:
            print("  無線偵錯: ❌ 被系統寫回 0 —— 這個 Wi-Fi 尚未被該設備信任")
            print("     → 戴上頭盔（螢幕要亮）開一次 Oculus Wireless ADB 按「允許」")

        code, out = sh(["adb", "-s", serial, "tcpip", "5555"], timeout=20)
        _t.sleep(4)
        code, out = sh(["adb", "connect", f"{ip}:5555"], timeout=20)
        print(f"  5555 無線連線: {'✅ ' + ip + ':5555' if 'connected' in out else '❌ ' + out.strip()[:60]}")

        sh(["ping", "-c", "2", "-W", "800", ip], timeout=10)
        code, out = sh(["arp", "-an"], timeout=10)
        for line in out.splitlines():
            if f"({ip})" in line:
                import re as _re
                mm = _re.search(r"at ([0-9a-fA-F:]+)", line)
                if mm:
                    mac = ":".join(f"{int(x,16):02x}" for x in mm.group(1).split(":"))
                    print(f"  MAC（DHCP 保留用）: {mac}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="批次安裝無線 ADB helper 到 Quest")
    ap.add_argument("--ip", help="只針對指定 IP")
    ap.add_argument("--usb", action="store_true",
                    help="對目前 USB 連著的設備做完整設定（新機／5555 已關掉的機器用這個）")
    ap.add_argument("--status", action="store_true", help="只檢查狀態，不安裝")
    args = ap.parse_args()

    if args.usb:
        return setup_over_usb()

    if args.ip:
        targets = {args.ip: ""}
    else:
        targets = load_known_devices()
    if not targets:
        print("❌ 找不到已登記的設備")
        return 1

    if not args.status and not ensure_apk():
        return 1

    action = device_state if args.status else setup_device
    print(f"🔍 檢查 {len(targets)} 台設備…\n")
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(action, targets.keys()))

    print(f"{'別名':<10} {'IP':<17} {'狀態'}")
    print("-" * 62)
    ready = offline = 0
    for r in sorted(results, key=lambda x: [int(v) for v in x["ip"].split(".")]):
        alias = targets.get(r["ip"]) or "-"
        if not r["online"]:
            status = f"⚪ {r['note']}"
            offline += 1
        elif r["installed"] and r["granted"]:
            _wd = "、無線偵錯開啟" if r.get("wifi_debug") else "、⚠️ 無線偵錯未開"
            status = f"✅ 已就緒（{r['note'] or '先前已設定'}{_wd}）"
            ready += 1
        elif r["installed"]:
            status = "⚠️  已安裝但沒有權限"
        else:
            status = f"❌ {r['note'] or '未安裝'}"
        print(f"{alias:<10} {r['ip']:<17} {status}")
    print("-" * 62)
    print(f"就緒 {ready} 台 · 連不上 {offline} 台")

    if ready:
        print("\n✅ 這些設備重開機後可用以下任一方式自動恢復，不必接線：")
        print("   • UI：設備管理 →「🔗 一鍵連接所有設備」")
        print("   • 指令：python3 tools/wake_devices.py")
        print("\n   （只有在某台重開機後「5555 和無線偵錯都關了」的情況，")
        print("     才需要戴頭盔開一次 Oculus Wireless ADB 當救命稻草。）")
    if offline:
        print(f"\n⏳ 有 {offline} 台連不上（睡著或關機）。醒著時再跑一次這支腳本即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
