"""Market regime detection using time-series momentum and adaptive volatility.

Classifies each trading day into one of four regimes:
- "trend_up":    market trending up, moderate-to-high volatility
- "trend_down":  market trending down, moderate-to-high volatility
- "range":       no clear direction, or low volatility
- "volatile":    high volatility without consensus direction

Pipeline
--------
1. **Breadth signal** (trend direction & strength)
   For each stock: above_sma = 1 if close > SMA(20), else 0.
   Cross-sectional aggregation: breadth = mean(above_sma) across all stocks.
   Centered: trend_consensus = breadth - 0.5.
   Range: [-0.5, +0.5].  Positive = more stocks in uptrend.

2. **Return confirmation** (direction tiebreaker)
   median_return = median of per-stock 20-day returns.
   Used as tiebreaker when trend_consensus is near zero.

3. **Realized volatility** (regime context)
   realized_vol = cross-sectional std of daily returns.
   Adaptive thresholds via rolling 60-day percentile:
   - high: above 75th percentile → "high vol" regime context
   - low:  below 25th percentile → "low vol" regime context
   - normal: between → "normal vol" context

4. **EMA smoothing** (noise reduction)
   All three signals are smoothed with EMA(span=5) before classification.
   Prevents single-day noise from flipping the regime.

5. **Classification rules**

   ===========  ================  ==========
   Vol Context   trend_consensus  → Regime
   ===========  ================  ==========
   High         |tc| > 0.2       trend direction from tc sign
   High         |tc| <= 0.2      volatile
   Normal       |tc| > 0.15      trend direction from tc sign
   Normal       |tc| <= 0.15     range
   Low          (any)            range
   ===========  ================  ==========

   Direction: tc > 0 or median_return > 0 → up; else down.

6. **Persistence enforcement**
   Short runs (< min_persistence days) are merged into their longer
   neighbor.  Ensures regime blocks are meaningful (default: 7 days).

Parameters (defaults tuned on 20 CSI 300 stocks, 2023-2026)
------------------------------------------------------------
- trend_window=20:  SMA period for breadth calculation
- vol_lookback=60:  rolling window for adaptive volatility thresholds
- ema_span=5:       EMA smoothing span
- min_persistence=7: minimum regime duration in trading days
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


def _enforce_persistence(regime: pd.Series, min_days: int = 5) -> pd.Series:
    """Enforce minimum regime duration.

    Short runs (< min_days) are merged into whichever neighbor is longer.
    Single-pass, O(n).
    """
    labels = regime.values
    n = len(labels)

    # Step 1: identify runs
    runs = []  # (start, end, label)
    i = 0
    while i < n:
        j = i + 1
        while j < n and labels[j] == labels[i]:
            j += 1
        runs.append([i, j, labels[i]])
        i = j

    # Step 2: merge short runs (single pass, left to right)
    merged = [runs[0]]
    for s, e, lbl in runs[1:]:
        prev_s, prev_e, prev_lbl = merged[-1]
        if (prev_e - prev_s) < min_days and prev_lbl != lbl:
            # Previous run is short and different label → absorb it
            merged[-1] = [prev_s, e, lbl]
        elif (e - s) < min_days:
            # Current run is short → extend previous to cover it
            merged[-1] = [prev_s, e, prev_lbl]
        else:
            merged.append([s, e, lbl])

    # Step 3: rebuild series
    result = labels.copy()
    for s, e, lbl in merged:
        result[s:e] = lbl

    return pd.Series(result, index=regime.index)


def detect_regime(
    data: pd.DataFrame,
    trend_window: int = 20,
    vol_lookback: int = 60,
    vol_high_pct: float = 75.0,
    vol_low_pct: float = 25.0,
    trend_strong_thresh: float = 0.2,
    trend_weak_thresh: float = 0.15,
    ema_span: int = 5,
    min_persistence: int = 7,
) -> pd.Series:
    """Detect market regime per date.

    Parameters
    ----------
    data : DataFrame
        Must contain date, code, open, high, low, close, volume.
    trend_window : int
        Window for SMA trend computation (per stock).
    vol_lookback : int
        Rolling window for adaptive volatility percentile thresholds.
    vol_high_pct : float
        Percentile above which volatility is "high" (0-100).
    vol_low_pct : float
        Percentile below which volatility is "low" (0-100).
    trend_strong_thresh : float
        |trend_consensus| above this in high-vol → trend.
    trend_weak_thresh : float
        |trend_consensus| above this in normal-vol → trend.
    ema_span : int
        EMA span for smoothing raw signals before classification.
        0 = no smoothing.
    min_persistence : int
        Minimum days a regime must persist before switching.
        1 = no enforcement.

    Returns
    -------
    Series
        Index: unique dates, sorted.
        Values: "trend_up", "trend_down", "range", or "volatile".
    """
    data = data.sort_values(["code", "date"]).reset_index(drop=True)
    dates = sorted(data["date"].unique())

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", category=RuntimeWarning, message="Mean of empty slice",
        )
        # --- Signal 1: Breadth — fraction of stocks above their SMA ---
        sma = (
            data.groupby("code")["close"]
            .rolling(window=trend_window, min_periods=trend_window)
            .mean()
            .droplevel(0)
            .sort_index()
        )
        above_sma = (data["close"] > sma).astype(float)
        above_sma = pd.Series(above_sma, index=data.index)

        # --- Signal 2: Per-stock 20d return ---
        ret_20d = (
            data.groupby("code")["close"]
            .pct_change(trend_window)
        )

    # --- Aggregate per date ---
    trend_consensus = pd.Series(np.nan, index=dates, dtype=float)
    median_return = pd.Series(np.nan, index=dates, dtype=float)

    for d in dates:
        mask = data["date"] == d
        # Breadth: fraction of stocks above their SMA (0 to 1)
        # Convert to directional: >0.5 = bullish, <0.5 = bearish
        breadth = above_sma[mask].mean()
        trend_consensus[d] = breadth - 0.5  # center at 0: positive = up, negative = down
        median_return[d] = ret_20d[mask].median()

    # --- Signal 3: Realized volatility (cross-sectional std of daily returns) ---
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", category=RuntimeWarning, message="Mean of empty slice",
        )
        daily_ret = data.groupby("code")["close"].pct_change()
    realized_vol = pd.Series(np.nan, index=dates, dtype=float)

    for d in dates:
        mask = data["date"] == d
        realized_vol[d] = daily_ret[mask].std()

    # --- Smooth signals before classification (EMA) ---
    if ema_span > 1:
        trend_consensus = trend_consensus.ewm(span=ema_span, min_periods=1).mean()
        median_return = median_return.ewm(span=ema_span, min_periods=1).mean()
        realized_vol = realized_vol.ewm(span=ema_span, min_periods=1).mean()

    # --- Adaptive volatility thresholds (rolling percentile) ---
    vol_high = realized_vol.rolling(
        window=vol_lookback, min_periods=20,
    ).quantile(vol_high_pct / 100.0)
    vol_low = realized_vol.rolling(
        window=vol_lookback, min_periods=20,
    ).quantile(vol_low_pct / 100.0)

    # Fill NaN thresholds with overall percentiles (warmup period)
    overall_high = realized_vol.quantile(vol_high_pct / 100.0)
    overall_low = realized_vol.quantile(vol_low_pct / 100.0)
    vol_high = vol_high.fillna(overall_high)
    vol_low = vol_low.fillna(overall_low)

    # --- Classify regime ---
    regime = pd.Series("range", index=dates, dtype=str)

    is_high_vol = realized_vol > vol_high
    is_low_vol = realized_vol < vol_low

    # Use return direction as tiebreaker, trend_consensus for strength
    is_up = (trend_consensus > 0) | (median_return > 0)
    is_down = (trend_consensus < 0) | (median_return < 0)

    is_strong = trend_consensus.abs() > trend_strong_thresh
    is_moderate = trend_consensus.abs() > trend_weak_thresh

    # High vol + strong consensus → trend
    regime[is_high_vol & is_strong & is_up] = "trend_up"
    regime[is_high_vol & is_strong & is_down] = "trend_down"
    # High vol + no consensus → volatile
    regime[is_high_vol & ~is_strong] = "volatile"
    # Normal vol + moderate consensus → trend
    regime[~is_high_vol & ~is_low_vol & is_moderate & is_up] = "trend_up"
    regime[~is_high_vol & ~is_low_vol & is_moderate & is_down] = "trend_down"
    # Low vol → range (already default)

    # --- Enforce minimum persistence ---
    if min_persistence > 1:
        regime = _enforce_persistence(regime, min_days=min_persistence)

    return regime
