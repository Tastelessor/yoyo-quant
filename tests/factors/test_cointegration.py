import numpy as np
import pandas as pd

from factors.cointegration import (
    calc_coint_pvalue,
    calc_half_life,
    calc_spread,
    calc_spread_zscore,
    kalman_filter_hedge_ratio,
)


def _make_series(n=100, seed=42):
    """生成两个有协整关系的价格序列。"""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # 共同随机游走 + 独立噪声
    common = np.cumsum(np.random.randn(n) * 0.5)
    noise_a = np.random.randn(n) * 0.1
    noise_b = np.random.randn(n) * 0.1
    close_a = 100 + common + noise_a
    close_b = 80 + common * 0.8 + noise_b
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": close_a})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": close_b})
    return df_a, df_b


# ── calc_spread ──────────────────────────────────────────────


def test_calc_spread_returns_series():
    df_a, df_b = _make_series()
    result = calc_spread(df_a, df_b)
    assert isinstance(result, pd.Series)
    assert len(result) == len(df_a)


def test_calc_spread_log_price_ratio():
    """手动验证 spread = log(A) - beta * log(B)。"""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": [10, 20, 30, 40, 50]})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": [5, 10, 15, 20, 25]})
    result = calc_spread(df_a, df_b, beta=1.0)
    expected = np.log(df_a["close"].values) - 1.0 * np.log(df_b["close"].values)
    np.testing.assert_allclose(result.values, expected)


def test_calc_spread_constant_prices_gives_zero():
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": [100.0] * 5})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": [100.0] * 5})
    result = calc_spread(df_a, df_b, beta=1.0)
    np.testing.assert_allclose(result.values, 0.0, atol=1e-15)


def test_calc_spread_ols_beta():
    """beta=None 时应自动估计 OLS beta。"""
    dates = pd.date_range("2024-01-01", periods=50, freq="B")
    np.random.seed(42)
    close_a = 100 + np.cumsum(np.random.randn(50) * 0.5)
    close_b = 50 + np.cumsum(np.random.randn(50) * 0.5)
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": close_a})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": close_b})
    result = calc_spread(df_a, df_b, beta=None)
    assert isinstance(result, pd.Series)
    assert len(result) == 50


# ── calc_spread_zscore ───────────────────────────────────────


def test_calc_spread_zscore_returns_series():
    spread = pd.Series(np.random.randn(100))
    result = calc_spread_zscore(spread, window=20)
    assert isinstance(result, pd.Series)
    assert len(result) == 100


def test_calc_spread_zscore_first_window_nan():
    """前 window-1 个值应为 NaN（被填零）。"""
    spread = pd.Series(np.random.randn(100))
    result = calc_spread_zscore(spread, window=20)
    # 非常数 spread：NaN 位置被填零，有效 z-score 有值
    assert len(result) == 100
    assert result.notna().all()  # fillna(0.0) 处理了所有 NaN


def test_calc_spread_zscore_zero_mean_unit_std():
    """长窗口下 z-score 应近似零均值单位标准差。"""
    np.random.seed(42)
    spread = pd.Series(np.random.randn(200))
    result = calc_spread_zscore(spread, window=50)
    valid = result.dropna()
    assert abs(valid.mean()) < 0.15
    assert abs(valid.std() - 1.0) < 0.15


def test_calc_spread_zscore_constant_spread_is_zero():
    spread = pd.Series([5.0] * 50)
    result = calc_spread_zscore(spread, window=20)
    # 常数 spread 的 std=0，z-score 应为 0（除零保护）
    valid = result.dropna()
    assert (valid == 0.0).all()


# ── calc_coint_pvalue ────────────────────────────────────────


def test_calc_coint_pvalue_returns_float():
    df_a, df_b = _make_series()
    result = calc_coint_pvalue(df_a, df_b, min_obs=60)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_calc_coint_pvalue_cointegrated_series_low_pvalue():
    """完全相同的序列应有很低的 p-value（强协整）。"""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": close})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": close})
    pval = calc_coint_pvalue(df_a, df_b, min_obs=60)
    assert pval < 0.05


def test_calc_coint_pvalue_independent_series_high_pvalue():
    """两个独立随机游走应有较高的 p-value。"""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    close_a = 100 + np.cumsum(np.random.randn(100) * 1.0)
    np.random.seed(123)
    close_b = 200 + np.cumsum(np.random.randn(100) * 2.0)
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": close_a})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": close_b})
    pval = calc_coint_pvalue(df_a, df_b, min_obs=60)
    assert pval > 0.05


