"""tests/cli/test_clean_b_cmd.py — yq factor clean-b CLI 测试。"""
import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from analysis.factor_monitor import STATE_COLS
from yq.cli import app

runner = CliRunner()


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


def _state(tmp_path):
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2025-06-02", periods=120)
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


def test_clean_b_runs_and_json(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    result = runner.invoke(
        app, [
            "factor", "clean-b",
            "--state", str(state), "--data", str(ohlcv),
            "--train-months", "1", "--test-months", "1",
            "--top-k", "2", "--bootstrap-iters", "50",
            "--t-window", "10", "--window", "20",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "overall_win_rate" in payload
    assert "periods_total" in payload


def test_clean_b_invalid_top_k_exits_1(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(ohlcv)
    state = _state(tmp_path)
    result = runner.invoke(
        app, [
            "factor", "clean-b",
            "--state", str(state), "--data", str(ohlcv),
            "--top-k", "0",
        ]
    )
    assert result.exit_code != 0
    assert "错误" in result.output
