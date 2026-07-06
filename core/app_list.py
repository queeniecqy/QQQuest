"""應用程式清單（應用名稱 ↔ package）。

給「動作管理」與「房間管理」共用：在動作管理頁維護，執行動作時用應用名稱挑要操作的 package。
"""
import json
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

# app_packages.json 放在專案根目錄（本檔在 core/ 之下，parent.parent = 專案根）
APP_LIST_FILE = str(Path(__file__).resolve().parent.parent / "app_packages.json")

DEFAULT_APP_LIST = [
    {"name": "東方美人 (OrientalBeauty)", "package": "com.Awespire.OrientalBeauty"},
]


def load_app_list():
    """讀取應用程式清單 [{name, package}]；檔案不存在則建立預設。"""
    try:
        if not Path(APP_LIST_FILE).exists():
            with open(APP_LIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_APP_LIST, f, indent=2, ensure_ascii=False)
            return list(DEFAULT_APP_LIST)
        with open(APP_LIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        out = []
        for d in data:
            pkg = str(d.get('package', '') or '').strip()
            name = str(d.get('name', '') or '').strip()
            if pkg:
                out.append({"name": name or pkg, "package": pkg})
        return out
    except Exception as e:
        logger.error(f"讀取應用清單失敗: {e}")
        return list(DEFAULT_APP_LIST)


def save_app_list(df_data):
    """將 DataFrame（name, package）存回 JSON，只保留有 package 的列。"""
    try:
        import pandas as pd
        apps = []
        for _, row in df_data.iterrows():
            pkg_val = row.get('package', '')
            name_val = row.get('name', '')
            pkg = '' if pd.isna(pkg_val) else str(pkg_val).strip()
            name = '' if pd.isna(name_val) else str(name_val).strip()
            if pkg and pkg.lower() != 'nan':
                apps.append({"name": name or pkg, "package": pkg})
        with open(APP_LIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(apps, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"保存應用清單失敗: {e}")
        return False
