"""Volume-price factors: RSI, OBV, volume ratio, ATR."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Relative Strength Index (RSI).

    RSI = 100 - 100 / (1 + avg_gain / avg_loss)

    Parameters
    ----------
    df : DataFrame
        Must contain date, code, close.
    window : int
        Lookback window for average gain/loss.

    Returns
    -------
    Series
        RSI values in [0, 100]. NaN where insufficient data.
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    delta = df.groupby("code")["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.groupby(df["code"]).rolling(
        window=window, min_periods=window
    ).mean().droplevel(0)
    avg_loss = loss.groupby(df["code"]).rolling(
        window=window, min_periods=window
    ).mean().droplevel(0)

    # RSI = 100 - 100/(1 + avg_gain/avg_loss)
    # Handle edge cases explicitly:
    # - avg_loss = 0, avg_gain > 0 → RSI = 100
    # - avg_gain = 0, avg_loss > 0 → RSI = 0
    # - both 0 → RSI = 50 (convention)
    # - either NaN (insufficient window) → RSI = NaN
    both_valid = avg_gain.notna() & avg_loss.notna()
    rsi = pd.Series(np.nan, index=df.index)

    mask_both_zero = both_valid & (avg_gain == 0) & (avg_loss == 0)
    mask_loss_zero = both_valid & (avg_loss == 0) & (avg_gain > 0)
    mask_gain_zero = both_valid & (avg_gain == 0) & (avg_loss > 0)
    mask_normal = both_valid & (avg_gain > 0) & (avg_loss > 0)

    rsi[mask_both_zero] = 50.0
    rsi[mask_loss_zero] = 100.0
    rsi[mask_gain_zero] = 0.0
    rs = avg_gain[mask_normal] / avg_loss[mask_normal]
    rsi[mask_normal] = 100 - 100 / (1 + rs)

    return rsi.sort_index()


def calc_obv(df: pd.DataFrame) -> pd.Series:
    """On Balance Volume (OBV).

    OBV += volume if close > prev_close
    OBV -= volume if close < prev_close
    OBV unchanged if close == prev_close

    Parameters
    ----------
    df : DataFrame
        Must contain date, code, close, volume.

    Returns
    -------
    Series
        Cumulative OBV. First value per stock is 0.
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    sign = df.groupby("code")["close"].diff().apply(np.sign).fillna(0)
    obv = (sign * df["volume"]).groupby(df["code"]).cumsum()

    return obv.sort_index()


def calc_volume_ratio(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volume ratio: current volume / rolling average volume.

    Parameters
    ----------
    df : DataFrame
        Must contain date, code, volume.
    window : int
        Rolling window for average volume.

    Returns
    -------
    Series
        Volume ratio. NaN where insufficient data.
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    avg_vol = df.groupby("code")["volume"].rolling(
        window=window, min_periods=window
    ).mean().droplevel(0)

    ratio = df["volume"] / avg_vol
    return ratio.sort_index()


def calc_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range (ATR).

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = rolling mean of TR.

    Parameters
    ----------
    df : DataFrame
        Must contain date, code, high, low, close.
    window : int
        Rolling window for ATR.

    Returns
    -------
    Series
        ATR values. NaN where insufficient data.
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    prev_close = df.groupby("code")["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.groupby(df["code"]).rolling(
        window=window, min_periods=window
    ).mean().droplevel(0)

    return atr.sort_index()
