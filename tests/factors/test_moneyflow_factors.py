"""tests/factors/test_moneyflow_factors.py — 资金流因子族单测。"""
import numpy as np
import pandas as pd

from factors.mining.sources.moneyflow import (
    calc_moneyflow_big_net_ratio,
    calc_moneyflow_net_ratio,
    calc_moneyflow_streak,
)
from factors.registry import list_factors, run_factor


def _mf_df(n_days=5, codes=("600000", "600001")):
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for c in codes:
            rows.append(
                {
                    "date": d, "code": c,
                    "buy_sm_amount": 100.0, "sell_sm_amount": 80.0,
                    "buy_md_amount": 50.0, "sell_md_amount": 40.0,
                    "buy_lg_amount": 20.0, "sell_lg_amount": 10.0,
                    "buy_elg_amount": 10.0, "sell_elg_amount": 5.0,
                    "net_mf_amount": 30.0, "circ_mv": 1000.0,
                }
            )
    # 600001 最后两天净流出 → streak 归零
    df = pd.DataFrame(rows)
    df.loc[
        (df["code"] == "600001") & (df["date"] >= dates[-2]), "net_mf_amount"
    ] = -10.0
    return df


def test_moneyflow_net_ratio():
    df = _mf_df()
    s = calc_moneyflow_net_ratio(df)
    assert s.name == "moneyflow_net_ratio"
    assert abs(s.iloc[0] - 30.0 / 1000.0) < 1e-9  # 净流入/流通市值
    assert not np.isnan(s.iloc[0])  # 值非 NaN


def test_moneyflow_net_ratio_missing_circ_mv_nan():
    df = _mf_df().drop(columns=["circ_mv"])
    s = calc_moneyflow_net_ratio(df)
    assert s.isna().all()  # 缺列 → 全 NaN（上游宽表准备层负责保证列存在）


def test_moneyflow_streak_counts_consecutive():
    df = _mf_df()
    s = calc_moneyflow_streak(df)
    # 600000 全期净流入 → 第 5 天 streak = 5；600001 第 3 天后转负 → 第 4 天归 0
    c0 = df["code"] == "600000"
    assert s[c0].iloc[-1] == 5
    c1 = df["code"] == "600001"
    assert s[c1].iloc[3] == 0
    assert s[c1].iloc[4] == 0  # 连续为负不计正 streak


def test_moneyflow_big_net_ratio():
    df = _mf_df()
    s = calc_moneyflow_big_net_ratio(df)
    # (20+10-10-5) / (100+80+50+40+20+10+10+5) = 15/315
    assert abs(s.iloc[0] - 15.0 / 315.0) < 1e-9


def test_moneyflow_factors_registered():
    # 防御性重建默认注册：test_factor_cache 的 autouse fixture 会清空全局
    # FACTOR_REGISTRY 且不恢复（既有顺序污染），与 test_registry 的
    # _ensure_defaults 同模式
    from factors.registry import FACTOR_REGISTRY, _register_defaults

    FACTOR_REGISTRY.clear()
    _register_defaults()
    names = list_factors(kind="single")
    assert "calc_moneyflow_net_ratio" in names
    assert "calc_moneyflow_streak" in names
    assert "calc_moneyflow_big_net_ratio" in names
    # run_factor 可调（缺列 → 全 NaN，不抛错）
    df = pd.DataFrame({"date": ["2025-06-02"], "code": ["600000"]})
    out = run_factor("calc_moneyflow_net_ratio", df)
    assert out.isna().all()
