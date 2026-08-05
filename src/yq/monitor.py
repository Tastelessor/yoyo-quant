"""yq factor monitor 输出层：状态表聚合与变更 diff 渲染。

纯函数，不依赖 typer；CLI 命令（``yq/factors.py``）调用它们做渲染。
"""

from __future__ import annotations

import pandas as pd

#: 状态显示排序：dead 置顶（最需要关注），active 垫底
_STATE_ORDER = {"dead": 0, "reverse": 1, "decaying": 2, "active": 3}


def build_status_table(state: pd.DataFrame) -> pd.DataFrame:
    """state 长表 → 每 (factor, fwd_window) 一行状态摘要。

    取每个键最新日期行的 state / t_stat / rolling_ir / sustain_days，
    并补最近一次状态切换日期（无切换为 NaT）。按状态排序（dead 置顶），
    同状态下按 factor / fwd_window 排序。

    Parameters
    ----------
    state : DataFrame
        与 ``factor_monitor.STATE_COLS`` 一致的长表（含完整时序）。

    Returns
    -------
    DataFrame
        列：factor / fwd_window / state / t_stat / rolling_ir /
        sustain_days / last_switch_date。
    """
    state = state.sort_values(["factor", "fwd_window", "date"])
    latest = state.groupby(["factor", "fwd_window"], as_index=False).tail(1)
    # 最近切换日期：同一键内 state 相对前一行发生变化的最近日期
    prev_state = state.groupby(["factor", "fwd_window"])["state"].shift(1)
    switched = state[prev_state.notna() & (state["state"] != prev_state)]
    last_switch = switched.groupby(["factor", "fwd_window"])["date"].max()
    latest = latest.copy()
    key = latest.set_index(["factor", "fwd_window"]).index
    latest["last_switch_date"] = key.map(last_switch).to_numpy()
    latest["_order"] = latest["state"].map(_STATE_ORDER).fillna(9).astype(int)
    latest = latest.sort_values(["_order", "factor", "fwd_window"]).drop(
        columns="_order"
    )
    return latest[
        [
            "factor",
            "fwd_window",
            "state",
            "t_stat",
            "rolling_ir",
            "sustain_days",
            "last_switch_date",
        ]
    ].reset_index(drop=True)


def render_changes(changes: pd.DataFrame) -> str:
    """changes 长表 → 人类可读文本（每行一次切换）。"""
    if changes.empty:
        return "无状态切换"
    lines = [f"状态切换（{len(changes)} 处）："]
    for _, row in changes.sort_values(["date", "factor", "fwd_window"]).iterrows():
        lines.append(
            f"{row['date'].date()}  {row['factor']}  fwd={row['fwd_window']}  "
            f"{row['old_state']} → {row['new_state']}"
        )
    return "\n".join(lines)
