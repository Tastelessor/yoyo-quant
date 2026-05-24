"""Forward-looking market regime detection.

Classifies each date into a market regime based on cross-sectional signals:
- "trend_up": market trending up (most stocks rising, volatility expanding)
- "trend_down": market trending down
- "range": no clear direction, low volatility
- "volatile": high uncertainty, high volatility without clear direction

Uses 3 signals:
1. Volatility level: ATR ratio (current / baseline) — is vol high or low?
2. Momentum direction: cross-sectional mean of sign(20d return) — up or down?
3. Momentum strength: |momentum direction| — how strong is the consensus?

Regime classification:
| Vol Level | Mom Direction | Mom Strength | → Regime |
|-----------|--------------|--------------|----------|
| High | Up | Strong | trend_up |
| High | Down | Strong | trend_down |
| High | Any | Weak | volatile |
| Low | Any | Any | range |
| Normal | Up | Strong | trend_up |
| Normal | Down | Strong | trend_down |
| Normal | Any | Weak | range |
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.factors.momentum import calc_momentum_20d_return
from src.factors.volatility_gtja import calc_atr_12d


def detect_regime(
    data: pd.DataFrame,
    vol_baseline_window: int = 20,
    mom_window: int = 20,
    vol_high_thresh: float = 1.3,
    vol_low_thresh: float = 0.8,
    mom_strong_thresh: float = 0.25,
) -> pd.Series:
    """Detect market regime per date.

    Parameters
    ----------
    data : DataFrame
        Must contain date, code, open, high, low, close, volume.
    vol_baseline_window : int
        Window for ATR baseline computation.
    mom_window : int
        Window for momentum computation.
    vol_high_thresh : float
        ATR ratio above this → high volatility.
    vol_low_thresh : float
        ATR ratio below this → low volatility.
    mom_strong_thresh : float
        |momentum direction| above this → strong consensus.

    Returns
    -------
    Series
        Index: unique dates, sorted.
        Values: "trend_up", "trend_down", "range", or "volatile".
    """
    data = data.sort_values(["code", "date"]).reset_index(drop=True)

    # Signal 1: Volatility level (ATR ratio)
    atr = calc_atr_12d(data)
    atr_df = pd.concat([data[["code", "date"]], atr.rename("atr")], axis=1)
    atr_baseline = (
        atr_df.groupby("code")["atr"]
        .rolling(window=vol_baseline_window, min_periods=10)
        .mean()
        .droplevel(0)
        .sort_index()
    )
    vol_ratio = (atr / atr_baseline).replace([np.inf, -np.inf], np.nan)

    # Signal 2: Momentum direction + strength
    mom = calc_momentum_20d_return(data)
    mom_sign = np.sign(mom)

    # Assemble per-date cross-sectional signals
    dates = sorted(data["date"].unique())
    vol_level = pd.Series(index=dates, dtype=float)
    mom_dir = pd.Series(index=dates, dtype=float)

    for d in dates:
        mask = data["date"] == d
        vol_level[d] = vol_ratio[mask].median()
        mom_dir[d] = mom_sign[mask].mean()

    mom_strength = mom_dir.abs()

    # Classify regime
    regime = pd.Series("range", index=dates, dtype=str)

    is_high_vol = vol_level > vol_high_thresh
    is_low_vol = vol_level < vol_low_thresh
    is_strong = mom_strength > mom_strong_thresh
    is_up = mom_dir > 0
    is_down = mom_dir < 0

    # High vol + strong direction → trend
    regime[is_high_vol & is_strong & is_up] = "trend_up"
    regime[is_high_vol & is_strong & is_down] = "trend_down"
    # High vol + weak direction → volatile
    regime[is_high_vol & ~is_strong] = "volatile"
    # Normal vol + strong direction → trend
    regime[~is_high_vol & ~is_low_vol & is_strong & is_up] = "trend_up"
    regime[~is_high_vol & ~is_low_vol & is_strong & is_down] = "trend_down"

    return regime
