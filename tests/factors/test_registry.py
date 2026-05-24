"""Tests for the factor registry."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.registry import (
    FACTOR_REGISTRY,
    calc_factors,
    get_factor,
    list_factors,
    register_factor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_factor_a(df: pd.DataFrame) -> pd.Series:
    return df["close"] * 2


def _dummy_factor_b(df: pd.DataFrame) -> pd.Series:
    return df["close"] + 1


# ---------------------------------------------------------------------------
# Tests
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
        func, tags = FACTOR_REGISTRY["tagged"]
        assert func is _dummy_factor_a
        assert tags == ["momentum", "gtja"]


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

    def test_list_factors_empty(self) -> None:
        result = list_factors()
        assert result == []


class TestCalcFactors:
    def setup_method(self) -> None:
        FACTOR_REGISTRY.clear()

    def test_assembles_dataframe(self) -> None:
        register_factor("factor_a", _dummy_factor_a)
        register_factor("factor_b", _dummy_factor_b)

        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "code": "A",
            "close": [10.0, 20.0, 30.0],
        })

        result = calc_factors(df, ["factor_a", "factor_b"])
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) == {"date", "code", "factor_a", "factor_b"}
        np.testing.assert_allclose(result["factor_a"].values, [20.0, 40.0, 60.0])
        np.testing.assert_allclose(result["factor_b"].values, [11.0, 21.0, 31.0])

    def test_single_factor(self) -> None:
        register_factor("f", _dummy_factor_a)
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=2, freq="B"),
            "code": "A",
            "close": [5.0, 10.0],
        })
        result = calc_factors(df, ["f"])
        assert "f" in result.columns
        np.testing.assert_allclose(result["f"].values, [10.0, 20.0])
