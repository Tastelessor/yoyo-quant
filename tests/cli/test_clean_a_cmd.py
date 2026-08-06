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
    rows = [
        (
            "2025-12-01", "calc_momentum_5d_change", 5,
            0.05, 0.06, 0.8, 4.5, "active", 100,
        ),
        ("2025-12-01", "calc_volume_ratio", 5, 0.04, 0.05, 0.7, 3.9, "active", 95),
    ]
    p = tmp_path / "state.parquet"
    pd.DataFrame(rows, columns=STATE_COLS).to_parquet(p, index=False)
    return p


def test_clean_a_cmd_runs(tmp_path):
    state = _state(tmp_path)
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["factor", "clean-a", "--state", str(state), "--data", str(data),
         "--no-cache", "--output-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "代表因子" in result.output
    assert (out / "corr_heatmap.png").exists()


def test_clean_a_cmd_json(tmp_path):
    state = _state(tmp_path)
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    result = runner.invoke(
        app,
        ["factor", "clean-a", "--state", str(state), "--data", str(data),
         "--no-cache", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["as_of"] == "2025-12-01"
    assert len(payload["factors"]) == 2


def test_clean_a_cmd_requires_state(tmp_path):
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    result = runner.invoke(app, ["factor", "clean-a", "--data", str(data)])
    assert result.exit_code != 0


def test_clean_a_cmd_invalid_threshold(tmp_path):
    # CLI 显式非法阈值须被优雅捕获（错误消息 + 非 0 退出码），不得裸抛 traceback
    state = _state(tmp_path)
    data = tmp_path / "ohlcv.parquet"
    _ohlcv().to_parquet(data, index=False)
    result = runner.invoke(
        app,
        ["factor", "clean-a", "--state", str(state), "--data", str(data),
         "--no-cache", "--threshold", "2.0"],
    )
    assert result.exit_code != 0
    assert "错误" in result.output
