"""GTJA 191 Alpha Factors — Volume-Price Relationship category."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.operators import delay, rolling_sum


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def calc_money_flow_6d(df: pd.DataFrame) -> pd.Series:
    """6d money flow: sum(((close-low)-(high-close))/(high-low)*vol, 6).

    GTJA Factor #11. Directional pressure weighted by volume.
    """
    df = _prepare(df)
    hl_range = df["high"] - df["low"]
    # Avoid division by zero
    hl_range = hl_range.replace(0, np.nan)
    pressure = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl_range
    signed_vol = pressure * df["volume"]
    tmp = pd.concat([df[["code", "date"]], signed_vol.rename("val")], axis=1)
    return rolling_sum(tmp, "val", 6)


def calc_up_down_vol_ratio_26d(df: pd.DataFrame) -> pd.Series:
    """26d up-volume / down-volume ratio * 100.

    GTJA Factor #40.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    up_vol = df["volume"].where(delta > 0, 0.0)
    down_vol = df["volume"].where(delta < 0, 0.0)
    tmp_up = pd.concat([df[["code", "date"]], up_vol.rename("val")], axis=1)
    tmp_down = pd.concat([df[["code", "date"]], down_vol.rename("val")], axis=1)
    sum_up = rolling_sum(tmp_up, "val", 26)
    sum_down = rolling_sum(tmp_down, "val", 26)
    return (sum_up / sum_down * 100).replace([np.inf, -np.inf], 0.0)


def calc_obv_6d(df: pd.DataFrame) -> pd.Series:
    """6d OBV-like signed volume sum.

    GTJA Factor #43.
    """
    df = _prepare(df)
    delta = df["close"] - delay(df, "close", 1)
    signed = df["volume"].where(delta > 0, -df["volume"].where(delta < 0, 0.0))
    tmp = pd.concat([df[["code", "date"]], signed.rename("val")], axis=1)
    return rolling_sum(tmp, "val", 6)
