import numpy as np
import pandas as pd


def calc_hv(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """计算历史波动率 (Historical Volatility)。

    使用收盘价的对数收益率标准差 × sqrt(252) 年化。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close 列。
    window : int
        滚动窗口天数，默认 20。

    Returns
    -------
    Series
        与 df 等长的 HV 序列，前 window 个值为 NaN（含首行 shift 产生的 NaN）。
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    log_ret = np.log(df["close"] / df.groupby("code")["close"].shift(1))
    hv = (
        log_ret.groupby(df["code"])
        .rolling(window=window, min_periods=window)
        .std()
        .droplevel(0)
        * np.sqrt(252)
    )
    return hv.sort_index()
