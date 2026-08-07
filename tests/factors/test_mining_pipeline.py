"""tests/factors/test_mining_pipeline.py — run_mining_screen 端到端测试。"""
import json

import numpy as np
import pandas as pd

from factors.mining.pipeline import _domain_for, run_mining_screen


def _ohlcv(n_days=40, n_stocks=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "open": close - 0.05, "high": close + 0.1,
                    "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _basic(n_days=40, n_stocks=12, seed=0):
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "circ_mv": float(100 * (i + 1)),
                    "turnover_rate": float((n_stocks - i) * 0.5),
                }
            )
    return pd.DataFrame(rows)


def _moneyflow(n_days=40, n_stocks=12, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append(
                {
                    "date": d, "code": f"{600000 + i}",
                    "buy_sm_amount": 100.0, "sell_sm_amount": 80.0,
                    "buy_md_amount": 50.0, "sell_md_amount": 40.0,
                    "buy_lg_amount": 20.0, "sell_lg_amount": 10.0,
                    "buy_elg_amount": 10.0, "sell_elg_amount": 5.0,
                    "net_mf_amount": float(rng.normal(30.0, 10.0)),
                }
            )
    return pd.DataFrame(rows)


def test_run_mining_screen_end_to_end(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv().to_parquet(ohlcv)
    _basic().to_parquet(basic)
    _moneyflow().to_parquet(mf)

    out = run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        factors=["calc_moneyflow_net_ratio"],
        fwd_window=5,
    )
    screen = out["screen"]
    assert "calc_moneyflow_net_ratio" in screen.index
    assert "all_mean_ic" in screen.columns
    assert "small-high_t_stat" in screen.columns
    assert "domain" in screen.columns
    assert out["summary"]["calc_moneyflow_net_ratio"]["domain"] in (
        "universal", "none",
    ) or isinstance(out["summary"]["calc_moneyflow_net_ratio"]["domain"], list)
    # 层标签表结构与因子宽表对齐
    assert list(out["layers"].columns) == ["date", "code", "size_layer", "liq_layer"]


def test_run_mining_screen_output_dir(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv(n_days=20, n_stocks=8).to_parquet(ohlcv)
    _basic(n_days=20, n_stocks=8).to_parquet(basic)
    _moneyflow(n_days=20, n_stocks=8).to_parquet(mf)
    out_dir = tmp_path / "out"

    run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        factors=["calc_moneyflow_net_ratio"],
        output_dir=out_dir,
    )
    assert (out_dir / "screen.parquet").exists()
    assert (out_dir / "layers.parquet").exists()
    summary = json.loads((out_dir / "summary.json").read_text())
    assert "calc_moneyflow_net_ratio" in summary


def test_run_mining_screen_all_three_factors(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    _basic(n_days=30, n_stocks=10).to_parquet(basic)
    _moneyflow(n_days=30, n_stocks=10).to_parquet(mf)

    out = run_mining_screen(
        ohlcv_path=ohlcv,
        basic_path=basic,
        moneyflow_path=mf,
        fwd_window=5,
    )  # factors=None → 默认资金流三因子
    assert list(out["screen"].index) == [
        "calc_moneyflow_net_ratio",
        "calc_moneyflow_streak",
        "calc_moneyflow_big_net_ratio",
    ]


# --- _domain_for 适用域判定：确定性单测（核心业务逻辑，直接测私有函数） ---


def test_domain_for_universal_short_circuit():
    # all_t_stat >= t_active → 直接 universal，不再评估各层
    row = pd.Series(
        {
            "all_t_stat": 2.5,           # >= 2.0 → universal
            "small-high_t_stat": 0.5,    # 即使层不达标也忽略
            "mid-low_t_stat": 0.8,
        }
    )
    assert _domain_for(row, t_active=2.0, layer_t=2.81) == "universal"


def test_domain_for_significant_layers_only():
    # all_t_stat < t_active，仅返回 t_stat >= layer_t 的层名（按列序）
    row = pd.Series(
        {
            "all_t_stat": 1.5,           # < 2.0 → 走层列表分支
            "small-high_t_stat": 3.2,    # 达标
            "mid-low_t_stat": 2.0,       # 不达标
            "big-high_t_stat": 2.0,      # 不达标
        }
    )
    assert _domain_for(row, t_active=2.0, layer_t=2.81) == ["small-high"]


def test_domain_for_none():
    # all_t_stat 与所有层均不达标 → "none"
    row = pd.Series(
        {
            "all_t_stat": 1.0,
            "small-high_t_stat": 1.8,
            "mid-low_t_stat": 2.0,
            "big-low_t_stat": 0.5,
        }
    )
    assert _domain_for(row, t_active=2.0, layer_t=2.81) == "none"


def test_domain_for_boundary_nan_and_exact_threshold():
    # NaN 层不误入列表；t_stat 恰好等于 layer_t 算达标
    row = pd.Series(
        {
            "all_t_stat": 1.0,
            "small-high_t_stat": 2.81,    # 恰好等于 layer_t → 达标
            "mid-low_t_stat": np.nan,     # NaN → 不误入列表
            "big-low_t_stat": 2.80,       # 差一点 → 不达标
        }
    )
    assert _domain_for(row, t_active=2.0, layer_t=2.81) == ["small-high"]
