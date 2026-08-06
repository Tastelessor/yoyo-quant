"""Factor industry neutralization: strip industry exposure from factor values."""

from __future__ import annotations

import pandas as pd


def demean_by_industry(
    factor_df: pd.DataFrame,
    industry_map: dict[str, str],
    factor_cols: list[str],
    unknown_label: str = "__unknown__",
    min_peers: int = 3,
) -> pd.DataFrame:
    """Cross-sectional industry demeaning (vectorized).

    For each (date, industry), subtract the industry mean from every stock
    in that industry.  Stocks not in *industry_map* are grouped under
    *unknown_label*.  Industries with fewer than *min_peers* stocks on a
    given date are dynamically degraded to *unknown_label* to prevent
    single-stock industries from having their factor values collapsed to 0
    (which would cause rank deadlock downstream).

    Parameters
    ----------
    factor_df : DataFrame
        Must contain ``date``, ``code``, and all columns in *factor_cols*.
    industry_map : dict
        Mapping from stock code to industry name.
    factor_cols : list[str]
        Column names to neutralize.
    unknown_label : str
        Industry label for stocks not in the map.
    min_peers : int
        Minimum number of stocks in an industry-date group.  Groups smaller
        than this are merged into *unknown_label*.

    Returns
    -------
    DataFrame
        Copy of *factor_df* with *factor_cols* replaced by demeaned values.
        ``date``, ``code``, and other columns are unchanged.

    Raises
    ------
    ValueError
        If *min_peers* < 1.
    """
    if min_peers < 1:
        raise ValueError(f"min_peers must be >= 1, got {min_peers}")

    result = factor_df.copy()
    result["_industry"] = result["code"].map(
        lambda c: industry_map.get(c, unknown_label)
    )

    # Dynamic degradation: merge small industries into unknown
    if min_peers > 1:
        counts = result.groupby(["date", "_industry"])["code"].transform("count")
        result.loc[counts < min_peers, "_industry"] = unknown_label

    # Vectorized: subtract group mean for all factor columns at once
    grouped_means = result.groupby(["date", "_industry"])[factor_cols].transform("mean")
    result[factor_cols] = result[factor_cols] - grouped_means

    return result.drop(columns=["_industry"])


def neutralize_factors(
    factor_df: pd.DataFrame,
    industry_map: dict[str, str],
    factor_cols: list[str],
    method: str = "demean",
    **kwargs,
) -> pd.DataFrame:
    """Neutralize industry exposure from factor values.

    Parameters
    ----------
    factor_df : DataFrame
        Must contain ``date``, ``code``, and all columns in *factor_cols*.
    industry_map : dict
        Mapping from stock code to industry name.
    factor_cols : list[str]
        Column names to neutralize.
    method : str
        Neutralization method.  Currently only ``"demean"`` is supported.
    **kwargs
        Forwarded to the underlying method (e.g. ``min_peers``).

    Returns
    -------
    DataFrame
        Neutralized factor DataFrame.

    Raises
    ------
    ValueError
        If *method* is not recognized.
    """
    if method == "demean":
        return demean_by_industry(factor_df, industry_map, factor_cols, **kwargs)
    raise ValueError(f"Unknown neutralization method: {method!r}")