# ── calc_half_life ───────────────────────────────────────────


def test_half_life_returns_positive():
    """均值回复的 spread 应返回正的 half-life。"""
    np.random.seed(42)
    # 构造一个均值回复的 spread（AR(1) with negative coefficient）
    n = 200
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = 0.5 * spread[i - 1] + np.random.randn() * 0.1
    spread = pd.Series(spread)
    result = calc_half_life(spread, window=100)
    assert result > 0


def test_half_life_non_mean_reverting():
    """非均值回复的 spread（正系数）应返回负值或 NaN。"""
    np.random.seed(42)
    n = 200
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = 1.5 * spread[i - 1] + np.random.randn() * 0.1
    spread = pd.Series(spread)
    result = calc_half_life(spread, window=100)
    # 正系数 -> lambda > 0 -> half_life < 0
    assert result < 0 or np.isnan(result)


# ── 边界情况 ──────────────────────────────────────────────────


def test_calc_spread_returns_date_index():
    """spread 应以 date 为索引，而非整数索引。"""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": [10, 20, 30, 40, 50]})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": [5, 10, 15, 20, 25]})
    result = calc_spread(df_a, df_b, beta=1.0)
    pd.testing.assert_index_equal(result.index, dates)


def test_calc_spread_deduplicates_dates():
    """重复日期应去重，取最后一行。"""
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    df_a = pd.DataFrame({
        "date": [dates[0], dates[0], dates[1], dates[2]],
        "code": "A",
        "close": [10.0, 20.0, 30.0, 40.0],
    })
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": [5, 10, 15]})
    result = calc_spread(df_a, df_b, beta=1.0)
    # 去重后应只有 3 行
    assert len(result) == 3


def test_calc_spread_empty_data():
    df_a = pd.DataFrame(columns=["date", "code", "close"])
    df_b = pd.DataFrame(columns=["date", "code", "close"])
    result = calc_spread(df_a, df_b, beta=1.0)
    assert len(result) == 0


def test_calc_coint_pvalue_short_series():
    """观测数不足 min_obs 时应返回 1.0。"""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    df_a = pd.DataFrame({"date": dates, "code": "A", "close": range(10)})
    df_b = pd.DataFrame({"date": dates, "code": "B", "close": range(10)})
    pval = calc_coint_pvalue(df_a, df_b, min_obs=60)
    assert pval == 1.0


def test_calc_half_life_short_series():
    """spread 长度不足 window+1 时应返回 NaN。"""
    spread = pd.Series([1.0, 2.0, 3.0])
    result = calc_half_life(spread, window=60)
    assert np.isnan(result)


def test_calc_coint_pvalue_renamed_param():
    """min_obs 参数应正常工作（向后兼容旧 window 参数名）。"""
    df_a, df_b = _make_series()
    result = calc_coint_pvalue(df_a, df_b, min_obs=30)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


# ── kalman_filter_hedge_ratio ────────────────────────────────


def test_kalman_returns_array():
    np.random.seed(42)
    n = 100
    log_a = np.cumsum(np.random.randn(n) * 0.5) + 100
    log_b = np.cumsum(np.random.randn(n) * 0.5) + 80
    result = kalman_filter_hedge_ratio(log_a, log_b)
    assert isinstance(result, np.ndarray)
    assert len(result) == n


def test_kalman_beta_reasonable_range():
    """Kalman beta 应在合理范围内（不会发散）。"""
    np.random.seed(42)
    n = 200
    common = np.cumsum(np.random.randn(n) * 0.5)
    log_a = 100 + common + np.random.randn(n) * 0.1
    log_b = 80 + common * 0.8 + np.random.randn(n) * 0.1
    betas = kalman_filter_hedge_ratio(log_a, log_b)
    # beta 应大致在 0.5-1.5 范围内（真实值约 0.8）
    assert betas.mean() > 0.3
    assert betas.mean() < 2.0
    # 不应有 NaN 或 inf
    assert np.isfinite(betas).all()


def test_kalman_adapts_to_change():
    """Kalman 应能追踪 beta 的结构性变化。"""
    n = 200
    log_b = np.linspace(10, 12, n)
    # 前 100 个点 beta=1.0，后 100 个点 beta=1.5
    log_a = np.concatenate([
        log_b[:100] * 1.0 + 5,
        log_b[100:] * 1.5 + 3,
    ])
    betas = kalman_filter_hedge_ratio(log_a, log_b, q=1e-4)
    # 后半段 beta 应接近 1.5
    assert betas[150:] .mean() > 1.2
