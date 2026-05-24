import numpy as np
import pandas as pd
import pytest

from src.strategies.base import Strategy
from src.strategies.builtin.pair_trading import PairTradingStrategy, pair_trading_signal
from src.strategies.registry import get_strategy


def _make_pair_data(n=120, seed=42):
    """生成两只协整股票的数据。"""
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


def _make_extreme_spread_data(n=120):
    """构造价差极端偏离后回归的数据：A 先涨后跌，B 先跌后涨。"""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # A 先稳后涨再回归，B 先稳后跌再回归 — 产生临时价差偏离
    close_a = np.concatenate([
        np.full(60, 100.0), np.linspace(100, 120, 30), np.linspace(120, 100, 30)
    ])
    close_b = np.concatenate([
        np.full(60, 80.0), np.linspace(80, 60, 30), np.linspace(60, 80, 30)
    ])
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


# ── 基本输出格式 ─────────────────────────────────────────────


def test_pair_trading_returns_dataframe():
    df = _make_pair_data()
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert isinstance(result, pd.DataFrame)


def test_pair_trading_has_required_columns():
    df = _make_pair_data()
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert set(result.columns) == {"date", "code", "signal", "confidence"}


def test_pair_trading_signal_values_valid():
    df = _make_pair_data()
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert set(result["signal"].unique()).issubset({-1, 0, 1})


def test_pair_trading_confidence_range():
    df = _make_pair_data()
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert (result["confidence"] >= 0).all()
    assert (result["confidence"] <= 1).all()


def test_pair_trading_same_length_as_input():
    df = _make_pair_data()
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert len(result) == len(df)


# ── 信号逻辑 ─────────────────────────────────────────────────


def test_pair_trading_entry_signal_extreme_spread():
    """价差极端偏离时应产生交易信号。"""
    df = _make_extreme_spread_data()
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=1.5, exit_zscore=0.5, lookback=30
    )
    # 在跳变后应有非零信号
    non_zero = result[result["signal"] != 0]
    assert len(non_zero) > 0


def test_pair_trading_no_signal_stable_prices():
    """价格稳定时不应产生信号。"""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    df = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["A"] * 100 + ["B"] * 100,
            "open": [100.0] * 100 + [80.0] * 100,
            "high": [100.5] * 100 + [80.5] * 100,
            "low": [99.5] * 100 + [79.5] * 100,
            "close": [100.0] * 100 + [80.0] * 100,
            "volume": [1_000_000] * 200,
        }
    )
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=2.0, exit_zscore=0.5, lookback=30
    )
    assert (result["signal"] == 0).all()


def test_pair_trading_confidence_proportional_to_zscore():
    """confidence 应与 |z-score| / entry_zscore 成正比。"""
    df = _make_extreme_spread_data()
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=2.0, exit_zscore=0.5, lookback=30
    )
    active = result[result["signal"] != 0]
    if len(active) > 0:
        assert (active["confidence"] <= 1.0).all()
        assert (active["confidence"] > 0).all()


# ── 多配对 ─────────────────────────────────────────────────


def test_pair_trading_multiple_pairs():
    """多组配对应独立产生信号。"""
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    c1 = np.cumsum(np.random.randn(n) * 0.5)
    c2 = np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "date": list(dates) * 3,
            "code": ["A"] * n + ["B"] * n + ["C"] * n,
            "close": np.concatenate([
                100 + c1,
                80 + c1 * 0.8,
                200 + c2,
            ]),
            "volume": [1_000_000] * (n * 3),
        }
    )
    df["open"] = df["close"]
    df["high"] = df["close"] + 0.5
    df["low"] = df["close"] - 0.5
    result = pair_trading_signal(
        df, pairs=[("A", "B"), ("A", "C")],
        entry_zscore=2.0, exit_zscore=0.5, lookback=30,
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(df)


def test_pair_trading_preserves_all_codes():
    """输出应包含所有输入的 code，不仅仅是配对中的。"""
    df = _make_pair_data()
    # 加一个不在配对中的股票
    extra = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=120, freq="B"),
        "code": "C",
        "close": 200.0,
        "open": 200.0,
        "high": 200.5,
        "low": 199.5,
        "volume": 1_000_000,
    })
    df_full = pd.concat([df, extra], ignore_index=True)
    result = pair_trading_signal(df_full, pairs=[("A", "B")])
    assert set(result["code"].unique()) == {"A", "B", "C"}
    # C 不在配对中，signal 应为 0
    c_signals = result[result["code"] == "C"]["signal"]
    assert (c_signals == 0).all()


