import numpy as np
import pandas as pd
import pytest

from src.analysis.param_sweep import best_result, build_grid, run_sweep


# --- fixtures ---


@pytest.fixture
def sample_data():
    """合成行情数据：1只股票120天，带有趋势和波动。"""
    np.random.seed(42)
    n = 120
    dates = pd.bdate_range("2024-01-02", periods=n)
    price = 10.0 + np.cumsum(np.random.randn(n) * 0.3)
    price = np.maximum(price, 1.0)
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": price,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": np.random.randint(1_000_000, 5_000_000, n).astype(float),
            "limit_up": False,
            "limit_down": False,
            "is_suspended": False,
        }
    )


@pytest.fixture
def simple_signal_gen():
    """最简信号生成器：价格低于 MA 时买入，高于时卖出。"""

    def gen(data, window=20):
        df = data.sort_values(["code", "date"]).reset_index(drop=True)
        ma = df.groupby("code")["close"].transform(
            lambda s: s.rolling(window=window, min_periods=window).mean()
        )
        signal = pd.Series(0, index=df.index, dtype=int)
        signal[df["close"] < ma] = 1
        signal[df["close"] > ma] = -1
        return pd.DataFrame(
            {
                "date": df["date"],
                "code": df["code"],
                "signal": signal,
                "confidence": 0.5,
            }
        )

    return gen


# --- build_grid ---


def test_build_grid_basic():
    """应生成所有参数组合。"""
    grid = build_grid({"window": [10, 20], "num_std": [1.5, 2.0]})
    assert len(grid) == 4
    assert {"window": 10, "num_std": 1.5} in grid
    assert {"window": 20, "num_std": 2.0} in grid


def test_build_grid_single_param():
    """单参数应生成对应数量的组合。"""
    grid = build_grid({"window": [10, 15, 20]})
    assert len(grid) == 3
    assert all("window" in g for g in grid)


def test_build_grid_empty():
    """空参数空间应返回空列表。"""
    grid = build_grid({})
    assert grid == []


# --- run_sweep ---


def test_run_sweep_returns_dataframe(sample_data, simple_signal_gen):
    """应返回 DataFrame。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20]},
        data=sample_data,
        capital=100_000,
    )
    assert isinstance(results, pd.DataFrame)


def test_run_sweep_row_count_matches_grid(sample_data, simple_signal_gen):
    """行数应等于参数组合数。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 15, 20, 25]},
        data=sample_data,
        capital=100_000,
    )
    assert len(results) == 4


def test_run_sweep_contains_param_columns(sample_data, simple_signal_gen):
    """结果应包含所有参数列。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20], "num_std": [1.5, 2.0]},
        data=sample_data,
        capital=100_000,
    )
    assert "window" in results.columns
    assert "num_std" in results.columns


def test_run_sweep_contains_metric_columns(sample_data, simple_signal_gen):
    """结果应包含所有绩效指标列。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20]},
        data=sample_data,
        capital=100_000,
    )
    expected_cols = [
        "total_return", "annual_return", "sharpe_ratio",
        "max_drawdown", "win_rate", "trade_count",
    ]
    for col in expected_cols:
        assert col in results.columns, f"missing column: {col}"


def test_run_sweep_different_params_different_results(sample_data, simple_signal_gen):
    """不同参数应产生不同结果。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [5, 50]},
        data=sample_data,
        capital=100_000,
    )
    # 至少 trade_count 或 sharpe 应不同
    assert not (
        results.iloc[0]["trade_count"] == results.iloc[1]["trade_count"]
        and results.iloc[0]["sharpe_ratio"] == results.iloc[1]["sharpe_ratio"]
    )


def test_run_sweep_empty_grid(sample_data, simple_signal_gen):
    """空参数网格应返回空 DataFrame。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={},
        data=sample_data,
        capital=100_000,
    )
    assert isinstance(results, pd.DataFrame)
    assert len(results) == 0


# --- best_result ---


def test_best_result_returns_series(sample_data, simple_signal_gen):
    """应返回一行 Series。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20, 30]},
        data=sample_data,
        capital=100_000,
    )
    best = best_result(results)
    assert isinstance(best, pd.Series)


def test_best_result_maximizes_sharpe(sample_data, simple_signal_gen):
    """应选择 Sharpe 最高的行。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20, 30, 40, 50]},
        data=sample_data,
        capital=100_000,
    )
    best = best_result(results)
    assert best["sharpe_ratio"] == results["sharpe_ratio"].max()


def test_best_result_custom_metric(sample_data, simple_signal_gen):
    """应支持按自定义指标选择。"""
    results = run_sweep(
        signal_gen=simple_signal_gen,
        param_grid={"window": [10, 20, 30]},
        data=sample_data,
        capital=100_000,
    )
    best = best_result(results, metric="total_return")
    assert best["total_return"] == results["total_return"].max()


def test_best_result_empty_df():
    """空 DataFrame 应返回空 Series。"""
    empty = pd.DataFrame()
    best = best_result(empty)
    assert len(best) == 0
