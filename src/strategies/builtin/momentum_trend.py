"""动量突破 + 趋势过滤策略。

在 momentum_breakout 基础上增加均线趋势过滤：
- 买入：放量 + OBV 上升 + 价格 > MA（确认上升趋势）
- 卖出：放量 + OBV 下降 + 价格 < MA（确认下降趋势）
"""

from __future__ import annotations

import pandas as pd

from src.factors.registry import run_factor
from src.strategies.base import Strategy
from src.strategies.registry import register_strategy


@register_strategy("momentum_trend")
class MomentumTrendStrategy(Strategy):
    """Momentum breakout with MA trend filter."""

    name = "momentum_trend"

    def __init__(
        self,
        vol_window: int = 20,
        vol_threshold: float = 1.5,
        obv_window: int = 10,
        trend_window: int = 60,
    ):
        self.vol_window = vol_window
        self.vol_threshold = vol_threshold
        self.obv_window = obv_window
        self.trend_window = trend_window

    def generate_signal(self, data, factors=None):
        return momentum_trend_signal(
            data,
            vol_window=self.vol_window,
            vol_threshold=self.vol_threshold,
            obv_window=self.obv_window,
            trend_window=self.trend_window,
        )


def momentum_trend_signal(
    df: pd.DataFrame,
    vol_window: int = 20,
    vol_threshold: float = 1.5,
    obv_window: int = 10,
    trend_window: int = 60,
) -> pd.DataFrame:
    """动量突破 + 趋势过滤信号。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close, volume 列。
    vol_window : int
        成交量比率窗口。
    vol_threshold : float
        放量阈值（倍数）。
    obv_window : int
        OBV 均线窗口。
    trend_window : int
        趋势判断均线窗口。

    Returns
    -------
    DataFrame
        包含 date, code, signal, confidence 列。
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # 成交量比率
    vol_ratio = run_factor("calc_volume_ratio", df, window=vol_window).values

    # OBV 趋势
    obv = run_factor("calc_obv", df)
    obv_ma = (
        obv.groupby(df["code"])
        .rolling(window=obv_window, min_periods=1)
        .mean()
        .droplevel(0)
        .sort_index()
        .values
    )
    obv_rising = pd.Series(obv_ma, index=df.index) > obv

    # 趋势判断：价格 vs MA
    ma = df.groupby("code")["close"].transform(
        lambda s: s.rolling(window=trend_window, min_periods=trend_window).mean()
    )
    uptrend = df["close"] > ma
    downtrend = df["close"] < ma

    volume_spike = vol_ratio > vol_threshold

    signal = pd.Series(0, index=df.index, dtype=int)
    # 放量 + OBV 上升 + 上升趋势 → 买入
    signal[volume_spike & obv_rising & uptrend] = 1
    # 放量 + OBV 下降 + 下降趋势 → 卖出
    signal[volume_spike & ~obv_rising & downtrend] = -1

    confidence = pd.Series(vol_ratio / vol_threshold, index=df.index)
    confidence = confidence.clip(upper=1.0).fillna(0.0)

    # 趋势窗口不足时置零
    insufficient = ma.isna()
    signal[insufficient] = 0
    confidence[insufficient] = 0.0

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
