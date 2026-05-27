"""Industry cap allocation: limit per-industry portfolio weight."""

from __future__ import annotations

import numpy as np
import pandas as pd


def apply_industry_cap(
    positions: pd.DataFrame,
    industry_map: dict[str, str],
    max_industry_weight: float = 0.30,
) -> pd.DataFrame:
    """Cap per-industry weight and redistribute excess.

    For each date, industries exceeding *max_industry_weight* are
    compressed to the cap. The freed weight is redistributed
    proportionally to industries under the cap.

    Parameters
    ----------
    positions : DataFrame
        Columns: date, code, weight, shares.
    industry_map : dict
        Mapping from stock code to industry name.
        Missing codes are assigned to "其他".
    max_industry_weight : float
        Maximum weight per industry. Default 0.30 (30%).

    Returns
    -------
    DataFrame
        Positions with adjusted weights and shares.
    """
    if positions.empty:
        return positions.copy()

    result = positions.copy()
    result["industry"] = result["code"].map(
        lambda c: industry_map.get(c, "其他")
    )

    # Process each date independently
    for date, group in result.groupby("date"):
        idx = group.index
        weights = group["weight"].values.copy()
        industries = group["industry"].values

        # Compute per-industry total weight
        unique_industries = set(industries)
        industry_totals = {}
        for ind in unique_industries:
            industry_totals[ind] = weights[industries == ind].sum()

        # Check if any industry exceeds cap
        over_cap = {ind: total for ind, total in industry_totals.items()
                    if total > max_industry_weight + 1e-10}
        if not over_cap:
            continue  # nothing to do

        # Redistribute: compress over-cap, distribute excess to under-cap
        excess = 0.0
        under_cap_total = 0.0
        for ind, total in industry_totals.items():
            if total > max_industry_weight + 1e-10:
                excess += total - max_industry_weight
            else:
                under_cap_total += total

        # Apply caps and redistribute
        new_weights = weights.copy()
        for i, ind in enumerate(industries):
            ind_total = industry_totals[ind]
            if ind_total > max_industry_weight + 1e-10:
                # Scale this stock's weight proportionally within the industry
                new_weights[i] = weights[i] * (max_industry_weight / ind_total)
            elif under_cap_total > 0:
                # Add proportional share of excess
                new_weights[i] = weights[i] + excess * (weights[i] / under_cap_total)

        # Normalize to ensure weights sum to 1.0 (unless all over cap)
        total_over = sum(1 for t in industry_totals.values()
                         if t > max_industry_weight + 1e-10)
        if total_over < len(industry_totals):
            # Some industries are under cap, normalize
            weight_sum = new_weights.sum()
            if weight_sum > 0:
                new_weights = new_weights / weight_sum

        result.loc[idx, "weight"] = new_weights

    # Recalculate shares based on new weights
    # We need prices to recalculate, but positions don't have prices.
    # Scale shares proportionally to weight change.
    weight_ratio = result["weight"] / positions["weight"]
    weight_ratio = weight_ratio.fillna(0.0)
    result["shares"] = np.floor(
        positions["shares"] * weight_ratio / 100
    ).astype(int) * 100

    result = result.drop(columns=["industry"])
    return result.reset_index(drop=True)
