"""Factor registry: register and retrieve factor functions by name or alias."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from factors.ops.cache import get_default_cache_dir, load_cached, save_cached

VALID_KINDS = ("single", "pair")


@dataclass(frozen=True)
class FactorSpec:
    """注册条目：函数 + 元数据。

    kind: "single"（单股票截面，可用 run_factor/calc_factors）
          "pair"（配对专用签名，仅可按名发现，由调用方按配对接口直接调用）
    params: 默认参数（缓存键参数哈希用），未显式传入时从函数签名自动提取。
    """

    func: Callable[..., pd.Series]
    tags: list[str]
    kind: str = "single"
    params: dict = field(default_factory=dict)


FACTOR_REGISTRY: dict[str, FactorSpec] = {}


def _extract_default_params(func: Callable) -> dict:
    """从函数签名提取带默认值的 kwargs（排除 df 输入参数）。"""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return {}
    params = {}
    for pname, p in sig.parameters.items():
        if pname == "df":
            continue
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and (
            p.default is not inspect.Parameter.empty
        ):
            params[pname] = p.default
    return params


def register_factor(
    name: str,
    func: Callable,
    tags: list[str] | None = None,
    kind: str = "single",
    params: dict | None = None,
) -> None:
    """Register a factor function under *name*.

    Parameters
    ----------
    name : str
        因子名（primary 名或别名）。
    func : Callable
        因子函数。single 因子签名 ``func(df, **kwargs) -> pd.Series``。
    tags : list[str] | None
        分类标签（如 momentum / gtja / volume_price）。
    kind : str
        "single"（默认）或 "pair"（配对专用签名）。
    params : dict | None
        默认参数；不传时从函数签名自动提取（仅带默认值的 kwargs）。
    """
    if kind not in VALID_KINDS:
        msg = f"Invalid kind: {kind!r}. Valid kinds: {', '.join(VALID_KINDS)}"
        raise ValueError(msg)
    resolved = params if params is not None else _extract_default_params(func)
    FACTOR_REGISTRY[name] = FactorSpec(
        func=func, tags=tags or [], kind=kind, params=resolved
    )


def get_factor(name: str) -> Callable:
    """Look up a registered factor by name. Raises KeyError if not found.

    返回原始函数对象（带默认参数），调用方式与直接 import 一致。
    """
    if name not in FACTOR_REGISTRY:
        raise KeyError(f"Unknown factor: {name!r}")
    return FACTOR_REGISTRY[name].func


def get_spec(name: str) -> FactorSpec:
    """Look up a registered factor's metadata. Raises KeyError if not found."""
    if name not in FACTOR_REGISTRY:
        raise KeyError(f"Unknown factor: {name!r}")
    return FACTOR_REGISTRY[name]


def list_factors(tag: str | None = None, kind: str | None = None) -> list[str]:
    """List registered factor names, optionally filtered by tag / kind."""
    result = []
    for name, spec in FACTOR_REGISTRY.items():
        if tag is not None and tag not in spec.tags:
            continue
        if kind is not None and spec.kind != kind:
            continue
        result.append(name)
    return result


