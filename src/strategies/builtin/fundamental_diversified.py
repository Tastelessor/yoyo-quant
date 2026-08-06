"""Fundamental diversified strategy: combine non-price factors for cross-source alpha.

Active factors (default weights): earnings_surprise (1.0), amihud (0.8),
roe_stability (0.6).

Evaluation history: candidate pool was 9 factors (ep, bp, amihud, turnover,
roe_level, roe_stability, cashflow_quality, earnings_surprise, earnings_acceleration).
After single-factor walk-forward evaluation (notebooks/evaluate_new_factors.py),
only the 3 above were kept — one from each source (earnings / liquidity / quality).
The rest (ep, bp, turnover, roe_level, cashflow_quality, earnings_acceleration)
did not add dispersion value and were dropped.

Uses cross-sectional rank normalization + weighted scoring on each rebalance date.
"""

from __future__ import annotations

import pandas as pd

from factors.registry import run_factor
from strategies.base import Strategy
from strategies.registry import register_strategy

DEFAULT_WEIGHTS = {
    "earnings_surprise": 1.0,
    "amihud": 0.8,
    "roe_stability": 0.6,
}

FACTOR_COLS = list(DEFAULT_WEIGHTS.keys())

# Map factor column name → (factor registry name, required_columns)
FACTOR_COMPUTE = {
    "earnings_surprise": ("calc_earnings_surprise", ["earnings_surprise"]),
    "amihud": ("calc_amihud", ["volume", "close"]),
    "roe_stability": ("calc_roe_stability", ["roe_stability"]),
}


@register_strategy("fundamental_diversified")
class FundamentalDiversifiedStrategy(Strategy):
    name = "fundamental_diversified"

    def __init__(
        self,
        rebalance: int = 15,
        top_n: int = 10,
        bottom_n: int = 5,
        weights: dict | None = None,
        industry_map: dict[str, str] | None = None,
        min_peers: int = 3,
    ):
        self.rebalance = rebalance
        self.top_n = top_n
        self.bottom_n = bottom_n
        self.weights = weights or DEFAULT_WEIGHTS
        self.industry_map = industry_map
        self.min_peers = min_peers

    def generate_signal(self, data, factors=None):
        return fundamental_diversified_signal(
            data,
            self.rebalance,
            self.top_n,
            self.bottom_n,
            self.weights,
            factors,
            industry_map=self.industry_map,
            min_peers=self.min_peers,
        )


def fundamental_diversified_signal(
    df: pd.DataFrame,
    rebalance: int = 15,
    top_n: int = 10,
    bottom_n: int = 5,
    weights: dict | None = None,
    factors: pd.DataFrame | None = None,
    industry_map: dict[str, str] | None = None,
    min_peers: int = 3,
) -> pd.DataFrame:
    if weights is None:
        weights = DEFAULT_WEIGHTS

    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())

    # Compute factors: use pre-computed if available, otherwise compute inline
    active_factors = [f for f in FACTOR_COLS if f in weights]
    factor_data = {}

    for col in active_factors:
        if factors is not None and col in factors.columns:
            factor_data[col] = factors[col].values
        else:
            calc_name, req_cols = FACTOR_COMPUTE[col]
            if all(c in df.columns for c in req_cols):
                factor_data[col] = run_factor(calc_name, df).values
            # else: skip this factor (missing data)

    if not factor_data:
        return pd.DataFrame(
            {"date": df["date"], "code": df["code"], "signal": 0, "confidence": 0.0}
        )

    factor_df = pd.DataFrame({"date": df["date"], "code": df["code"], **factor_data})

    if industry_map is not None:
        from factors.ops.neutralize import neutralize_factors

        factor_df = neutralize_factors(
            factor_df, industry_map, list(factor_data.keys()), min_peers=min_peers
        )

    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)
    min_window = 21
    rebalance_dates = [
        all_dates[i] for i in range(min_window, len(all_dates), rebalance)
    ]

    for rb_date in rebalance_dates:
        day_data = factor_df[factor_df["date"] == rb_date].copy()
        if len(day_data) < 2:
            continue

        # Weighted rank scoring
        day_data["score"] = 0.0
        total_w = 0.0
        for col in active_factors:
            if col not in day_data.columns:
                continue
            w = weights.get(col, 0.0)
            day_data["score"] += day_data[col].rank(pct=True) * w
            total_w += w
        if total_w > 0:
            day_data["score"] /= total_w

        day_data = day_data.sort_values("score", ascending=False)
        buy_codes = set(day_data.head(top_n)["code"].tolist()) if top_n > 0 else set()
        sell_codes = (
            set(day_data.tail(bottom_n)["code"].tolist()) if bottom_n > 0 else set()
        )

        rb_idx = all_dates.index(rb_date)
        next_rb_idx = min(rb_idx + rebalance, len(all_dates))
        for h_date in all_dates[rb_idx:next_rb_idx]:
            h_mask = df["date"] == h_date
            for code in buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = 1
                    sv = day_data[day_data["code"] == code]["score"].values
                    confidence.iloc[idx] = float(sv[0]) if len(sv) > 0 else 0.5
            for code in sell_codes - buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = -1
                    confidence.iloc[idx] = 0.5

    if not all_dates:
        return pd.DataFrame(
            {"date": df["date"], "code": df["code"], "signal": 0, "confidence": 0.0}
        )

    if min_window < len(all_dates):
        first_valid = all_dates[min_window]
    else:
        first_valid = all_dates[-1]
    early = df["date"] < first_valid
    signal[early] = 0
    confidence[early] = 0.0

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
