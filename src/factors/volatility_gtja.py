"""GTJA 191 Alpha Factors — Volatility / Risk category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.operators import corr, delay, rolling_mean, rolling_std


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_cci_12d(df: pd.DataFrame) -> pd.Series:
    """12d Commodity Channel Index.

    GTJA Factor #78.
    CCI = (TP - MA(TP)) / (0.015 * mean(|TP - MA(TP)|))
    """
    df = _prepare(df)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    tp_df = pd.concat([df[["code", "date"]], tp.rename("val")], axis=1)
    ma_tp = rolling_mean(tp_df, "val", 12)
    deviation = (tp - ma_tp).abs()
    dev_df = pd.concat([df[["code", "date"]], deviation.rename("val")], axis=1)
    mean_dev = rolling_mean(dev_df, "val", 12)
    cci = (tp - ma_tp) / (0.015 * mean_dev)
    return cci.replace([np.inf, -np.inf], 0.0)


def calc_volume_vol_10d(df: pd.DataFrame) -> pd.Series:
    """10d volume volatility: std(vol, 10).

    GTJA Factor #97.
    """
    df = _prepare(df)
    vol_df = pd.concat([df[["code", "date"]], df["volume"].rename("val")], axis=1)
    return rolling_std(vol_df, "val", 10)


def calc_volume_vol_20d(df: pd.DataFrame) -> pd.Series:
    """20d volume volatility: std(vol, 20).

    GTJA Factor #100.
    """
    df = _prepare(df)
    vol_df = pd.concat([df[["code", "date"]], df["volume"].rename("val")], axis=1)
    return rolling_std(vol_df, "val", 20)


def calc_atr_12d(df: pd.DataFrame) -> pd.Series:
    """12d Average True Range.

    GTJA Factor #161.
    ATR = mean(max(high-low, |high-prev_close|, |low-prev_close|), 12)
    """
    df = _prepare(df)
    prev_close = delay(df, "close", 1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr_df = pd.concat([df[["code", "date"]], true_range.rename("val")], axis=1)
    return rolling_mean(tr_df, "val", 12)


def calc_atr_6d(df: pd.DataFrame) -> pd.Series:
    """6d Average True Range.

    GTJA Factor #175.
    """
    df = _prepare(df)
    prev_close = delay(df, "close", 1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr_df = pd.concat([df[["code", "date"]], true_range.rename("val")], axis=1)
    return rolling_mean(tr_df, "val", 6)
