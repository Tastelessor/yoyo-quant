"""Tests for factor result disk cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.factors.cache import clear_factor_cache
from src.factors.registry import FACTOR_REGISTRY, register_factor, run_factor


def _make_df(n_days: int = 10, codes: list[str] | None = None) -> pd.DataFrame:
    codes = codes or ["A"]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    frames = []
    for code in codes:
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    "close": np.linspace(10.0, 10.0 + n_days, n_days),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _counting_factor(calls: dict, rolling: bool = False) -> object:
    def f(df: pd.DataFrame, window: int = 14) -> pd.Series:
        calls["n"] += 1
        if rolling:
            # 滚动均值：窗口不足产生 NaN，用于测试 NaN 往返
            return (
                df["close"]
                .groupby(df["code"])
                .rolling(window, min_periods=window)
                .mean()
                .droplevel(0)
                .sort_index()
            )
        return df["close"] / window

    return f


@pytest.fixture(autouse=True)
def _clean_registry():
    FACTOR_REGISTRY.clear()
    yield
    FACTOR_REGISTRY.clear()


class TestFactorCache:
    def test_hit_reuses_computation(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("cached_f", _counting_factor(calls))
        df = _make_df()
        cache_dir = str(tmp_path)

        r1 = run_factor("cached_f", df, cache_dir=cache_dir)
        r2 = run_factor("cached_f", df, cache_dir=cache_dir)

        assert calls["n"] == 1  # 第二次命中缓存，不重算
        pd.testing.assert_series_equal(r1, r2)

    def test_param_change_misses(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("param_f", _counting_factor(calls))
        df = _make_df(n_days=4)
        df["close"] = [14.0, 28.0, 42.0, 56.0]
        cache_dir = str(tmp_path)

        r7 = run_factor("param_f", df, cache_dir=cache_dir, window=7)
        r14 = run_factor("param_f", df, cache_dir=cache_dir, window=14)

        assert calls["n"] == 2
        np.testing.assert_allclose(r7.values, [2.0, 4.0, 6.0, 8.0])
        np.testing.assert_allclose(r14.values, [1.0, 2.0, 3.0, 4.0])

    def test_data_change_misses(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("data_f", _counting_factor(calls))
        cache_dir = str(tmp_path)

        df_a = _make_df(n_days=5)
        df_b = _make_df(n_days=8)

        run_factor("data_f", df_a, cache_dir=cache_dir)
        run_factor("data_f", df_b, cache_dir=cache_dir)

        assert calls["n"] == 2

    def test_result_aligned_to_sorted_input(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("align_f", _counting_factor(calls))
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=3, freq="B").append(
                    pd.date_range("2024-01-01", periods=3, freq="B")
                ),
                "code": ["A", "A", "A", "B", "B", "B"],
                "close": [30.0, 10.0, 20.0, 60.0, 20.0, 40.0],
            }
        )
        cache_dir = str(tmp_path)

        r1 = run_factor("align_f", df, cache_dir=cache_dir)
        r2 = run_factor("align_f", df, cache_dir=cache_dir)

        assert calls["n"] == 1
        pd.testing.assert_series_equal(r1, r2)
        # 返回排序后（code, date）等长序列：close / 14
        np.testing.assert_allclose(
            r1.values, [30 / 14, 10 / 14, 20 / 14, 60 / 14, 20 / 14, 40 / 14]
        )

    def test_aligned_to_unsorted_input_with_cache_hit(self, tmp_path) -> None:
        """乱序输入：计算与缓存命中两条路径都返回与输入逐行对齐的序列。"""
        calls = {"n": 0}
        register_factor("u_f", _counting_factor(calls))
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=2, freq="B").append(
                    pd.date_range("2024-01-01", periods=2, freq="B")
                ),
                "code": ["B", "A", "B", "A"],
                "close": [28.0, 14.0, 56.0, 42.0],
            }
        )
        cache_dir = str(tmp_path)

        r1 = run_factor("u_f", df, cache_dir=cache_dir)
        r2 = run_factor("u_f", df, cache_dir=cache_dir)

        assert calls["n"] == 1
        pd.testing.assert_series_equal(r1, r2)
        # 逐行对齐：close / 14，按输入顺序
        np.testing.assert_allclose(r1.values, df["close"].values / 14)

    def test_disabled_cache_recomputes(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("no_cache_f", _counting_factor(calls))
        df = _make_df()

        run_factor("no_cache_f", df, use_cache=False)
        run_factor("no_cache_f", df, use_cache=False)

        assert calls["n"] == 2

    def test_clear_factor_cache(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("clear_f", _counting_factor(calls))
        df = _make_df()
        cache_dir = str(tmp_path)

        run_factor("clear_f", df, cache_dir=cache_dir)
        assert calls["n"] == 1

        clear_factor_cache(cache_dir=cache_dir)
        assert list(Path(cache_dir).rglob("*.parquet")) == []

        run_factor("clear_f", df, cache_dir=cache_dir)
        assert calls["n"] == 2

    def test_nan_values_roundtrip(self, tmp_path) -> None:
        calls = {"n": 0}
        register_factor("nan_f", _counting_factor(calls, rolling=True))
        df = _make_df(n_days=3)
        cache_dir = str(tmp_path)

        r1 = run_factor("nan_f", df, cache_dir=cache_dir)
        assert calls["n"] == 1
        assert r1.isna().any()  # window=14 大于 3 天，全 NaN

        r2 = run_factor("nan_f", df, cache_dir=cache_dir)
        assert calls["n"] == 1
        pd.testing.assert_series_equal(r1, r2, check_dtype=False)
        assert r2.isna().all()
