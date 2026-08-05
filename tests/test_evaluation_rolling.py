"""滚动 IC/IR/t 统计量测试（因子生命周期监控 Task 1）。

三个函数均为纯 Series → Series 变换：
- compute_rolling_ic(ic_series, window, min_periods=None)
- compute_rolling_ir(ic_series, window, min_periods=None)
- compute_rolling_tstat(ic_series, window, min_periods=None)
"""

import numpy as np
import pandas as pd
import pytest

from factors.evaluation import (
    compute_rolling_ic,
    compute_rolling_ir,
    compute_rolling_tstat,
)


def _ic_series(values, start="2026-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values)))


# --- compute_rolling_ic ---


def test_rolling_ic_basic():
    ic = _ic_series([1.0, 2.0, 3.0, 4.0])
    out = compute_rolling_ic(ic, window=2)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(1.5)
    assert out.iloc[2] == pytest.approx(2.5)
    assert out.iloc[3] == pytest.approx(3.5)


def test_rolling_ic_min_periods():
    ic = _ic_series([1.0, 2.0])
    out = compute_rolling_ic(ic, window=5, min_periods=2)
    # 位置 0 窗口仅 1 个有效值 < min_periods=2 → NaN；位置 1 有 2 个 → 1.5
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(1.5)


def test_rolling_ic_empty():
    ic = _ic_series([])
    out = compute_rolling_ic(ic, window=2)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_rolling_ic_invalid_window():
    with pytest.raises(ValueError):
        compute_rolling_ic(_ic_series([1.0, 2.0]), window=0)
    with pytest.raises(ValueError):
        compute_rolling_ic(_ic_series([1.0, 2.0]), window=1, min_periods=0)


def test_rolling_ic_returns_series_aligned_index():
    ic = _ic_series([1.0, 2.0, 3.0])
    out = compute_rolling_ic(ic, window=2)
    assert isinstance(out, pd.Series)
    pd.testing.assert_index_equal(out.index, ic.index)


# --- compute_rolling_ir ---


def test_rolling_ir_basic():
    ic = _ic_series([1.0, 2.0, 3.0, 4.0])
    out = compute_rolling_ir(ic, window=2)
    # 窗口 [1,2]：mean=1.5, std(ddof=1)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(1.5 / np.std([1.0, 2.0], ddof=1))
    assert out.iloc[2] == pytest.approx(2.5 / np.std([2.0, 3.0], ddof=1))


def test_rolling_ir_constant_ic_is_inf():
    ic = _ic_series([2.0] * 5)
    out = compute_rolling_ir(ic, window=3)
    assert np.isinf(out.iloc[-1])


def test_rolling_ir_nan_handling():
    ic = _ic_series([1.0, np.nan, 3.0, 4.0])
    out = compute_rolling_ir(ic, window=3, min_periods=2)
    # 窗口 [1.0, NaN, 3.0]：有效 [1.0, 3.0]，mean=2.0, std(ddof=1)=sqrt(2)
    assert out.iloc[2] == pytest.approx(2.0 / np.std([1.0, 3.0], ddof=1))


# --- compute_rolling_tstat ---


def test_rolling_tstat_basic():
    ic = _ic_series([1.0, 2.0, 3.0, 4.0])
    out = compute_rolling_tstat(ic, window=2)
    # 窗口 [2,3]：mean=2.5, std(ddof=1)=sqrt(0.5), n=2 → t=2.5/sqrt(0.5)*sqrt(2)=5.0
    assert np.isnan(out.iloc[0])
    assert out.iloc[2] == pytest.approx(5.0)


def test_rolling_tstat_uses_valid_count_not_window():
    ic = _ic_series([1.0, 2.0, np.nan, 4.0])
    out = compute_rolling_tstat(ic, window=3, min_periods=2)
    # 窗口 [2.0, NaN, 4.0]：有效 [2.0, 4.0]，mean=3.0, std=sqrt(2), n=2
    # → t = 3.0/sqrt(2)*sqrt(2) = 3.0（若 n 误用窗口长度 3，t≈3.67）
    assert out.iloc[-1] == pytest.approx(3.0)


def test_rolling_tstat_insufficient_window_is_nan():
    ic = _ic_series([1.0])
    out = compute_rolling_tstat(ic, window=5)
    assert np.isnan(out.iloc[0])


def test_rolling_tstat_empty():
    ic = _ic_series([])
    out = compute_rolling_tstat(ic, window=5)
    assert len(out) == 0
