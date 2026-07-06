"""執行動作時的「選擇要操作的應用」共用 UI 元件（動作管理 / 房間管理共用）。"""
import copy

import streamlit as st

from core.app_list import load_app_list
from core.action import ActionType

# 有 package 參數、可在執行時改選 app 的動作類型
APP_PACKAGE_ACTION_TYPES = {
    ActionType.LAUNCH_APP, ActionType.RESUME_APP,
    ActionType.STOP_APP, ActionType.RESTART_APP,
}


def app_override_dropdown(action, key):
    """若 action 是 app 類動作，顯示「要操作的應用」下拉，回傳要覆蓋的 package（或 None）。

    預設選中動作存檔時的 package；清單為空且動作無預設時回傳 None。
    """
    if action.action_type not in APP_PACKAGE_ACTION_TYPES:
        return None

    app_list = load_app_list()
    saved_pkg = str(action.params.get('package', '') or '')

    opts = [(f"{a['name']} — {a['package']}", a['package']) for a in app_list]
    # 動作預設的 package 若不在清單，補一個可選項
    if saved_pkg and saved_pkg not in [p for _, p in opts]:
        opts.insert(0, (f"（動作預設）{saved_pkg}", saved_pkg))

    if not opts:
        st.warning("⚠️ 應用程式清單為空且此動作無預設 package，請先到『動作管理 → 📦 應用程式清單』新增。")
        return None

    pkgs = [p for _, p in opts]
    default_idx = pkgs.index(saved_pkg) if saved_pkg in pkgs else 0

    st.markdown("**選擇要操作的應用**")
    sel_idx = st.selectbox(
        "應用",
        options=range(len(opts)),
        index=default_idx,
        format_func=lambda i: opts[i][0],
        key=key,
        help="選擇這次要操作的應用；清單在『動作管理 → 📦 應用程式清單』維護。"
    )
    st.caption(f"將對 `{pkgs[sel_idx]}` 執行此動作")
    return pkgs[sel_idx]


def apply_package_override(action, override_package):
    """回傳套用 package 覆蓋後的 action 副本（不改原動作）。override 為 None 則原樣回傳。

    換成不同 app 時，原動作的 activity 不一定適用，會一併清掉改用預設啟動。
    """
    if not override_package:
        return action
    ex = copy.deepcopy(action)
    new_params = {**action.params, 'package': override_package}
    if override_package != str(action.params.get('package', '') or ''):
        new_params['activity'] = ''
    ex.params = new_params
    return ex
