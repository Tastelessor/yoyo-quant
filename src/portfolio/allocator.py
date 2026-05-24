"""Portfolio allocation strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd


def equal_weight(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    capital: float = 1_000_000,
    exposure: pd.Series | None = None,
) -> pd.DataFrame:
    """Equal-weight allocation among buy signals.

    For each date, allocate capital equally among stocks with signal=1.
    Shares are rounded down to nearest 100 (A 股手数).

    This is a per-date target calculator: each date is allocated the
    full capital independently. It does not track consumed capital
    across dates. For capital-aware execution, pipe through backtest.

    Parameters
    ----------
    signals : DataFrame
        Signal data with columns: date, code, signal, confidence.
    prices : DataFrame
        Price data with columns: date, code, close.
    capital : float
        Total capital to allocate per date.
    exposure : Series | None
        Optional exposure fraction per date (indexed by date).
        When provided, per-date capital = capital * exposure[date].
        Dates not in the Series default to 1.0.

    Returns
    -------
    DataFrame
        Position data with columns: date, code, weight, shares.
    """
    if signals.empty or capital <= 0:
        return pd.DataFrame(columns=["date", "code", "weight", "shares"])

    buy = signals[signals["signal"] == 1].copy()
    if buy.empty:
        return pd.DataFrame(columns=["date", "code", "weight", "shares"])

    merged = buy.merge(
        prices[["date", "code", "close"]], on=["date", "code"], how="left"
    )

    result = merged[["date", "code"]].copy()
    # Equal weight per date
    count_per_date = merged.groupby("date")["code"].transform("count")
    result["weight"] = 1.0 / count_per_date

    # Apply exposure scaling per date
    if exposure is not None:
        date_capital = merged["date"].map(
            lambda d: capital * exposure.get(d, 1.0)
        )
    else:
        date_capital = pd.Series(capital, index=merged.index)

    # Share calculation: allocate capital * weight, round down to 100
    alloc = date_capital * result["weight"]
    result["shares"] = np.floor(alloc / merged["close"] / 100).astype(int) * 100
    # Where close is NaN, shares = 0
    result.loc[merged["close"].isna(), "shares"] = 0
    result.loc[merged["close"].isna(), "weight"] = 0.0

    return result.reset_index(drop=True)
