"""Factor registry: register and retrieve factor functions by name or alias."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

FACTOR_REGISTRY: dict[str, tuple[Callable[[pd.DataFrame], pd.Series], list[str]]] = {}


def register_factor(
    name: str,
    func: Callable[[pd.DataFrame], pd.Series],
    tags: list[str] | None = None,
) -> None:
    """Register a factor function under *name*."""
    FACTOR_REGISTRY[name] = (func, tags or [])


def get_factor(name: str) -> Callable[[pd.DataFrame], pd.Series]:
    """Look up a registered factor by name. Raises KeyError if not found."""
    if name not in FACTOR_REGISTRY:
        raise KeyError(f"Unknown factor: {name!r}")
    return FACTOR_REGISTRY[name][0]


def list_factors(tag: str | None = None) -> list[str]:
    """List registered factor names, optionally filtered by tag."""
    if tag is None:
        return list(FACTOR_REGISTRY.keys())
    return [name for name, (_, tags) in FACTOR_REGISTRY.items() if tag in tags]


def calc_factors(
    df: pd.DataFrame,
    factor_names: list[str],
) -> pd.DataFrame:
    """Compute multiple factors and assemble into a DataFrame.

    Returns DataFrame with columns: date, code, <factor_name_1>, ...
    """
    df_sorted = df.sort_values(["code", "date"]).reset_index(drop=True)
    result = df_sorted[["date", "code"]].copy()
    for name in factor_names:
        func = get_factor(name)
        result[name] = func(df_sorted).values
    return result


def _register_defaults() -> None:
    """Auto-register all GTJA momentum factors with primary names and aliases."""
    from src.factors.momentum import (
        calc_momentum_5d_change,
        calc_momentum_5d_ratio,
        calc_momentum_6d_return,
        calc_momentum_20d_change,
        calc_momentum_20d_return,
    )

    momentum_factors = [
        ("calc_momentum_5d_change", calc_momentum_5d_change, "gtja_14"),
        ("calc_momentum_5d_ratio", calc_momentum_5d_ratio, "gtja_18"),
        ("calc_momentum_6d_return", calc_momentum_6d_return, "gtja_20"),
        ("calc_momentum_20d_return", calc_momentum_20d_return, "gtja_88"),
        ("calc_momentum_20d_change", calc_momentum_20d_change, "gtja_106"),
    ]
    for primary_name, func, alias in momentum_factors:
        register_factor(primary_name, func, tags=["momentum", "gtja"])
        register_factor(alias, func, tags=["momentum", "gtja"])

    from src.factors.volume_price_gtja import (
        calc_candle_body_vol_composite,
        calc_close_vol_rank_cov_5d,
        calc_dollar_vol_std_6d,
        calc_high_vol_rank_corr_3d,
        calc_money_flow_6d,
        calc_obv_6d,
        calc_open_vol_corr_10d,
        calc_open_vwap_close_vwap,
        calc_return_1d_times_vol,
        calc_return_6d_times_vol,
        calc_shadow_ratio_20d,
        calc_up_down_vol_ratio_26d,
        calc_vol_change_pct_5d,
        calc_vol_macd_9_26_12,
        calc_vol_rank_intraday_corr_6d,
        calc_vol_rsi_6d,
        calc_vwap_vol_rank_corr_5d,
        calc_williams_r_smoothed_6d,
    )

    volume_price_factors = [
        ("calc_money_flow_6d", calc_money_flow_6d, "gtja_11"),
        ("calc_up_down_vol_ratio_26d", calc_up_down_vol_ratio_26d, "gtja_40"),
        ("calc_obv_6d", calc_obv_6d, "gtja_43"),
        ("calc_vol_rank_intraday_corr_6d", calc_vol_rank_intraday_corr_6d, "gtja_1"),
        ("calc_vol_change_pct_5d", calc_vol_change_pct_5d, "gtja_80"),
        ("calc_return_6d_times_vol", calc_return_6d_times_vol, "gtja_29"),
        ("calc_return_1d_times_vol", calc_return_1d_times_vol, "gtja_178"),
        ("calc_high_vol_rank_corr_3d", calc_high_vol_rank_corr_3d, "gtja_32"),
        ("calc_close_vol_rank_cov_5d", calc_close_vol_rank_cov_5d, "gtja_99"),
        ("calc_open_vol_corr_10d", calc_open_vol_corr_10d, "gtja_139"),
        ("calc_vwap_vol_rank_corr_5d", calc_vwap_vol_rank_corr_5d, "gtja_90"),
        ("calc_williams_r_smoothed_6d", calc_williams_r_smoothed_6d, "gtja_47"),
        ("calc_shadow_ratio_20d", calc_shadow_ratio_20d, "gtja_118"),
        ("calc_candle_body_vol_composite", calc_candle_body_vol_composite, "gtja_54"),
        ("calc_open_vwap_close_vwap", calc_open_vwap_close_vwap, "gtja_12"),
        ("calc_dollar_vol_std_6d", calc_dollar_vol_std_6d, "gtja_70"),
        ("calc_vol_macd_9_26_12", calc_vol_macd_9_26_12, "gtja_145"),
        ("calc_vol_rsi_6d", calc_vol_rsi_6d, "gtja_102"),
    ]
    for primary_name, func, alias in volume_price_factors:
        register_factor(primary_name, func, tags=["volume_price", "gtja"])
        register_factor(alias, func, tags=["volume_price", "gtja"])

    from src.factors.earnings import calc_earnings_acceleration, calc_earnings_surprise

    register_factor("calc_earnings_surprise", calc_earnings_surprise, tags=["fundamental", "earnings"])
    register_factor("calc_earnings_acceleration", calc_earnings_acceleration, tags=["fundamental", "earnings"])


_register_defaults()
