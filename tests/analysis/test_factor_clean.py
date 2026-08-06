import json

import numpy as np
import pandas as pd
import pytest

from analysis.factor_clean import run_phase_a
from analysis.factor_monitor import STATE_COLS


def _ohlcv(n_days=120, n_stocks=40, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-06-02", periods=n_days)
    codes = [f"{600000 + i}" for i in range(n_stocks)]
    rows = []
    for d in dates:
        for c in codes:
            close = 10.0 + rng.normal(scale=0.5)
            rows.append(
                {
                    "date": d,
                    "code": c,
                    "open": close - 0.05,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "close": close,
                    "pre_close": close - 0.02,
                    "volume": float(rng.integers(1_000, 100_000)),
                    "limit_up": False,
                    "limit_down": False,
                    "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _state(as_of="2025-12-01"):
    rows = [
        (
            "2025-12-01",
            "calc_momentum_5d_change",
            5,
            0.05,
            0.06,
            0.8,
            4.5,
            "active",
            100,
        ),
        ("2025-12-01", "calc_volume_ratio", 5, 0.04, 0.05, 0.7, 3.9, "active", 95),
        ("2025-12-01", "calc_hv", 5, -0.02, -0.03, -0.4, -2.1, "dead", 30),
        (
            "2025-12-01",
            "calc_earnings_surprise",
            5,
            np.nan,
            np.nan,
            np.nan,
            np.nan,
            "active",
            0,
        ),
    ]
    return pd.DataFrame(rows, columns=STATE_COLS)


def test_run_phase_a_filters_active_decaying(tmp_path):
    state_path = tmp_path / "state.parquet"
    ohlcv_path = tmp_path / "ohlcv.parquet"
    _state().to_parquet(state_path, index=False)
    _ohlcv().to_parquet(ohlcv_path, index=False)

    out = run_phase_a(
        state_path=state_path,
        ohlcv_path=ohlcv_path,
        use_cache=False,
    )
    assert set(out["factors"]) == {"calc_momentum_5d_change", "calc_volume_ratio"}
    assert len(out["skipped"]) == 1
    assert "calc_earnings_surprise" in out["skipped"][0]  # 缺 earnings 列
    assert out["corr_matrix"].shape == (2, 2)
    assert out["corr_matrix"].index.tolist() == [
        "calc_momentum_5d_change",
        "calc_volume_ratio",
    ]
    assert out["clusters"].columns.tolist() == ["factor", "cluster_id"]
    assert out["representatives"].columns.tolist() == [
        "cluster_id",
        "representative",
        "members",
        "member_count",
    ]
    assert out["representatives"]["member_count"].sum() == 2
    assert out["as_of"] == pd.Timestamp("2025-12-01")


def test_run_phase_a_writes_outputs(tmp_path):
    state_path = tmp_path / "state.parquet"
    ohlcv_path = tmp_path / "ohlcv.parquet"
    out_dir = tmp_path / "out"
    _state().to_parquet(state_path, index=False)
    _ohlcv().to_parquet(ohlcv_path, index=False)

    out = run_phase_a(
        state_path=state_path,
        ohlcv_path=ohlcv_path,
        use_cache=False,
        output_dir=out_dir,
    )
    assert (out_dir / "corr_matrix.parquet").exists()
    assert (out_dir / "clusters.parquet").exists()
    assert (out_dir / "representatives.json").exists()
    assert (out_dir / "corr_heatmap.png").exists()
    assert (out_dir / "dendrogram.png").exists()
    payload = json.loads((out_dir / "representatives.json").read_text())
    assert payload["as_of"] == "2025-12-01"
    assert (
        len(payload["representatives"])
        == out["representatives"]["member_count"].sum()
    )


def test_run_phase_a_missing_state_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_phase_a(
            state_path=tmp_path / "nope.parquet",
            ohlcv_path=tmp_path / "nope.parquet",
        )
