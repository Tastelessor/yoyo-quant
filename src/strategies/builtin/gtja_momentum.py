"""GTJA momentum strategy.

Uses 5 GTJA momentum factors to score stocks cross-sectionally:
- #14: 5d price change (short-term momentum)
- #18: 5d price ratio (relative momentum)
- #20: 6d return percentage
- #88: 20d return percentage (medium-term momentum)
- #106: 20d price change

On each rebalance date, ranks all stocks by composite factor score.
Buys top_n, sells bottom_n.
"""

from __future__ import annotations

import pandas as pd

from factors.registry import run_factor
from strategies.base import Strategy
from strategies.registry import register_strategy

DEFAULT_WEIGHTS = {
    "gtja_14": 1.0,
    "gtja_18": 1.0,
    "gtja_20": 1.0,
    "gtja_88": 1.0,
    "gtja_106": 1.0,
}

FACTOR_COLS = ["gtja_14", "gtja_18", "gtja_20", "gtja_88", "gtja_106"]


@register_strategy("gtja_momentum")
class GTJAMomentumStrategy(Strategy):
    """GTJA multi-factor momentum strategy."""

    name = "gtja_momentum"

    def __init__(
        self,
        rebalance: int = 20,
        top_n: int = 5,
        bottom_n: int = 3,
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
        return gtja_momentum_signal(
            data,
            rebalance=self.rebalance,
            top_n=self.top_n,
            bottom_n=self.bottom_n,
            weights=self.weights,
            factors=factors,
            industry_map=self.industry_map,
            min_peers=self.min_peers,
        )


def _rank_normalize(s: pd.Series) -> pd.Series:
    """Cross-sectional rank normalization to [0, 1]."""
    return s.rank(pct=True)


def gtja_momentum_signal(
    df: pd.DataFrame,
    rebalance: int = 20,
    top_n: int = 5,
    bottom_n: int = 3,
    weights: dict | None = None,
    factors: pd.DataFrame | None = None,
    industry_map: dict[str, str] | None = None,
    min_peers: int = 3,
) -> pd.DataFrame:
    """GTJA momentum signal.

    Parameters
    ----------
    df : DataFrame
        Must contain date, code, open, high, low, close, volume.
    rebalance : int
        Rebalance every N trading days.
    top_n : int
        Buy top N stocks by score.
    bottom_n : int
        Sell bottom N stocks by score.
    weights : dict, optional
        Factor weights keyed by factor column name.
    factors : DataFrame, optional
        Pre-computed factors with columns: date, code, gtja_14, gtja_18, ...
        If None, factors are computed inline.

    Returns
    -------
    DataFrame
        Columns: date, code, signal, confidence.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())

    # Compute or use pre-computed factors
    if factors is not None and all(c in factors.columns for c in FACTOR_COLS):
        factor_df = factors[["date", "code"] + FACTOR_COLS].copy()
    else:
        factor_df = pd.DataFrame(
            {
                "date": df["date"],
                "code": df["code"],
                "gtja_14": run_factor("calc_momentum_5d_change", df).values,
                "gtja_18": run_factor("calc_momentum_5d_ratio", df).values,
                "gtja_20": run_factor("calc_momentum_6d_return", df).values,
                "gtja_88": run_factor("calc_momentum_20d_return", df).values,
                "gtja_106": run_factor("calc_momentum_20d_change", df).values,
            }
        )

    # Industry neutralization: strip industry exposure before ranking
    if industry_map is not None:
        from factors.neutralize import neutralize_factors

        factor_df = neutralize_factors(
            factor_df, industry_map, FACTOR_COLS, min_peers=min_peers
        )

    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)

    # Minimum lookback: need 20 days for longest factor
    min_window = 21
    rebalance_dates = [
        all_dates[i] for i in range(min_window, len(all_dates), rebalance)
    ]

    for rb_date in rebalance_dates:
        day_mask = factor_df["date"] == rb_date
        day_data = factor_df[day_mask].copy()

        if len(day_data) < 2:
            continue

        # Cross-sectional rank normalization + weighted sum
        active_factors = [c for c in FACTOR_COLS if c in weights]
        day_data["score"] = 0.0
        total_weight = 0.0
        for col in active_factors:
            w = weights[col]
            day_data["score"] += _rank_normalize(day_data[col]) * w
            total_weight += w

        if total_weight > 0:
            day_data["score"] /= total_weight

        day_data = day_data.sort_values("score", ascending=False)

        buy_codes = set(day_data.head(top_n)["code"].tolist()) if top_n > 0 else set()
        sell_codes = (
            set(day_data.tail(bottom_n)["code"].tolist()) if bottom_n > 0 else set()
        )

        # Apply signals from rebalance date until next rebalance
        rb_idx = all_dates.index(rb_date)
        next_rb_idx = min(rb_idx + rebalance, len(all_dates))
        holding_dates = all_dates[rb_idx:next_rb_idx]

        for h_date in holding_dates:
            h_mask = df["date"] == h_date
            for code in buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = 1
                    score_val = day_data[day_data["code"] == code]["score"].values
                    confidence.iloc[idx] = (
                        float(score_val[0]) if len(score_val) > 0 else 0.5
                    )

            for code in sell_codes - buy_codes:
                mask = h_mask & (df["code"] == code)
                idx = df.index[mask]
                if len(idx) > 0:
                    signal.iloc[idx] = -1
                    confidence.iloc[idx] = 0.5

    # Zero out rows where factor data is insufficient
    if min_window < len(all_dates):
        first_valid_date = all_dates[min_window]
    else:
        first_valid_date = all_dates[-1]
    early_mask = df["date"] < first_valid_date
    signal[early_mask] = 0
    confidence[early_mask] = 0.0

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
