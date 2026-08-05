"""Strategy combiner and registry tests."""

import numpy as np
import pandas as pd
import pytest

from strategies.base import Strategy
from strategies.combiner import FilterCombiner, WeightedVoteCombiner

# --- Fixtures ---


@pytest.fixture
def sample_data():
    """Minimal OHLCV data for two stocks, 5 days."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
                * 2
            ),
            "code": ["000001"] * 5 + ["600519"] * 5,
            "close": [
                10.0, 10.5, 11.0, 10.5, 10.0,  # stock 1
                500.0, 490.0, 480.0, 490.0, 500.0,  # stock 2
            ],
            "volume": [1_000_000] * 10,
        }
    )


# --- Test strategies ---


class AlwaysBuyStrategy(Strategy):
    """Always generates buy signal with confidence 0.8."""

    name = "always_buy"

    def generate_signal(self, data, factors=None):
        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": 1,
                "confidence": 0.8,
            }
        )


class AlwaysSellStrategy(Strategy):
    """Always generates sell signal with confidence 0.6."""

    name = "always_sell"

    def generate_signal(self, data, factors=None):
        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": -1,
                "confidence": 0.6,
            }
        )


class HoldStrategy(Strategy):
    """Always holds (signal=0)."""

    name = "always_hold"

    def generate_signal(self, data, factors=None):
        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": 0,
                "confidence": 0.0,
            }
        )


# --- Strategy ABC ---


class TestStrategyABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            Strategy()

    def test_concrete_strategy_satisfies_interface(self, sample_data):
        s = AlwaysBuyStrategy()
        assert s.name == "always_buy"
        result = s.generate_signal(sample_data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_strategy_missing_name_raises(self):
        class NoName(Strategy):
            def generate_signal(self, data, factors=None):
                return pd.DataFrame()

        with pytest.raises(TypeError):
            NoName()

    def test_strategy_missing_generate_signal_raises(self):
        class NoMethod(Strategy):
            name = "test"

        with pytest.raises(TypeError):
            NoMethod()


# --- WeightedVoteCombiner ---


class TestWeightedVoteCombiner:
    def test_single_strategy(self, sample_data):
        combiner = WeightedVoteCombiner([(AlwaysBuyStrategy(), 1.0)])
        result = combiner.combine(sample_data)
        assert (result["signal"] == 1).all()

    def test_two_strategies_equal_weight(self, sample_data):
        """Buy (1.0) + Sell (-1.0) with equal weight → net 0 → hold."""
        combiner = WeightedVoteCombiner(
            [(AlwaysBuyStrategy(), 0.5), (AlwaysSellStrategy(), 0.5)]
        )
        result = combiner.combine(sample_data)
        # Weighted signal: 1*0.5 + (-1)*0.5 = 0 → hold
        assert (result["signal"] == 0).all()

    def test_buy_dominates_with_heavier_weight(self, sample_data):
        """Buy (0.7) + Sell (0.3) → net 0.4 > 0 → buy."""
        combiner = WeightedVoteCombiner(
            [(AlwaysBuyStrategy(), 0.7), (AlwaysSellStrategy(), 0.3)]
        )
        result = combiner.combine(sample_data)
        assert (result["signal"] == 1).all()

    def test_sell_dominates_with_heavier_weight(self, sample_data):
        """Buy (0.3) + Sell (0.7) → net -0.4 < 0 → sell."""
        combiner = WeightedVoteCombiner(
            [(AlwaysBuyStrategy(), 0.3), (AlwaysSellStrategy(), 0.7)]
        )
        result = combiner.combine(sample_data)
        assert (result["signal"] == -1).all()

    def test_confidence_is_weighted_average(self, sample_data):
        """Confidence = weighted avg of individual confidences."""
        combiner = WeightedVoteCombiner(
            [(AlwaysBuyStrategy(), 0.6), (AlwaysSellStrategy(), 0.4)]
        )
        result = combiner.combine(sample_data)
        # 0.8*0.6 + 0.6*0.4 = 0.48 + 0.24 = 0.72
        np.testing.assert_allclose(result["confidence"], 0.72, atol=1e-8)

    def test_output_columns(self, sample_data):
        combiner = WeightedVoteCombiner([(AlwaysBuyStrategy(), 1.0)])
        result = combiner.combine(sample_data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_preserves_date_code(self, sample_data):
        combiner = WeightedVoteCombiner([(AlwaysBuyStrategy(), 1.0)])
        result = combiner.combine(sample_data)
        pd.testing.assert_frame_equal(
            result[["date", "code"]], sample_data[["date", "code"]]
        )

    def test_empty_strategies_raises(self, sample_data):
        with pytest.raises(ValueError, match="at least one"):
            WeightedVoteCombiner([]).combine(sample_data)

    def test_factors_passed_to_strategy(self, sample_data):
        """Verify factors kwarg is forwarded."""

        class FactorUsingStrategy(Strategy):
            name = "factor_user"

            def generate_signal(self, data, factors=None):
                assert factors is not None
                return pd.DataFrame(
                    {
                        "date": data["date"],
                        "code": data["code"],
                        "signal": 0,
                        "confidence": 0.0,
                    }
                )

        factors = pd.DataFrame({"rsi": [50.0] * 10})
        combiner = WeightedVoteCombiner([(FactorUsingStrategy(), 1.0)])
        result = combiner.combine(sample_data, factors=factors)
        assert len(result) == 10


# --- FilterCombiner ---


class TestFilterCombiner:
    def test_primary_agrees_filters_agree(self, sample_data):
        """All agree → signal passes through."""
        combiner = FilterCombiner(
            primary=AlwaysBuyStrategy(), filters=[AlwaysBuyStrategy()]
        )
        result = combiner.combine(sample_data)
        assert (result["signal"] == 1).all()

    def test_primary_agrees_filter_disagrees(self, sample_data):
        """Primary buys, filter sells → signal zeroed out."""
        combiner = FilterCombiner(
            primary=AlwaysBuyStrategy(), filters=[HoldStrategy()]
        )
        result = combiner.combine(sample_data)
        # Hold strategy returns signal=0, which is not the same direction as buy
        assert (result["signal"] == 0).all()

    def test_no_filters_passes_through(self, sample_data):
        """No filters → primary signal passes through unchanged."""
        combiner = FilterCombiner(primary=AlwaysBuyStrategy(), filters=[])
        result = combiner.combine(sample_data)
        assert (result["signal"] == 1).all()

    def test_output_columns(self, sample_data):
        combiner = FilterCombiner(
            primary=AlwaysBuyStrategy(), filters=[]
        )
        result = combiner.combine(sample_data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_factors_forwarded(self, sample_data):
        class FactorCheck(Strategy):
            name = "check"

            def generate_signal(self, data, factors=None):
                assert factors is not None
                return pd.DataFrame(
                    {
                        "date": data["date"],
                        "code": data["code"],
                        "signal": 1,
                        "confidence": 0.5,
                    }
                )

        factors = pd.DataFrame({"rsi": [50.0] * 10})
        combiner = FilterCombiner(primary=FactorCheck(), filters=[FactorCheck()])
        combiner.combine(sample_data, factors=factors)
