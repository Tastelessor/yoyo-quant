import numpy as np
import pandas as pd
import pytest

from analysis.pool_matrix import best_per_pool, pivot_matrix, run_matrix

# --- fixtures ---


@pytest.fixture
def sample_data():
    """合成行情数据：3只股票共120天，含市场标注列。"""
    np.random.seed(42)
    n = 120
    dates = pd.bdate_range("2024-01-02", periods=n)
    codes = ["000001", "600519", "000858"]
    rows = []
    for code in codes:
        price = 10.0 + np.cumsum(np.random.randn(n) * 0.3)
        price = np.maximum(price, 1.0)
        for i, d in enumerate(dates):
            rows.append({
                "date": d,
                "code": code,
                "open": price[i],
                "high": price[i] * 1.02,
                "low": price[i] * 0.98,
                "close": price[i],
                "volume": np.random.randint(1_000_000, 5_000_000),
                "limit_up": False,
                "limit_down": False,
                "is_suspended": False,
            })
    return pd.DataFrame(rows)


# --- run_matrix ---


def test_run_matrix_returns_dataframe(sample_data):
    """应返回 DataFrame。"""
    results = run_matrix(
        pool_groups={"all": ["000001", "600519", "000858"]},
        strategy_specs=[{"name": "mean_reversion"}],
        data=sample_data,
        capital=100_000,
    )
    assert isinstance(results, pd.DataFrame)


def test_run_matrix_row_count_cross_product(sample_data):
    """行数应等于 pool × strategy 的交叉积。"""
    results = run_matrix(
        pool_groups={
            "pool_a": ["000001"],
            "pool_b": ["600519"],
            "pool_c": ["000858"],
        },
        strategy_specs=[
            {"name": "mean_reversion"},
            {"name": "rsi_reversal"},
        ],
        data=sample_data,
        capital=100_000,
    )
    assert len(results) == 6  # 3 × 2


def test_run_matrix_contains_label_columns(sample_data):
    """结果应包含 pool 和 strategy 列。"""
    results = run_matrix(
        pool_groups={"pool_a": ["000001"]},
        strategy_specs=[{"name": "mean_reversion"}],
        data=sample_data,
        capital=100_000,
    )
    assert "pool" in results.columns
    assert "strategy" in results.columns


def test_run_matrix_contains_metric_columns(sample_data):
    """结果应包含所有绩效指标列。"""
    results = run_matrix(
        pool_groups={"pool_a": ["000001"]},
        strategy_specs=[{"name": "mean_reversion"}],
        data=sample_data,
        capital=100_000,
    )
    expected_cols = [
        "total_return", "annual_return", "sharpe_ratio",
        "max_drawdown", "win_rate", "trade_count",
    ]
    for col in expected_cols:
        assert col in results.columns, f"missing column: {col}"


def test_run_matrix_with_custom_params(sample_data):
    """策略带自定义 params 应正确传入。"""
    results_default = run_matrix(
        pool_groups={"pool_a": ["000001"]},
        strategy_specs=[{"name": "mean_reversion"}],
        data=sample_data,
        capital=100_000,
    )
    results_custom = run_matrix(
        pool_groups={"pool_a": ["000001"]},
        strategy_specs=[{"name": "mean_reversion", "params": {"window": 5, "num_std": 3.0}}],
        data=sample_data,
        capital=100_000,
    )
    # 不同参数应产生不同结果
    assert (
        results_default.iloc[0]["trade_count"]
        != results_custom.iloc[0]["trade_count"]
    )


def test_run_matrix_empty_pool_warning_and_nan(sample_data):
    """空 pool（代码在 data 中不存在）应产生 NaN metrics 并 warning。"""
    with pytest.warns(UserWarning, match="empty or has no matching rows"):
        results = run_matrix(
            pool_groups={"ghost": ["999999"]},
            strategy_specs=[{"name": "mean_reversion"}],
            data=sample_data,
            capital=100_000,
        )
    assert pd.isna(results.iloc[0]["sharpe_ratio"])


def test_run_matrix_unknown_strategy_warning_and_nan(sample_data):
    """不存在的策略名应产生 NaN metrics 并 warning。"""
    with pytest.warns(UserWarning, match="Unknown strategy"):
        results = run_matrix(
            pool_groups={"pool_a": ["000001"]},
            strategy_specs=[{"name": "nonexistent_strategy_xyz"}],
            data=sample_data,
            capital=100_000,
        )
    assert pd.isna(results.iloc[0]["sharpe_ratio"])


def test_run_matrix_multi_strategy_different_results(sample_data):
    """不同策略在同一 pool 上应产生不同结果。"""
    results = run_matrix(
        pool_groups={"pool_a": ["000001"]},
        strategy_specs=[
            {"name": "mean_reversion"},
            {"name": "rsi_reversal"},
        ],
        data=sample_data,
        capital=100_000,
    )
    # 至少有一项指标不同
    mr = results[results["strategy"] == "mean_reversion"].iloc[0]
    rsi = results[results["strategy"] == "rsi_reversal"].iloc[0]
    different = (
        mr["trade_count"] != rsi["trade_count"]
        or mr["sharpe_ratio"] != rsi["sharpe_ratio"]
        or mr["total_return"] != rsi["total_return"]
    )
    assert different


# --- pivot_matrix ---


@pytest.fixture
def sample_results():
    """合成 matrix 结果用于测试 pivot/best。"""
    return pd.DataFrame({
        "strategy": ["s_a", "s_a", "s_b", "s_b"],
        "pool": ["bank", "tech", "bank", "tech"],
        "total_return": [0.10, 0.20, 0.15, 0.05],
        "annual_return": [0.08, 0.16, 0.12, 0.04],
        "sharpe_ratio": [0.5, 1.0, 0.8, 0.3],
        "max_drawdown": [0.15, 0.10, 0.12, 0.20],
        "win_rate": [0.55, 0.60, 0.58, 0.50],
        "trade_count": [30, 25, 40, 35],
    })


def test_pivot_matrix_shape(sample_results):
    """透视表行列应对应。"""
    piv = pivot_matrix(sample_results, metric="sharpe_ratio")
    assert piv.shape == (2, 2)  # 2 pools × 2 strategies
    assert "bank" in piv.index
    assert "tech" in piv.index


def test_pivot_matrix_values(sample_results):
    """透视表取值应正确。"""
    piv = pivot_matrix(sample_results, metric="sharpe_ratio")
    assert piv.loc["bank", "s_a"] == 0.5
    assert piv.loc["tech", "s_b"] == 0.3


# --- best_per_pool ---


def test_best_per_pool_returns_dataframe(sample_results):
    """应返回 DataFrame。"""
    best = best_per_pool(sample_results, metric="sharpe_ratio")
    assert isinstance(best, pd.DataFrame)


def test_best_per_pool_selects_max(sample_results):
    """每 pool 应选择指定指标最大的策略。"""
    best = best_per_pool(sample_results, metric="sharpe_ratio")
    # bank: s_a=0.5 vs s_b=0.8 → s_b
    assert best[best["pool"] == "bank"].iloc[0]["strategy"] == "s_b"
    # tech: s_a=1.0 vs s_b=0.3 → s_a
    assert best[best["pool"] == "tech"].iloc[0]["strategy"] == "s_a"