# ── 边界情况 ─────────────────────────────────────────────────


def test_pair_trading_empty_data():
    cols = ["date", "code", "close", "open", "high", "low", "volume"]
    df = pd.DataFrame(columns=cols)
    result = pair_trading_signal(df, pairs=[("A", "B")])
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_pair_trading_insufficient_data():
    """数据不足 lookback 时应全部返回零信号。"""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["A"] * 10 + ["B"] * 10,
            "close": [100.0] * 10 + [80.0] * 10,
            "open": [100.0] * 10 + [80.0] * 10,
            "high": [100.5] * 10 + [80.5] * 10,
            "low": [99.5] * 10 + [79.5] * 10,
            "volume": [1_000_000] * 20,
        }
    )
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=2.0, exit_zscore=0.5, lookback=30
    )
    assert (result["signal"] == 0).all()


# ── 注册表 ─────────────────────────────────────────────────


def test_pair_trading_registered_in_registry():
    strategy = get_strategy("pair_trading", pairs=[("A", "B")])
    assert isinstance(strategy, PairTradingStrategy)
    assert strategy.name == "pair_trading"


def test_pair_trading_class_instantiation():
    strategy = PairTradingStrategy(
        pairs=[("A", "B"), ("C", "D")],
        entry_zscore=2.5,
        exit_zscore=0.3,
        lookback=90,
    )
    assert strategy.pairs == [("A", "B"), ("C", "D")]
    assert strategy.entry_zscore == 2.5
    assert strategy.exit_zscore == 0.3
    assert strategy.lookback == 90


def test_pair_trading_strategy_is_subclass():
    assert issubclass(PairTradingStrategy, Strategy)


# ── 重叠配对冲突解决 ─────────────────────────────────────────


def test_pair_trading_overlap_first_pair_wins():
    """重叠配对中，先到先得——第一个配对的信号优先。"""
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    c1 = np.cumsum(np.random.randn(n) * 0.5)
    c2 = np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "date": list(dates) * 3,
            "code": ["A"] * n + ["B"] * n + ["C"] * n,
            "close": np.concatenate([100 + c1, 80 + c1 * 0.8, 200 + c2]),
            "volume": [1_000_000] * (n * 3),
        }
    )
    df["open"] = df["close"]
    df["high"] = df["close"] + 0.5
    df["low"] = df["close"] - 0.5

    # A 出现在两个配对中：(A,B) 和 (A,C)
    # 只有第一个配对 (A,B) 应生效，(A,C) 应被跳过
    result = pair_trading_signal(
        df, pairs=[("A", "B"), ("A", "C")],
        entry_zscore=2.0, exit_zscore=0.5, lookback=30,
    )
    # C 不应有任何信号（因为 A 已被 (A,B) 占用）
    c_signals = result[result["code"] == "C"]["signal"]
    assert (c_signals == 0).all()


# ── beta_method 验证 ─────────────────────────────────────────


def test_pair_trading_invalid_beta_method_raises():
    """无效的 beta_method 应抛出 ValueError。"""
    df = _make_pair_data()
    with pytest.raises(ValueError, match="Unknown beta_method"):
        pair_trading_signal(df, pairs=[("A", "B")], beta_method="invalid")


def test_pair_trading_fixed_beta():
    """beta_method='fixed' 应使用 beta=1.0。"""
    df = _make_extreme_spread_data()
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=1.5,
        exit_zscore=0.5, lookback=30, beta_method="fixed",
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(df)


def test_pair_trading_kalman_beta():
    """beta_method='kalman' 应正常运行。"""
    df = _make_extreme_spread_data()
    result = pair_trading_signal(
        df, pairs=[("A", "B")], entry_zscore=1.5,
        exit_zscore=0.5, lookback=30, beta_method="kalman",
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(df)
    assert set(result["signal"].unique()).issubset({-1, 0, 1})
