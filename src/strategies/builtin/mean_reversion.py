import pandas as pd

from src.strategies.base import Strategy
from src.strategies.registry import register_strategy


@register_strategy("mean_reversion")
class MeanReversionStrategy(Strategy):
    """Mean reversion strategy (Bollinger Band style)."""

    name = "mean_reversion"

    def __init__(self, window: int = 20, num_std: float = 2.0):
        self.window = window
        self.num_std = num_std

    def generate_signal(self, data, factors=None):
        return mean_reversion_signal(data, window=self.window, num_std=self.num_std)


def mean_reversion_signal(
    df: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """均值回归策略信号。

    规则：
    - 价格 < MA - num_std*σ → 买入 (signal=1)
    - 价格 > MA + num_std*σ → 卖出 (signal=-1)
    - 其他 → 持有 (signal=0)
    - confidence = |price - MA| / (num_std * σ)，上限 1.0

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close 列。
    window : int
        移动平均窗口，默认 20。
    num_std : float
        标准差倍数，默认 2.0。

    Returns
    -------
    DataFrame
        包含 date, code, signal, confidence 列。
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    ma = df.groupby("code")["close"].transform(
        lambda s: s.rolling(window=window, min_periods=window).mean()
    )
    std = df.groupby("code")["close"].transform(
        lambda s: s.rolling(window=window, min_periods=window).std()
    )

    upper = ma + num_std * std
    lower = ma - num_std * std

    deviation = (df["close"] - ma) / (num_std * std)
    deviation = deviation.fillna(0.0)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal[df["close"] < lower] = 1
    signal[df["close"] > upper] = -1

    confidence = deviation.abs().clip(upper=1.0)

    # 窗口不足时 signal 和 confidence 置零
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
