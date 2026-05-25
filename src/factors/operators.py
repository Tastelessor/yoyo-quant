"""Reusable GTJA base operators.

All operators work on code-grouped DataFrames and return
pd.Series aligned to the input index. NaN where insufficient data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def delay(df: pd.DataFrame, col: str, n: int) -> pd.Series:
    """Delay (lag) a column by n periods within each stock group.

    delay(x, n) = value of x, n periods ago.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name to delay.
    n : int
        Number of periods to lag. Must be >= 0.

    Returns
    -------
    Series
        Delayed values. First n rows per stock are NaN.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    return df.groupby("code")[col].shift(n)


def delta(df: pd.DataFrame, col: str, n: int) -> pd.Series:
    """Change over n periods: x - delay(x, n).

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    n : int
        Lookback period.

    Returns
    -------
    Series
        Difference. First n rows per stock are NaN.
    """
    return df[col] - delay(df, col, n)


def rolling_mean(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Rolling mean within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling mean. First (window-1) rows per stock are NaN.
    """
    return (
        df.groupby("code")[col]
        .rolling(window=window, min_periods=window)
        .mean()
        .droplevel(0)
        .sort_index()
    )


def rolling_std(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Rolling standard deviation within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling std (ddof=1). First (window-1) rows per stock are NaN.
    """
    return (
        df.groupby("code")[col]
        .rolling(window=window, min_periods=window)
        .std()
        .droplevel(0)
        .sort_index()
    )


def rolling_sum(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Rolling sum within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling sum. First (window-1) rows per stock are NaN.
    """
    return (
        df.groupby("code")[col]
        .rolling(window=window, min_periods=window)
        .sum()
        .droplevel(0)
        .sort_index()
    )


def sma(df: pd.DataFrame, col: str, n: int, m: int) -> pd.Series:
    """Exponential moving average: sma(x, n, m) with alpha = m/n.

    GTJA notation: sma(x, n, m) = EMA with alpha = m/n.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    n : int
        Window size (denominator for alpha).
    m : int
        Weight (numerator for alpha). alpha = m/n.

    Returns
    -------
    Series
        EMA values. NaN where insufficient data.
    """
    alpha = m / n
    return (
        df.groupby("code")[col]
        .ewm(alpha=alpha, min_periods=n)
        .mean()
        .droplevel(0)
        .sort_index()
    )


def corr(
    df: pd.DataFrame, col_x: str, col_y: str, window: int,
) -> pd.Series:
    """Rolling correlation between two columns within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and both named columns.
    col_x : str
        First column name.
    col_y : str
        Second column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling correlation. First (window-1) rows per stock are NaN.
    """
    results = []
    for _, group in df.groupby("code"):
        corr_vals = (
            group[col_x]
            .rolling(window=window, min_periods=window)
            .corr(group[col_y])
        )
        results.append(corr_vals)
    return pd.concat(results).sort_index()


def rank(df: pd.DataFrame, col: str) -> pd.Series:
    """Cross-sectional percentile rank within each date.

    Computes rank as percentile (0 to 1) across all stocks on the same
    date. Unlike other operators, this groups by ``date``, not ``code``.

    Parameters
    ----------
    df : DataFrame
        Must contain 'date' and the column named by `col`.
    col : str
        Column name to rank.

    Returns
    -------
    Series
        Percentile ranks [0, 1] per date. No NaN values (rank works
        with any group size >= 1).
    """
    return df.groupby("date")[col].rank(pct=True)


def ts_max(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Rolling maximum within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling max. First (window-1) rows per stock are NaN.
    """
    return (
        df.groupby("code")[col]
        .rolling(window=window, min_periods=window)
        .max()
        .droplevel(0)
        .sort_index()
    )


def ts_min(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """Rolling minimum within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and the column named by `col`.
    col : str
        Column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling min. First (window-1) rows per stock are NaN.
    """
    return (
        df.groupby("code")[col]
        .rolling(window=window, min_periods=window)
        .min()
        .droplevel(0)
        .sort_index()
    )


def rolling_cov(
    df: pd.DataFrame, col_x: str, col_y: str, window: int,
) -> pd.Series:
    """Rolling covariance between two columns within each stock group.

    Parameters
    ----------
    df : DataFrame
        Must contain 'code' and both named columns.
    col_x : str
        First column name.
    col_y : str
        Second column name.
    window : int
        Rolling window size.

    Returns
    -------
    Series
        Rolling covariance. First (window-1) rows per stock are NaN.
    """
    results = []
    for _, group in df.groupby("code"):
        cov_vals = (
            group[col_x]
            .rolling(window=window, min_periods=window)
            .cov(group[col_y])
        )
        results.append(cov_vals)
    return pd.concat(results).sort_index()
