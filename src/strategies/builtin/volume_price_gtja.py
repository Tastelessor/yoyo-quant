"""GTJA volume-price strategy."""

from __future__ import annotations

import pandas as pd

from factors.registry import run_factor
from strategies.base import Strategy
from strategies.registry import register_strategy

_FACTOR_COMPUTERS = {
    "money_flow_6d": "calc_money_flow_6d",
    "up_down_vol_26d": "calc_up_down_vol_ratio_26d",
    "obv_6d": "calc_obv_6d",
    "vol_rank_intraday_corr_6d": "calc_vol_rank_intraday_corr_6d",
    "vol_change_pct_5d": "calc_vol_change_pct_5d",
    "return_6d_times_vol": "calc_return_6d_times_vol",
    "return_1d_times_vol": "calc_return_1d_times_vol",
    "high_vol_rank_corr_3d": "calc_high_vol_rank_corr_3d",
    "close_vol_rank_cov_5d": "calc_close_vol_rank_cov_5d",
    "open_vol_corr_10d": "calc_open_vol_corr_10d",
    "vwap_vol_rank_corr_5d": "calc_vwap_vol_rank_corr_5d",
    "williams_r_smoothed_6d": "calc_williams_r_smoothed_6d",
    "shadow_ratio_20d": "calc_shadow_ratio_20d",
    "candle_body_vol_composite": "calc_candle_body_vol_composite",
    "open_vwap_close_vwap": "calc_open_vwap_close_vwap",
    "dollar_vol_std_6d": "calc_dollar_vol_std_6d",
    "vol_macd_9_26_12": "calc_vol_macd_9_26_12",
    "vol_rsi_6d": "calc_vol_rsi_6d",
}

DEFAULT_WEIGHTS = {
    "money_flow_6d": 1.0,
    "up_down_vol_26d": 1.0,
    "obv_6d": 1.0,
    "shadow_ratio_20d": 1.0,
    "return_1d_times_vol": 1.0,
    "vol_rank_intraday_corr_6d": 0.0,
    "vol_change_pct_5d": 0.0,
    "return_6d_times_vol": 0.0,
    "high_vol_rank_corr_3d": 0.0,
    "close_vol_rank_cov_5d": 0.0,
    "open_vol_corr_10d": 0.0,
    "vwap_vol_rank_corr_5d": 0.0,
    "williams_r_smoothed_6d": 0.0,
    "candle_body_vol_composite": 0.0,
    "open_vwap_close_vwap": 0.0,
    "dollar_vol_std_6d": 0.0,
    "vol_macd_9_26_12": 0.0,
    "vol_rsi_6d": 0.0,
}


@register_strategy("gtja_volume_price")
class GTJAVolumePriceStrategy(Strategy):
    name = "gtja_volume_price"

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
        return gtja_volume_price_signal(
            data,
            self.rebalance,
            self.top_n,
            self.bottom_n,
            self.weights,
            factors,
            industry_map=self.industry_map,
            min_peers=self.min_peers,
        )


def _active_factor_cols(weights: dict) -> list[str]:
    """Return factor columns with non-zero weight."""
    return [k for k, v in weights.items() if v > 0 and k in _FACTOR_COMPUTERS]


def gtja_volume_price_signal(
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

    active = _active_factor_cols(weights)
    if factors is not None and all(c in factors.columns for c in active):
        factor_df = factors[["date", "code"] + active].copy()
    else:
        factor_df = pd.DataFrame({"date": df["date"], "code": df["code"]})
        for col in active:
            if col in _FACTOR_COMPUTERS:
                factor_df[col] = run_factor(_FACTOR_COMPUTERS[col], df).values

    if industry_map is not None:
        from factors.ops.neutralize import neutralize_factors

        factor_df = neutralize_factors(
            factor_df, industry_map, active, min_peers=min_peers
        )

    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)
    min_window = 27
    rebalance_dates = [
        all_dates[i] for i in range(min_window, len(all_dates), rebalance)
    ]

    for rb_date in rebalance_dates:
        day_data = factor_df[factor_df["date"] == rb_date].copy()
        if len(day_data) < 2:
            continue
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
