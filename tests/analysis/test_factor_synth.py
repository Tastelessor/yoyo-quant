"""tests/analysis/test_factor_synth.py — Phase C 编排集成测试。"""
import json

import numpy as np
import pandas as pd

from analysis.factor_monitor import STATE_COLS
from analysis.factor_synth import (
    _resolve_representatives,
    compare_backtests,
    run_phase_c,
)


def _ohlcv(n_days=40, n_stocks=20, seed=0):
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


def _state(tmp_path, factors=("calc_momentum_5d_change", "calc_volume_ratio")):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-06-02", periods=40)
    rows = []
    for d in dates:
        for name in factors:
            rows.append(
                {
                    "date": d, "factor": name, "fwd_window": 5,
                    "ic": float(rng.normal(0.02, 0.03)),
                    "rolling_ic": 0.02, "rolling_ir": 0.4,
                    "t_stat": 3.0, "state": "active", "sustain_days": 30,
                }
            )
    df = pd.DataFrame(rows, columns=STATE_COLS)
    p = tmp_path / "state.parquet"
    df.to_parquet(p)
    return p


def test_compare_backtests_returns_metrics_table(tmp_path):
    data = _ohlcv(n_days=30, n_stocks=10)
    sig = pd.DataFrame(
        {
            "date": data["date"],
            "code": data["code"],
            "signal": 1,
            "confidence": 0.5,
        }
    )
    compare, curves = compare_backtests(
        {"synth": sig, "single": sig}, data, capital=100_000, dead_zone=0.0
    )
    assert list(compare.index) == ["synth", "single"]
    for col in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "trade_count"):
        assert col in compare.columns
    assert "synth" in curves and "single" in curves
    assert "equity" in curves["synth"].columns


def test_run_phase_c_equal_weight_end_to_end(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out = run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        synth_weighting="equal",
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
    )
    sig = out["signals"]
    assert list(sig.columns) == ["date", "code", "signal", "confidence"]
    assert sig["signal"].isin([-1, 0, 1]).all()
    assert set(sig["code"].unique()) <= set(
        pd.read_parquet(ohlcv)["code"].unique()
    )
    assert "compare" in out and "equity_curves" in out and "summary" in out
    assert out["summary"]["synth_weighting"] == "equal"
    assert out["summary"]["weights"] is None


def test_run_phase_c_ic_weighted_and_output_dir(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out_dir = tmp_path / "out"
    run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        synth_weighting="ic_weighted",
        ic_lookback=20,
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
        output_dir=out_dir,
    )
    assert (out_dir / "synth_signals.parquet").exists()
    assert (out_dir / "backtest_compare.parquet").exists()
    assert (out_dir / "equity_compare.png").exists()
    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["synth_weighting"] == "ic_weighted"
    assert "best_single" in summary
    # 契约：ic_weighted 模式 summary 必须带 weights（可观测各因子实际参与权重）
    w = summary["weights"]
    assert isinstance(w, dict)
    assert set(w) == {"calc_momentum_5d_change", "calc_volume_ratio"}


def test_run_phase_c_best_single_and_beats_flag(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv(n_days=30, n_stocks=10).to_parquet(ohlcv)
    state = _state(tmp_path)
    out = run_phase_c(
        state_path=state,
        ohlcv_path=ohlcv,
        representatives=["calc_momentum_5d_change", "calc_volume_ratio"],
        rebalance=5,
        top_n=3,
        bottom_n=2,
        capital=100_000,
        dead_zone=0.0,
    )
    s = out["summary"]
    assert "best_single" in s and "best_single_sharpe" in s
    assert "synth_sharpe" in s and "synth_beats_best_single" in s
    assert isinstance(s["synth_beats_best_single"], bool)


def test_resolve_representatives(tmp_path):
    assert _resolve_representatives(["a", "b"]) == ["a", "b"]
    p = tmp_path / "reps.json"
    p.write_text(
        json.dumps(
            {
                "representatives": [
                    {"cluster_id": 0, "representative": "a", "members": ["a"]},
                    {"cluster_id": 1, "representative": "b", "members": ["b"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _resolve_representatives(p) == ["a", "b"]
