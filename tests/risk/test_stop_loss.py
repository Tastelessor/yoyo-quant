"""Stop loss rule tests."""

import pandas as pd
import pytest

from src.risk.rules import RuleContext
from src.risk.stop_loss import ATRStopLossRule, FixedStopLossRule, FixedTakeProfitRule

# --- Fixtures ---


@pytest.fixture
def market_data():
    """Multi-day market data for two stocks."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["000001"] * 4 + ["600519"] * 4,
            "open": [10.0, 9.5, 9.0, 8.5, 500, 490, 480, 470],
            "high": [10.5, 10.0, 9.5, 9.0, 510, 500, 490, 480],
            "low": [9.8, 9.3, 8.8, 8.3, 495, 485, 475, 465],
            "close": [10.0, 9.5, 9.0, 8.5, 500, 490, 480, 470],
            "volume": [1_000_000] * 8,
        }
    )


@pytest.fixture
def positions_with_avg_price():
    """Positions with avg_cost column for P&L calculation."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-05"]),
            "code": ["000001", "600519"],
            "weight": [0.5, 0.5],
            "shares": [5000, 100],
            "avg_cost": [10.0, 500.0],  # bought at these prices
        }
    )


@pytest.fixture
def signals():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-05"]),
            "code": ["000001", "600519"],
            "signal": [0, 0],
            "confidence": [0.0, 0.0],
        }
    )


# --- FixedStopLossRule ---