def run_factor(
    name: str,
    df: pd.DataFrame,
    *,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    **params,
) -> pd.Series:
    """Compute a single registered single-kind factor, with disk cache.

    返回与输入 df **逐行对齐**的 Series：内部按 (code, date) 排序计算后
    映射回输入行顺序，调用方无需自行排序。

    Parameters
    ----------
    name : str
        已注册的 single 因子名。
    df : DataFrame
        输入行情数据（date, code, close, ...）。
    cache_dir : str | Path | None
        缓存目录。None 时用默认（``FACTOR_CACHE_DIR`` 环境变量或
        ``data/factors/``）。
    use_cache : bool
        False 时禁用缓存（不读不写）。
    **params
        因子参数，覆盖注册时的默认参数。
    """
    spec = get_spec(name)
    if spec.kind != "single":
        raise ValueError(
            f"Factor {name!r} is a pair factor; it cannot be run via run_factor. "
            "Call its function directly with pair arguments."
        )
    merged = {**spec.params, **params}
    # 记录排序后每行对应的原输入位置，计算完映射回输入顺序
    tmp = df.assign(__pos__=range(len(df)))
    df_sorted = tmp.sort_values(["code", "date"]).reset_index(drop=True)
    orig_pos = df_sorted.pop("__pos__").to_numpy()
    back_order = np.argsort(orig_pos)
    if use_cache:
        dir_path = Path(cache_dir) if cache_dir is not None else get_default_cache_dir()
        cached = load_cached(name, df_sorted, merged, dir_path)
        if cached is not None:
            return cached.iloc[back_order].reset_index(drop=True).rename(name)
    result = spec.func(df_sorted, **merged)
    if use_cache:
        dir_path = Path(cache_dir) if cache_dir is not None else get_default_cache_dir()
        save_cached(name, df_sorted, merged, result, dir_path)
    result = result.iloc[back_order]
    return result.reset_index(drop=True).rename(name)


