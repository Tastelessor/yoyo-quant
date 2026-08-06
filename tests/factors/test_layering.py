"""factors 分层卫生测试：顶层(registry/operators) + builtin(因子实现) + ops(操作)。

分层标签原语单测（``compute_size_liquidity_layers``，见 task-2-brief）：
每日截面按 circ_mv / turnover_rate 三分位 → size / liquidity 层标签。
"""
import importlib

import numpy as np
import pandas as pd

from factors.ops.layering import compute_size_liquidity_layers

BUILTIN = [
    "momentum", "volume_price_gtja", "volatility_gtja", "mean_reversion",
    "trend", "vwap", "volatility", "volume_price", "cointegration",
    "earnings", "value", "quality", "liquidity",
]
OPS = ["evaluation", "neutralize", "cache", "layering"]


def test_builtin_modules_importable():
    for m in BUILTIN:
        importlib.import_module(f"factors.builtin.{m}")


def test_ops_modules_importable():
    for m in OPS:
        importlib.import_module(f"factors.ops.{m}")


def test_top_level_modules_importable():
    for m in ["registry", "operators"]:
        importlib.import_module(f"factors.{m}")


def test_top_level_reexports_work():
    from factors import (  # noqa: F401
        calc_hv,
        calc_momentum_5d_change,
        compute_ic,
        list_factors,
        neutralize_factors,
    )


# ---------------------------------------------------------------------------
# 分层标签原语单测（task-2-brief 逐字）
# ---------------------------------------------------------------------------


def _basic_df(n_days=3, n_stocks=6):
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            # circ_mv 递增（0..5），turnover 递减（5..0）→ 截面分位确定
            rows.append(
                {
                    "date": d,
                    "code": f"{600000 + i}",
                    "circ_mv": float(i * 100),
                    "turnover_rate": float((n_stocks - 1 - i) * 1.0),
                }
            )
    return pd.DataFrame(rows)


def test_layers_tercile_per_day():
    df = _basic_df(n_days=2, n_stocks=6)
    out = compute_size_liquidity_layers(df)
    assert list(out.columns) == ["date", "code", "size_layer", "liq_layer"]
    assert len(out) == len(df)
    # 每日截面：circ_mv 最小 1/3 → small；turnover 最大 1/3 → high
    day0 = out[out["date"] == out["date"].iloc[0]]
    assert set(day0.loc[day0["size_layer"] == "small", "code"]) == {"600000", "600001"}
    assert set(day0.loc[day0["size_layer"] == "large", "code"]) == {"600004", "600005"}
    assert set(day0.loc[day0["liq_layer"] == "high", "code"]) == {"600000", "600001"}
    assert set(day0.loc[day0["liq_layer"] == "low", "code"]) == {"600004", "600005"}


def test_layers_daily_cross_section_not_global():
    """分层按每日截面（不是全局分位）：日期间市值互换仍各自三分。"""
    dates = pd.bdate_range("2025-06-02", periods=2)
    rows = []
    for d, base in zip(dates, (0.0, 1000.0)):
        for i in range(6):
            rows.append(
                {
                    "date": d,
                    "code": f"{600000 + i}",
                    "circ_mv": base + i * 100.0,
                    "turnover_rate": 1.0,
                }
            )
    df = pd.DataFrame(rows)
    out = compute_size_liquidity_layers(df)
    # 两天各自的 small 都是最小两只（600000/600001），不受整体水平影响
    for d in dates:
        day = out[out["date"] == d]
        small_codes = day.loc[day["size_layer"] == "small", "code"]
        assert set(small_codes) == {"600000", "600001"}


def test_layers_nan_value_gives_nan_layer():
    df = _basic_df(n_days=1, n_stocks=6)
    df.loc[0, "circ_mv"] = np.nan
    df.loc[1, "turnover_rate"] = np.nan
    out = compute_size_liquidity_layers(df)
    assert pd.isna(out.loc[0, "size_layer"])
    assert pd.isna(out.loc[1, "liq_layer"])
    # 其他行不受影响
    assert out.loc[2, "size_layer"] == "small"


def test_layers_min_rows_falls_back_rank():
    """当日有效样本过少（< bins×2）时用 rank 分位降级，仍不报错。"""
    df = pd.DataFrame(
        {
            "date": ["2025-06-02"] * 4,
            "code": ["A", "B", "C", "D"],
            "circ_mv": [1.0, 2.0, 3.0, 4.0],
            "turnover_rate": [4.0, 3.0, 2.0, 1.0],
        }
    )
    out = compute_size_liquidity_layers(df)
    assert out["size_layer"].notna().all() and out["liq_layer"].notna().all()
    assert sorted(out["size_layer"].unique()) == ["large", "mid", "small"]
