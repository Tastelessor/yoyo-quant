"""GTJA VWAP strategy."""

from __future__ import annotations

import pandas as pd

from src.factors.registry import run_factor
from src.strategies.base import Strategy
from src.strategies.registry import register_strategy

DEFAULT_WEIGHTS = {"vwap_ratio": 1.0, "vwap_dev": 1.0}
FACTOR_COLS = list(DEFAULT_WEIGHTS.keys())


@register_strategy("gtja_vwap")
class GTJAVWAPStrategy(Strategy):
    name = "gtja_vwap"

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
        return gtja_vwap_signal(
            data,
            self.rebalance,
            self.top_n,
            self.bottom_n,
            self.weights,
            factors,
            industry_map=self.industry_map,
            min_peers=self.min_peers,
        )


def gtja_vwap_signal(
    df: pd.DataFrame,
    rebalance: int = 20,
    top_n: int = 5,
    bottom_n: int = 3,
    weights: dict | None = None,
    factors: pd.DataFrame | None = None,
    industry_map: dict[str, str] | None = None,
    min_peers: int = 3,
) -> pd.DataFrame:
    if weights is None:
        weights = DEFAULT_WEIGHTS
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())

    if factors is not None and all(c in factors.columns for c in FACTOR_COLS):
        factor_df = factors[["date", "code"] + FACTOR_COLS].copy()
    else:
        vr = run_factor("calc_vwap_close_ratio", df)
        vd = run_factor("calc_vwap_deviation", df)
        factor_df = pd.DataFrame(
            {
                "date": df["date"],
                "code": df["code"],
                "vwap_ratio": vr.values,
                "vwap_dev": vd.values,
            }
        )

    if industry_map is not None:
        from src.factors.neutralize import neutralize_factors

        factor_df = neutralize_factors(
            factor_df, industry_map, FACTOR_COLS, min_peers=min_peers
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
        active = [c for c in FACTOR_COLS if c in weights]
        day_data["score"] = 0.0
        total_w = 0.0
        for col in active:
            day_data["score"] += day_data[col].rank(pct=True) * weights[col]
            total_w += weights[col]
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


@register_strategy("reversed_gtja_vwap")
class ReversedGTJAVWAPStrategy(GTJAVWAPStrategy):
    """Reversed VWAP: flips buy/sell signals. Strongest single strategy in backtests."""

    @property
    def name(self) -> str:
        return "reversed_gtja_vwap"

    def generate_signal(self, data, factors=None):
        sig = super().generate_signal(data, factors=factors)
        result = sig.copy()
        result["signal"] = -result["signal"]
        return result
