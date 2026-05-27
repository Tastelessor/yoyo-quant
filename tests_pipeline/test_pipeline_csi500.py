"""管道测试：CSI 500 大股票池扩展验证。

用合成数据验证管道在更大股票池（20 只）下正常工作。
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.analysis.pool_matrix import pivot_matrix, run_matrix
from src.context.regime import detect_regime
from src.data.filters import detect_limit_price, detect_suspension
from src.data.universe import resolve_universe


@pytest.fixture
def large_universe_ohlcv():
    """20 只股票各 60 天的合成行情数据。"""
    dates = pd.date_range("2024-01-02", periods=60, freq="B")
    np.random.seed(42)

    frames = []
    for i in range(20):
        code = f"{600000 + i:06d}"
        close = 50 + np.cumsum(np.random.randn(60) * 0.5)
        close = np.maximum(close, 1.0)  # 避免负价格
        vol = np.random.randint(500_000, 5_000_000, size=60).astype(float)
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "open": close - 0.1,
                    "high": close + 0.3,
                    "low": close - 0.3,
                    "close": close,
                    "volume": vol,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_csi500_universe_resolves_from_mock_index():
    """source=index 应正确解析为代码列表。"""
    cfg = {
        "source": "index",
        "index_code": "000905.SH",
        "fetch_date": "2026-05-23",
    }
    with patch(
        "src.data.fetcher.fetch_index_constituents",
        return_value=[f"{600000 + i:06d}" for i in range(20)],
    ):
        result = resolve_universe(cfg)
    assert len(result) == 20


def test_csi500_data_pipeline_end_to_end(large_universe_ohlcv):
    """20 只股票数据应能跑完整管道（detect → run_matrix）。"""
    market = detect_limit_price(large_universe_ohlcv)
    market = detect_suspension(market)

    codes = market["code"].unique().tolist()
    pool_groups = {"CSI500": codes}

    strategy_specs = [
        {
            "name": "gtja_momentum",
            "params": {"rebalance": 20, "top_n": 5, "bottom_n": 3},
        },
    ]

    results = run_matrix(pool_groups, strategy_specs, market)
    assert not results.empty
    assert "sharpe_ratio" in results.columns
    assert "total_return" in results.columns
    assert len(results) == 1


def test_csi500_regime_detection_works(large_universe_ohlcv):
    """20 只股票数据应能正常检测 regime。"""
    market = detect_limit_price(large_universe_ohlcv)
    market = detect_suspension(market)

    regimes = detect_regime(market)
    assert isinstance(regimes, pd.Series)
    assert len(regimes) > 0
    valid_regimes = {"trend_up", "trend_down", "range", "volatile"}
    assert set(regimes.unique()).issubset(valid_regimes)


def test_cross_universe_comparison_structure(large_universe_ohlcv):
    """两个 universe 的结果应能拼接并透视。"""
    market = detect_limit_price(large_universe_ohlcv)
    market = detect_suspension(market)

    codes = market["code"].unique().tolist()
    half = len(codes) // 2

    pool_groups = {
        "CSI300": codes[:half],
        "CSI500": codes[half:],
    }

    strategy_specs = [
        {
            "name": "gtja_momentum",
            "params": {"rebalance": 20, "top_n": 3, "bottom_n": 3},
        },
    ]

    results = run_matrix(pool_groups, strategy_specs, market)
    assert len(results) == 2
    assert set(results["pool"]) == {"CSI300", "CSI500"}

    pivot = pivot_matrix(results, metric="sharpe_ratio")
    assert pivot.shape == (2, 1)
