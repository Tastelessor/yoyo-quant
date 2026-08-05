"""GTJA 191 Alpha Factors — Price Momentum / Trend category.

Factor formulas from Guotai Junan Securities 191 Alpha Factors paper.
Each function follows the standard factor contract:
  calc_xxx(df) -> pd.Series

Parameters
----------
df : DataFrame
    Must contain date, code, open, high, low, close, volume.
    Will be sorted by (code, date) internally.

Returns
-------
pd.Series
    Aligned to input index. NaN where insufficient data.
"""

from __future__ import annotations

import pandas as pd

from factors.operators import delay


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Sort and reset index for consistent groupby computation."""
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_momentum_5d_change(df: pd.DataFrame) -> pd.Series:
    """5-day price change: close - delay(close, 5).

    GTJA Factor #14.
    """
    df = _prepare(df)
    return df["close"] - delay(df, "close", 5)


def calc_momentum_5d_ratio(df: pd.DataFrame) -> pd.Series:
    """5-day price ratio: close / delay(close, 5).

    GTJA Factor #18.
    """
    df = _prepare(df)
    return df["close"] / delay(df, "close", 5)


def calc_momentum_6d_return(df: pd.DataFrame) -> pd.Series:
    """6-day return percentage: (close - delay(close, 6)) / delay(close, 6) * 100.

    GTJA Factor #20.
    """
    df = _prepare(df)
    delayed = delay(df, "close", 6)
    return (df["close"] - delayed) / delayed * 100


def calc_momentum_20d_return(df: pd.DataFrame) -> pd.Series:
    """20-day return percentage: (close - delay(close, 20)) / delay(close, 20) * 100.

    GTJA Factor #88.
    """
    df = _prepare(df)
    delayed = delay(df, "close", 20)
    return (df["close"] - delayed) / delayed * 100


def calc_momentum_20d_change(df: pd.DataFrame) -> pd.Series:
    """20-day price change: close - delay(close, 20).

    GTJA Factor #106.
    """
    df = _prepare(df)
    return df["close"] - delay(df, "close", 20)
