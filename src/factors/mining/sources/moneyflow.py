"""factors/mining/sources/moneyflow.py — 资金流因子族。

吃含 moneyflow 列与 circ_mv 的宽表（date/code 行对齐），输出截面因子值。
金额单位：net_mf_amount / circ_mv 均为万元（同单位相除，无量纲）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_moneyflow_net_ratio(df: pd.DataFrame) -> pd.Series:
    """主力净流入强度：net_mf_amount / circ_mv（万元相除）。"""
    if "circ_mv" not in df.columns:
        return pd.Series(np.nan, index=df.index, name="moneyflow_net_ratio")
    out = df["net_mf_amount"] / df["circ_mv"]
    return out.rename("moneyflow_net_ratio")


def calc_moneyflow_streak(df: pd.DataFrame) -> pd.Series:
    """连续净流入天数（net_mf_amount > 0 的连续计数，按 code 分组日期升序）。"""
    tmp = df[["date", "code", "net_mf_amount"]].copy()
    tmp["__pos__"] = (tmp["net_mf_amount"] > 0).astype(int)
    tmp["__grp__"] = tmp.groupby("code")["__pos__"].transform(
        lambda x: (x != x.shift()).cumsum()
    )
    streak = tmp.groupby(["code", "__grp__"])["__pos__"].cumsum()
    return pd.Series(streak.to_numpy(), index=df.index, name="moneyflow_streak")


def calc_moneyflow_big_net_ratio(df: pd.DataFrame) -> pd.Series:
    """大单+特大单净额占当日四档总金额比例。"""
    buy = df["buy_lg_amount"] + df["buy_elg_amount"]
    sell = df["sell_lg_amount"] + df["sell_elg_amount"]
    denom = (
        df["buy_sm_amount"]
        + df["sell_sm_amount"]
        + df["buy_md_amount"]
        + df["sell_md_amount"]
        + df["buy_lg_amount"]
        + df["sell_lg_amount"]
        + df["buy_elg_amount"]
        + df["sell_elg_amount"]
    )
    out = (buy - sell) / denom.replace(0, np.nan)
    return out.rename("moneyflow_big_net_ratio")
