"""Market regime detector based on index MA crossovers.

Computes a daily exposure fraction based on the position of price
relative to two moving averages (short and long):

- price > MA_long AND MA_short > MA_long -> bullish (1.0)
- price > MA_long AND MA_short < MA_long -> neutral (0.6)
- price < MA_long AND MA_short > MA_long -> cautious (0.4)
- price < MA_long AND MA_short < MA_long -> bearish (0.2)

This is NOT a Strategy subclass — it does not produce per-stock signals.
It produces a single exposure fraction per date for portfolio-level scaling.
"""

from __future__ import annotations

import pandas as pd

DEFAULT_EXPOSURE = {1.0: 1.0, 0.6: 0.6, 0.4: 0.4, 0.2: 0.2}


def market_regime_exposure(
    close: pd.Series,
    ma_short: int = 50,
    ma_long: int = 200,
    exposure: dict[float, float] | None = None,
) -> pd.Series:
    """Compute daily exposure fraction from index close prices.

    Parameters
    ----------
    close : Series
        Index close prices, indexed by date (datetime64).
    ma_short : int
        Short-term moving average window.
    ma_long : int
        Long-term moving average window.
    exposure : dict | None
        Mapping from raw regime value to scaled exposure.
        Default maps each regime to itself.

    Returns
    -------
    Series
        Exposure fraction per date, values in [0, 1].
    """
    if exposure is None:
        exposure = DEFAULT_EXPOSURE

    close = close.sort_index()

    ma_s = close.rolling(window=ma_short, min_periods=ma_short).mean()
    ma_l = close.rolling(window=ma_long, min_periods=ma_long).mean()

    raw = pd.Series(0.6, index=close.index, dtype=float)

    bullish = (close > ma_l) & (ma_s > ma_l)
    neutral = (close > ma_l) & (ma_s <= ma_l)
    cautious = (close <= ma_l) & (ma_s > ma_l)
    bearish = (close <= ma_l) & (ma_s <= ma_l)

    # Only assign where both MAs are valid (not NaN)
    valid = ma_s.notna() & ma_l.notna()
    raw[valid & bullish] = 1.0
    raw[valid & neutral] = 0.6
    raw[valid & cautious] = 0.4
    raw[valid & bearish] = 0.2

    # Map through exposure config
    result = raw.map(exposure)

    return result


class MarketRegime:
    """Market regime detector using index MA crossovers.

    This is NOT a Strategy subclass. It computes a portfolio-level
    exposure fraction, not per-stock signals.

    Parameters
    ----------
    ma_short : int
        Short-term MA window (default 50).
    ma_long : int
        Long-term MA window (default 200).
    exposure : dict | None
        Mapping from raw regime to exposure fraction.
    """

    def __init__(
        self,
        ma_short: int = 50,
        ma_long: int = 200,
        exposure: dict[float, float] | None = None,
    ):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.exposure = exposure or DEFAULT_EXPOSURE

    def compute_exposure(self, index_data: pd.DataFrame) -> pd.Series:
        """Compute exposure fraction from index data.

        Parameters
        ----------
        index_data : DataFrame
            Must contain 'date' and 'close' columns.

        Returns
        -------
        Series
            Exposure fraction per date, indexed by date.
        """
        if "close" not in index_data.columns:
            raise ValueError("index_data must contain 'close' column")

        df = index_data.sort_values("date").copy()
        close = df.set_index("date")["close"]

        return market_regime_exposure(
            close,
            ma_short=self.ma_short,
            ma_long=self.ma_long,
            exposure=self.exposure,
        )
