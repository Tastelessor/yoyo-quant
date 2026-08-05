"""Momentum breakout strategy using volume ratio and OBV trend."""

from __future__ import annotations

import pandas as pd

from src.factors.registry import run_factor
from src.strategies.base import Strategy
from src.strategies.registry import register_strategy


@register_strategy("momentum_breakout")
class MomentumBreakoutStrategy(Strategy):
    """Buy on volume spike + rising OBV, sell on volume spike + falling OBV."""

    name = "momentum_breakout"

    def __init__(
        self,
        vol_window: int = 20,
        vol_threshold: float = 1.5,
        obv_window: int = 10,
    ):
        self.vol_window = vol_window
        self.vol_threshold = vol_threshold
        self.obv_window = obv_window

    def generate_signal(self, data, factors=None):
        vol_ratio = run_factor("calc_volume_ratio", data, window=self.vol_window).values
        obv = run_factor("calc_obv", data)

        # OBV trend: rolling mean slope (positive = rising)
        obv_ma = (
            obv.groupby(data["code"])
            .rolling(window=self.obv_window, min_periods=1)
            .mean()
            .droplevel(0)
            .sort_index()
            .values
        )
        obv_rising = pd.Series(obv_ma, index=data.index) > obv

        volume_spike = vol_ratio > self.vol_threshold

        signal = pd.Series(0, index=data.index, dtype=int)
        # volume up + OBV falling → contrarian buy
        signal[volume_spike & ~obv_rising] = 1
        # volume up + OBV rising → sell (distribution)
        signal[volume_spike & obv_rising] = -1

        # Confidence based on how extreme the volume spike is
        confidence = pd.Series(vol_ratio / self.vol_threshold, index=data.index)
        confidence = confidence.clip(upper=1.0).fillna(0.0)

        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": signal,
                "confidence": confidence,
            }
        )
