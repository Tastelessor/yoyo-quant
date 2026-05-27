"""Industry momentum scoring and tilt allocation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolio.industry_cap import apply_industry_cap


def compute_industry_momentum(
    data: pd.DataFrame,
    lookback: int = 20,
) -> pd.DataFrame:
    """Compute per-industry momentum as average stock return over lookback.

    Uses T-lookback to T-1 returns (no lookahead). Each industry's
    momentum is the equal-weighted average of its constituent stocks'
    rolling returns.

    Parameters
    ----------
    data : DataFrame
        Must contain: date, code, close, industry.
    lookback : int
        Rolling window in trading days. Default 20.

    Returns
    -------
    DataFrame
        Columns: date, industry, momentum.
    """
    df = data[["date", "code", "close", "industry"]].copy()
    df = df.sort_values(["code", "date"])

    # Per-stock daily return (T-1 to T)
    df["ret"] = df.groupby("code")["close"].pct_change()

    # Rolling average return over lookback (per stock)
    df["rolling_ret"] = (
        df.groupby("code")["ret"]
        .rolling(window=lookback, min_periods=lookback)
        .mean()
        .reset_index(level=0, drop=True)
    )

    # Average across stocks within each industry per date
    industry_momentum = (
        df.groupby(["date", "industry"])["rolling_ret"]
        .mean()
        .reset_index()
        .rename(columns={"rolling_ret": "momentum"})
    )

    return industry_momentum


def apply_industry_tilt(
    positions: pd.DataFrame,
    industry_map: dict[str, str],
    momentum_scores: pd.DataFrame,
    tilt_strength: float = 0.5,
    max_industry_weight: float = 0.30,
) -> pd.DataFrame:
    """Tilt industry weights based on momentum, then apply cap.

    High-momentum industries get higher weight; low-momentum get lower.
    The tilt is applied by scaling each stock's weight by a factor
    derived from its industry's momentum percentile rank.

    Parameters
    ----------
    positions : DataFrame
        Columns: date, code, weight, shares.
    industry_map : dict
        Mapping from stock code to industry name.
    momentum_scores : DataFrame
        Output of compute_industry_momentum. Columns: date, industry, momentum.
    tilt_strength : float
        How aggressively to tilt. 0 = no tilt, 1 = full tilt.
        Default 0.5.
    max_industry_weight : float
        Maximum weight per industry after tilt. Default 0.30.

    Returns
    -------
    DataFrame
        Positions with tilted and capped weights.
    """
    if positions.empty or tilt_strength == 0.0:
        return apply_industry_cap(positions, industry_map, max_industry_weight)

    result = positions.copy()
    result["industry"] = result["code"].map(
        lambda c: industry_map.get(c, "其他")
    )

    # Process each date
    for date, group in result.groupby("date"):
        idx = group.index
        date_momentum = momentum_scores[momentum_scores["date"] == date]
        if date_momentum.empty:
            continue

        # Compute percentile rank of momentum across industries
        mom_values = date_momentum.set_index("industry")["momentum"]
        if mom_values.isna().all():
            continue
        ranks = mom_values.rank(pct=True)  # 0 to 1

        # Apply tilt to each stock's weight
        weights = group["weight"].values.copy()
        industries = group["industry"].values
        for i, ind in enumerate(industries):
            if ind in ranks.index and not np.isnan(ranks[ind]):
                # Scale factor: 1 + tilt * (rank - 0.5) * 2
                # rank=1 -> factor = 1 + tilt
                # rank=0 -> factor = 1 - tilt
                factor = 1.0 + tilt_strength * (ranks[ind] - 0.5) * 2
                weights[i] *= factor

        # Normalize
        weight_sum = weights.sum()
        if weight_sum > 0:
            weights = weights / weight_sum

        result.loc[idx, "weight"] = weights

    # Recalculate shares proportionally
    weight_ratio = result["weight"] / positions["weight"]
    weight_ratio = weight_ratio.fillna(0.0)
    result["shares"] = np.floor(
        positions["shares"] * weight_ratio / 100
    ).astype(int) * 100

    result = result.drop(columns=["industry"])

    # Apply industry cap
    return apply_industry_cap(result, industry_map, max_industry_weight)
