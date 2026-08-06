"""GTJA 191 Alpha Factors — Mean Reversion / Overbought-Oversold category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from factors.operators import delay, sma


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_rsi_6d(df: pd.DataFrame) -> pd.Series:
    """6-day RSI: sma(max(delta,0), 6, 1) / sma(abs(delta), 6, 1) * 100.

    GTJA Factor #63.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    gain = delta.clip(lower=0)
    loss = delta.abs()
    up = sma(pd.concat([df[["code", "date"]], gain.rename("val")], axis=1), "val", 6, 1)
    total = sma(pd.concat([df[["code", "date"]], loss.rename("val")], axis=1), "val", 6, 1)
    return (up / total * 100).replace([np.inf, -np.inf], 0.0)


def calc_rsi_12d(df: pd.DataFrame) -> pd.Series:
    """12-day RSI: sma(max(delta,0), 12, 1) / sma(abs(delta), 12, 1) * 100.

    GTJA Factor #79.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    gain = delta.clip(lower=0)
    loss = delta.abs()
    up = sma(pd.concat([df[["code", "date"]], gain.rename("val")], axis=1), "val", 12, 1)
    total = sma(pd.concat([df[["code", "date"]], loss.rename("val")], axis=1), "val", 12, 1)
    return (up / total * 100).replace([np.inf, -np.inf], 0.0)


def calc_directional_balance_12d(df: pd.DataFrame) -> pd.Series:
    """12d directional balance: (up_moves - down_moves) / (up_moves + down_moves) * 100.

    GTJA Factor #112.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    up_moves = delta.clip(lower=0)
    down_moves = (-delta).clip(lower=0)
    window = 12
    sum_up = (
        up_moves.groupby(df["code"])
        .rolling(window=window, min_periods=window)
        .sum()
        .droplevel(0)
        .sort_index()
    )
    sum_down = (
        down_moves.groupby(df["code"])
        .rolling(window=window, min_periods=window)
        .sum()
        .droplevel(0)
        .sort_index()
    )
    total = sum_up + sum_down
    result = ((sum_up - sum_down) / total * 100).replace([np.inf, -np.inf], 0.0)
    return result


def calc_mfi_14d(df: pd.DataFrame) -> pd.Series:
    """14-day Money Flow Index-like: 100 - 100/(1 + sum(up_amount)/sum(down_amount)).

    GTJA Factor #128.
    Typical price * volume = amount. Up amount if close > prev close.
    """
    df = _prepare(df)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    amount = typical * df["volume"]
    delta = df["close"] - delay(df, "close", 1)
    up_amount = amount.where(delta > 0, 0.0)
    down_amount = amount.where(delta < 0, 0.0)
    window = 14
    sum_up = (
        up_amount.groupby(df["code"])
        .rolling(window=window, min_periods=window)
        .sum()
        .droplevel(0)
        .sort_index()
    )
    sum_down = (
        down_amount.groupby(df["code"])
        .rolling(window=window, min_periods=window)
        .sum()
        .droplevel(0)
        .sort_index()
    )
    mfr = sum_up / sum_down
    result = (100 - 100 / (1 + mfr)).replace([np.inf, -np.inf], 0.0)
    return result
