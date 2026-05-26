"""Stock selector: factor quality evaluation and dynamic stock pool filtering.

Two primary use cases:

1. **Factor audit** — ``evaluate_factors`` runs on a quarterly cadence.
   Scores every factor on coverage, rank stability, and cross-sectional
   dispersion. Returns a DataFrame marking which factors are "active".

2. **Stock selection** — ``select_tradable`` runs per trading day.
   Uses only active factors to score stocks. Stocks passing the most
   factor-quality checks are selected for the day's universe.

Underlying metrics (strategy-independent, no return prediction):
- **Coverage** — is the factor value available for this stock?
- **Rank stability** — is the stock's cross-sectional rank consistent over time?
- **Dispersion** — does the factor distinguish between stocks on this date?
"""

from __future__ import annotations

import pandas as pd

from src.factors.operators import corr, delay, rank


def factor_coverage(
    factor_df: pd.DataFrame, factor_col: str, lookback: int,
) -> pd.Series:
    """Fraction of non-NaN *factor_col* values per stock over *lookback*.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and *factor_col*.
    factor_col : str
        Column name of the factor to check.
    lookback : int
        Rolling window for coverage computation.

    Returns
    -------
    Series
        Values in [0, 1], same index as *factor_df*.
        First *lookback* - 1 rows per stock are NaN (warmup).
    """
    valid = factor_df[factor_col].notna().astype(float)
    coverage = (
        valid.groupby(factor_df["code"])
        .rolling(window=lookback, min_periods=lookback)
        .mean()
        .droplevel(0)
        .sort_index()
    )
    return pd.Series(coverage, index=factor_df.index).astype(float)


def rank_stability(
    factor_df: pd.DataFrame,
    factor_col: str,
    lookback: int,
    lag: int = 5,
) -> pd.Series:
    """Rolling rank autocorrelation per stock.

    For each stock, computes the correlation between today's cross-sectional
    rank and the rank *lag* days ago, over a rolling *lookback* window.

    High stability → stock's factor rank is persistent (useful signal).
    Low stability → rank bounces randomly (noise).

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and *factor_col*.
    factor_col : str
        Column name of the factor.
    lookback : int
        Rolling window for correlation.
    lag : int
        Lag between current rank and delayed rank (default 5).

    Returns
    -------
    Series
        Values in [-1, 1], same index as *factor_df*.
        First *lookback* + *lag* - 1 rows per stock are NaN.
    """
    import numpy as np

    df = factor_df[["date", "code"]].copy()
    df["_rank"] = rank(factor_df, factor_col)
    df["_rank_lag"] = delay(df, "_rank", lag)
    raw = corr(df, "_rank", "_rank_lag", lookback)
    # Replace inf/-inf (division by zero in rolling window) with NaN
    raw = raw.replace([np.inf, -np.inf], np.nan)
    return raw.clip(lower=-1.0, upper=1.0)


def factor_dispersion(
    factor_df: pd.DataFrame, factor_col: str,
) -> pd.Series:
    """Cross-sectional coefficient of variation per date.

    Computes std(raw values) / mean(|raw values|) across all stocks on each
    date. The result is a dimensionless measure of factor differentiation:

    - Near 0 → all stocks have nearly identical factor values (useless).
    - >> 0 → factor spreads stocks apart meaningfully (potentially useful).

    Uses raw values (not ranks) because rank-based dispersion is insensitive
    to the magnitude of differences.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and *factor_col*.
    factor_col : str
        Column name of the factor.

    Returns
    -------
    Series
        Indexed by unique dates (sorted), values >= 0.
        NaN on dates where all values are zero.
    """
    per_date = factor_df.groupby("date")[factor_col]
    raw_std = per_date.std()
    mean_abs = per_date.apply(lambda x: x.abs().mean())
    mean_abs = mean_abs.replace(0.0, float("nan"))
    return raw_std / mean_abs


def evaluate_factors(
    factor_df: pd.DataFrame,
    factor_names: list[str],
    lookback: int = 60,
    lag: int = 5,
    min_coverage: float = 0.8,
    min_stability: float = 0.3,
    min_dispersion: float = 0.10,
    date_filter: pd.DatetimeIndex | pd.Index | None = None,
) -> pd.DataFrame:
    """Audit factor quality across all stocks and dates.

    Computes per-factor aggregate metrics and marks each factor as active
    or inactive based on thresholds. Run quarterly (or at any cadence) to
    determine which factors should participate in stock selection.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and all columns in *factor_names*.
    factor_names : list[str]
        Factor columns to evaluate.
    lookback : int
        Rolling window for coverage and stability. Default 60.
    lag : int
        Lag for rank autocorrelation. Default 5.
    min_coverage : float
        Minimum fraction of non-NaN values. Default 0.8.
    min_stability : float
        Minimum rank autocorrelation. Default 0.3.
    min_dispersion : float
        Minimum cross-sectional CV. Default 0.10.
    date_filter : DatetimeIndex or None
        Optional set of dates to restrict the audit to. When provided,
        only rows with ``date`` in *date_filter* are included.
        Use with ``evaluate_factors_by_regime`` to split audit by regime.

    Returns
    -------
    DataFrame
        Columns: factor, coverage, stability, dispersion, active.
        One row per factor in *factor_names*.
    """
    if not factor_names:
        return pd.DataFrame(
            columns=["factor", "coverage", "stability", "dispersion", "active"],
        )

    if date_filter is not None:
        factor_df = factor_df[factor_df["date"].isin(date_filter)]
        if factor_df.empty:
            return pd.DataFrame(
                columns=["factor", "coverage", "stability", "dispersion", "active"],
            )

    rows = []
    for fcol in factor_names:
        cov = factor_coverage(factor_df, fcol, lookback)
        stab = rank_stability(factor_df, fcol, lookback, lag)
        disp = factor_dispersion(factor_df, fcol)

        mean_cov = float(cov.dropna().mean())
        med_stab = float(stab.dropna().median())
        med_disp = float(disp.dropna().median())

        active = bool(
            mean_cov >= min_coverage
            and med_stab >= min_stability
            and med_disp >= min_dispersion
        )

        rows.append({
            "factor": fcol,
            "coverage": mean_cov,
            "stability": med_stab,
            "dispersion": med_disp,
            "active": active,
        })

    return pd.DataFrame(rows)


