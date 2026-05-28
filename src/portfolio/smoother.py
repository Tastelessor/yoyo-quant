"""Portfolio position smoothing via dead-zone state machine.

Converts positions to a wide-table matrix (date x code) for sequential
daily recursion, preventing Cartesian-product explosion and enabling
intra-period smoothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def smooth_positions(
    current_df: pd.DataFrame,
    last_period_last_day: pd.DataFrame | None,
    prices: pd.DataFrame,
    capital: float,
    exposure: pd.Series | None = None,
    dead_zone: float = 0.01,
) -> pd.DataFrame:
    """Smooth portfolio weights via daily dead-zone state machine.

    For each day, if a stock's weight change from the previous day is
    less than ``dead_zone``, the previous weight is held. This prevents
    price-driven drift from triggering unnecessary rebalancing.

    Parameters
    ----------
    current_df : DataFrame
        Positions from ``equal_weight()``: columns (date, code, weight, shares).
    last_period_last_day : DataFrame or None
        Previous period's last-day positions for cold-start. None on first period.
    prices : DataFrame
        Price data: columns (date, code, close).
    capital : float
        Total capital for shares recalculation.
    exposure : Series or None
        Per-date exposure fraction (indexed by date). None = 1.0 for all dates.
    dead_zone : float
        Absolute weight change threshold below which positions are held.
        Default 0.01 (1%).

    Returns
    -------
    DataFrame
        Smoothed positions: columns (date, code, weight, shares).
    """
    if current_df.empty:
        return current_df.copy()

    # ── Step 1: Cold-start init state ────────────────────────────────
    init_state: dict[str, float] = {}
    if last_period_last_day is not None and not last_period_last_day.empty:
        last_date = last_period_last_day["date"].max()
        last_day = last_period_last_day[last_period_last_day["date"] == last_date]
        init_state = dict(zip(last_day["code"], last_day["weight"]))

    # ── Step 2: Pivot to wide table + cross-period column stitching ──
    weight_matrix = current_df.pivot(
        index="date", columns="code", values="weight"
    ).fillna(0.0)

    # Reindex columns to include stocks from init_state that are not in
    # current period (prevents silent drop of held positions)
    if init_state:
        all_codes = weight_matrix.columns.union(init_state.keys())
        weight_matrix = weight_matrix.reindex(columns=all_codes, fill_value=0.0)

    all_dates = sorted(weight_matrix.index)
    daily_total_exposure = current_df.groupby("date")["weight"].sum().to_dict()

    # ── Step 3: Daily state machine recursion ────────────────────────
    last_w = pd.Series(0.0, index=weight_matrix.columns)
    for c, v in init_state.items():
        last_w[c] = v

    smoothed_rows: list[pd.Series] = []
    first_day = not bool(init_state)  # no prior state → skip dead zone on day 1
    for date in all_dates:
        row = weight_matrix.loc[date]

        if first_day:
            # No prior state: accept current weights as-is
            new_row = row.copy()
            first_day = False
        else:
            delta = (row - last_w).abs()
            new_row = row.copy()
            mask = delta < dead_zone
            new_row[mask] = last_w[mask]

        # Normalize weights to sum to 1.0 (relative allocation).
        # Exposure scaling is applied later when computing shares (via capital).
        smoothed_sum = new_row.sum()
        if smoothed_sum > 0:
            new_row = new_row / smoothed_sum

        smoothed_rows.append(new_row)
        last_w = new_row

    # ── Step 4: Stack back to long table ─────────────────────────────
    smoothed_matrix = pd.DataFrame(smoothed_rows, index=all_dates, columns=weight_matrix.columns)
    long_weight = smoothed_matrix.stack().reset_index()
    long_weight.columns = ["date", "code", "weight"]
    long_weight = long_weight[long_weight["weight"] > 0].reset_index(drop=True)

    # ── Step 5: Merge prices + ffill + recompute shares ──────────────
    # Caller (walk_forward.py) includes previous period's last-day prices
    # in the `prices` parameter. We stamp those as the first date of the
    # current period so they survive the left merge and serve as ffill seeds.
    price_data = prices[["date", "code", "close"]].copy()
    if last_period_last_day is not None and not last_period_last_day.empty:
        prev_date = last_period_last_day["date"].max()
        prev_prices = price_data[price_data["date"] == prev_date].copy()
        if not prev_prices.empty:
            prev_prices["date"] = all_dates[0]  # stamp as first day of current period
            price_data = pd.concat([price_data, prev_prices], ignore_index=True)
            price_data = price_data.drop_duplicates(subset=["date", "code"], keep="last")

    # Step 5a: left merge — creates rows for resurrected stocks (close=NaN)
    merged = long_weight.merge(price_data, on=["date", "code"], how="left")

    # Step 5b: sort + ffill — forward-fill close along (code, date) axis
    merged = merged.sort_values(["code", "date"])
    merged["close"] = merged.groupby("code")["close"].ffill()

    # Step 5c: compute shares inside merged DF (no cross-table assignment)
    if exposure is not None:
        merged["date_cap"] = merged["date"].map(
            lambda d: capital * exposure.get(d, 1.0)
        )
    else:
        merged["date_cap"] = capital

    merged["shares"] = (
        np.floor(merged["date_cap"] * merged["weight"] / merged["close"] / 100)
        .astype(int)
        * 100
    )
    merged["shares"] = merged["shares"].fillna(0).astype(int)

    return (
        merged[["date", "code", "weight", "shares"]]
        .sort_values(["date", "code"])
        .reset_index(drop=True)
    )