def calc_factors(
    df: pd.DataFrame,
    factor_names: list[str],
    params: dict[str, dict] | None = None,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Compute multiple factors and assemble into a DataFrame.

    Returns DataFrame with columns: date, code, <factor_name_1>, ...

    Parameters
    ----------
    params : dict[str, dict] | None
        按因子名透传参数，如 ``{"calc_hv": {"window": 60}}``。
    cache_dir / use_cache
        透传给 ``run_factor``。
    """
    df_sorted = df.sort_values(["code", "date"]).reset_index(drop=True)
    result = df_sorted[["date", "code"]].copy()
    params = params or {}
    for name in factor_names:
        factor_params = params.get(name, {})
        result[name] = run_factor(
            name, df_sorted, cache_dir=cache_dir, use_cache=use_cache, **factor_params
        ).values
    return result


def _register_defaults() -> None:
    """Auto-register all built-in factors with primary names and aliases."""
    from factors.builtin.momentum import (
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

    from factors.builtin.volume_price_gtja import (
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

    from factors.builtin.earnings import calc_earnings_acceleration, calc_earnings_surprise

    register_factor(
        "calc_earnings_surprise",
        calc_earnings_surprise,
        tags=["fundamental", "earnings"],
    )
    register_factor(
        "calc_earnings_acceleration",
        calc_earnings_acceleration,
        tags=["fundamental", "earnings"],
    )

    from factors.builtin.value import calc_bp, calc_ep

    register_factor("calc_ep", calc_ep, tags=["fundamental", "value"])
    register_factor("calc_bp", calc_bp, tags=["fundamental", "value"])

    from factors.builtin.liquidity import calc_amihud, calc_turnover

    register_factor("calc_amihud", calc_amihud, tags=["liquidity"])
    register_factor("calc_turnover", calc_turnover, tags=["liquidity"])

    from factors.builtin.quality import (
        calc_cashflow_quality,
        calc_roe_level,
        calc_roe_stability,
    )

    register_factor("calc_roe_level", calc_roe_level, tags=["fundamental", "quality"])
    register_factor(
        "calc_roe_stability", calc_roe_stability, tags=["fundamental", "quality"]
    )
    register_factor(
        "calc_cashflow_quality", calc_cashflow_quality, tags=["fundamental", "quality"]
    )

    # --- 新增：GTJA 波动率（5） ---
    from factors.builtin.volatility_gtja import (
        calc_atr_6d,
        calc_atr_12d,
        calc_cci_12d,
        calc_volume_vol_10d,
        calc_volume_vol_20d,
    )

    volatility_gtja_factors = [
        ("calc_cci_12d", calc_cci_12d, "gtja_78"),
        ("calc_volume_vol_10d", calc_volume_vol_10d, "gtja_97"),
        ("calc_volume_vol_20d", calc_volume_vol_20d, "gtja_100"),
        ("calc_atr_12d", calc_atr_12d, "gtja_161"),
        ("calc_atr_6d", calc_atr_6d, "gtja_175"),
    ]
    for primary_name, func, alias in volatility_gtja_factors:
        register_factor(primary_name, func, tags=["volatility", "gtja"])
        register_factor(alias, func, tags=["volatility", "gtja"])

    # --- 新增：GTJA 均值回归（4） ---
    from factors.builtin.mean_reversion import (
        calc_directional_balance_12d,
        calc_mfi_14d,
        calc_rsi_6d,
        calc_rsi_12d,
    )

    mean_reversion_factors = [
        ("calc_rsi_6d", calc_rsi_6d, "gtja_63"),
        ("calc_rsi_12d", calc_rsi_12d, "gtja_79"),
        ("calc_directional_balance_12d", calc_directional_balance_12d, "gtja_112"),
        ("calc_mfi_14d", calc_mfi_14d, "gtja_128"),
    ]
    for primary_name, func, alias in mean_reversion_factors:
        register_factor(primary_name, func, tags=["mean_reversion", "gtja"])
        register_factor(alias, func, tags=["mean_reversion", "gtja"])

    # --- 新增：GTJA 趋势（3） ---
    from factors.builtin.trend import calc_ma_slope_6d, calc_ma_slope_20d, calc_macd_like

    trend_factors = [
        ("calc_ma_slope_6d", calc_ma_slope_6d, "gtja_21"),
        ("calc_ma_slope_20d", calc_ma_slope_20d, "gtja_116"),
        ("calc_macd_like", calc_macd_like, "gtja_89"),
    ]
    for primary_name, func, alias in trend_factors:
        register_factor(primary_name, func, tags=["trend", "gtja"])
        register_factor(alias, func, tags=["trend", "gtja"])

    # --- 新增：GTJA VWAP（2） ---
    from factors.builtin.vwap import calc_vwap_close_ratio, calc_vwap_deviation

    vwap_factors = [
        ("calc_vwap_close_ratio", calc_vwap_close_ratio, "gtja_120"),
        ("calc_vwap_deviation", calc_vwap_deviation, "gtja_124"),
    ]
    for primary_name, func, alias in vwap_factors:
        register_factor(primary_name, func, tags=["vwap", "gtja"])
        register_factor(alias, func, tags=["vwap", "gtja"])

    # --- 新增：通用量价（4，带 window 参数） ---
    from factors.builtin.volume_price import calc_atr, calc_obv, calc_rsi, calc_volume_ratio

    register_factor("calc_rsi", calc_rsi, tags=["volume_price"])
    register_factor("calc_obv", calc_obv, tags=["volume_price"])
    register_factor("calc_volume_ratio", calc_volume_ratio, tags=["volume_price"])
    register_factor("calc_atr", calc_atr, tags=["volume_price"])

    # --- 新增：HV（1，带 window 参数） ---
    from factors.builtin.volatility import calc_hv

    register_factor("calc_hv", calc_hv, tags=["volatility"])

    # --- 新增：配对专用（5，kind="pair"） ---
    from factors.builtin.cointegration import (
        calc_coint_pvalue,
        calc_half_life,
        calc_spread,
        calc_spread_zscore,
        kalman_filter_hedge_ratio,
    )

    pair_factors = [
        ("calc_spread", calc_spread),
        ("calc_spread_zscore", calc_spread_zscore),
        ("calc_coint_pvalue", calc_coint_pvalue),
        ("calc_half_life", calc_half_life),
        ("kalman_filter_hedge_ratio", kalman_filter_hedge_ratio),
    ]
    for name, func in pair_factors:
        register_factor(name, func, kind="pair", tags=["pair", "cointegration"])


_register_defaults()
