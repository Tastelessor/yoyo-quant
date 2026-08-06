"""Tests for the factor registry."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.registry import (
    FACTOR_REGISTRY,
    calc_factors,
    get_factor,
    list_factors,
    register_factor,
    run_factor,
)

# ---------------------------------------------------------------------------
# 实现清单（注册表口径守卫：注册集必须与实现集完全一致）
# ---------------------------------------------------------------------------

# 已注册 single 因子（32）——来自 _register_defaults 的既有条目
REGISTERED_SINGLE_PRIMARY = [
    # momentum (5)
    "calc_momentum_5d_change",
    "calc_momentum_5d_ratio",
    "calc_momentum_6d_return",
    "calc_momentum_20d_return",
    "calc_momentum_20d_change",
    # volume_price_gtja (18)
    "calc_money_flow_6d",
    "calc_up_down_vol_ratio_26d",
    "calc_obv_6d",
    "calc_vol_rank_intraday_corr_6d",
    "calc_vol_change_pct_5d",
    "calc_return_6d_times_vol",
    "calc_return_1d_times_vol",
    "calc_high_vol_rank_corr_3d",
    "calc_close_vol_rank_cov_5d",
    "calc_open_vol_corr_10d",
    "calc_vwap_vol_rank_corr_5d",
    "calc_williams_r_smoothed_6d",
    "calc_shadow_ratio_20d",
    "calc_candle_body_vol_composite",
    "calc_open_vwap_close_vwap",
    "calc_dollar_vol_std_6d",
    "calc_vol_macd_9_26_12",
    "calc_vol_rsi_6d",
    # earnings (2)
    "calc_earnings_surprise",
    "calc_earnings_acceleration",
    # value (2)
    "calc_ep",
    "calc_bp",
    # liquidity (2)
    "calc_amihud",
    "calc_turnover",
    # quality (3)
    "calc_roe_level",
    "calc_roe_stability",
    "calc_cashflow_quality",
]

# 本次新增 single 因子（19）
NEW_SINGLE_PRIMARY = [
    # volatility_gtja (5)
    "calc_cci_12d",
    "calc_volume_vol_10d",
    "calc_volume_vol_20d",
    "calc_atr_12d",
    "calc_atr_6d",
    # mean_reversion (4)
    "calc_rsi_6d",
    "calc_rsi_12d",
    "calc_directional_balance_12d",
    "calc_mfi_14d",
    # trend (3)
    "calc_ma_slope_6d",
    "calc_ma_slope_20d",
    "calc_macd_like",
    # vwap (2)
    "calc_vwap_close_ratio",
    "calc_vwap_deviation",
    # volume_price (4)
    "calc_rsi",
    "calc_obv",
    "calc_volume_ratio",
    "calc_atr",
    # volatility (1)
    "calc_hv",
]

SINGLE_PRIMARY = REGISTERED_SINGLE_PRIMARY + NEW_SINGLE_PRIMARY

# 本次新增 moneyflow 因子（3）——需要 moneyflow 宽表列，独立分组（不纳入 OHLCV smoke）
MONEYFLOW_SINGLE_PRIMARY = [
    "calc_moneyflow_net_ratio",
    "calc_moneyflow_streak",
    "calc_moneyflow_big_net_ratio",
]

SINGLE_PRIMARY = (
    REGISTERED_SINGLE_PRIMARY + NEW_SINGLE_PRIMARY + MONEYFLOW_SINGLE_PRIMARY
)

# pair 因子（5）——配对专用签名
PAIR_PRIMARY = [
    "calc_spread",
    "calc_spread_zscore",
    "calc_coint_pvalue",
    "calc_half_life",
    "kalman_filter_hedge_ratio",
]

# 别名（37）——primary 的 GTJA 编号别名
ALIASES = [
    # momentum (5)
    "gtja_14",
    "gtja_18",
    "gtja_20",
    "gtja_88",
    "gtja_106",
    # volume_price_gtja (18)
    "gtja_11",
    "gtja_40",
    "gtja_43",
    "gtja_1",
    "gtja_80",
    "gtja_29",
    "gtja_178",
    "gtja_32",
    "gtja_99",
    "gtja_139",
    "gtja_90",
    "gtja_47",
    "gtja_118",
    "gtja_54",
    "gtja_12",
    "gtja_70",
    "gtja_145",
    "gtja_102",
    # volatility_gtja (5)
    "gtja_78",
    "gtja_97",
    "gtja_100",
    "gtja_161",
    "gtja_175",
    # mean_reversion (4)
    "gtja_63",
    "gtja_79",
    "gtja_112",
    "gtja_128",
    # trend (3)
    "gtja_21",
    "gtja_116",
    "gtja_89",
    # vwap (2)
    "gtja_120",
    "gtja_124",
]

ALL_EXPECTED = set(SINGLE_PRIMARY) | set(PAIR_PRIMARY) | set(ALIASES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_factor_a(df: pd.DataFrame) -> pd.Series:
    return df["close"] * 2


def _dummy_factor_b(df: pd.DataFrame) -> pd.Series:
    return df["close"] + 1


def _make_df(
    close: list[float] | None = None, codes: list[str] | None = None
) -> pd.DataFrame:
    close = close or [10.0, 20.0, 30.0]
    codes = codes or ["A"]
    n = len(close)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="B"),
            "code": codes[0],
            "close": close,
        }
    )


def _ensure_defaults() -> None:
    """重建默认注册表（防御：其他测试可能 clear 过 FACTOR_REGISTRY）。"""
    from factors.registry import _register_defaults

    FACTOR_REGISTRY.clear()
    _register_defaults()


# ---------------------------------------------------------------------------
# Register / Get
# ---------------------------------------------------------------------------


class TestRegisterAndGet:
    def setup_method(self) -> None:
        FACTOR_REGISTRY.clear()

    def test_register_and_get(self) -> None:
        register_factor("test_a", _dummy_factor_a)
        func = get_factor("test_a")
        assert func is _dummy_factor_a

    def test_alias_lookup(self) -> None:
        register_factor("primary_name", _dummy_factor_a)
        register_factor("alias_name", _dummy_factor_a)
        assert get_factor("primary_name") is get_factor("alias_name")

    def test_get_unknown_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Unknown factor"):
            get_factor("nonexistent")

    def test_register_with_tags(self) -> None:
        register_factor("tagged", _dummy_factor_a, tags=["momentum", "gtja"])
        spec = FACTOR_REGISTRY["tagged"]
        assert spec.func is _dummy_factor_a
        assert spec.tags == ["momentum", "gtja"]
        assert spec.kind == "single"
        assert spec.params == {}

    def test_register_with_kind_pair(self) -> None:
        register_factor("paired", _dummy_factor_a, kind="pair")
        assert FACTOR_REGISTRY["paired"].kind == "pair"

    def test_register_params_extracted_from_signature(self) -> None:
        def f(df: pd.DataFrame, window: int = 14) -> pd.Series:
            return df["close"] / window

        register_factor("param_f", f)
        assert FACTOR_REGISTRY["param_f"].params == {"window": 14}

    def test_register_params_explicit_override(self) -> None:
        register_factor("override_f", _dummy_factor_a, params={"window": 30})
        assert FACTOR_REGISTRY["override_f"].params == {"window": 30}

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            register_factor("bad_kind", _dummy_factor_a, kind="matrix")


# ---------------------------------------------------------------------------
# List factors
# ---------------------------------------------------------------------------


class TestListFactors:
    def setup_method(self) -> None:
        FACTOR_REGISTRY.clear()

    def test_list_factors_returns_all(self) -> None:
        register_factor("a", _dummy_factor_a)
        register_factor("b", _dummy_factor_b)
        result = list_factors()
        assert set(result) == {"a", "b"}

    def test_list_factors_by_tag(self) -> None:
        register_factor("a", _dummy_factor_a, tags=["momentum"])
        register_factor("b", _dummy_factor_b, tags=["volatility"])
        register_factor("c", _dummy_factor_a, tags=["momentum", "gtja"])
        result = list_factors(tag="momentum")
        assert set(result) == {"a", "c"}

    def test_list_factors_by_kind(self) -> None:
        register_factor("s", _dummy_factor_a, kind="single")
        register_factor("p", _dummy_factor_a, kind="pair")
        assert set(list_factors(kind="single")) == {"s"}
        assert set(list_factors(kind="pair")) == {"p"}

    def test_list_factors_empty(self) -> None:
        result = list_factors()
        assert result == []


# ---------------------------------------------------------------------------
# Run factor
# ---------------------------------------------------------------------------


class TestRunFactor:
    def setup_method(self) -> None:
        FACTOR_REGISTRY.clear()

    def test_uses_default_params(self) -> None:
        def f(df: pd.DataFrame, window: int = 14) -> pd.Series:
            return df["close"] / window

        register_factor("f", f)
        result = run_factor("f", _make_df(close=[14.0, 28.0]))
        np.testing.assert_allclose(result.values, [1.0, 2.0])

    def test_passthrough_params(self) -> None:
        def f(df: pd.DataFrame, window: int = 14) -> pd.Series:
            return df["close"] / window

        register_factor("f", f)
        result = run_factor("f", _make_df(close=[14.0, 28.0]), window=7)
        np.testing.assert_allclose(result.values, [2.0, 4.0])

    def test_rejects_pair_factor(self) -> None:
        register_factor("p", _dummy_factor_a, kind="pair")
        with pytest.raises(ValueError, match="pair"):
            run_factor("p", _make_df())

    def test_returns_series_sorted_by_code_date(self) -> None:
        register_factor("f", _dummy_factor_a)
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=2, freq="B").append(
                    pd.date_range("2024-01-01", periods=2, freq="B")
                ),
                "code": ["A", "A", "B", "B"],
                "close": [30.0, 10.0, 20.0, 5.0],
            }
        )
        result = run_factor("f", df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)
        # 排序后（code, date）：A(30→60), A(10→20), B(20→40), B(5→10)
        np.testing.assert_allclose(result.values, [60.0, 20.0, 40.0, 10.0])

    def test_aligns_to_unsorted_input(self) -> None:
        """返回与输入 df 逐行对齐（内部排序计算后映射回输入顺序）。"""
        register_factor("f", _dummy_factor_a)
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=3, freq="B").append(
                    pd.date_range("2024-01-01", periods=3, freq="B")
                ),
                "code": ["B", "A", "B", "A", "B", "A"],
                "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            }
        )
        result = run_factor("f", df)
        # 逐行对齐：第 i 行结果 = 输入第 i 行的 close * 2
        np.testing.assert_allclose(result.values, df["close"].values * 2)


# ---------------------------------------------------------------------------
# Calc factors
# ---------------------------------------------------------------------------


class TestCalcFactors:
    def setup_method(self) -> None:
        FACTOR_REGISTRY.clear()

    def test_assembles_dataframe(self) -> None:
        register_factor("factor_a", _dummy_factor_a)
        register_factor("factor_b", _dummy_factor_b)

        df = _make_df()
        result = calc_factors(df, ["factor_a", "factor_b"])
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) == {"date", "code", "factor_a", "factor_b"}
        np.testing.assert_allclose(result["factor_a"].values, [20.0, 40.0, 60.0])
        np.testing.assert_allclose(result["factor_b"].values, [11.0, 21.0, 31.0])

    def test_single_factor(self) -> None:
        register_factor("f", _dummy_factor_a)
        result = calc_factors(_make_df(close=[5.0, 10.0]), ["f"])
        assert "f" in result.columns
        np.testing.assert_allclose(result["f"].values, [10.0, 20.0])

    def test_calc_factors_with_params(self) -> None:
        def f(df: pd.DataFrame, window: int = 14) -> pd.Series:
            return df["close"] / window

        register_factor("f", f)
        result = calc_factors(
            _make_df(close=[14.0, 28.0]), ["f"], params={"f": {"window": 7}}
        )
        np.testing.assert_allclose(result["f"].values, [2.0, 4.0])

    def test_calc_factors_rejects_pair(self) -> None:
        register_factor("p", _dummy_factor_a, kind="pair")
        with pytest.raises(ValueError, match="pair"):
            calc_factors(_make_df(), ["p"])


# ---------------------------------------------------------------------------
# 全口径守卫：注册表 = 实际可用因子集
# ---------------------------------------------------------------------------


class TestRegistryInventory:
    def setup_method(self) -> None:
        _ensure_defaults()

    def test_registered_names_match_implementations(self) -> None:
        assert set(list_factors()) == ALL_EXPECTED

    def test_single_kind_covers_all_single_implementations(self) -> None:
        assert set(list_factors(kind="single")) == set(SINGLE_PRIMARY) | set(ALIASES)

    def test_pair_kind_covers_pair_implementations(self) -> None:
        assert set(list_factors(kind="pair")) == set(PAIR_PRIMARY)

    def test_single_count(self) -> None:
        # 54 primary + 37 aliases
        assert len(list_factors(kind="single")) == 91
        assert len(list_factors(kind="pair")) == 5

    def test_new_single_factors_smoke(self) -> None:
        """新增 19 个 OHLCV 因子在合成数据上可运行且返回等长 Series。"""
        n_days = 40
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        rng = np.random.default_rng(42)
        frames = []
        for code in ["A", "B", "C"]:
            close = 10 + np.cumsum(rng.normal(0, 0.1, n_days))
            frames.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "code": code,
                        "open": close * 0.99,
                        "high": close * 1.02,
                        "low": close * 0.98,
                        "close": close,
                        "volume": rng.integers(1_000_000, 5_000_000, n_days),
                    }
                )
            )
        df = pd.concat(frames, ignore_index=True)

        for name in NEW_SINGLE_PRIMARY:
            result = run_factor(name, df, use_cache=False)
            assert isinstance(result, pd.Series), name
            assert len(result) == len(df), name
            assert result.dtype == np.float64, name
