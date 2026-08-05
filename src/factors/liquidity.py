"""Liquidity factor functions: Amihud illiquidity and turnover rate."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.operators import rolling_mean


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_amihud(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Amihud illiquidity: mean(|return| / (volume * close)) over rolling window.

    Higher value = less liquid. Zero volume → NaN for that day (excluded from mean).
    """
    df = _prepare(df)
    ret = df.groupby("code")["close"].transform(lambda s: s.pct_change().abs())
    turnover = df["volume"].astype(float) * df["close"].astype(float)
    # Avoid division by zero: zero turnover → NaN
    ratio = np.where(turnover > 0, ret / turnover, np.nan)
    ratio = pd.Series(ratio, index=df.index)
    return rolling_mean(df.assign(_amihud=ratio), "_amihud", window)


def calc_turnover(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Rolling average turnover rate: volume * close / (total_mv * 1e8).

    total_mv is in 亿元 (1e8 yuan), volume is in shares, close is in yuan.
    """
    df = _prepare(df)
    daily_turnover = df["volume"].astype(float) * df["close"].astype(float) / (
        df["total_mv"].astype(float) * 1e8
    )
    return rolling_mean(df.assign(_turnover=daily_turnover), "_turnover", window)
