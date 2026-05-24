"""GTJA 191 Alpha Factors — Trend category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.operators import delay, rolling_mean, sma


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_ma_slope_6d(df: pd.DataFrame) -> pd.Series:
    """6d moving average slope (linear regression beta).

    GTJA Factor #21. Simplified: mean(close,6) - delay(mean(close,6), 1).
    """
    df = _prepare(df)
    ma_df = pd.concat([df[["code", "date"]], df["close"].rename("val")], axis=1)
    ma = rolling_mean(ma_df, "val", 6)
    return ma - delay(pd.concat([df[["code", "date"]], ma.rename("val")], axis=1), "val", 1)


def calc_ma_slope_20d(df: pd.DataFrame) -> pd.Series:
    """20d linear regression slope.

    GTJA Factor #116. Simplified: mean(close,20) - delay(mean(close,20), 1).
    """
    df = _prepare(df)
    ma_df = pd.concat([df[["code", "date"]], df["close"].rename("val")], axis=1)
    ma = rolling_mean(ma_df, "val", 20)
    return ma - delay(pd.concat([df[["code", "date"]], ma.rename("val")], axis=1), "val", 1)


def calc_macd_like(df: pd.DataFrame) -> pd.Series:
    """MACD-like indicator: 2*(sma(close,13,2)-sma(close,27,2)-sma(...,10,2)).

    GTJA Factor #89.
    """
    df = _prepare(df)
    close_df = pd.concat([df[["code", "date"]], df["close"].rename("val")], axis=1)
    ema13 = sma(close_df, "val", 13, 2)
    ema27 = sma(close_df, "val", 27, 2)
    diff = ema13 - ema27
    diff_df = pd.concat([df[["code", "date"]], diff.rename("val")], axis=1)
    signal = sma(diff_df, "val", 10, 2)
    return 2 * (diff - signal)
