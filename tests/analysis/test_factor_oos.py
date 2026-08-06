"""tests/analysis/test_factor_oos.py — run_phase_b 集成测试。"""
import json

import numpy as np
import pandas as pd
import pytest

from analysis.factor_monitor import STATE_COLS
from analysis.factor_oos import run_phase_b


def _ohlcv(n_days=120, n_stocks=40, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for c in [f"{600000 + i}" for i in range(n_stocks)]:
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d, "code": c, "open": close - 0.05,
                    "high": close + 0.1, "low": close - 0.1, "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False, "limit_down": False, "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _state(tmp_path, n_days=120, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for name, t in [("calc_momentum_5d_change", 5.0), ("calc_volume_ratio", 3.0)]:
            rows.append(
                {
                    "date": d, "factor": name, "fwd_window": 5,
                    "ic": float(rng.normal(0.02, 0.03)),
                    "rolling_ic": 0.02, "rolling_ir": 0.4,
                    "t_stat": t, "state": "active", "sustain_days": 100,
                }
            )
    df = pd.DataFrame(rows, columns=STATE_COLS)
    p = tmp_path / "state.parquet"
    df.to_parquet(p)
    return p


def _state_nan_ic(tmp_path, n_days=120, nan_days=60, seed=0):
    """_state 变体：两因子前 nan_days 天的 ic 全置 NaN（其余日期有效）。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    rows = []
    for d in dates:
        for name, t in [("calc_momentum_5d_change", 5.0), ("calc_volume_ratio", 3.0)]:
            rows.append(
                {
                    "date": d, "factor": name, "fwd_window": 5,
                    "ic": float(rng.normal(0.02, 0.03)),
                    "rolling_ic": 0.02, "rolling_ir": 0.4,
                    "t_stat": t, "state": "active", "sustain_days": 100,
                }
            )
    df = pd.DataFrame(rows, columns=STATE_COLS)
    cut = dates[nan_days - 1]
    df.loc[df["date"] < cut, "ic"] = np.nan
    p = tmp_path / "state_nan.parquet"
    df.to_parquet(p)
    return p


def test_run_phase_b_outputs_structure(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    out = run_phase_b(
        state_path=state, ohlcv_path=ohlcv,
        train_months=1, test_months=1, top_k=2,
        bootstrap_iters=50, t_window=10, corr_window=20,
        fwd_window=5, seed=42,
    )
    assert set(out.keys()) == {"periods", "summary"}
    periods = out["periods"]
    assert len(periods) > 0
    expect_cols = {
        "period_idx", "train_start", "train_end", "test_start", "test_end",
        "factor", "cluster_id", "train_t", "null_95", "selected",
        "test_ic_mean", "test_ic_t", "test_ic_n", "test_sig", "win",
    }
    assert expect_cols.issubset(periods.columns)
    assert periods["win"].dtype == bool
    assert periods["selected"].dtype == bool
    # 入选因子满足入选规则：|train_t| > max(1.0, null_95)（pool 规则，实现保证）
    for _, row in periods[periods["selected"]].iterrows():
        assert abs(row["train_t"]) > max(1.0, row["null_95"])
    s = out["summary"]
    for key in (
        "periods_total", "periods_with_selection", "overall_win_rate",
        "overall_sig_rate", "null_95_mean", "period_win_rates",
    ):
        assert key in s


def test_run_phase_b_writes_output_dir(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    out_dir = tmp_path / "out"
    run_phase_b(
        state_path=state, ohlcv_path=ohlcv,
        train_months=1, test_months=1, top_k=2,
        bootstrap_iters=50, t_window=10, corr_window=20,
        fwd_window=5, seed=42, output_dir=out_dir,
    )
    for fname in (
        "oos_results.parquet", "oos_summary.json",
        "oos_winrate.png", "oos_bootstrap.png",
    ):
        assert (out_dir / fname).exists(), fname
    summary = json.loads((out_dir / "oos_summary.json").read_text(encoding="utf-8"))
    assert "overall_win_rate" in summary


def test_run_phase_b_too_short_raises(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=60).to_parquet(ohlcv)
    state = _state(tmp_path, n_days=60)
    with pytest.raises(ValueError, match="窗口"):
        run_phase_b(
            state_path=state, ohlcv_path=ohlcv,
            train_months=12, test_months=1,
        )


def test_run_phase_b_ic_nan_not_pollute_null(tmp_path):
    """覆盖 review finding 1：bootstrap 守卫必须按 dropna 后有效值判定。

    两因子前 60 天 ic 全 NaN：首 3 个窗口的 train 段 len(ic) >= t_window 但
    dropna().size < t_window。旧守卫（len 口径）会让全 NaN 零分布混入
    null_list → np.nanquantile 返回 NaN → max(1.0, NaN)=1.0 门槛退化、虚增
    入选（periods 出现 null_95=NaN 的行）；修复（dropna 口径）后污染期无
    入选，periods 的 null_95 不含 NaN，summary 的 null_95_mean 也不为 NaN。
    """
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state_nan_ic(tmp_path)
    out = run_phase_b(
        state_path=state, ohlcv_path=ohlcv,
        train_months=1, test_months=1, top_k=2,
        bootstrap_iters=50, t_window=10, corr_window=20,
        fwd_window=5, seed=42,
    )
    periods = out["periods"]
    assert periods["null_95"].notna().all()
    assert not np.isnan(out["summary"]["null_95_mean"])


def test_run_phase_b_fwd_window_too_long_raises(tmp_path):
    """覆盖 review finding 2：fwd_window 相对 test 期长度需显式校验。"""
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    with pytest.raises(ValueError, match="test 期过短"):
        run_phase_b(
            state_path=state, ohlcv_path=ohlcv,
            train_months=1, test_months=1, top_k=2,
            bootstrap_iters=50, t_window=10, corr_window=20,
            fwd_window=50, seed=42,
        )
