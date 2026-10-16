#!/usr/bin/env python3
"""
喚醒 Quest 的 adb 連線（重開機後救援）

背景：Quest 重開機後 `service.adb.tcp.port` 會被清空（那是非持久屬性），5555 因此關閉，
原本只能接 USB 線重下 `adb tcpip 5555`。

但只要該機的「無線偵錯」還開著，adbd 會另外在一個隨機埠提供 TLS 連線並用 mDNS 廣播。
本工具就是從那裡連進去、重下 tcpip 5555 把固定埠救回來——不必接線，也不必戴頭盔。

前提：該設備的無線偵錯必須是開啟的（adb_wifi_enabled=1）且本機金鑰已配對過。
      沒開的話會明確告訴你哪幾台需要戴頭盔開一次 Oculus Wireless ADB。

用法：
    python3 tools/wake_devices.py                    # 對所有已登記設備
    python3 tools/wake_devices.py --ip 192.168.68.90 # 只處理某台
    python3 tools/wake_devices.py --status           # 只看狀態，不動作
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.adb_manager import ADBManager          # noqa: E402
from tools.dhcp_reservations import load_known_devices  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="重開機後喚醒 Quest 的 adb 連線")
    ap.add_argument("--ip", help="只處理指定 IP")
    ap.add_argument("--status", action="store_true", help="只檢查狀態，不嘗試救援")
    args = ap.parse_args()

    adb = ADBManager()
    known = {args.ip: ""} if args.ip else load_known_devices()
    if not known:
        print("❌ 找不到已登記的設備")
        return 1

    live = {d.get('serial'): d.get('state') for d in adb.get_devices(use_cache=False)}
    print(f"🔍 檢查 {len(known)} 台設備…\n")

    need = []          # 需要救援的
    rows = []          # (別名, ip, 狀態字串)
    for ip, alias in known.items():
        target = f"{ip}:5555"
        state = live.get(target)
        if state == 'device':
            rows.append((alias, ip, "✅ 已連線"))
        else:
            tls = adb.find_mdns_tls_port(ip)
            if tls:
                rows.append((alias, ip, f"🔄 5555 未通，但無線偵錯在 {tls}" +
                             ("（可救援）" if not args.status else "")))
                need.append((ip, alias))
            else:
                rows.append((alias, ip, "⚪ 無回應（睡著／關機／無線偵錯未開）"))

    if need and not args.status:
        print(f"🚀 嘗試救援 {len(need)} 台…\n")

        def _do(item):
            ip, alias = item
            ok, msg = adb.reconnect_via_mdns(ip)
            return alias, ip, ok, msg

        with ThreadPoolExecutor(max_workers=6) as ex:
            results = list(ex.map(_do, need))

        fixed = {ip: (ok, msg) for _, ip, ok, msg in results}
        rows = [(a, ip, ("✅ 已喚醒（5555 已恢復）" if fixed[ip][0]
                         else "❌ 救援失敗：" + (fixed[ip][1].splitlines() or [""])[-1])
                 if ip in fixed else s)
                for a, ip, s in rows]

    print(f"{'別名':<10} {'IP':<17} 狀態")
    print("-" * 78)
    for alias, ip, state in sorted(rows, key=lambda r: [int(v) for v in r[1].split(".")]):
        print(f"{(alias or '-'):<10} {ip:<17} {state}")
    print("-" * 78)

    okc = sum(1 for _, _, s in rows if s.startswith("✅"))
    print(f"可用 {okc}/{len(rows)} 台")

    dead = [(a, ip) for a, ip, s in rows if s.startswith("⚪")]
    if dead:
        print(f"\n⏳ {len(dead)} 台無回應。若確定它已開機並在網路上，")
        print("   表示該台的無線偵錯沒開 → 戴上頭盔開一次 Oculus Wireless ADB 即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
