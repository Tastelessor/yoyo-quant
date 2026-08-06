"""tests/cli/test_mining_cmd.py — yq factor mining-screen CLI 测试。"""
import json

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from yq.cli import app

runner = CliRunner()


def _ohlcv(n_days=30, n_stocks=10, seed=0):
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


def _basic(n_days=30, n_stocks=10, seed=0):
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


def _moneyflow(n_days=30, n_stocks=10, seed=0):
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


def test_mining_screen_runs_and_json(tmp_path):
    ohlcv = tmp_path / "ohlcv.parquet"
    basic = tmp_path / "basic.parquet"
    mf = tmp_path / "moneyflow.parquet"
    _ohlcv().to_parquet(ohlcv)
    _basic().to_parquet(basic)
    _moneyflow().to_parquet(mf)
    result = runner.invoke(
        app, [
            "factor", "mining-screen",
            "--data", str(ohlcv), "--basic", str(basic),
            "--moneyflow", str(mf),
            "--fwd-window", "5",
            "--json",
        ]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "calc_moneyflow_net_ratio" in payload
    assert "domain" in payload["calc_moneyflow_net_ratio"]


def test_mining_screen_missing_input_exits_1(tmp_path):
    result = runner.invoke(
        app, [
            "factor", "mining-screen",
            "--data", str(tmp_path / "nope.parquet"),
            "--basic", str(tmp_path / "nope.parquet"),
            "--moneyflow", str(tmp_path / "nope.parquet"),
        ]
    )
    assert result.exit_code != 0
    assert "错误" in result.output
