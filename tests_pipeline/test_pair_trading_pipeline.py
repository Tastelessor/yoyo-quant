"""Pipeline test: pair trading signals -> risk -> portfolio -> backtest."""

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable
from src.strategies.builtin.pair_trading import pair_trading_signal


def _make_pair_ohlcv(n=120, seed=42):
    """生成两只协整股票的完整 OHLCV 数据。"""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    common = np.cumsum(np.random.randn(n) * 0.5)
    close_a = 100 + common + np.random.randn(n) * 0.1
    close_b = 80 + common * 0.8 + np.random.randn(n) * 0.1
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["A"] * n + ["B"] * n,
            "open": np.concatenate([close_a, close_b]),
            "high": np.concatenate([close_a + 0.5, close_b + 0.5]),
            "low": np.concatenate([close_a - 0.5, close_b - 0.5]),
            "close": np.concatenate([close_a, close_b]),
            "volume": [1_000_000] * (n * 2),
        }
    )


def _make_market_data(ohlcv):
    """给 OHLCV 数据加上 limit_up, limit_down, is_suspended 列。"""
    df = ohlcv.copy()
    df["limit_up"] = False
    df["limit_down"] = False
    df["is_suspended"] = False
    return df


def test_pair_trading_through_filter_tradable():
    """信号通过 filter_tradable 正确过滤。"""
    ohlcv = _make_pair_ohlcv()
    market = _make_market_data(ohlcv)
    signals = pair_trading_signal(ohlcv, pairs=[("A", "B")])

    filtered = filter_tradable(market, signals)
    assert set(filtered.columns) == set(signals.columns)
    assert len(filtered) == len(signals)


def test_pair_trading_through_enforce_t1():
    """信号通过 enforce_t1 正确处理。"""
    ohlcv = _make_pair_ohlcv()
    signals = pair_trading_signal(ohlcv, pairs=[("A", "B")])

    t1_signals = enforce_t1(signals)
    assert set(t1_signals.columns) == set(signals.columns)
    assert set(t1_signals["signal"].unique()).issubset({-1, 0, 1})


def test_pair_trading_through_equal_weight():
    """equal_weight 只分配到 signal=1 的股票。"""
    ohlcv = _make_pair_ohlcv()
    prices = ohlcv[["date", "code", "close"]].copy()
    signals = pair_trading_signal(ohlcv, pairs=[("A", "B")])

    positions = equal_weight(signals, prices, capital=1_000_000)
    if not positions.empty:
        assert set(positions.columns) == {"date", "code", "weight", "shares"}
        assert (positions["weight"] >= 0).all()
        assert (positions["weight"] <= 1.0 + 1e-8).all()


def test_pair_trading_through_position_limit():
    """position_limit 正确限制单只股票权重。"""
    ohlcv = _make_pair_ohlcv()
    prices = ohlcv[["date", "code", "close"]].copy()
    signals = pair_trading_signal(ohlcv, pairs=[("A", "B")])

    positions = equal_weight(signals, prices, capital=1_000_000)
    if not positions.empty:
        adjusted = apply_position_limit(positions, max_weight=0.3)
        assert all(w <= 0.3 + 1e-8 for w in adjusted["weight"].values)


def test_pair_trading_full_pipeline():
    """完整管道：signal -> filter -> t1 -> equal_weight -> position_limit -> backtest。"""
    ohlcv = _make_pair_ohlcv()
    market = _make_market_data(ohlcv)
    prices = ohlcv[["date", "code", "close"]].copy()

    signals = pair_trading_signal(
        ohlcv, pairs=[("A", "B")], entry_zscore=2.0, exit_zscore=0.5, lookback=30
    )
    filtered = filter_tradable(market, signals)
    t1_signals = enforce_t1(filtered)
    positions = equal_weight(t1_signals, prices, capital=1_000_000)
    adjusted = apply_position_limit(positions, max_weight=0.3)

    engine = BacktestEngine(capital=1_000_000)
    result = engine.run(adjusted, prices)

    assert "trades" in result
    assert "equity_curve" in result
    assert "metrics" in result
    assert "total_return" in result["metrics"]
    assert "sharpe_ratio" in result["metrics"]


def test_pair_trading_param_sweep_compatible():
    """pair_trading_signal 兼容 param_sweep 的 signal_gen 签名。"""
    from src.analysis.param_sweep import build_grid, run_sweep

    ohlcv = _make_pair_ohlcv()
    market = _make_market_data(ohlcv)

    def signal_gen(data, **params):
        return pair_trading_signal(data, pairs=[("A", "B")], **params)

    param_grid = {
        "entry_zscore": [1.5, 2.0],
        "exit_zscore": [0.3, 0.5],
        "lookback": [30],
    }

    grid = build_grid(param_grid)
    assert len(grid) == 4

    results = run_sweep(signal_gen, param_grid, market, capital=1_000_000, max_weight=0.3)
    assert len(results) == 4
    assert "sharpe_ratio" in results.columns
    assert "total_return" in results.columns
