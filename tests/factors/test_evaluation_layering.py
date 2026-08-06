"""tests/factors/test_evaluation_layering.py — compute_ic_by_layer 单测。"""
import numpy as np
import pandas as pd

from factors.ops.evaluation import compute_ic_by_layer


def _make_data(n_days=30, n_per_layer=8, seed=0):
    """每层股票因子值与 forward return 强相关（层内），构造可预期分层 IC。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows, fwd = [], []
    layers = ["small-low", "small-mid", "small-high", "mid-low", "mid-mid",
              "mid-high", "large-low", "large-mid", "large-high"]
    for d in dates:
        for li, layer in enumerate(layers):
            s, liq = layer.split("-")
            for k in range(n_per_layer):
                code = f"{600000 + li * 100 + k}"
                x = rng.normal(size=1)[0]
                y = x * 0.5 + rng.normal(scale=0.1)  # 层内强相关
                rows.append({"date": d, "code": code, "f": x,
                             "size_layer": s, "liq_layer": liq})
                fwd.append(y)
    factor_df = pd.DataFrame(rows)
    factor_cols = ["date", "code", "f"]
    layer_cols = ["date", "code", "size_layer", "liq_layer"]
    return factor_df[factor_cols], pd.Series(fwd), factor_df[layer_cols]


def test_ic_by_layer_structure_and_correlation():
    factor_df, fwd, layers = _make_data()
    out = compute_ic_by_layer(factor_df, "f", fwd, layers)
    assert list(out.index) == ["all"] + [
        f"{s}-{liq}" for s in ("small", "mid", "large")
        for liq in ("low", "mid", "high")
    ]
    for col in ("mean_ic", "t_stat", "n_days"):
        assert col in out.columns
    # 层内强正相关 → 每层 mean_ic > 0 且 t 显著
    assert (out["mean_ic"] > 0.2).all()
    assert (out["t_stat"] > 2).all()
    assert (out["n_days"] == 30).all()


def test_ic_by_layer_weak_layer_reported_not_dropped():
    """弱层如实报告（低 t），不静默剔除。"""
    factor_df, fwd, layers = _make_data(seed=1)
    # 把 small-low 层的因子值打乱 → 该层 IC 接近 0
    mask = (layers["size_layer"] == "small") & (layers["liq_layer"] == "low")
    rng = np.random.default_rng(99)
    factor_df.loc[mask, "f"] = rng.permutation(factor_df.loc[mask, "f"].to_numpy())
    out = compute_ic_by_layer(factor_df, "f", fwd, layers)
    assert abs(out.loc["small-low", "mean_ic"]) < 0.15  # 弱层低 IC 但仍在表里
    assert "small-low" in out.index


def test_ic_by_layer_short_history_nan_t():
    """层有效天数 < min_days → t_stat NaN（n_days 仍如实记录）。"""
    factor_df, fwd, layers = _make_data(n_days=5)
    out = compute_ic_by_layer(factor_df, "f", fwd, layers, min_days=10)
    assert (out["t_stat"].isna()).all()
    assert (out["n_days"] == 5).all()
    assert out["mean_ic"].notna().all()
