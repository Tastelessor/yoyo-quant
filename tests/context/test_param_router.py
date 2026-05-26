"""Tests for parameter routing."""

from __future__ import annotations

from src.context.param_router import DEFAULT_REGIME_PARAMS, route_params


class TestRouteParams:
    def test_returns_dict(self):
        result = route_params("trend_up")
        assert isinstance(result, dict)

    def test_trend_up_faster_rebalance(self):
        p = route_params("trend_up")
        assert p["rebalance"] < DEFAULT_REGIME_PARAMS["range"]["rebalance"], (
            "trend_up should rebalance faster than range"
        )

    def test_trend_down_fewer_longs(self):
        p = route_params("trend_down")
        assert p["top_n"] < DEFAULT_REGIME_PARAMS["range"]["top_n"], (
            "trend_down should hold fewer longs"
        )

    def test_volatile_nimble(self):
        p = route_params("volatile")
        assert p["rebalance"] < DEFAULT_REGIME_PARAMS["range"]["rebalance"], (
            "volatile should rebalance faster than range"
        )
        assert p["top_n"] < DEFAULT_REGIME_PARAMS["range"]["top_n"], (
            "volatile should hold fewer positions"
        )

    def test_range_normal(self):
        p = route_params("range")
        assert p["rebalance"] == 20
        assert p["top_n"] == 5

    def test_unknown_regime_falls_back_to_range(self):
        result = route_params("nonexistent")
        assert result == DEFAULT_REGIME_PARAMS["range"]

    def test_custom_params_map(self):
        custom = {
            "trend_up": {"rebalance": 7, "top_n": 4},
            "range": {"rebalance": 30, "top_n": 8},
        }
        result = route_params("trend_up", params_map=custom)
        assert result["rebalance"] == 7
        assert result["top_n"] == 4

    def test_custom_map_unknown_falls_back(self):
        custom = {"range": {"rebalance": 30}}
        result = route_params("volatile", params_map=custom)
        assert result["rebalance"] == 30

    def test_all_default_regimes_have_required_keys(self):
        for regime in ["trend_up", "trend_down", "range", "volatile"]:
            p = route_params(regime)
            for key in ["rebalance", "top_n", "bottom_n"]:
                assert key in p, f"{regime} missing {key}"

    def test_default_regime_params_not_mutated(self):
        """route_params returns a copy, not a reference."""
        original = DEFAULT_REGIME_PARAMS["range"]["rebalance"]
        result = route_params("range")
        result["rebalance"] = 999
        assert DEFAULT_REGIME_PARAMS["range"]["rebalance"] == original
