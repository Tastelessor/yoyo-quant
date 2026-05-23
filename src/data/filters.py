"""A 股市场状态标注。

为行情数据附加涨跌停、停牌等布尔列，供下游模块使用。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_limit_price(
    df: pd.DataFrame,
    limit_pct: float = 0.10,
) -> pd.DataFrame:
    """检测涨跌停。

    判定规则：收盘价相对前收盘涨跌幅 >= limit_pct。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close 列。
    limit_pct : float
        涨跌停幅度，默认 0.10（10%）。

    Returns
    -------
    DataFrame
        原 df 增加 limit_up (bool) 和 limit_down (bool) 列。
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    prev_close = df.groupby("code")["close"].shift(1)
    change_pct = (df["close"] - prev_close) / prev_close

    has_prev = prev_close.notna()
    eps = 1e-8  # 浮点容差
    limit_up = (change_pct >= limit_pct - eps) & has_prev
    limit_down = (change_pct <= -limit_pct + eps) & has_prev

    df = df.copy()
    df["limit_up"] = limit_up
    df["limit_down"] = limit_down
    return df


def detect_suspension(df: pd.DataFrame) -> pd.DataFrame:
    """检测停牌日。

    判定规则：成交量为 0 视为停牌。

    Parameters
    ----------
    df : DataFrame
        必须包含 volume 列。

    Returns
    -------
    DataFrame
        原 df 增加 is_suspended (bool) 列。
    """
    df = df.copy()
    df["is_suspended"] = df["volume"] == 0
    return df
