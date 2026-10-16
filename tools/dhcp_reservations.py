#!/usr/bin/env python3
"""
產生路由器 DHCP 保留（固定 IP）設定表

用途：讓每台 Quest 的 IP 不再漂移。IP 固定後，adb / QQQuest 的自動重連才可靠，
也不會再出現同一台機器在設備清單裡有兩個 IP 的情況。

做法：掃描區網 → 從 ARP 表取得每台設備在「你這個 Wi-Fi 上實際使用的 MAC」
（Android 14 預設每個 SSID 一組隨機 MAC，所以查硬體 MAC 是沒用的，
 必須用實際通訊的這個），再對照 QQQuest 設備清單補上別名。

睡著的 Quest 抓不到（整台會離開網路）。所以本工具會把每次的結果
「累積」存進 data/dhcp_reservations.json，可以分幾次、趁不同機器醒著時跑，
直到收齊為止。

用法：
    python3 tools/dhcp_reservations.py                # 掃描本機網段
    python3 tools/dhcp_reservations.py --net 192.168.68   # 指定網段
    python3 tools/dhcp_reservations.py --adb          # 額外用 adb 確認機型（較慢）
    python3 tools/dhcp_reservations.py --show         # 只看目前累積結果，不掃描
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "dhcp_reservations.json"
CSV_FILE = DATA_DIR / "dhcp_reservations.csv"


# ----------------------------------------------------------------------
# 基礎工具
# ----------------------------------------------------------------------

def normalize_mac(mac: str) -> str:
    """macOS 的 arp 會省略前導零（6:89:5e），路由器要的是完整格式（06:89:5e）"""
    parts = [p for p in mac.strip().split(':') if p != '']
    if len(parts) != 6:
        return ""
    try:
        return ':'.join(f"{int(p, 16):02x}" for p in parts)
    except ValueError:
        return ""


def is_random_mac(mac: str) -> bool:
    """locally administered bit（第一個 byte 的 0x02）→ Android 的每網路隨機 MAC"""
    try:
        return bool(int(mac.split(':')[0], 16) & 0x02)
    except (ValueError, IndexError):
        return False


def local_subnet() -> str:
    for iface in ("en0", "en1"):
        try:
            ip = subprocess.run(["ipconfig", "getifaddr", iface],
                                capture_output=True, text=True, timeout=5).stdout.strip()
            if ip:
                return ".".join(ip.split(".")[:3])
        except Exception:
            continue
    return ""


# ----------------------------------------------------------------------
# 掃描
# ----------------------------------------------------------------------

def ping_sweep(subnet: str):
    """並行 ping 整個 /24，目的是把還醒著的設備填進本機 ARP 表"""
    def ping(i):
        ip = f"{subnet}.{i}"
        try:
            # macOS ping：-W 單位是毫秒
            subprocess.run(["ping", "-c", "1", "-W", "800", ip],
                           capture_output=True, timeout=3)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(ping, range(1, 255)))


def read_arp_table(subnet: str) -> dict:
    """讀 ARP 表，回傳 {ip: mac}（MAC 已正規化）"""
    out = {}
    try:
        raw = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return out
    # 格式：? (192.168.68.90) at aa:bb:cc:6:89:5e on en0 ifscope [ethernet]
    pattern = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)")
    for line in raw.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        ip, mac_raw = m.group(1), m.group(2)
        if not ip.startswith(subnet + "."):
            continue
        mac = normalize_mac(mac_raw)
        if mac and mac != "ff:ff:ff:ff:ff:ff":
            out[ip] = mac
    return out


# ----------------------------------------------------------------------
# QQQuest 設備清單（取別名）
# ----------------------------------------------------------------------

def load_known_devices() -> dict:
    """回傳 {ip: alias}，來自 QQQuest 的設備登記"""
    known = {}
    db = DATA_DIR / "devices.json"
    if not db.exists():
        return known
    try:
        raw = json.loads(db.read_text(encoding="utf-8"))
    except Exception:
        return known
    tables = raw.values() if isinstance(raw, dict) else []
    for rows in tables:
        if not isinstance(rows, dict):
            continue
        for rec in rows.values():
            if not isinstance(rec, dict):
                continue
            ip = rec.get("ip") or ""
            if not ip:
                serial = rec.get("serial") or ""
                ip = serial.split(":")[0] if ":" in serial else ""
            if ip:
                known[ip] = rec.get("alias") or rec.get("name") or ""
    return known


def adb_probe(ip: str) -> dict:
    """（可選）用 adb 連上該 IP 確認機型與 wlan0 MAC"""
    target = f"{ip}:5555"
    info = {}
    try:
        r = subprocess.run(["adb", "connect", target], capture_output=True, text=True, timeout=8)
        if "connected" not in r.stdout:
            return info
        q = subprocess.run(
            ["adb", "-s", target, "shell",
             "getprop ro.product.model; cat /sys/class/net/wlan0/address"],
            capture_output=True, text=True, timeout=10)
        lines = [l.strip() for l in q.stdout.splitlines() if l.strip()]
        if lines:
            info["model"] = lines[0]
        if len(lines) > 1:
            info["wlan0_mac"] = normalize_mac(lines[1])
    except Exception:
        pass
    return info


# ----------------------------------------------------------------------
# 狀態累積
# ----------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    DATA_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(state: dict):
    DATA_DIR.mkdir(exist_ok=True)
    rows = sorted(state.values(), key=lambda r: [int(x) for x in r["ip"].split(".")])
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["別名", "保留 IP", "MAC", "MAC 類型", "機型", "最後偵測"])
        for r in rows:
            w.writerow([r.get("alias", ""), r["ip"], r["mac"],
                        "隨機" if r.get("random_mac") else "實體",
                        r.get("model", ""), r.get("last_seen", "")])


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="產生 DHCP 保留（固定 IP）設定表")
    ap.add_argument("--net", help="網段前三段，例如 192.168.68（預設自動偵測）")
    ap.add_argument("--adb", action="store_true", help="額外用 adb 確認機型（較慢）")
    ap.add_argument("--show", action="store_true", help="只顯示已累積結果，不掃描")
    args = ap.parse_args()

    state = load_state()

    if not args.show:
        subnet = args.net or local_subnet()
        if not subnet:
            print("❌ 抓不到本機網段，請用 --net 指定，例如：--net 192.168.68")
            return 1

        print(f"🔍 掃描 {subnet}.0/24 中（約 10 秒）…")
        ping_sweep(subnet)
        arp = read_arp_table(subnet)
        known = load_known_devices()

        # 只保留「QQQuest 認識的設備」——網段上還有路由器、電腦等無關裝置
        hits = {ip: mac for ip, mac in arp.items() if ip in known}
        print(f"   ARP 表共 {len(arp)} 筆，其中 {len(hits)} 筆是 QQQuest 已登記的設備")

        if args.adb and hits:
            print("   用 adb 確認機型中…")
            with ThreadPoolExecutor(max_workers=8) as ex:
                probes = dict(zip(hits.keys(), ex.map(adb_probe, hits.keys())))
        else:
            probes = {}

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for ip, mac in hits.items():
            entry = state.get(ip, {})
            entry.update({
                "ip": ip,
                "mac": mac,
                "alias": known.get(ip) or entry.get("alias", ""),
                "random_mac": is_random_mac(mac),
                "last_seen": now,
            })
            p = probes.get(ip) or {}
            if p.get("model"):
                entry["model"] = p["model"]
            if p.get("wlan0_mac"):
                entry["wlan0_mac"] = p["wlan0_mac"]
            state[ip] = entry

        save_state(state)

    if not state:
        print("\n⚠️  目前沒有任何結果。Quest 睡著時會整台離開網路，抓不到。")
        print("   請在設備醒著時（例如戴上頭盔、或活動開始前）重跑一次。")
        return 0

    write_csv(state)

    # ---- 輸出表格 ----
    rows = sorted(state.values(), key=lambda r: [int(x) for x in r["ip"].split(".")])
    print("\n" + "=" * 74)
    print("路由器 DHCP 保留設定表（把下面的 MAC ↔ IP 填進路由器）")
    print("=" * 74)
    print(f"{'別名':<10} {'保留 IP':<17} {'MAC':<19} {'類型':<6} {'最後偵測'}")
    print("-" * 74)
    for r in rows:
        print(f"{(r.get('alias') or '-'):<10} {r['ip']:<17} {r['mac']:<19} "
              f"{'隨機' if r.get('random_mac') else '實體':<6} {r.get('last_seen', '')}")
    print("-" * 74)
    print(f"共 {len(rows)} 台 · 已存到 {CSV_FILE.relative_to(PROJECT_ROOT)}")

    # ---- 尚未收齊的設備（分成「同網段睡著」與「不在目前網段」）----
    known = load_known_devices()
    subnet_now = args.net or local_subnet()
    missing = [(ip, alias) for ip, alias in known.items() if ip not in state]
    same_net = [(ip, a) for ip, a in missing if subnet_now and ip.startswith(subnet_now + ".")]
    other_net = [(ip, a) for ip, a in missing if not (subnet_now and ip.startswith(subnet_now + "."))]

    if same_net:
        print(f"\n⏳ 還有 {len(same_net)} 台在本網段但沒回應（睡著或關機），醒著時再跑一次就會累積進來：")
        for ip, alias in sorted(same_net, key=lambda x: [int(v) for v in x[0].split(".")]):
            print(f"   {alias or '-':<10} {ip}")

    if other_net:
        print(f"\nℹ️  另有 {len(other_net)} 筆登記在別的網段（掃不到，多半是舊記錄，可考慮清掉）：")
        for ip, alias in sorted(other_net):
            print(f"   {alias or '-':<10} {ip}")

    # ---- 同一台機器有多個 IP：設保留時要挑一個 ----
    by_alias = {}
    for r in rows:
        a = r.get("alias") or ""
        if a:
            by_alias.setdefault(a, []).append(r["ip"])
    for ip, alias in known.items():
        if alias and ip not in [x["ip"] for x in rows]:
            by_alias.setdefault(alias, []).append(ip)
    dupes = {a: ips for a, ips in by_alias.items() if len(set(ips)) > 1}
    if dupes:
        print("\n⚠️  這些別名有多個 IP（就是 IP 漂移造成的重複，設好保留後就不會再發生）：")
        for a, ips in sorted(dupes.items()):
            print(f"   {a:<10} {', '.join(sorted(set(ips)))}   ← 保留設其中一個，其餘可從設備清單刪除")

    if any(r.get("random_mac") for r in rows):
        print("\n💡 標示「隨機」的是 Android 14 的每網路隨機 MAC。同一個 Wi-Fi(SSID) 下它是固定的，")
        print("   直接拿去設保留沒問題；但如果之後換 SSID 或重設網路，MAC 會變、保留要重設。")
        print("   想一勞永逸：在 Quest 該 Wi-Fi 的設定裡把隱私權改成「使用裝置 MAC」。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