def evaluate_factors_by_regime(
    factor_df: pd.DataFrame,
    factor_names: list[str],
    regime_series: pd.Series,
    lookback: int = 60,
    lag: int = 5,
    min_coverage: float = 0.8,
    min_stability: float = 0.3,
    min_dispersion: float = 0.10,
) -> dict[str, pd.DataFrame]:
    """Run factor audit separately for each regime.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and all columns in *factor_names*.
    factor_names : list[str]
        Factor columns to evaluate.
    regime_series : Series
        Index: dates. Values: regime labels. Output of ``detect_regime``.
    lookback, lag, min_coverage, min_stability, min_dispersion :
        Passed through to ``evaluate_factors``.

    Returns
    -------
    dict
        Mapping from regime label to audit DataFrame.
        Keys are all unique regime labels found in *regime_series*.
    """
    result = {}
    for regime_label in sorted(regime_series.unique()):
        regime_dates = regime_series[regime_series == regime_label]
        result[regime_label] = evaluate_factors(
            factor_df,
            factor_names,
            lookback=lookback,
            lag=lag,
            min_coverage=min_coverage,
            min_stability=min_stability,
            min_dispersion=min_dispersion,
            date_filter=regime_dates.index,
        )
    return result


def select_tradable(
    factor_df: pd.DataFrame,
    factor_names: list[str],
    lookback: int = 60,
    lag: int = 5,
    min_coverage: float = 0.8,
    min_stability: float = 0.3,
    min_dispersion: float = 0.10,
    min_stocks: int = 5,
    top_n: int | None = None,
) -> dict[pd.Timestamp, list[str]]:
    """Select tradable stocks for each date by filtering on factor quality.

    For each factor in *factor_names*, every stock-date is scored on three
    dimensions. A stock passes a factor when all three thresholds are met.
    Stocks passing the most factors are selected each date, capped at
    *top_n* stocks.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain date, code, and all columns in *factor_names*.
    factor_names : list[str]
        Factor columns to use for quality filtering. Must be non-empty
        for any stocks to pass.
    lookback : int
        Rolling window for coverage and stability. Default 60.
    lag : int
        Lag for rank autocorrelation. Default 5.
    min_coverage : float
        Minimum fraction of non-NaN values. Default 0.8.
    min_stability : float
        Minimum rank autocorrelation. Default 0.3.
    min_dispersion : float
        Minimum cross-sectional std of ranks. Default 0.10.
    min_stocks : int
        Minimum number of stocks that must pass per date. If fewer,
        that date returns an empty list. Default 5.
    top_n : int or None
        Maximum number of stocks to select per date. None = no limit.
        Default None.

    Returns
    -------
    dict
        Mapping from date to list of selected stock codes.
        Dates with fewer than *min_stocks* passing are excluded.
    """
    if not factor_names or factor_df.empty:
        return {}

    dates = sorted(factor_df["date"].unique())

    # Accumulate pass count per row
    pass_counts = pd.Series(0.0, index=factor_df.index, dtype=float)

    for fcol in factor_names:
        cov = factor_coverage(factor_df, fcol, lookback)
        stab = rank_stability(factor_df, fcol, lookback, lag)
        disp = factor_dispersion(factor_df, fcol)

        # Map per-date dispersion to each row
        disp_per_row = factor_df["date"].map(disp).values

        passes = (
            (cov >= min_coverage)
            & (stab >= min_stability)
            & (disp_per_row >= min_dispersion)
        )
        pass_counts += passes.astype(float)

    # For each date, select codes passing the most factors
    result: dict[pd.Timestamp, list[str]] = {}
    for d in dates:
        day_mask = factor_df["date"] == d
        day_counts = pass_counts[day_mask]
        day_codes = factor_df.loc[day_mask, "code"]

        passing = day_counts[day_counts > 0]
        if len(passing) < min_stocks:
            continue

        # Sort by pass_count descending
        passing_sorted = passing.sort_values(ascending=False)
        selected = day_codes.loc[passing_sorted.index].tolist()
        if top_n is not None and len(selected) > top_n:
            selected = selected[:top_n]
        result[d] = selected

    return result