class TestFixedStopLossRule:
    def test_name_and_priority(self):
        rule = FixedStopLossRule()
        assert rule.name == "fixed_stop_loss"
        assert rule.priority == 120

    def test_no_trigger_when_profitable(self, signals, market_data):
        """No stop loss when price > avg_cost."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [8.0],  # bought at 8, current is 8.5 → profitable
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 1.0
        assert "stopped_out" not in result.metadata

    def test_trigger_when_loss_exceeds_threshold(
        self, signals, market_data, positions_with_avg_price
    ):
        """000001: avg_cost=10, current=8.5 → -15% loss → triggers -8% stop."""
        ctx = RuleContext(
            signals=signals,
            positions=positions_with_avg_price,
            market_data=market_data,
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        row = result.positions[result.positions["code"] == "000001"].iloc[0]
        assert row["weight"] == 0.0
        assert row["shares"] == 0

    def test_no_trigger_when_within_threshold(
        self, signals, market_data
    ):
        """600519: avg_cost=500, current=470 → -6% loss → within -8% threshold."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["600519"],
                "weight": [1.0],
                "shares": [100],
                "avg_cost": [500.0],
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 1.0

    def test_metadata_records_stopped_out(
        self, signals, market_data, positions_with_avg_price
    ):
        ctx = RuleContext(
            signals=signals,
            positions=positions_with_avg_price,
            market_data=market_data,
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        assert "stopped_out" in result.metadata
        assert "000001" in result.metadata["stopped_out"]

    def test_returns_rule_context(
        self, signals, market_data, positions_with_avg_price
    ):
        ctx = RuleContext(
            signals=signals,
            positions=positions_with_avg_price,
            market_data=market_data,
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        assert isinstance(result, RuleContext)

    def test_empty_positions(self, signals, market_data):
        positions = pd.DataFrame(
            columns=["date", "code", "weight", "shares", "avg_cost"]
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedStopLossRule(threshold=-0.08)
        result = rule.apply(ctx)
        assert len(result.positions) == 0


# --- ATRStopLossRule ---


class TestATRStopLossRule:
    def test_name_and_priority(self):
        rule = ATRStopLossRule()
        assert rule.name == "atr_stop_loss"
        assert rule.priority == 121

    def test_no_trigger_when_price_above_stop(
        self, signals, market_data
    ):
        """Price well above stop level → no trigger."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["600519"],
                "weight": [1.0],
                "shares": [100],
                "avg_cost": [470.0],  # bought at 470, current 470, stop = 470 - 3*ATR
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = ATRStopLossRule(atr_multiplier=3.0, atr_window=3)
        result = rule.apply(ctx)
        # With small ATR (~10), stop would be ~440, current=470 → no trigger
        assert result.positions["weight"].iloc[0] == 1.0

    def test_trigger_when_price_below_stop(
        self, signals, market_data
    ):
        """Price drops below stop level → trigger."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [5000],
                "avg_cost": [10.0],  # bought at 10, current 8.5
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        # ATR for 000001 with window=3: TR values ~0.7, ATR ~0.7
        # stop = 10.0 - 1.0 * 0.7 = 9.3, current=8.5 < 9.3 → trigger
        rule = ATRStopLossRule(atr_multiplier=1.0, atr_window=3)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 0.0

    def test_wider_stop_for_volatile_stock(self, signals):
        """Higher ATR multiplier → wider stop → less likely to trigger.

        Data: ATR(3) ≈ 0.117, avg_cost=10.0, current=10.05 (slightly profitable)
        - multiplier=3: stop = 10.0 - 0.35 = 9.65, current 10.05 > 9.65 → no trigger
        - multiplier=0.1: stop = 10.0 - 0.012 = 9.99, current 10.05 > 9.99 → no trigger
        Both profitable → use a losing position instead to test the difference.
        """
        # Use losing position: avg_cost=10.1, current=10.0, loss=1%
        low_vol = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
                ),
                "code": "LOWVOL",
                "open": [10.0, 10.05, 10.1, 10.0],
                "high": [10.1, 10.15, 10.2, 10.1],
                "low": [10.0, 10.05, 10.1, 10.0],
                "close": [10.05, 10.1, 10.15, 10.0],
                "volume": [1_000_000] * 4,
            }
        )
        sig = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["LOWVOL"],
                "signal": [0],
                "confidence": [0.0],
            }
        )

        # Wide multiplier: stop = 10.1 - 3*0.117 = 9.75, current=10.0 > 9.75 → no trigger
        positions1 = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["LOWVOL"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [10.1],
            }
        )
        ctx1 = RuleContext(
            signals=sig, positions=positions1, market_data=low_vol
        )
        rule_wide = ATRStopLossRule(atr_multiplier=3.0, atr_window=3)
        result1 = rule_wide.apply(ctx1)
        assert result1.positions["weight"].iloc[0] == 1.0

        # Tight multiplier: stop = 10.1 - 0.1*0.117 = 10.088, current=10.0 < 10.088 → trigger
        positions2 = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["LOWVOL"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [10.1],
            }
        )
        ctx2 = RuleContext(
            signals=sig, positions=positions2, market_data=low_vol
        )
        rule_tight = ATRStopLossRule(atr_multiplier=0.1, atr_window=3)
        result2 = rule_tight.apply(ctx2)
        assert result2.positions["weight"].iloc[0] == 0.0

    def test_empty_positions(self, signals, market_data):
        positions = pd.DataFrame(
            columns=["date", "code", "weight", "shares", "avg_cost"]
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = ATRStopLossRule()
        result = rule.apply(ctx)
        assert len(result.positions) == 0


# --- FixedTakeProfitRule ---


class TestFixedTakeProfitRule:
    def test_name_and_priority(self):
        rule = FixedTakeProfitRule()
        assert rule.name == "fixed_take_profit"
        assert rule.priority == 122

    def test_trigger_when_profit_exceeds_threshold(self, signals, market_data):
        """000001: avg_cost=8.0, current=8.5 → +6.25% profit → triggers +5% take-profit."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [8.0],
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 0.0
        assert result.positions["shares"].iloc[0] == 0

    def test_no_trigger_when_profit_below_threshold(self, signals, market_data):
        """600519: avg_cost=480, current=470 → -2% → no trigger."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["600519"],
                "weight": [1.0],
                "shares": [100],
                "avg_cost": [480.0],
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 1.0

    def test_no_trigger_when_loss(self, signals, market_data):
        """Losing position should NOT trigger take-profit."""
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [5000],
                "avg_cost": [10.0],  # bought at 10, current 8.5 → -15% loss
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert result.positions["weight"].iloc[0] == 1.0

    def test_metadata_records_taken_profit(self, signals, market_data):
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [8.0],
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert "taken_profit" in result.metadata
        assert "000001" in result.metadata["taken_profit"]

    def test_returns_rule_context(self, signals, market_data):
        positions = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-05"]),
                "code": ["000001"],
                "weight": [1.0],
                "shares": [1000],
                "avg_cost": [8.0],
            }
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert isinstance(result, RuleContext)

    def test_empty_positions(self, signals, market_data):
        positions = pd.DataFrame(
            columns=["date", "code", "weight", "shares", "avg_cost"]
        )
        ctx = RuleContext(
            signals=signals, positions=positions, market_data=market_data
        )
        rule = FixedTakeProfitRule(threshold=0.05)
        result = rule.apply(ctx)
        assert len(result.positions) == 0
