"""GTJA 191 Alpha Factors — VWAP-Based category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.operators import rolling_mean


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def _calc_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price (cumulative VWAP approximation)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    amount = typical * df["volume"]
    cum_amount = amount.groupby(df["code"]).cumsum()
    cum_vol = df["volume"].groupby(df["code"]).cumsum()
    return (cum_amount / cum_vol).replace([np.inf, -np.inf], np.nan)


def calc_vwap_close_ratio(df: pd.DataFrame) -> pd.Series:
    """VWAP vs close rank ratio: rank(vwap - close) / rank(vwap + close).

    GTJA Factor #120.
    Simplified: (vwap - close) / (vwap + close) as a proxy.
    """
    df = _prepare(df)
    vwap = _calc_vwap(df)
    diff = vwap - df["close"]
    total = vwap + df["close"]
    return (diff / total).replace([np.inf, -np.inf], 0.0)


def calc_vwap_deviation(df: pd.DataFrame) -> pd.Series:
    """VWAP deviation: (close - vwap) / decaylinear(rank(tsmax(close,30)), 2).

    GTJA Factor #124. Simplified to (close - vwap) / close.
    """
    df = _prepare(df)
    vwap = _calc_vwap(df)
    return ((df["close"] - vwap) / df["close"]).replace([np.inf, -np.inf], 0.0)
